"""FastAPI router for the white / underbase producer.

Mounts under ``/v1/white-underbase`` from
:mod:`compile_pdf.api.main`. Single endpoint today:
``POST /v1/white-underbase/apply``. Mirrors the trap / marks /
impose / rewrite / soft-proof producer surface so operator tooling
treats every producer the same way.
"""

from __future__ import annotations

import base64
import hashlib

import structlog
from fastapi import APIRouter, HTTPException, status

from compile_pdf.cache import compute_cache_key, hash_canonical_plan
from compile_pdf.version import (
    CODEX_DOCUMENT_SCHEMA_VERSION_PIN,
    VERSION,
    WHITE_UNDERBASE_SCHEMA_VERSION,
)
from compile_pdf.white_underbase.engine import (
    WhiteUnderbaseEngineError,
    apply_white_underbase,
)
from compile_pdf.white_underbase.schema import (
    WhiteUnderbaseApplyRequest,
    WhiteUnderbaseApplyResponse,
)
from compile_pdf.white_underbase.verify import verify_white_underbase

logger = structlog.get_logger(__name__)

router = APIRouter()


def _resolve_codex_pdf_version() -> str:
    """Mirror of the helper in every producer's api.py.

    Duplicated rather than imported so the producer modules stay
    independent — a fix to one producer's codex handling won't
    break white_underbase's cache key.
    """
    try:
        from codex_pdf import __version__ as codex_version
    except ImportError:
        return "unknown"
    return str(codex_version)


def _decode_input_pdf(blob: str) -> bytes:
    """Decode + validate the request's base64-encoded PDF."""
    try:
        decoded = base64.b64decode(blob, validate=True)
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"input_pdf_b64 is not valid base64: {exc}",
        ) from exc
    if not decoded:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="input_pdf_b64 is empty after decoding",
        )
    return decoded


@router.post(
    "/apply",
    response_model=WhiteUnderbaseApplyResponse,
    status_code=status.HTTP_200_OK,
)
async def white_underbase_apply(
    payload: WhiteUnderbaseApplyRequest,
) -> WhiteUnderbaseApplyResponse:
    """Generate a white / underbase plate per the request policy.

    Today's engine is a passthrough (see
    :mod:`compile_pdf.white_underbase.engine`); the response shape
    is final. Once the real tracer lands the only visible change
    to callers is that ``output_pdf_b64`` differs from the input
    when the policy selects any pages.
    """
    input_bytes = _decode_input_pdf(payload.input_pdf_b64)

    input_sha256 = hashlib.sha256(input_bytes).hexdigest()
    policy_sha256 = hash_canonical_plan(payload.policy.model_dump(mode="json"))

    try:
        from codex_pdf.color import COLOR_SCHEMA_VERSION
        from codex_pdf.geom import GEOM_SCHEMA_VERSION
    except ImportError as exc:  # pragma: no cover — codex-pdf is a hard dep
        raise HTTPException(
            status_code=500,
            detail=f"codex-pdf surface unavailable: {exc}",
        ) from exc

    cache_key = compute_cache_key(
        producer="white_underbase",
        input_sha256=input_sha256,
        canonical_plan_sha256=policy_sha256,
        codex_pdf_package_version=_resolve_codex_pdf_version(),
        color_schema_version=COLOR_SCHEMA_VERSION,
        geom_schema_version=GEOM_SCHEMA_VERSION,
        codex_document_schema_version=CODEX_DOCUMENT_SCHEMA_VERSION_PIN,
    )

    logger.info(
        "white_underbase.apply.start",
        input_sha256=input_sha256[:16],
        policy_sha256=policy_sha256[:16],
        separation_name=payload.policy.separation_name,
        strategy=payload.policy.strategy,
        cache_key=cache_key[:16],
    )

    try:
        result = apply_white_underbase(input_bytes, payload.policy)
    except WhiteUnderbaseEngineError as exc:
        raise HTTPException(status_code=422, detail=f"engine rejected: {exc}") from exc

    verify = verify_white_underbase(input_bytes=input_bytes, result=result)
    if not verify.ok:
        logger.error("white_underbase.apply.verify_failed", failures=verify.failures)
        raise HTTPException(
            status_code=500,
            detail={"error": "verify failed", "failures": verify.failures},
        )

    output_sha256 = hashlib.sha256(result.output_bytes).hexdigest()

    logger.info(
        "white_underbase.apply.ok",
        output_sha256=output_sha256[:16],
        pages_processed=result.summary.pages_processed,
    )

    return WhiteUnderbaseApplyResponse(
        output_pdf_b64=base64.b64encode(result.output_bytes).decode("ascii"),
        pdf_sha256=output_sha256,
        input_sha256=input_sha256,
        policy_sha256=policy_sha256,
        cache_key=cache_key,
        cache_hit=False,
        summary=result.summary,
        schema_version=WHITE_UNDERBASE_SCHEMA_VERSION,
        compile_version=VERSION,
    )
