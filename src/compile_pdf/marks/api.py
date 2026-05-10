"""FastAPI router for the marks producer.

Mounts under ``/v1/marks`` from :mod:`compile_pdf.api.main`. Single
endpoint today: ``POST /v1/marks/apply``.
"""

from __future__ import annotations

import base64
import hashlib

import structlog
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from compile_pdf.cache import compute_cache_key, hash_canonical_plan
from compile_pdf.marks.engine import MarksTemplateError, apply_template
from compile_pdf.marks.template_schema import MarksTemplate
from compile_pdf.marks.verify import verify_marks
from compile_pdf.version import (
    CODEX_DOCUMENT_SCHEMA_VERSION_PIN,
    MARKS_SCHEMA_VERSION,
    VERSION,
)

logger = structlog.get_logger(__name__)

router = APIRouter()


class MarksApplyRequest(BaseModel):
    """Request envelope: an inline base64-encoded PDF + a template.

    Bytes-in / bytes-out. Lineage records persist to the configured S3
    bucket asynchronously and are addressable by the returned
    ``cache_key`` (Phase 5 lights up the actual store).

    External-file marks are not supported through the inline JSON
    transport — they require a multipart upload variant (Phase 2.x).
    Templates that include ``{"type": "external", ...}`` are rejected
    here with ``422 external_marks_not_supported_inline``.
    """

    model_config = {"extra": "forbid"}

    input_pdf_b64: str = Field(min_length=1)
    template: MarksTemplate


class MarksApplyResponse(BaseModel):
    model_config = {"extra": "forbid"}

    output_pdf_b64: str
    pdf_sha256: str
    input_sha256: str
    template_sha256: str
    cache_key: str
    cache_hit: bool = False
    marks_applied: int
    schema_version: str = MARKS_SCHEMA_VERSION
    compile_version: str = VERSION


@router.post("/apply", response_model=MarksApplyResponse, status_code=status.HTTP_200_OK)
async def marks_apply(payload: MarksApplyRequest) -> MarksApplyResponse:
    """Stamp a marks template over an inline base64-encoded PDF.

    Verification (spec §2.3 four layers) runs server-side before the
    response is returned. A failed verify is a 500 — the template was
    valid but the engine produced output that doesn't satisfy the
    post-conditions.
    """
    try:
        input_bytes = base64.b64decode(payload.input_pdf_b64, validate=True)
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"input_pdf_b64 is not valid base64: {exc}",
        ) from exc

    if not input_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="input is empty")

    if any(m.type == "external" for m in payload.template.marks):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="external_marks_not_supported_inline",
        )

    input_sha256 = hashlib.sha256(input_bytes).hexdigest()
    template_sha256 = hash_canonical_plan(payload.template.model_dump(mode="json"))

    try:
        from codex_pdf.color import COLOR_SCHEMA_VERSION
        from codex_pdf.geom import GEOM_SCHEMA_VERSION
    except ImportError as exc:  # pragma: no cover — codex-pdf is a hard dep
        raise HTTPException(
            status_code=500, detail=f"codex-pdf surface unavailable: {exc}"
        ) from exc

    cache_key = compute_cache_key(
        producer="marks",
        input_sha256=input_sha256,
        canonical_plan_sha256=template_sha256,
        codex_pdf_package_version=_resolve_codex_pdf_version(),
        color_schema_version=COLOR_SCHEMA_VERSION,
        geom_schema_version=GEOM_SCHEMA_VERSION,
        codex_document_schema_version=CODEX_DOCUMENT_SCHEMA_VERSION_PIN,
    )

    logger.info(
        "marks.apply.start",
        marks=len(payload.template.marks),
        input_sha256=input_sha256[:16],
        template_sha256=template_sha256[:16],
        cache_key=cache_key[:16],
    )

    try:
        result = apply_template(input_bytes, payload.template)
    except MarksTemplateError as exc:
        raise HTTPException(status_code=422, detail=f"template rejected: {exc}") from exc

    verify = verify_marks(
        input_bytes=input_bytes,
        output_bytes=result.output_bytes,
        template=payload.template,
        determinism_replay=False,
    )
    if not (verify.layer1_schema and verify.layer3_unchanged):
        logger.error("marks.apply.verify_failed", failures=verify.failures)
        raise HTTPException(
            status_code=500,
            detail={"error": "verify failed", "failures": verify.failures},
        )

    logger.info(
        "marks.apply.ok",
        output_sha256=result.pdf_sha256[:16],
        marks_applied=result.marks_applied,
    )

    return MarksApplyResponse(
        output_pdf_b64=base64.b64encode(result.output_bytes).decode("ascii"),
        pdf_sha256=result.pdf_sha256,
        input_sha256=input_sha256,
        template_sha256=template_sha256,
        cache_key=cache_key,
        cache_hit=False,
        marks_applied=result.marks_applied,
    )


def _resolve_codex_pdf_version() -> str:
    """Read codex_pdf wheel version Compile was deployed against."""
    try:
        from codex_pdf import __version__ as codex_version
    except ImportError:
        return "unknown"
    return str(codex_version)
