"""Tests for the wrapper-level verify hook."""

from __future__ import annotations

from compile_pdf.stream.verify import verify_stream_output


def test_verify_accepts_pdf_bytes() -> None:
    result = verify_stream_output(b"%PDF-1.4\n%%EOF\n")
    assert result.ok
    assert result.failures == []


def test_verify_rejects_empty() -> None:
    result = verify_stream_output(b"")
    assert not result.ok
    # Both "empty" and "header missing" fire on empty input — the
    # second is a side-effect of the empty check itself, surfacing
    # both gives the caller the clearest diagnostic.
    assert any("empty" in f for f in result.failures)


def test_verify_rejects_non_pdf_bytes() -> None:
    result = verify_stream_output(b"NOT-A-PDF")
    assert not result.ok
    assert any("PDF header" in f for f in result.failures)
