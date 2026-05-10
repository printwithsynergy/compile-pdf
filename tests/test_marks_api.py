"""Integration tests for POST /v1/marks/apply."""

from __future__ import annotations

import base64
import io

import pikepdf
from fastapi.testclient import TestClient
from pikepdf import Name

from compile_pdf.api.main import app


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def test_marks_apply_round_trips(printer_pdf: bytes) -> None:
    client = TestClient(app)
    response = client.post(
        "/v1/marks/apply",
        json={
            "input_pdf_b64": _b64(printer_pdf),
            "template": {
                "marks": [
                    {"type": "register", "anchor": "trim_corners"},
                    {"type": "color_bar", "anchor": "slug_top", "inks": ["C", "M", "Y", "K"]},
                ]
            },
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["marks_applied"] >= 4  # broadcast + color_bar
    assert body["pdf_sha256"]
    assert body["cache_key"]
    assert body["template_sha256"]
    assert body["compile_version"]

    output = pikepdf.open(io.BytesIO(base64.b64decode(body["output_pdf_b64"])))
    try:
        contents = output.pages[0].obj[Name.Contents]
        assert isinstance(contents, pikepdf.Array)
        assert len(contents) == 2  # original + overlay
    finally:
        output.close()


def test_marks_apply_rejects_invalid_base64() -> None:
    client = TestClient(app)
    response = client.post(
        "/v1/marks/apply",
        json={"input_pdf_b64": "not-valid-base64!!!", "template": {"marks": []}},
    )
    assert response.status_code == 400


def test_marks_apply_rejects_empty_input() -> None:
    client = TestClient(app)
    response = client.post(
        "/v1/marks/apply",
        json={"input_pdf_b64": _b64(b""), "template": {"marks": []}},
    )
    assert response.status_code == 422


def test_marks_apply_rejects_external_marks_inline(printer_pdf: bytes) -> None:
    client = TestClient(app)
    response = client.post(
        "/v1/marks/apply",
        json={
            "input_pdf_b64": _b64(printer_pdf),
            "template": {
                "marks": [{"type": "external", "file": "watermark.pdf", "anchor": "trim_center"}]
            },
        },
    )
    assert response.status_code == 422
    assert "external_marks_not_supported_inline" in response.json()["detail"]


def test_marks_apply_rejects_unknown_type(printer_pdf: bytes) -> None:
    client = TestClient(app)
    response = client.post(
        "/v1/marks/apply",
        json={
            "input_pdf_b64": _b64(printer_pdf),
            "template": {"marks": [{"type": "wat"}]},
        },
    )
    assert response.status_code == 422


def test_contract_endpoint_lists_marks() -> None:
    client = TestClient(app)
    response = client.get("/v1/contract")
    assert response.status_code == 200
    endpoints = response.json()["endpoints"]
    assert any("/v1/marks/apply" in e for e in endpoints)


def test_same_input_same_template_same_cache_key(printer_pdf: bytes) -> None:
    client = TestClient(app)
    payload = {
        "input_pdf_b64": _b64(printer_pdf),
        "template": {"marks": [{"type": "proof_slug"}]},
    }
    a = client.post("/v1/marks/apply", json=payload).json()
    b = client.post("/v1/marks/apply", json=payload).json()
    assert a["cache_key"] == b["cache_key"]
    assert a["pdf_sha256"] == b["pdf_sha256"]
