"""Tests for the white-underbase verify hook."""

from __future__ import annotations

from compile_pdf.white_underbase.engine import (
    WhiteUnderbaseResult,
    apply_white_underbase,
)
from compile_pdf.white_underbase.schema import (
    WhiteUnderbasePolicy,
    WhiteUnderbaseSummary,
)
from compile_pdf.white_underbase.verify import verify_white_underbase


def test_verify_accepts_passthrough_result(simple_pdf: bytes) -> None:
    result = apply_white_underbase(simple_pdf, WhiteUnderbasePolicy())
    check = verify_white_underbase(input_bytes=simple_pdf, result=result)
    assert check.ok
    assert check.failures == []


def test_verify_rejects_empty_output(simple_pdf: bytes) -> None:
    bad = WhiteUnderbaseResult(
        output_bytes=b"",
        summary=WhiteUnderbaseSummary(
            pages_processed=0,
            separation_name="White",
            plate_use="white",
            strategy_applied="auto",
        ),
    )
    check = verify_white_underbase(input_bytes=simple_pdf, result=bad)
    assert not check.ok
    assert any("empty" in f for f in check.failures)


def test_verify_rejects_non_pdf_output(simple_pdf: bytes) -> None:
    bad = WhiteUnderbaseResult(
        output_bytes=b"DEFINITELY-NOT-PDF",
        summary=WhiteUnderbaseSummary(
            pages_processed=0,
            separation_name="White",
            plate_use="white",
            strategy_applied="auto",
        ),
    )
    check = verify_white_underbase(input_bytes=simple_pdf, result=bad)
    assert not check.ok
    assert any("%PDF" in f for f in check.failures)


def test_verify_rejects_page_count_mismatch(simple_pdf: bytes, three_page_pdf: bytes) -> None:
    """If the output's page count differs from the input, verify must fail."""
    bad = WhiteUnderbaseResult(
        output_bytes=three_page_pdf,
        summary=WhiteUnderbaseSummary(
            pages_processed=1,
            separation_name="White",
            plate_use="white",
            strategy_applied="auto",
        ),
    )
    check = verify_white_underbase(input_bytes=simple_pdf, result=bad)
    assert not check.ok
    assert any("page count" in f for f in check.failures)
