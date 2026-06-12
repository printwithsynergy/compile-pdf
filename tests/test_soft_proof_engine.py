"""Engine-level tests for the soft-proof producer (Wave 2 PR-G).

These test the passthrough engine + verify hook in isolation,
without going through the FastAPI layer. The API tests cover the
HTTP surface; these cover the engine determinism and edge cases.
"""

from __future__ import annotations

import pytest
from compile_pdf_soft_proof.engine import (
    SoftProofEngineError,
    apply_soft_proof,
)
from compile_pdf_soft_proof.schema import SoftProofOptions
from compile_pdf_soft_proof.verify import verify_soft_proof


def _opts(**kwargs: object) -> SoftProofOptions:
    return SoftProofOptions.model_validate(kwargs)


def test_engine_rejects_empty_input() -> None:
    with pytest.raises(SoftProofEngineError, match="empty"):
        apply_soft_proof(b"", b"src", b"dst", _opts())


def test_engine_rejects_missing_profiles() -> None:
    with pytest.raises(SoftProofEngineError, match="ICC"):
        apply_soft_proof(b"%PDF-1.4", b"", b"dst", _opts())
    with pytest.raises(SoftProofEngineError, match="ICC"):
        apply_soft_proof(b"%PDF-1.4", b"src", b"", _opts())


def test_engine_passthrough_preserves_input_bytes() -> None:
    input_bytes = b"%PDF-1.4\nfake-content\n%%EOF\n"
    result = apply_soft_proof(input_bytes, b"src", b"dst", _opts())
    assert result.output_bytes == input_bytes


def test_engine_zero_drift_for_identical_profiles() -> None:
    result = apply_soft_proof(b"%PDF-1.4", b"same", b"same", _opts())
    assert result.delta_e.max == 0
    assert result.delta_e.avg == 0
    assert result.delta_e.p95 == 0


def test_engine_nonzero_drift_for_distinct_profiles() -> None:
    result = apply_soft_proof(b"%PDF-1.4", b"src-bytes", b"dst-bytes", _opts())
    assert result.delta_e.max > 0


def test_verify_passes_on_passthrough() -> None:
    input_bytes = b"%PDF-1.4\n"
    result = apply_soft_proof(input_bytes, b"src", b"dst", _opts())
    report = verify_soft_proof(input_bytes=input_bytes, result=result)
    assert report.ok
    assert report.failures == []


def test_engine_is_deterministic_across_calls() -> None:
    a = apply_soft_proof(b"%PDF-1.4", b"src", b"dst", _opts())
    b = apply_soft_proof(b"%PDF-1.4", b"src", b"dst", _opts())
    assert a.delta_e == b.delta_e
    assert a.output_bytes == b.output_bytes
