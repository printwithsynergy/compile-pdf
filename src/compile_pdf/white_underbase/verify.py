"""Post-condition checks for the white / underbase producer.

Today's passthrough engine returns input bytes verbatim, so the
verify hook is minimal: confirm the output is non-empty, looks
like a PDF, and reports the same page count the engine claims it
processed. When the real tracer lands in a follow-up, this hook
gains separation-presence and content-preservation checks.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field

import pikepdf

from compile_pdf.white_underbase.engine import WhiteUnderbaseResult


@dataclass(slots=True)
class WhiteUnderbaseVerifyResult:
    """Lightweight verify outcome. ``ok=True`` when all checks pass."""

    ok: bool
    failures: list[str] = field(default_factory=list)


def verify_white_underbase(
    *, input_bytes: bytes, result: WhiteUnderbaseResult
) -> WhiteUnderbaseVerifyResult:
    """Run post-condition checks against an engine result.

    Three checks today:

    1. Output bytes are non-empty.
    2. Output starts with the ``%PDF`` header (defence-in-depth
       against an engine bug returning JSON / debug text).
    3. Output page count matches the input page count.
    """
    failures: list[str] = []
    if not result.output_bytes:
        failures.append("output_bytes is empty")
    if not result.output_bytes.startswith(b"%PDF"):
        failures.append("output_bytes does not start with %PDF header")

    try:
        with pikepdf.open(io.BytesIO(result.output_bytes)) as out_pdf:
            out_pages = len(out_pdf.pages)
    except (pikepdf.PdfError, ValueError) as exc:
        failures.append(f"output PDF failed to open: {exc}")
        return WhiteUnderbaseVerifyResult(ok=False, failures=failures)

    try:
        with pikepdf.open(io.BytesIO(input_bytes)) as in_pdf:
            in_pages = len(in_pdf.pages)
    except (pikepdf.PdfError, ValueError) as exc:
        # We can verify the output without the input being
        # parseable, but we can't compare page counts. The engine
        # already rejected unparseable inputs, so reaching this
        # branch means the input was mutated under us — surface
        # rather than swallow.
        failures.append(f"input PDF unexpectedly malformed at verify time: {exc}")
        return WhiteUnderbaseVerifyResult(ok=False, failures=failures)

    if in_pages != out_pages:
        failures.append(
            f"output page count {out_pages} differs from input {in_pages}"
        )

    return WhiteUnderbaseVerifyResult(ok=not failures, failures=failures)
