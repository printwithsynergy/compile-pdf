"""Post-condition checks for the streaming wrapper.

Producer-level verify hooks already run inside each underlying
engine path during ``dispatch_stream``. The wrapper-level
verify is intentionally narrow: confirm the produced bytes
look like a PDF before the HTTP layer commits to streaming
``Content-Type: application/pdf``. Anything stronger would
duplicate work the per-producer verify already did.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class StreamVerifyResult:
    """Lightweight verify outcome. ``ok=True`` when all checks pass."""

    ok: bool
    failures: list[str] = field(default_factory=list)


def verify_stream_output(output_bytes: bytes) -> StreamVerifyResult:
    """Sanity-check the streamed payload before we commit headers.

    Two checks: non-empty bytes and a recognisable PDF header. We
    don't parse the full PDF — that's the underlying producer's
    job, and re-parsing here would defeat the streaming optimization.
    """
    failures: list[str] = []
    if not output_bytes:
        failures.append("output_bytes is empty")
    if not output_bytes.startswith(b"%PDF"):
        failures.append("output_bytes does not start with %PDF header")
    return StreamVerifyResult(ok=not failures, failures=failures)
