"""FastAPI router for the soft-proof producer.

Mounts under ``/v1/soft-proof`` from :mod:`compile_pdf.api.main`.
Single endpoint today: ``POST /v1/soft-proof/apply``. Mirrors the
trap / marks / impose / rewrite producer surface so operator
tooling (lineage extraction, cache-hit metrics, etc.) treats every
producer the same way.
"""

from __future__ import annotations

import base64
import hashlib

import structlog
from fastapi import APIRouter, HTTPException, status

from compile_pdf.cache import compute_cache_key, hash_canonical_plan
from compile_pdf.soft_proof.engine import SoftProofEngineError, apply_soft_proof
from compile_pdf.soft_proof.schema import (
    SoftProofApplyRequest,
    SoftProofApplyResponse,
)
from compile_pdf.soft_proof.verify import verify_soft_proof
from compile_pdf.version import (
    CODEX_DOCUMENT_SCHEMA_VERSION_PIN,
    SOFT_PROOF_SCHEMA_VERSION,
    VERSION,
)

logger = structlog.get_logger(__name__)

router = APIRouter()


def _resolve_codex_pdf_version() -> str:
    """Mirror of the helper in :mod:`compile_pdf.trap.api`.

    Duplicated rather than imported so the producer modules stay
    independent — the trap producer can ship a fix to its codex
    handling without breaking soft-proof's cache key.
    """
    try:
        from codex_pdf import __version__ as codex_version
    except ImportError:
        return "unknown"
    return str(codex_version)


def _decode_b64(blob: str, field: str) -> bytes:
    """Decode + validate a request field as strict base64.

    Wraps :func:`base64.b64decode` so the 400 response carries the
    offending field name — otherwise a malformed source profile
    looks identical to a malformed destination profile to the
    caller, and debugging is unnecessarily hard.
    """
    try:
        decoded = base64.b64decode(blob, validate=True)
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field} is not valid base64: {exc}",
        ) from exc
    if not decoded:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field} is empty after decoding",
        )
    return decoded


@router.post(
    "/apply",
    response_model=SoftProofApplyResponse,
    status_code=status.HTTP_200_OK,
)
async def soft_proof_apply(payload: SoftProofApplyRequest) -> SoftProofApplyResponse:
    """Simulate the input PDF under the destination ICC profile.

    The current engine is a passthrough (see
    :mod:`compile_pdf.soft_proof.engine`); the response shape is
    final. Once the real LCMS-based simulator lands the only
    visible change to callers is that the ΔE summary becomes
    meaningfully larger for mismatched profile pairs.
    """
    input_bytes = _decode_b64(payload.input_pdf_b64, "input_pdf_b64")
    source_icc = _decode_b64(payload.source_icc_b64, "source_icc_b64")
    destination_icc = _decode_b64(payload.destination_icc_b64, "destination_icc_b64")

    input_sha256 = hashlib.sha256(input_bytes).hexdigest()
    source_icc_sha256 = hashlib.sha256(source_icc).hexdigest()
    destination_icc_sha256 = hashlib.sha256(destination_icc).hexdigest()
    # Cache key hashes the options object + both profile digests.
    # Same input + same profiles + same options → cache hit, even
    # though the profile bytes themselves are inlined on each
    # request.
    options_payload = {
        "options": payload.options.model_dump(mode="json"),
        "source_icc_sha256": source_icc_sha256,
        "destination_icc_sha256": destination_icc_sha256,
    }
    options_sha256 = hash_canonical_plan(options_payload)

    try:
        from codex_pdf.color import COLOR_SCHEMA_VERSION
        from codex_pdf.geom import GEOM_SCHEMA_VERSION
    except ImportError as exc:  # pragma: no cover — codex-pdf is a hard dep
        raise HTTPException(
            status_code=500,
            detail=f"codex-pdf surface unavailable: {exc}",
        ) from exc

    cache_key = compute_cache_key(
        producer="soft_proof",
        input_sha256=input_sha256,
        canonical_plan_sha256=options_sha256,
        codex_pdf_package_version=_resolve_codex_pdf_version(),
        color_schema_version=COLOR_SCHEMA_VERSION,
        geom_schema_version=GEOM_SCHEMA_VERSION,
        codex_document_schema_version=CODEX_DOCUMENT_SCHEMA_VERSION_PIN,
    )

    logger.info(
        "soft_proof.apply.start",
        input_sha256=input_sha256[:16],
        source_icc_sha256=source_icc_sha256[:16],
        destination_icc_sha256=destination_icc_sha256[:16],
        intent=payload.options.intent,
        cache_key=cache_key[:16],
    )

    try:
        result = apply_soft_proof(input_bytes, source_icc, destination_icc, payload.options)
    except SoftProofEngineError as exc:
        raise HTTPException(status_code=422, detail=f"engine rejected: {exc}") from exc

    verify = verify_soft_proof(input_bytes=input_bytes, result=result)
    if not verify.ok:
        raise HTTPException(status_code=500, detail=f"verify failed: {verify.failures}")

    output_sha256 = hashlib.sha256(result.output_bytes).hexdigest()

    return SoftProofApplyResponse(
        output_pdf_b64=base64.b64encode(result.output_bytes).decode("ascii"),
        pdf_sha256=output_sha256,
        input_sha256=input_sha256,
        options_sha256=options_sha256,
        source_icc_sha256=source_icc_sha256,
        destination_icc_sha256=destination_icc_sha256,
        cache_key=cache_key,
        cache_hit=False,
        delta_e=result.delta_e,
        schema_version=SOFT_PROOF_SCHEMA_VERSION,
        compile_version=VERSION,
    )
