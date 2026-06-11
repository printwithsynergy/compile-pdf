"""Surface test for the Wave 3 PR-7 white / underbase producer.

Mirrors :mod:`tests.test_soft_proof_surface` — confirms the module
exposes its public router via the package barrel so the API mount
in :mod:`compile_pdf.api.main` doesn't need internal imports.
"""

from __future__ import annotations


def test_module_exposes_router() -> None:
    import compile_pdf_white_underbase as white_underbase

    assert hasattr(white_underbase, "router")
    assert "router" in white_underbase.__all__


def test_module_exposes_schema_version() -> None:
    import compile_pdf_white_underbase as white_underbase

    assert hasattr(white_underbase, "WHITE_UNDERBASE_SCHEMA_VERSION")
    assert "WHITE_UNDERBASE_SCHEMA_VERSION" in white_underbase.__all__
    assert white_underbase.WHITE_UNDERBASE_SCHEMA_VERSION == "1.0.0"


def test_schema_version_registered_in_contract_map() -> None:
    """``white_underbase`` must appear in PRODUCER_SCHEMA_VERSIONS
    so ops tooling and ``GET /v1/contract`` surface it alongside
    the other producers."""
    from compile_pdf.version import (
        PRODUCER_SCHEMA_VERSIONS,
        WHITE_UNDERBASE_SCHEMA_VERSION,
    )

    assert PRODUCER_SCHEMA_VERSIONS.get("white_underbase") == WHITE_UNDERBASE_SCHEMA_VERSION
