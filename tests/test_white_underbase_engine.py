"""Engine-level tests for the white / underbase producer (Wave 3 PR-7).

Cover the passthrough engine + policy validation. The API tests
cover the HTTP surface; these cover engine determinism and edge
cases the API surface doesn't reach.
"""

from __future__ import annotations

import pytest
from compile_pdf_white_underbase.engine import (
    WhiteUnderbaseEngineError,
    apply_white_underbase,
)
from compile_pdf_white_underbase.schema import WhiteUnderbasePolicy


def _policy(**kwargs: object) -> WhiteUnderbasePolicy:
    return WhiteUnderbasePolicy.model_validate(kwargs)


def test_engine_rejects_empty_input() -> None:
    with pytest.raises(WhiteUnderbaseEngineError, match="empty"):
        apply_white_underbase(b"", _policy())


def test_engine_rejects_non_pdf_input() -> None:
    with pytest.raises(WhiteUnderbaseEngineError, match="%PDF header"):
        apply_white_underbase(b"NOT-A-PDF", _policy())


def test_engine_rejects_malformed_pdf() -> None:
    with pytest.raises(WhiteUnderbaseEngineError, match="malformed"):
        apply_white_underbase(b"%PDF-1.4\nthis-is-not-actually-a-pdf", _policy())


def test_engine_passthrough_preserves_input_bytes(simple_pdf: bytes) -> None:
    result = apply_white_underbase(simple_pdf, _policy())
    assert result.output_bytes == simple_pdf


def test_summary_reports_default_separation(simple_pdf: bytes) -> None:
    result = apply_white_underbase(simple_pdf, _policy())
    assert result.summary.separation_name == "White"
    assert result.summary.plate_use == "white"
    assert result.summary.strategy_applied == "auto"
    # simple_pdf is 1-page; all pages processed by default.
    assert result.summary.pages_processed == 1


def test_summary_honours_explicit_separation_name(simple_pdf: bytes) -> None:
    result = apply_white_underbase(
        simple_pdf,
        _policy(separation_name="Underbase", plate_use="underbase"),
    )
    assert result.summary.separation_name == "Underbase"
    assert result.summary.plate_use == "underbase"


def test_engine_rejects_out_of_range_page_indices(three_page_pdf: bytes) -> None:
    with pytest.raises(WhiteUnderbaseEngineError, match="out-of-range"):
        apply_white_underbase(three_page_pdf, _policy(page_indices=[0, 5]))


def test_engine_honours_page_indices_subset(three_page_pdf: bytes) -> None:
    result = apply_white_underbase(three_page_pdf, _policy(page_indices=[0, 2]))
    assert result.summary.pages_processed == 2


def test_engine_determinism(simple_pdf: bytes) -> None:
    """Same input + same policy across 3 runs → identical output
    bytes + identical summary."""
    runs = [apply_white_underbase(simple_pdf, _policy()) for _ in range(3)]
    first = runs[0]
    for run in runs[1:]:
        assert run.output_bytes == first.output_bytes
        assert run.summary == first.summary
