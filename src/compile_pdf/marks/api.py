"""FastAPI router for the marks producer.

Mounts under ``/v1/marks`` from :mod:`compile_pdf.api.main`. Two
endpoints:

* ``POST /v1/marks/apply`` — inline JSON, no external-file marks
* ``POST /v1/marks/apply-multipart`` — multipart upload, supports
  ``{"type": "external", ...}`` marks. The PDF is uploaded as one
  file part, the JSON template as another, and each external file
  referenced by the template is uploaded as a named part whose name
  matches the template's ``file`` field.
"""

from __future__ import annotations

import base64
import hashlib
import json
import tempfile
from pathlib import Path

import structlog
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, Field, ValidationError

from compile_pdf.cache import compute_cache_key, hash_canonical_plan
from compile_pdf.marks.engine import MarksTemplateError, apply_template
from compile_pdf.marks.template_schema import MarksTemplate
from compile_pdf.marks.verify import verify_marks
from compile_pdf.retention import (
    CONSENT_FORM_FIELD,
    parse_consent,
    persist_if_opted_in,
    resolve_tenant,
)
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
async def marks_apply(payload: MarksApplyRequest, request: Request) -> MarksApplyResponse:
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

    consent = parse_consent(request)
    response = MarksApplyResponse(
        output_pdf_b64=base64.b64encode(result.output_bytes).decode("ascii"),
        pdf_sha256=result.pdf_sha256,
        input_sha256=input_sha256,
        template_sha256=template_sha256,
        cache_key=cache_key,
        cache_hit=False,
        marks_applied=result.marks_applied,
    )
    retained = persist_if_opted_in(
        consent=consent,
        producer="marks",
        tenant=resolve_tenant(request),
        input_bytes=input_bytes,
        output_bytes=result.output_bytes,
        result=response.model_dump(mode="json"),
        input_sha256=input_sha256,
    )
    logger.info(
        "marks.apply.ok",
        output_sha256=result.pdf_sha256[:16],
        marks_applied=result.marks_applied,
        consent=consent,
        retained=retained,
    )
    return response


@router.post(
    "/apply-multipart",
    response_model=MarksApplyResponse,
    status_code=status.HTTP_200_OK,
)
async def marks_apply_multipart(
    request: Request,
    input_pdf: UploadFile = File(..., description="The input PDF."),  # noqa: B008
    template: str = Form(..., description="JSON marks-template document."),  # noqa: B008
    externals: list[UploadFile] = File(  # noqa: B008
        default=[],
        description=(
            "External-file marks. Each file's name must match the "
            "``file`` field of an external mark in the template."
        ),
    ),
    retain_for_training: str | None = Form(  # noqa: B008
        default=None,
        alias=CONSENT_FORM_FIELD,
        description="Opt-in flag — 'true'/'1'/'yes' persists the call for training.",
    ),
) -> MarksApplyResponse:
    """Stamp a marks template that may include ``external`` marks.

    External files arrive as separate multipart parts; the engine
    resolves each ``ExternalMark.file`` against the uploaded part with
    that name. Unknown external references (no matching part) → 422.
    """
    try:
        template_dict = json.loads(template)
        parsed = MarksTemplate.model_validate(template_dict)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"template_invalid: {exc}",
        ) from exc

    input_bytes = await input_pdf.read()
    if not input_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="input is empty")

    expected_files = {m.file for m in parsed.marks if m.type == "external"}
    provided_files = {(u.filename or "") for u in externals if u.filename}
    missing = expected_files - provided_files
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"external_files_missing: {sorted(missing)}",
        )

    input_sha256 = hashlib.sha256(input_bytes).hexdigest()
    template_sha256 = hash_canonical_plan(parsed.model_dump(mode="json"))

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
        "marks.apply_multipart.start",
        marks=len(parsed.marks),
        externals=len(externals),
        input_sha256=input_sha256[:16],
        template_sha256=template_sha256[:16],
    )

    with tempfile.TemporaryDirectory(prefix="compile-marks-ext-") as td:
        external_root = Path(td)
        for uploaded in externals:
            if not uploaded.filename:
                continue
            # Path-traversal guard: a multipart part's filename is fully
            # attacker-controlled, so e.g. "../../etc/cron.d/x" would escape
            # the temp dir on write. Externals are referenced by a bare name
            # in the template, so reject anything that isn't already a plain
            # in-directory filename (no separators, not "." / "..").
            safe_name = Path(uploaded.filename).name
            if not safe_name or safe_name in {".", ".."} or safe_name != uploaded.filename:
                raise HTTPException(status_code=400, detail="invalid external filename")
            (external_root / safe_name).write_bytes(await uploaded.read())

        try:
            result = apply_template(input_bytes, parsed, external_root=external_root)
        except MarksTemplateError as exc:
            raise HTTPException(status_code=422, detail=f"template rejected: {exc}") from exc

    verify = verify_marks(
        input_bytes=input_bytes,
        output_bytes=result.output_bytes,
        template=parsed,
        determinism_replay=False,
    )
    if not (verify.layer1_schema and verify.layer3_unchanged):
        logger.error("marks.apply_multipart.verify_failed", failures=verify.failures)
        raise HTTPException(
            status_code=500,
            detail={"error": "verify failed", "failures": verify.failures},
        )

    consent = parse_consent(request, form_value=retain_for_training)
    response = MarksApplyResponse(
        output_pdf_b64=base64.b64encode(result.output_bytes).decode("ascii"),
        pdf_sha256=result.pdf_sha256,
        input_sha256=input_sha256,
        template_sha256=template_sha256,
        cache_key=cache_key,
        cache_hit=False,
        marks_applied=result.marks_applied,
    )
    retained = persist_if_opted_in(
        consent=consent,
        producer="marks",
        tenant=resolve_tenant(request),
        input_bytes=input_bytes,
        output_bytes=result.output_bytes,
        result=response.model_dump(mode="json"),
        input_sha256=input_sha256,
    )
    logger.info(
        "marks.apply_multipart.ok",
        output_sha256=result.pdf_sha256[:16],
        marks_applied=result.marks_applied,
        consent=consent,
        retained=retained,
    )
    return response


def _resolve_codex_pdf_version() -> str:
    """Read codex_pdf wheel version Compile was deployed against."""
    try:
        from codex_pdf import __version__ as codex_version
    except ImportError:
        return "unknown"
    return str(codex_version)
