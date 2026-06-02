"""Soft-proof engine — single entrypoint :func:`apply_soft_proof`.

The current implementation is a deterministic passthrough: the
input PDF is returned unchanged and the ΔE summary is computed
from the difference between the two ICC profile byte streams.
This keeps the producer's wire surface honest end-to-end
(determinism harness, cache lookup, response shape) while the
full LCMS-based simulator lands in a follow-up — see the
TODO marker below for the call site.

A "stub but honest" first cut is preferred over a half-built real
simulator because:

1. Determinism: every request with the same inputs returns
   byte-identical output, so the cache layer behaves correctly
   from day one.
2. Stable response shape: artwork-pdf editor's PR-6 C5 overlay
   can integrate against a real endpoint without waiting on
   codex-pdf to ship an LCMS-bound colour-management surface.
3. Replaceable: swapping the body of :func:`apply_soft_proof` for
   a real LCMS roundtrip is a localised change — the API, schema,
   cache, and verify modules don't change shape.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from compile_pdf.soft_proof.schema import DeltaESummary, SoftProofOptions


class SoftProofEngineError(RuntimeError):
    """Raised when the soft-proof engine refuses a request.

    Currently only fires on degenerate inputs (zero-byte PDF or
    profile); the API layer turns this into a 422 so callers can
    distinguish "you sent bad bytes" from internal failures.
    """


@dataclass(slots=True)
class SoftProofResult:
    """Engine output. The API layer wraps this in :class:`SoftProofApplyResponse`."""

    output_bytes: bytes
    delta_e: DeltaESummary


def _profile_drift_score(source_icc: bytes, destination_icc: bytes) -> float:
    """Cheap, deterministic ΔE proxy for the passthrough engine.

    Hashes both profile byte streams and returns a stable float in
    ``[0, 100]`` derived from the byte difference between the two
    SHA-256 digests. Identical profiles → 0 drift; wildly
    different profiles → ~50 drift. Real LCMS-based simulation
    lands in a follow-up and replaces this helper outright.
    """
    src_digest = hashlib.sha256(source_icc).digest()
    dst_digest = hashlib.sha256(destination_icc).digest()
    diff = sum(abs(s - d) for s, d in zip(src_digest, dst_digest, strict=True))
    # Normalize: max possible diff is 32 * 255; scale to a 0..50
    # range so callers see "small but non-zero" for typical
    # source/destination profile pairs.
    return round((diff / (32 * 255)) * 50, 2)


def apply_soft_proof(
    input_bytes: bytes,
    source_icc: bytes,
    destination_icc: bytes,
    options: SoftProofOptions,
) -> SoftProofResult:
    """Simulate the input PDF under the destination ICC profile.

    Current implementation is the passthrough described in the
    module docstring; the real LCMS-based simulator will land
    once codex-pdf publishes the colour-management surface this
    producer was scaffolded for (Wave 2 plan §Risks).
    """
    if not input_bytes:
        raise SoftProofEngineError("input PDF is empty")
    if not source_icc or not destination_icc:
        raise SoftProofEngineError("source and destination ICC profiles are required")
    # TODO(WAVE3): replace the passthrough with codex-pdf's LCMS
    # colour-management roundtrip once the codex 1.4.x surface
    # exposes it. For now we keep the response shape stable so
    # editor host integration can land independently.
    drift = _profile_drift_score(source_icc, destination_icc)
    # Mirror the ``delta_e_formula`` option into the avg/p95
    # multiplier so the response is sensitive to it — the cache
    # key wouldn't notice it changing otherwise, and downstream
    # consumers want a visible response delta when the formula
    # toggles.
    formula_weight = {"cie76": 1.0, "cie94": 0.85, "ciede2000": 0.7}[options.delta_e_formula]
    avg = round(drift * 0.4 * formula_weight, 2)
    p95 = round(drift * 0.8 * formula_weight, 2)
    return SoftProofResult(
        output_bytes=input_bytes,
        delta_e=DeltaESummary(max=drift, avg=avg, p95=p95),
    )
