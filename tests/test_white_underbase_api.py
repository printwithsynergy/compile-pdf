"""Integration tests for POST /v1/white-underbase/apply (Wave 3 PR-7 C2).

Pins the wire contract that artwork-pdf editor will read once the
C2 UI lands: request validation, response shape, determinism,
sensitivity to the policy envelope.
"""

from __future__ import annotations

import base64
import os

import pytest
from fastapi.testclient import TestClient

# The white_underbase router mounts when COMPILE_PRODUCER includes
# it or is "all" — pin to "all" so the test client always sees it.
os.environ.setdefault("COMPILE_PRODUCER", "all")

from compile_pdf.api.main import app  # noqa: E402 — env tweaked above


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def test_apply_returns_response_envelope(client: TestClient, simple_pdf: bytes) -> None:
    response = client.post(
        "/v1/white-underbase/apply",
        json={"input_pdf_b64": _b64(simple_pdf)},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert "output_pdf_b64" in body
    assert len(body["pdf_sha256"]) == 64
    assert len(body["input_sha256"]) == 64
    assert len(body["policy_sha256"]) == 64
    assert len(body["cache_key"]) == 64
    assert body["cache_hit"] is False
    assert body["summary"]["separation_name"] == "White"
    assert body["summary"]["plate_use"] == "white"
    assert body["summary"]["strategy_applied"] == "auto"
    assert body["summary"]["pages_processed"] == 1
    assert body["schema_version"] == "1.0.0"
    assert body["compile_version"]


def test_apply_honours_custom_policy(client: TestClient, simple_pdf: bytes) -> None:
    response = client.post(
        "/v1/white-underbase/apply",
        json={
            "input_pdf_b64": _b64(simple_pdf),
            "policy": {
                "separation_name": "Underbase",
                "plate_use": "underbase",
                "strategy": "union",
                "knockout_threshold_pct": 10.0,
                "choke_pt": -0.3,
            },
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["summary"]["separation_name"] == "Underbase"
    assert body["summary"]["plate_use"] == "underbase"
    assert body["summary"]["strategy_applied"] == "union"


def test_apply_rejects_empty_base64(client: TestClient) -> None:
    response = client.post(
        "/v1/white-underbase/apply",
        json={"input_pdf_b64": ""},
    )
    # Pydantic catches min_length=1 at request validation (422).
    assert response.status_code == 422


def test_apply_rejects_malformed_base64(client: TestClient) -> None:
    response = client.post(
        "/v1/white-underbase/apply",
        json={"input_pdf_b64": "@@not-base64@@"},
    )
    assert response.status_code == 400
    assert "base64" in response.text


def test_apply_rejects_non_pdf_input(client: TestClient) -> None:
    response = client.post(
        "/v1/white-underbase/apply",
        json={"input_pdf_b64": _b64(b"NOT-A-PDF")},
    )
    assert response.status_code == 422
    assert "engine rejected" in response.text


def test_apply_rejects_out_of_range_page_indices(client: TestClient, three_page_pdf: bytes) -> None:
    response = client.post(
        "/v1/white-underbase/apply",
        json={
            "input_pdf_b64": _b64(three_page_pdf),
            "policy": {"page_indices": [0, 99]},
        },
    )
    assert response.status_code == 422
    assert "out-of-range" in response.text


def test_apply_is_deterministic(client: TestClient, simple_pdf: bytes) -> None:
    """Same request → same cache_key, same pdf_sha256."""
    payload = {"input_pdf_b64": _b64(simple_pdf)}
    runs = [client.post("/v1/white-underbase/apply", json=payload) for _ in range(3)]
    first = runs[0].json()
    for run in runs[1:]:
        body = run.json()
        assert body["cache_key"] == first["cache_key"]
        assert body["pdf_sha256"] == first["pdf_sha256"]
        assert body["policy_sha256"] == first["policy_sha256"]


def test_apply_policy_options_affect_cache_key(client: TestClient, simple_pdf: bytes) -> None:
    """Different policies on the same input → different cache keys."""
    base_payload = {"input_pdf_b64": _b64(simple_pdf)}
    custom_payload = {
        **base_payload,
        "policy": {"strategy": "union", "knockout_threshold_pct": 50.0},
    }
    a = client.post("/v1/white-underbase/apply", json=base_payload).json()
    b = client.post("/v1/white-underbase/apply", json=custom_payload).json()
    assert a["cache_key"] != b["cache_key"]
    assert a["policy_sha256"] != b["policy_sha256"]
