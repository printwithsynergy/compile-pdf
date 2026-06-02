"""Wave 2 PR-G — soft-proof producer.

Surfaces compile-pdf's ICC soft-proof simulator under
``POST /v1/soft-proof/apply``. The endpoint accepts an input PDF
and a profile pair (source + destination + rendering intent) and
returns a base64-encoded simulated PDF plus a per-pixel ΔE summary
that the artwork-pdf editor (Wave 2 PR-6 C5 overlay) paints over
the canvas.

Module surface (mirrors the trap / impose / marks producers so
ops tooling can treat every producer the same way):

- ``SOFT_PROOF_SCHEMA_VERSION`` — bumped per spec §6.2 when the
  request / response shape changes.
- ``router`` — FastAPI router mounted under ``/v1/soft-proof``.
- ``apply_soft_proof`` — engine entry point.
"""

from __future__ import annotations

from compile_pdf.soft_proof.api import router

__all__ = ["router"]
