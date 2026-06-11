"""POST /v1/cjd/apply-xml — XML envelope variant of /v1/cjd/apply."""

from __future__ import annotations

import base64

import pytest
from compile_pdf_core.lineage.store import reset_default_store
from fastapi.testclient import TestClient

from compile_pdf.api.main import app
from compile_pdf.cjd.schema import CjdJob
from compile_pdf.cjd.xml import render_cjd_xml


@pytest.fixture(autouse=True)
def _clear_lineage_store():
    reset_default_store()
    yield
    reset_default_store()


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _xml(printer_pdf: bytes) -> bytes:
    job = CjdJob.model_validate(
        {
            "input_pdf_b64": _b64(printer_pdf),
            "steps": [{"type": "rewrite", "plan": {"ops": []}}],
        }
    )
    return render_cjd_xml(job)


def test_xml_endpoint_round_trips(printer_pdf: bytes) -> None:
    client = TestClient(app)
    response = client.post(
        "/v1/cjd/apply-xml",
        content=_xml(printer_pdf),
        headers={"Content-Type": "application/xml"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["lineage_id"]
    assert body["steps"][0]["producer"] == "rewrite"


def test_xml_endpoint_with_trap_returns_trap_diff(simple_pdf: bytes) -> None:
    job = CjdJob.model_validate(
        {
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
        }
    )
    client = TestClient(app)
    response = client.post(
        "/v1/cjd/apply-xml",
        content=render_cjd_xml(job),
        headers={"Content-Type": "application/xml"},
    )
    assert response.status_code == 200
    assert response.json()["trap_diff"]["operations"][0]["from_ink"] == "Y"


def test_xml_endpoint_rejects_empty_body() -> None:
    client = TestClient(app)
    response = client.post("/v1/cjd/apply-xml", content=b"")
    assert response.status_code == 400


def test_xml_endpoint_rejects_malformed_xml() -> None:
    client = TestClient(app)
    response = client.post(
        "/v1/cjd/apply-xml",
        content=b"<cjd><unclosed>",
        headers={"Content-Type": "application/xml"},
    )
    assert response.status_code == 422
    assert "CJD XML rejected" in response.json()["detail"]


def test_xml_endpoint_rejects_unknown_step_type(printer_pdf: bytes) -> None:
    body = (
        b'<?xml version="1.0"?>'
        b"<cjd>"
        b"<input_pdf_b64>" + _b64(printer_pdf).encode("ascii") + b"</input_pdf_b64>"
        b"<steps><lasso><plan>{}</plan></lasso></steps>"
        b"</cjd>"
    )
    client = TestClient(app)
    response = client.post("/v1/cjd/apply-xml", content=body)
    assert response.status_code == 422


def test_lineage_get_works_after_xml_apply(printer_pdf: bytes) -> None:
    client = TestClient(app)
    xml_response = client.post("/v1/cjd/apply-xml", content=_xml(printer_pdf))
    lineage_id = xml_response.json()["lineage_id"]

    response = client.get(f"/v1/lineage/{lineage_id}")
    assert response.status_code == 200
    assert response.json()["lineage_id"] == lineage_id


def test_contract_endpoint_lists_apply_xml() -> None:
    client = TestClient(app)
    endpoints = client.get("/v1/contract").json()["endpoints"]
    assert any("/v1/cjd/apply-xml" in e for e in endpoints)
