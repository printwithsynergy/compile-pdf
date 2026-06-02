"""Surface test for the Wave 2 PR-G soft-proof producer.

Mirrors :mod:`tests.test_trap_surface` — confirms the module
exposes its public router via the package barrel so the API mount
in :mod:`compile_pdf.api.main` doesn't need internal imports.

The soft-proof scaffold doesn't re-export codex_pdf surfaces yet
(the engine is a passthrough until the LCMS roundtrip lands in a
follow-up); the surface contract today is purely the producer
barrel ``router`` + a stable ``SOFT_PROOF_SCHEMA_VERSION``.
"""

from __future__ import annotations


def test_module_exposes_router() -> None:
    from compile_pdf import soft_proof

    assert hasattr(soft_proof, "router")
    assert "router" in soft_proof.__all__


def test_schema_version_is_semver() -> None:
    from compile_pdf.version import SOFT_PROOF_SCHEMA_VERSION

    parts = SOFT_PROOF_SCHEMA_VERSION.split(".")
    assert len(parts) == 3, "SOFT_PROOF_SCHEMA_VERSION must be major.minor.patch"
    assert all(p.isdigit() for p in parts), "SOFT_PROOF_SCHEMA_VERSION parts must be numeric"


def test_producer_schema_versions_includes_soft_proof() -> None:
    """``GET /v1/contract`` reads PRODUCER_SCHEMA_VERSIONS — confirm
    soft_proof is wired into the aggregate map."""
    from compile_pdf.version import (
        PRODUCER_SCHEMA_VERSIONS,
        SOFT_PROOF_SCHEMA_VERSION,
    )

    assert "soft_proof" in PRODUCER_SCHEMA_VERSIONS
    assert PRODUCER_SCHEMA_VERSIONS["soft_proof"] == SOFT_PROOF_SCHEMA_VERSION
