"""Producer-agnostic dispatcher for the streaming wrapper.

Routes a :class:`compile_pdf.stream.schema.StreamApplyRequest` to
the underlying producer's engine in-process (no HTTP loopback)
and returns the resulting PDF bytes plus the metadata the API
layer publishes as response headers.

Cache keys and verify hooks are computed exactly as they would
be by the producer's own ``/apply`` endpoint — the streaming
surface is purely a transport optimization, not a semantics
change.
"""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass

from compile_pdf_core.cache import compute_cache_key, hash_canonical_plan

from compile_pdf.stream.schema import (
    SUPPORTED_PRODUCERS,
    ProducerName,
    StreamMetadata,
)
from compile_pdf.version import (
    CODEX_DOCUMENT_SCHEMA_VERSION_PIN,
    IMPOSE_SCHEMA_VERSION,
    MARKS_SCHEMA_VERSION,
    REWRITE_SCHEMA_VERSION,
    SOFT_PROOF_SCHEMA_VERSION,
    TRAP_SCHEMA_VERSION,
    VERSION,
)


class StreamEngineError(RuntimeError):
    """Raised when the streaming wrapper can't satisfy a request.

    Maps to HTTP 400 (unknown producer / malformed payload) or 422
    (underlying engine rejected the payload). The API layer
    inspects the message to choose the status code so callers can
    tell apart "payload didn't validate" from "engine rejected
    valid payload".
    """


@dataclass(slots=True)
class StreamResult:
    """Output of the dispatcher: bytes ready to stream + metadata.

    ``output_bytes`` is the raw PDF; the caller is responsible for
    wrapping it in a chunked HTTP response. ``metadata`` is what
    the API surface promotes to ``X-Compile-*`` headers so callers
    can recover cache identity without re-hashing the response.
    """

    output_bytes: bytes
    metadata: StreamMetadata


def _producer_schema_version(producer: ProducerName) -> str:
    """Return the schema-version constant for the named producer.

    Kept as a tiny lookup table rather than a dict at module scope
    so a future producer addition is a single-line change in one
    place and mypy still narrows the return type.
    """
    if producer == "rewrite":
        return REWRITE_SCHEMA_VERSION
    if producer == "marks":
        return MARKS_SCHEMA_VERSION
    if producer == "impose":
        return IMPOSE_SCHEMA_VERSION
    if producer == "trap":
        return TRAP_SCHEMA_VERSION
    if producer == "soft_proof":
        return SOFT_PROOF_SCHEMA_VERSION
    # Pydantic discriminator catches this at request validation;
    # the unreachable branch only fires if the SUPPORTED_PRODUCERS
    # tuple is widened without updating this function.
    raise StreamEngineError(f"unknown producer: {producer}")


def _resolve_codex_pdf_version() -> str:
    """Mirror of every producer's local helper.

    Each producer duplicates this rather than importing it so the
    producers stay independent; the streaming wrapper follows the
    same convention so a codex bump only requires changing each
    producer's helper once.
    """
    try:
        from codex_pdf import __version__ as codex_version
    except ImportError:
        return "unknown"
    return str(codex_version)


def _decode_input_pdf(payload: dict[str, object], field: str = "input_pdf_b64") -> bytes:
    """Pull the input PDF bytes out of a producer payload.

    Every supported producer carries the input PDF as base64 on
    ``input_pdf_b64``; the streaming wrapper centralizes the
    decode + sha256 so each dispatch branch stays small.
    """
    blob = payload.get(field)
    if not isinstance(blob, str) or not blob:
        raise StreamEngineError(f"{field} is missing or not a string")
    try:
        return base64.b64decode(blob, validate=True)
    except (ValueError, TypeError) as exc:
        raise StreamEngineError(f"{field} is not valid base64: {exc}") from exc


def _dispatch_rewrite(payload: dict[str, object]) -> tuple[bytes, str]:
    """In-process dispatch to the rewrite engine.

    Returns ``(output_bytes, plan_sha256)``. The plan_sha256 is
    threaded back to ``dispatch_stream`` for cache-key computation.
    """
    from compile_pdf_rewrite.engine import RewritePlanError, apply_plan
    from compile_pdf_rewrite.plan_schema import RewritePlan

    input_bytes = _decode_input_pdf(payload)
    try:
        plan = RewritePlan.model_validate(payload["plan"])
    except (KeyError, ValueError) as exc:
        raise StreamEngineError(f"plan validation failed: {exc}") from exc
    try:
        result = apply_plan(input_bytes, plan)
    except RewritePlanError as exc:
        raise StreamEngineError(f"plan rejected: {exc}") from exc
    plan_sha256 = hash_canonical_plan(plan.model_dump(mode="json"))
    return result.output_bytes, plan_sha256


def _dispatch_marks(payload: dict[str, object]) -> tuple[bytes, str]:
    from compile_pdf_marks.engine import MarksTemplateError, apply_template
    from compile_pdf_marks.template_schema import MarksTemplate

    input_bytes = _decode_input_pdf(payload)
    try:
        template = MarksTemplate.model_validate(payload["template"])
    except (KeyError, ValueError) as exc:
        raise StreamEngineError(f"template validation failed: {exc}") from exc
    try:
        result = apply_template(input_bytes, template)
    except MarksTemplateError as exc:
        raise StreamEngineError(f"template rejected: {exc}") from exc
    plan_sha256 = hash_canonical_plan(template.model_dump(mode="json"))
    return result.output_bytes, plan_sha256


def _dispatch_impose(payload: dict[str, object]) -> tuple[bytes, str]:
    from compile_pdf_impose.engine import ImposePlanError, apply_plan
    from compile_pdf_impose.layout_schema import ImposePlan

    input_bytes = _decode_input_pdf(payload)
    try:
        plan = ImposePlan.model_validate(payload["plan"])
    except (KeyError, ValueError) as exc:
        raise StreamEngineError(f"plan validation failed: {exc}") from exc
    try:
        result = apply_plan(input_bytes, plan)
    except ImposePlanError as exc:
        raise StreamEngineError(f"plan rejected: {exc}") from exc
    plan_sha256 = hash_canonical_plan(plan.model_dump(mode="json"))
    return result.output_bytes, plan_sha256


def _dispatch_trap(payload: dict[str, object]) -> tuple[bytes, str]:
    from compile_pdf_trap.engine import TrapEngineError, apply_policy
    from compile_pdf_trap.policy_schema import TrapPolicy

    input_bytes = _decode_input_pdf(payload)
    try:
        policy = TrapPolicy.model_validate(payload["policy"])
    except (KeyError, ValueError) as exc:
        raise StreamEngineError(f"policy validation failed: {exc}") from exc
    try:
        result = apply_policy(input_bytes, policy)
    except TrapEngineError as exc:
        raise StreamEngineError(f"policy rejected: {exc}") from exc
    plan_sha256 = hash_canonical_plan(policy.model_dump(mode="json"))
    return result.output_bytes, plan_sha256


def _dispatch_soft_proof(payload: dict[str, object]) -> tuple[bytes, str]:
    from compile_pdf.soft_proof.engine import SoftProofEngineError, apply_soft_proof
    from compile_pdf.soft_proof.schema import SoftProofOptions

    input_bytes = _decode_input_pdf(payload)
    source_icc = _decode_input_pdf(payload, field="source_icc_b64")
    destination_icc = _decode_input_pdf(payload, field="destination_icc_b64")
    try:
        options = SoftProofOptions.model_validate(payload.get("options", {}))
    except ValueError as exc:
        raise StreamEngineError(f"options validation failed: {exc}") from exc
    try:
        result = apply_soft_proof(input_bytes, source_icc, destination_icc, options)
    except SoftProofEngineError as exc:
        raise StreamEngineError(f"engine rejected: {exc}") from exc
    # Soft-proof's cache key hashes the options PLUS the two
    # profile digests — mirror the api.py logic so cache identity
    # matches between the JSON endpoint and the stream wrapper.
    options_payload = {
        "options": options.model_dump(mode="json"),
        "source_icc_sha256": hashlib.sha256(source_icc).hexdigest(),
        "destination_icc_sha256": hashlib.sha256(destination_icc).hexdigest(),
    }
    return result.output_bytes, hash_canonical_plan(options_payload)


_DISPATCH = {
    "rewrite": _dispatch_rewrite,
    "marks": _dispatch_marks,
    "impose": _dispatch_impose,
    "trap": _dispatch_trap,
    "soft_proof": _dispatch_soft_proof,
}


def dispatch_stream(producer: ProducerName, payload: dict[str, object]) -> StreamResult:
    """Run the named producer's engine on ``payload`` and return the
    PDF bytes plus header metadata.

    Raises :class:`StreamEngineError` for unknown producers,
    malformed payloads, or engine rejections. The HTTP layer maps
    these to 400 / 422 as appropriate.
    """
    if producer not in SUPPORTED_PRODUCERS:
        raise StreamEngineError(
            f"producer '{producer}' not supported; pick one of: {', '.join(SUPPORTED_PRODUCERS)}"
        )

    dispatcher = _DISPATCH[producer]
    output_bytes, plan_sha256 = dispatcher(payload)

    input_bytes = _decode_input_pdf(payload)
    input_sha256 = hashlib.sha256(input_bytes).hexdigest()
    pdf_sha256 = hashlib.sha256(output_bytes).hexdigest()

    try:
        from codex_pdf.color import COLOR_SCHEMA_VERSION
        from codex_pdf.geom import GEOM_SCHEMA_VERSION
    except ImportError as exc:
        raise StreamEngineError(f"codex-pdf surface unavailable: {exc}") from exc

    cache_key = compute_cache_key(
        producer=producer,
        input_sha256=input_sha256,
        canonical_plan_sha256=plan_sha256,
        codex_pdf_package_version=_resolve_codex_pdf_version(),
        color_schema_version=COLOR_SCHEMA_VERSION,
        geom_schema_version=GEOM_SCHEMA_VERSION,
        codex_document_schema_version=CODEX_DOCUMENT_SCHEMA_VERSION_PIN,
    )

    return StreamResult(
        output_bytes=output_bytes,
        metadata=StreamMetadata(
            producer=producer,
            pdf_sha256=pdf_sha256,
            input_sha256=input_sha256,
            cache_key=cache_key,
            schema_version=_producer_schema_version(producer),
            compile_version=VERSION,
        ),
    )
