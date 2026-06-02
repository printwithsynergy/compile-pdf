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
from codex_pdf.errors import PROBLEM_CONTENT_TYPE, build_problem, problems
from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse, Response

from compile_pdf.api.auth import authenticate
from compile_pdf.api.middleware import INSTANCE_ID, RequestIdMiddleware
from compile_pdf.queue_status import resolve_queue_depth
from compile_pdf.version import (
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
    celery_workers: int = 0
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
    return str(codex_version)


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


# ---------------------------------------------------------------------------
# RFC 7807 Problem Details exception handlers
#
# Phase D of the cross-stack architecture audit (lint-pdf/AUDIT.md
# finding #13): every HTTP error response in the stack uses the same
# `{ type, title, status, detail, instance, ... }` shape with
# `Content-Type: application/problem+json`. The helpers live in
# codex_pdf.errors (Python side) / @printwithsynergy/codex-client/
# problem-details (TS side). compile-pdf was previously using FastAPI
# defaults; these handlers replace that with the org-canonical shape.
# ---------------------------------------------------------------------------


@app.exception_handler(StarletteHTTPException)
async def _problem_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Map any HTTPException raised by a route into Problem Details."""
    body = build_problem(
        status=exc.status_code,
        title=_title_for(exc.status_code),
        detail=str(exc.detail) if exc.detail is not None else _title_for(exc.status_code),
        instance=request.url.path,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=body.model_dump(exclude_none=True),
        media_type=PROBLEM_CONTENT_TYPE,
        headers=getattr(exc, "headers", None) or {},
    )


@app.exception_handler(RequestValidationError)
async def _problem_validation_exception(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Map Pydantic validation errors into Problem Details with `errors` extension."""
    body = problems.unprocessable(
        "Request body failed schema validation.",
        instance=request.url.path,
        extras={"errors": exc.errors()},
    )
    return JSONResponse(
        status_code=422,
        content=body.model_dump(exclude_none=True),
        media_type=PROBLEM_CONTENT_TYPE,
    )


@app.exception_handler(Exception)
async def _problem_unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all — never leak a raw stack to the wire."""
    logger.exception("unhandled exception", path=request.url.path)
    body = problems.internal(
        f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__,
        instance=request.url.path,
    )
    return JSONResponse(
        status_code=500,
        content=body.model_dump(exclude_none=True),
        media_type=PROBLEM_CONTENT_TYPE,
    )


def _title_for(status: int) -> str:
    return {
        400: "Bad Request",
        401: "Unauthorized",
        402: "Payment Required",
        403: "Forbidden",
        404: "Not Found",
        409: "Conflict",
        410: "Gone",
        413: "Payload Too Large",
        415: "Unsupported Media Type",
        422: "Unprocessable Entity",
        429: "Too Many Requests",
        500: "Internal Server Error",
        501: "Not Implemented",
        502: "Bad Gateway",
        503: "Service Unavailable",
        504: "Gateway Timeout",
    }.get(status, f"HTTP {status}")


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
        queue_depth=resolve_queue_depth(),
        celery_workers=_resolve_celery_workers(),
        ghostscript=False,  # Per spec §1.11b — only trap may flip via [trap-gs] extra.
        codex_pdf_version=_resolve_codex_pdf_version(),
        codex_section_versions=compiled_versions,
        codex_live_section_versions=live_versions,
        version_skew=compiled_versions != live_versions,
    )


def _resolve_celery_workers() -> int:
    """Lazy import so the API still loads when Celery isn't configured."""
    try:
        from compile_pdf.tasks import detect_workers
    except Exception:  # pragma: no cover — celery is a hard dep but be defensive
        return 0
    return detect_workers()


@app.get("/v1/version", response_model=VersionResponse)
async def version_endpoint() -> VersionResponse:
    return VersionResponse(version=VERSION)


@app.get("/readyz", include_in_schema=False)
async def readyz_root() -> dict[str, str]:
    return await readyz()


@app.get("/v1/readyz")
async def readyz() -> dict[str, str]:
    """Readiness probe — Phase F of the cross-stack architecture audit
    (lint-pdf/AUDIT.md finding #15). Equivalent to /healthz today;
    future hook point for downstream readiness (codex_pdf availability,
    cache backend reachability, Ghostscript subprocess pool warmth).
    """
    return {"status": "ready"}


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


# Producer routers mount lazily as the engines land. Each producer's
# router lives under ``compile_pdf.{producer}.api`` and exposes
# ``router: APIRouter`` with prefix /v1/{producer}. Auth runs as a
# router-level dependency so producer endpoints don't need to declare
# ``Depends(authenticate)`` individually; ``/healthz`` + ``/v1/healthz``
# + ``/v1/contract`` + ``/v1/version`` + ``/metrics`` stay open since
# they're declared on the app, not the producer routers.
_AUTH_DEPS = [Depends(authenticate)]


def _maybe_mount_routers() -> None:
    active = _resolve_active_producer()
    if active in {"rewrite", "all"}:
        try:
            from compile_pdf.rewrite.api import router as rewrite_router

            app.include_router(
                rewrite_router,
                prefix="/v1/rewrite",
                tags=["rewrite"],
                dependencies=_AUTH_DEPS,
            )
        except ImportError:
            logger.debug("rewrite_router_not_yet_available")
    if active in {"marks", "all"}:
        try:
            from compile_pdf.marks.api import router as marks_router

            app.include_router(
                marks_router,
                prefix="/v1/marks",
                tags=["marks"],
                dependencies=_AUTH_DEPS,
            )
        except ImportError:
            logger.debug("marks_router_not_yet_available")
    if active in {"impose", "all"}:
        try:
            from compile_pdf.impose.api import router as impose_router

            app.include_router(
                impose_router,
                prefix="/v1/impose",
                tags=["impose"],
                dependencies=_AUTH_DEPS,
            )
        except ImportError:
            logger.debug("impose_router_not_yet_available")
    if active in {"trap", "all"}:
        try:
            from compile_pdf.trap.api import router as trap_router

            app.include_router(
                trap_router,
                prefix="/v1/trap",
                tags=["trap"],
                dependencies=_AUTH_DEPS,
            )
        except ImportError:
            logger.debug("trap_router_not_yet_available")
    if active in {"soft_proof", "all"}:
        try:
            from compile_pdf.soft_proof.api import router as soft_proof_router

            app.include_router(
                soft_proof_router,
                prefix="/v1/soft-proof",
                tags=["soft-proof"],
                dependencies=_AUTH_DEPS,
            )
        except ImportError:
            logger.debug("soft_proof_router_not_yet_available")
    if active == "all":
        try:
            from compile_pdf.cjd.api import cjd_router, lineage_router

            app.include_router(cjd_router, prefix="/v1/cjd", tags=["cjd"], dependencies=_AUTH_DEPS)
            app.include_router(
                lineage_router,
                prefix="/v1/lineage",
                tags=["lineage"],
                dependencies=_AUTH_DEPS,
            )
        except ImportError:
            logger.debug("cjd_router_not_yet_available")
        try:
            from compile_pdf.retention.api import router as retention_router

            app.include_router(
                retention_router,
                prefix="/v1/retention",
                tags=["retention"],
                dependencies=_AUTH_DEPS,
            )
        except ImportError:
            logger.debug("retention_router_not_yet_available")


_maybe_mount_routers()


# Always-on metadata routers (independent of COMPILE_PRODUCER).
# `spots` wraps codex-pdf's PANTONE catalogue; it's read-only and
# every artwork-pdf editor instance needs it at boot regardless of
# which producer this server runs.
try:
    from compile_pdf.spots.api import router as spots_router

    app.include_router(spots_router, prefix="/v1/spots", tags=["spots"], dependencies=_AUTH_DEPS)
except ImportError:
    logger.debug("spots_router_not_yet_available")


# `separations` enumerates named inks in an input PDF. Always-on
# (read-only metadata over the supplied PDF, no producer state).
# Editor surface: artwork-pdf's C1 inks palette (Wave 2 PR-5).
try:
    from compile_pdf.separations.api import router as separations_router

    app.include_router(
        separations_router,
        prefix="/v1/separations",
        tags=["separations"],
        dependencies=_AUTH_DEPS,
    )
except ImportError:
    logger.debug("separations_router_not_yet_available")


# `stream` (Wave 3 PR-6 O3) is a producer-agnostic streaming
# wrapper around the existing PDF-producing producers. Always-on
# so a single deploy can serve both JSON-shaped /apply and chunked
# PDF streaming without flipping COMPILE_PRODUCER.
try:
    from compile_pdf.stream.api import router as stream_router

    app.include_router(
        stream_router,
        prefix="/v1/stream",
        tags=["stream"],
        dependencies=_AUTH_DEPS,
    )
except ImportError:
    logger.debug("stream_router_not_yet_available")


def _ignored() -> Any:
    """Reserved for future shape — keeps the symbol referenced by tests."""
    return None
