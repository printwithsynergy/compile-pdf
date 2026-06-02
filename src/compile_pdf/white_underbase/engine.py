"""White / underbase plate generation engine.

Today's engine is a passthrough that:

1. Validates the input bytes look like a PDF.
2. Validates the policy is internally consistent.
3. Counts how many pages the plate would land on (so callers can
   surface the count in the response summary).
4. Returns the input bytes verbatim with a populated summary.

The actual underbase tracing lands in a follow-up once the compose
producer is shipped and a canonical content tree is available to
walk. The wire contract — request shape, response shape, cache
key derivation — is final, so artwork-pdf hosts can wire C2 UI
today against the stable response shape.

The passthrough behaviour mirrors how soft-proof shipped (Wave 2
PR-G): real schema, real cache key, real verify hooks, engine
swap is a single-file follow-up that doesn't touch any other
producer or any of the editor-side code.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import pikepdf

from compile_pdf.white_underbase.schema import (
    WhiteUnderbasePolicy,
    WhiteUnderbaseSummary,
)


class WhiteUnderbaseEngineError(RuntimeError):
    """Raised when the engine rejects an otherwise-valid request.

    Distinct from schema validation errors (which Pydantic raises
    at the API layer): this fires when the input PDF can't be
    parsed, or the policy's ``page_indices`` reference pages that
    don't exist in the input.
    """


@dataclass(slots=True)
class WhiteUnderbaseResult:
    """Engine output. The API layer wraps this in
    :class:`compile_pdf.white_underbase.schema.WhiteUnderbaseApplyResponse`.
    """

    output_bytes: bytes
    summary: WhiteUnderbaseSummary


def _count_pages(input_bytes: bytes) -> int:
    """Open the PDF and return its page count.

    Wraps pikepdf so a malformed PDF surfaces a clean engine
    error instead of a raw pikepdf exception leaking through the
    API layer.
    """
    try:
        with pikepdf.open(io.BytesIO(input_bytes)) as pdf:
            return len(pdf.pages)
    except (pikepdf.PdfError, ValueError) as exc:
        raise WhiteUnderbaseEngineError(f"input PDF is malformed: {exc}") from exc


def apply_white_underbase(
    input_bytes: bytes, policy: WhiteUnderbasePolicy
) -> WhiteUnderbaseResult:
    """Generate a white / underbase plate per ``policy``.

    Raises :class:`WhiteUnderbaseEngineError` if the input PDF is
    malformed or the policy references pages that don't exist.

    Today's implementation is a passthrough — the output bytes
    are identical to the input. The summary is fully populated so
    callers see realistic page counts in their UI even before the
    tracer lands.
    """
    if not input_bytes:
        raise WhiteUnderbaseEngineError("input is empty")
    if not input_bytes.startswith(b"%PDF"):
        raise WhiteUnderbaseEngineError("input does not start with %PDF header")

    total_pages = _count_pages(input_bytes)
    selected_pages = policy.page_indices_or_all(total_pages)

    # Validate page indices reference real pages — silent index
    # clamping would hide a typo in the host-side request builder
    # and make debugging harder.
    invalid = [idx for idx in selected_pages if idx < 0 or idx >= total_pages]
    if invalid:
        raise WhiteUnderbaseEngineError(
            f"page_indices reference out-of-range pages: {invalid} "
            f"(input has {total_pages} pages)"
        )

    summary = WhiteUnderbaseSummary(
        pages_processed=len(selected_pages),
        separation_name=policy.separation_name,
        plate_use=policy.plate_use,
        strategy_applied=policy.strategy,
    )

    # Passthrough: output bytes == input bytes. The follow-up
    # implementation swaps this line for a pikepdf round-trip that
    # walks each selected page's content tree and emits the white
    # plate as a DeviceN overlay.
    return WhiteUnderbaseResult(output_bytes=input_bytes, summary=summary)
