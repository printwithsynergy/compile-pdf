"""Integration tests for POST /v1/soft-proof/apply (Wave 2 PR-G).

These tests pin the wire contract that artwork-pdf editor's PR-6
C5 overlay reads. The engine itself is a passthrough today (real
LCMS roundtrip lands in a Wave 3 follow-up) so the assertions
focus on:

- Request validation (base64 sanity, empty-input rejection).
- Response shape (every field on :class:`SoftProofApplyResponse`).
- Determinism — same input → same cache key, same delta_e summary.
- Sensitivity to the options envelope (toggling
  ``delta_e_formula`` changes the cache key + summary).
"""

from __future__ import annotations

import base64
import os

import pytest
from fastapi.testclient import TestClient

# Ensure the soft-proof router is mounted even when COMPILE_PRODUCER
# is its default (un-set → "rewrite"). The test client construction
# below reads this env var via the module's _resolve_active_producer.
os.environ.setdefault("COMPILE_PRODUCER", "all")

from compile_pdf.api.main import app  # noqa: E402 — env tweaked above


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture()
def small_pdf() -> bytes:
    """A minimal PDF byte stream good enough for the passthrough engine.

    The engine doesn't parse the input; it only checks that the
    bytes start with ``%PDF`` so the verify hook passes. A real
    PDF would do too, but inlining one bloats the fixture.
    """
    return b"%PDF-1.4\n%%EOF\n"


@pytest.fixture()
def fake_icc_a() -> bytes:
    """Stand-in source ICC profile bytes. The engine hashes them,
    so any deterministic blob is fine for contract testing."""
    return b"fake-source-icc-profile-bytes-for-tests"


@pytest.fixture()
def fake_icc_b() -> bytes:
    """Stand-in destination ICC profile bytes — distinct from A."""
    return b"fake-destination-icc-profile-bytes-distinct"


def test_soft_proof_apply_round_trips(
    client: TestClient, small_pdf: bytes, fake_icc_a: bytes, fake_icc_b: bytes
) -> None:
    response = client.post(
        "/v1/soft-proof/apply",
        json={
            "input_pdf_b64": _b64(small_pdf),
            "source_icc_b64": _b64(fake_icc_a),
            "destination_icc_b64": _b64(fake_icc_b),
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    # Response shape — every field on SoftProofApplyResponse.
    for key in (
        "output_pdf_b64",
        "pdf_sha256",
        "input_sha256",
        "options_sha256",
        "source_icc_sha256",
        "destination_icc_sha256",
        "cache_key",
        "cache_hit",
        "delta_e",
        "schema_version",
        "compile_version",
    ):
        assert key in body, f"missing {key} in response"
    assert body["schema_version"] == "1.0.0"
    assert body["delta_e"]["max"] >= body["delta_e"]["avg"]
    assert body["delta_e"]["max"] >= body["delta_e"]["p95"]


def test_soft_proof_apply_rejects_invalid_base64(client: TestClient) -> None:
    response = client.post(
        "/v1/soft-proof/apply",
        json={
            "input_pdf_b64": "not-valid!!!",
            "source_icc_b64": _b64(b"a"),
            "destination_icc_b64": _b64(b"b"),
        },
    )
    assert response.status_code == 400
    assert "input_pdf_b64" in response.json()["detail"]


def test_soft_proof_apply_rejects_empty_icc(
    client: TestClient, small_pdf: bytes
) -> None:
    response = client.post(
        "/v1/soft-proof/apply",
        json={
            "input_pdf_b64": _b64(small_pdf),
            "source_icc_b64": _b64(b""),
            "destination_icc_b64": _b64(b"dst"),
        },
    )
    # Pydantic min_length=1 catches the empty source field first
    # at the request-validation layer (422), so we accept either
    # 400 (our decoder) or 422 (pydantic) — both reject the bad
    # request, just at different layers.
    assert response.status_code in (400, 422)


def test_soft_proof_apply_is_deterministic(
    client: TestClient, small_pdf: bytes, fake_icc_a: bytes, fake_icc_b: bytes
) -> None:
    payload = {
        "input_pdf_b64": _b64(small_pdf),
        "source_icc_b64": _b64(fake_icc_a),
        "destination_icc_b64": _b64(fake_icc_b),
    }
    first = client.post("/v1/soft-proof/apply", json=payload).json()
    second = client.post("/v1/soft-proof/apply", json=payload).json()
    assert first["cache_key"] == second["cache_key"]
    assert first["pdf_sha256"] == second["pdf_sha256"]
    assert first["delta_e"] == second["delta_e"]


def test_options_formula_affects_summary_and_cache_key(
    client: TestClient, small_pdf: bytes, fake_icc_a: bytes, fake_icc_b: bytes
) -> None:
    base_payload = {
        "input_pdf_b64": _b64(small_pdf),
        "source_icc_b64": _b64(fake_icc_a),
        "destination_icc_b64": _b64(fake_icc_b),
    }
    cie76 = client.post(
        "/v1/soft-proof/apply",
        json={**base_payload, "options": {"delta_e_formula": "cie76"}},
    ).json()
    ciede2000 = client.post(
        "/v1/soft-proof/apply",
        json={**base_payload, "options": {"delta_e_formula": "ciede2000"}},
    ).json()
    # Cache key must change when the formula changes (otherwise a
    # cached result for one formula would shadow another).
    assert cie76["cache_key"] != ciede2000["cache_key"]
    # And the avg should differ too because the engine weighs the
    # formula into the ΔE summary.
    assert cie76["delta_e"]["avg"] != ciede2000["delta_e"]["avg"]
