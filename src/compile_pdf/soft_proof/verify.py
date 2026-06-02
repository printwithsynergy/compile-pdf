"""Post-condition checks for the soft-proof engine output.

Mirrors :mod:`compile_pdf.trap.verify` — these run after the
engine returns and before the API hands the response back. The
goal is to catch silent corruption (engine produced empty bytes,
broken PDF signature, etc.) at the producer boundary rather than
leaving downstream tooling to discover it.
"""

from __future__ import annotations

from dataclasses import dataclass

from compile_pdf.soft_proof.engine import SoftProofResult


@dataclass(slots=True)
class VerifyReport:
    """Truthy when the result passed every post-condition.

    Mirrors the lightweight verify shape used by the trap
    producer. We only carry the failure list because callers
    don't need a structured pass record — they only ever consume
    ``failures`` (empty = OK).
    """

    ok: bool
    failures: list[str]


def verify_soft_proof(
    *,
    input_bytes: bytes,
    result: SoftProofResult,
) -> VerifyReport:
    """Confirm the engine produced a usable PDF and a sane ΔE summary."""
    failures: list[str] = []
    if not result.output_bytes:
        failures.append("engine returned empty output_bytes")
    elif not result.output_bytes.startswith(b"%PDF"):
        failures.append("engine output is not a recognisable PDF stream")
    # In passthrough mode the input is returned unchanged; once
    # the real LCMS simulator lands this invariant will drop. For
    # the scaffold we make sure the length didn't shrink to zero
    # under our feet (which would indicate engine misbehaviour
    # masquerading as a passthrough).
    if input_bytes and not result.output_bytes:
        failures.append("input was non-empty but output was empty")
    summary = result.delta_e
    if summary.max < 0 or summary.avg < 0 or summary.p95 < 0:
        failures.append("delta_e summary contains negative values")
    if summary.p95 > summary.max + 0.001:
        failures.append("delta_e.p95 cannot exceed delta_e.max")
    return VerifyReport(ok=not failures, failures=failures)
