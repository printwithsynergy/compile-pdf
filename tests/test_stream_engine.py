"""Engine-level tests for the stream dispatcher.

Exercises the dispatch table against rewrite (the simplest
producer) and verifies error paths for unknown producers and
malformed payloads.
"""

from __future__ import annotations

import base64

import pytest

from compile_pdf.stream.engine import (
    StreamEngineError,
    dispatch_stream,
)
from compile_pdf.stream.schema import SUPPORTED_PRODUCERS


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def test_dispatch_rejects_unknown_producer(simple_pdf: bytes) -> None:
    with pytest.raises(StreamEngineError, match="not supported"):
        # type ignore: intentionally feeding an invalid producer to
        # exercise the unknown-producer guard; the typed enum
        # would otherwise prevent reaching this code path.
        dispatch_stream(
            "no-such-producer",  # type: ignore[arg-type]
            {"input_pdf_b64": _b64(simple_pdf)},
        )


def test_dispatch_rejects_missing_input_pdf() -> None:
    with pytest.raises(StreamEngineError, match="input_pdf_b64 is missing"):
        dispatch_stream("rewrite", {"plan": {"ops": []}})


def test_dispatch_rejects_bad_base64() -> None:
    with pytest.raises(StreamEngineError, match="not valid base64"):
        dispatch_stream(
            "rewrite",
            {"input_pdf_b64": "@@not-base64@@", "plan": {"ops": []}},
        )


def test_dispatch_rejects_missing_plan(simple_pdf: bytes) -> None:
    with pytest.raises(StreamEngineError, match="plan validation failed"):
        dispatch_stream("rewrite", {"input_pdf_b64": _b64(simple_pdf)})


def test_rewrite_dispatch_returns_pdf_and_metadata(simple_pdf: bytes) -> None:
    result = dispatch_stream(
        "rewrite",
        {"input_pdf_b64": _b64(simple_pdf), "plan": {"ops": []}},
    )
    assert result.output_bytes.startswith(b"%PDF")
    assert result.metadata.producer == "rewrite"
    assert len(result.metadata.pdf_sha256) == 64
    assert len(result.metadata.input_sha256) == 64
    assert len(result.metadata.cache_key) == 64
    assert result.metadata.schema_version  # populated from REWRITE_SCHEMA_VERSION


def test_supported_producers_is_complete() -> None:
    """The dispatch table must cover every entry in
    :data:`SUPPORTED_PRODUCERS` — otherwise the wrapper would
    accept a request it can't actually route."""
    from compile_pdf.stream.engine import _DISPATCH

    assert set(_DISPATCH.keys()) == set(SUPPORTED_PRODUCERS)


def test_marks_dispatch_rejects_missing_template(simple_pdf: bytes) -> None:
    with pytest.raises(StreamEngineError, match="template validation failed"):
        dispatch_stream("marks", {"input_pdf_b64": _b64(simple_pdf)})


def test_impose_dispatch_rejects_missing_plan(simple_pdf: bytes) -> None:
    with pytest.raises(StreamEngineError, match="plan validation failed"):
        dispatch_stream("impose", {"input_pdf_b64": _b64(simple_pdf)})


def test_trap_dispatch_rejects_missing_policy(simple_pdf: bytes) -> None:
    with pytest.raises(StreamEngineError, match="policy validation failed"):
        dispatch_stream("trap", {"input_pdf_b64": _b64(simple_pdf)})


def test_soft_proof_dispatch_rejects_missing_icc(simple_pdf: bytes) -> None:
    with pytest.raises(StreamEngineError, match="source_icc_b64 is missing"):
        dispatch_stream(
            "soft_proof",
            {"input_pdf_b64": _b64(simple_pdf)},
        )


def test_soft_proof_dispatch_returns_pdf(simple_pdf: bytes) -> None:
    """Soft-proof's engine is a passthrough today; pinning the
    happy path here exercises the only dispatcher whose engine
    operates on three byte fields rather than a single PDF."""
    result = dispatch_stream(
        "soft_proof",
        {
            "input_pdf_b64": _b64(simple_pdf),
            "source_icc_b64": _b64(b"src-icc"),
            "destination_icc_b64": _b64(b"dst-icc"),
            "options": {},
        },
    )
    assert result.output_bytes.startswith(b"%PDF")
    assert result.metadata.producer == "soft_proof"


def test_unreachable_schema_version_branch_raises() -> None:
    """Defense-in-depth: ``_producer_schema_version`` raises if
    called with a producer outside the typed enum."""
    from compile_pdf.stream.engine import _producer_schema_version

    with pytest.raises(StreamEngineError, match="unknown producer"):
        _producer_schema_version("nope")  # type: ignore[arg-type]
