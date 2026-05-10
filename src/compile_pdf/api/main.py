"""FastAPI app — shared HTTP surface for all four producers.

Exposes:

- ``GET  /healthz``        — liveness + version + cache-backend + instance_id + version_skew
- ``GET  /v1/healthz``     — same shape (canonical)
- ``GET  /v1/version``     — bare version string
- ``GET  /v1/contract``    — published contract surface (producer schema versions, codex section versions)
- ``GET  /v1/schema/{name}``— individual JSON Schema document
- ``GET  /metrics``        — Prometheus exposition

Plus producer routers mounted under ``/v1/{rewrite,marks,impose,trap}``
when the corresponding producer module is enabled by ``COMPILE_PRODUCER``
(values: ``rewrite``, ``marks``, ``impose``, ``trap``, ``all``).

Per spec §1.4: each producer has its own container in production, but
the routers share this app. Standalone producer mode imports only the
relevant router.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, Field
from starlette.responses import Response

from compile_pdf.api.middleware import INSTANCE_ID, RequestIdMiddleware
from compile_pdf.version import (
    CJD_SCHEMA_VERSION,
    CODEX_DOCUMENT_SCHEMA_VERSION_PIN,
    COMPILE_DOCUMENT_SCHEMA_VERSION,
    PRODUCER_SCHEMA_VERSIONS,
    VERSION,
)

logger = structlog.get_logger(__name__)


class HealthResponse(BaseModel):
    status: str
    version: str
    producer: str
    instance_id: str
    cache_backend: str
    queue_depth: int = 0
    ghostscript: bool = False
    codex_pdf_version: str
    codex_section_versions: dict[str, str] = Field(default_factory=dict)
    codex_live_section_versions: dict[str, str] = Field(default_factory=dict)
    version_skew: bool = False


class VersionResponse(BaseModel):
    version: str


class ContractResponse(BaseModel):
    contract_name: str
    schema_version: str
    package_version: str
    schema_id: str
    endpoints: list[str]
    producer_schema_versions: dict[str, str] = Field(default_factory=dict)
    codex_section_versions: dict[str, str] = Field(default_factory=dict)


def _resolve_codex_pdf_version() -> str:
    """Read codex_pdf wheel version Compile was deployed against."""
    try:
        from codex_pdf import __version__ as codex_version
    except ImportError:
        return "unknown"
    return codex_version


def _resolve_codex_section_versions() -> dict[str, str]:
    """Read the COMPILE-time codex section versions Compile was built with."""
    try:
        from codex_pdf.color import COLOR_SCHEMA_VERSION
        from codex_pdf.geom import GEOM_SCHEMA_VERSION
    except ImportError:
        return {}
    return {
        "color": COLOR_SCHEMA_VERSION,
        "geom": GEOM_SCHEMA_VERSION,
        "codex-document": CODEX_DOCUMENT_SCHEMA_VERSION_PIN,
    }


def _resolve_active_producer() -> str:
    """``COMPILE_PRODUCER`` env var; defaults to ``all`` for the central app."""
    return os.environ.get("COMPILE_PRODUCER", "all").strip().lower() or "all"


@asynccontextmanager
async def lifespan(_app: FastAPI):  # type: ignore[no-untyped-def]
    """Startup/shutdown hooks. Currently no-op; reserved for future
    Redis warm-up + cache backend wiring."""
    logger.info(
        "compile_api.startup",
        version=VERSION,
        producer=_resolve_active_producer(),
        instance_id=INSTANCE_ID,
    )
    yield
    logger.info("compile_api.shutdown")


app = FastAPI(
    title="compile-pdf",
    version=VERSION,
    description="The only writer in the Print With Synergy stack.",
    lifespan=lifespan,
)
app.add_middleware(RequestIdMiddleware)


@app.get("/healthz", response_model=HealthResponse, include_in_schema=False)
async def healthz_root() -> HealthResponse:
    return await healthz()


@app.get("/v1/healthz", response_model=HealthResponse)
async def healthz() -> HealthResponse:
    """Liveness + identity + version-skew readout.

    Per spec §1.11a — extends codex's HealthResponse with producer,
    instance_id, codex versions, and ``version_skew`` boolean derived
    from comparing compiled-against vs live Codex section versions.
    Compile's contract guard (§1.11c) consumes this on the client side.
    """
    compiled_versions = _resolve_codex_section_versions()
    # In-process resolution returns the same versions; remote contract guard
    # comparison happens in the codex-pdf HttpClient already.
    live_versions = compiled_versions
    return HealthResponse(
        status="ok",
        version=VERSION,
        producer=_resolve_active_producer(),
        instance_id=INSTANCE_ID,
        cache_backend=os.environ.get("COMPILE_CACHE_BACKEND", "memory"),
        queue_depth=0,  # Wired to Celery in Phase 1.5; no-op until then.
        ghostscript=False,  # Per spec §1.11b — only trap may flip via [trap-gs] extra.
        codex_pdf_version=_resolve_codex_pdf_version(),
        codex_section_versions=compiled_versions,
        codex_live_section_versions=live_versions,
        version_skew=compiled_versions != live_versions,
    )


@app.get("/v1/version", response_model=VersionResponse)
async def version_endpoint() -> VersionResponse:
    return VersionResponse(version=VERSION)


@app.get("/v1/contract", response_model=ContractResponse)
async def contract_endpoint() -> ContractResponse:
    """Per spec §6.2 — exposes the full contract surface so callers can
    pin against ``producer_schema_versions`` and ``codex_section_versions``.

    Mirrors codex-pdf's GET /v1/contract pattern verbatim.
    """
    return ContractResponse(
        contract_name="compile-pdf",
        schema_version=COMPILE_DOCUMENT_SCHEMA_VERSION,
        package_version=VERSION,
        schema_id="https://printwithsynergy.com/schemas/compile/v1",
        endpoints=[r.path for r in app.routes if hasattr(r, "path")],
        producer_schema_versions=PRODUCER_SCHEMA_VERSIONS,
        codex_section_versions=_resolve_codex_section_versions(),
    )


@app.get("/metrics", include_in_schema=False)
async def metrics_endpoint() -> Response:
    """Prometheus exposition. Counters/histograms registered by
    :mod:`compile_pdf.metrics` are scraped here.

    Mirrors codex-pdf's /metrics pattern. Optionally token-gated when
    ``COMPILE_METRICS_TOKEN`` is set (not enforced in this skeleton —
    landing in Phase 1 production hardening)."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# Producer routers mount in Phase 1.x as the engines land. Each producer's
# router lives under ``compile_pdf.{producer}.api`` and exposes
# ``router: APIRouter`` with prefix /v1/{producer}.
def _maybe_mount_routers() -> None:
    active = _resolve_active_producer()
    if active in {"rewrite", "all"}:
        try:
            from compile_pdf.rewrite.api import router as rewrite_router
            app.include_router(rewrite_router, prefix="/v1/rewrite", tags=["rewrite"])
        except ImportError:
            logger.debug("rewrite_router_not_yet_available")
    if active in {"marks", "all"}:
        try:
            from compile_pdf.marks.api import router as marks_router
            app.include_router(marks_router, prefix="/v1/marks", tags=["marks"])
        except ImportError:
            logger.debug("marks_router_not_yet_available")
    if active in {"impose", "all"}:
        try:
            from compile_pdf.impose.api import router as impose_router
            app.include_router(impose_router, prefix="/v1/impose", tags=["impose"])
        except ImportError:
            logger.debug("impose_router_not_yet_available")
    if active in {"trap", "all"}:
        try:
            from compile_pdf.trap.api import router as trap_router
            app.include_router(trap_router, prefix="/v1/trap", tags=["trap"])
        except ImportError:
            logger.debug("trap_router_not_yet_available")


_maybe_mount_routers()


def _ignored() -> Any:
    """Reserved for future shape — keeps the symbol referenced by tests."""
    return None
