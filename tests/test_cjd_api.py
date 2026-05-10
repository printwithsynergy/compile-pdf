"""Integration tests for /v1/cjd/apply + /v1/lineage/{id}."""

from __future__ import annotations

import base64

import pytest
from fastapi.testclient import TestClient

from compile_pdf.api.main import app
from compile_pdf.lineage.store import reset_default_store


@pytest.fixture(autouse=True)
def _clear_lineage_store():
    reset_default_store()
    yield
    reset_default_store()


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def test_cjd_apply_round_trips(printer_pdf: bytes) -> None:
    client = TestClient(app)
    response = client.post(
        "/v1/cjd/apply",
        json={
            "input_pdf_b64": _b64(printer_pdf),
            "steps": [
                {
                    "type": "rewrite",
                    "plan": {"ops": [{"op": "metadata_set", "key": "Title", "value": "PWS Job"}]},
                },
                {
                    "type": "marks",
                    "template": {"marks": [{"type": "register", "anchor": "trim_corners"}]},
                },
            ],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["lineage_id"]
    assert len(body["steps"]) == 2
    assert body["steps"][0]["producer"] == "rewrite"


def test_cjd_apply_with_trap_returns_trap_diff(simple_pdf: bytes) -> None:
    client = TestClient(app)
    response = client.post(
        "/v1/cjd/apply",
        json={
            "input_pdf_b64": _b64(simple_pdf),
            "steps": [
                {
                    "type": "trap",
                    "policy": {
                        "trap_zones": [
                            {
                                "page_index": 0,
                                "rect_pt": [50, 50, 100, 100],
                                "from_ink": "Y",
                                "to_ink": "K",
                            }
                        ]
                    },
                }
            ],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["trap_diff"] is not None
    assert body["trap_diff"]["operations"][0]["from_ink"] == "Y"


def test_cjd_apply_strict_order_violation_returns_422(printer_pdf: bytes) -> None:
    client = TestClient(app)
    response = client.post(
        "/v1/cjd/apply",
        json={
            "input_pdf_b64": _b64(printer_pdf),
            "strict_order": True,
            "steps": [
                {"type": "marks", "template": {"marks": []}},
                {"type": "rewrite", "plan": {"ops": []}},
            ],
        },
    )
    assert response.status_code == 422


def test_cjd_apply_rejects_invalid_base64() -> None:
    client = TestClient(app)
    response = client.post(
        "/v1/cjd/apply",
        json={
            "input_pdf_b64": "not-valid-base64!!!",
            "steps": [{"type": "rewrite", "plan": {"ops": []}}],
        },
    )
    assert response.status_code == 400


def test_cjd_apply_rejects_unknown_step_type(printer_pdf: bytes) -> None:
    client = TestClient(app)
    response = client.post(
        "/v1/cjd/apply",
        json={
            "input_pdf_b64": _b64(printer_pdf),
            "steps": [{"type": "bogus"}],
        },
    )
    assert response.status_code == 422


def test_lineage_get_returns_chain_after_cjd(printer_pdf: bytes) -> None:
    client = TestClient(app)
    cjd_response = client.post(
        "/v1/cjd/apply",
        json={
            "input_pdf_b64": _b64(printer_pdf),
            "steps": [
                {"type": "rewrite", "plan": {"ops": []}},
                {"type": "marks", "template": {"marks": []}},
            ],
        },
    )
    lineage_id = cjd_response.json()["lineage_id"]

    response = client.get(f"/v1/lineage/{lineage_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["lineage_id"] == lineage_id
    assert len(body["steps"]) == 2


def test_lineage_get_404_for_unknown_id() -> None:
    client = TestClient(app)
    response = client.get("/v1/lineage/does-not-exist")
    assert response.status_code == 404


def test_contract_endpoint_lists_cjd_and_lineage() -> None:
    client = TestClient(app)
    response = client.get("/v1/contract")
    assert response.status_code == 200
    endpoints = response.json()["endpoints"]
    assert any("/v1/cjd/apply" in e for e in endpoints)
    assert any("/v1/lineage/" in e for e in endpoints)
