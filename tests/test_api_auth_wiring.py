"""Auth wiring — every producer route honors COMPILE_AUTH_MODE.

The healthz / contract / version / metrics routes stay open by design;
producer + cjd + lineage routes require auth when ``bearer`` /
``api-key`` / ``internal`` / ``basic`` is configured.
"""

from __future__ import annotations

import base64

import pytest
from fastapi.testclient import TestClient

from compile_pdf.api.main import app


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


@pytest.fixture
def client_with_bearer(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("COMPILE_AUTH_MODE", "bearer")
    monkeypatch.setenv("COMPILE_BEARER_TOKEN", "s3cret")
    return TestClient(app)


def test_healthz_open_under_bearer(client_with_bearer: TestClient) -> None:
    response = client_with_bearer.get("/v1/healthz")
    assert response.status_code == 200


def test_contract_open_under_bearer(client_with_bearer: TestClient) -> None:
    response = client_with_bearer.get("/v1/contract")
    assert response.status_code == 200


def test_version_open_under_bearer(client_with_bearer: TestClient) -> None:
    response = client_with_bearer.get("/v1/version")
    assert response.status_code == 200


def test_metrics_open_under_bearer(client_with_bearer: TestClient) -> None:
    response = client_with_bearer.get("/metrics")
    assert response.status_code == 200


def test_rewrite_apply_rejects_missing_auth(
    simple_pdf: bytes, client_with_bearer: TestClient
) -> None:
    response = client_with_bearer.post(
        "/v1/rewrite/apply",
        json={"input_pdf_b64": _b64(simple_pdf), "plan": {"ops": []}},
    )
    assert response.status_code == 401


def test_rewrite_apply_accepts_valid_bearer(
    simple_pdf: bytes, client_with_bearer: TestClient
) -> None:
    response = client_with_bearer.post(
        "/v1/rewrite/apply",
        json={"input_pdf_b64": _b64(simple_pdf), "plan": {"ops": []}},
        headers={"Authorization": "Bearer s3cret"},
    )
    assert response.status_code == 200


def test_marks_apply_rejects_missing_auth(
    printer_pdf: bytes, client_with_bearer: TestClient
) -> None:
    response = client_with_bearer.post(
        "/v1/marks/apply",
        json={"input_pdf_b64": _b64(printer_pdf), "template": {"marks": []}},
    )
    assert response.status_code == 401


def test_impose_apply_rejects_missing_auth(
    four_page_content_pdf: bytes, client_with_bearer: TestClient
) -> None:
    response = client_with_bearer.post(
        "/v1/impose/apply",
        json={
            "input_pdf_b64": _b64(four_page_content_pdf),
            "plan": {
                "sheet": {"width_pt": 612, "height_pt": 792},
                "cell": {"width_pt": 612, "height_pt": 792},
            },
        },
    )
    assert response.status_code == 401


def test_trap_apply_rejects_missing_auth(simple_pdf: bytes, client_with_bearer: TestClient) -> None:
    response = client_with_bearer.post(
        "/v1/trap/apply",
        json={"input_pdf_b64": _b64(simple_pdf), "policy": {}},
    )
    assert response.status_code == 401


def test_cjd_apply_rejects_missing_auth(simple_pdf: bytes, client_with_bearer: TestClient) -> None:
    response = client_with_bearer.post(
        "/v1/cjd/apply",
        json={
            "input_pdf_b64": _b64(simple_pdf),
            "steps": [{"type": "rewrite", "plan": {"ops": []}}],
        },
    )
    assert response.status_code == 401


def test_lineage_get_rejects_missing_auth(client_with_bearer: TestClient) -> None:
    response = client_with_bearer.get("/v1/lineage/anything")
    assert response.status_code == 401


def test_api_key_mode_accepts_header(monkeypatch: pytest.MonkeyPatch, simple_pdf: bytes) -> None:
    monkeypatch.setenv("COMPILE_AUTH_MODE", "api-key")
    monkeypatch.setenv("COMPILE_API_KEY", "k3y")
    client = TestClient(app)
    response = client.post(
        "/v1/rewrite/apply",
        json={"input_pdf_b64": _b64(simple_pdf), "plan": {"ops": []}},
        headers={"X-Compile-Key": "k3y"},
    )
    assert response.status_code == 200


def test_api_key_mode_rejects_bad_key(monkeypatch: pytest.MonkeyPatch, simple_pdf: bytes) -> None:
    monkeypatch.setenv("COMPILE_AUTH_MODE", "api-key")
    monkeypatch.setenv("COMPILE_API_KEY", "k3y")
    client = TestClient(app)
    response = client.post(
        "/v1/rewrite/apply",
        json={"input_pdf_b64": _b64(simple_pdf), "plan": {"ops": []}},
        headers={"X-Compile-Key": "wrong"},
    )
    assert response.status_code == 401


def test_default_none_mode_does_not_block(simple_pdf: bytes) -> None:
    """With COMPILE_AUTH_MODE unset, requests pass through."""
    client = TestClient(app)
    response = client.post(
        "/v1/rewrite/apply",
        json={"input_pdf_b64": _b64(simple_pdf), "plan": {"ops": []}},
    )
    assert response.status_code == 200
