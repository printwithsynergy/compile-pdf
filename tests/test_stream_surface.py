"""Surface test for the Wave 3 PR-6 stream producer.

Mirrors :mod:`tests.test_soft_proof_surface` — confirms the module
exposes its public router via the package barrel so the API mount
in :mod:`compile_pdf.api.main` doesn't need internal imports.
"""

from __future__ import annotations


def test_module_exposes_router() -> None:
    from compile_pdf import stream

    assert hasattr(stream, "router")
    assert "router" in stream.__all__


def test_module_exposes_schema_version() -> None:
    from compile_pdf import stream

    assert hasattr(stream, "STREAM_SCHEMA_VERSION")
    assert "STREAM_SCHEMA_VERSION" in stream.__all__
    # Wave 3 ships 1.0.0; bumps land in subsequent waves when the
    # request envelope or header set changes.
    assert stream.STREAM_SCHEMA_VERSION == "1.0.0"


def test_schema_version_registered_in_contract_map() -> None:
    """``stream`` must appear in PRODUCER_SCHEMA_VERSIONS so ops
    tooling and ``GET /v1/contract`` surface it alongside the
    other producers."""
    from compile_pdf.version import PRODUCER_SCHEMA_VERSIONS, STREAM_SCHEMA_VERSION

    assert PRODUCER_SCHEMA_VERSIONS.get("stream") == STREAM_SCHEMA_VERSION
