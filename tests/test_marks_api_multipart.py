"""Multipart marks API — POST /v1/marks/apply-multipart with external file uploads."""

from __future__ import annotations

import base64
import io
import json

import pikepdf
import pytest
from fastapi.testclient import TestClient
from pikepdf import Array, Dictionary, Name
from PIL import Image

from compile_pdf.api.main import app


def _make_external_pdf() -> bytes:
    pdf = pikepdf.new()
    pdf.pages.append(
        pikepdf.Page(
            pdf.make_indirect(
                Dictionary(
                    Type=Name.Page,
                    MediaBox=Array([0, 0, 72, 72]),
                    Resources=Dictionary(),
                    Contents=pdf.make_stream(b"q 0 0 72 72 re S Q"),
                )
            )
        )
    )
    buf = io.BytesIO()
    pdf.save(buf, deterministic_id=True, linearize=False)
    pdf.close()
    return buf.getvalue()


def _make_external_png() -> bytes:
    img = Image.new("RGB", (8, 8), color=(64, 128, 192))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_multipart_round_trips_pdf_external(printer_pdf: bytes) -> None:
    client = TestClient(app)
    template = {
        "marks": [
            {"type": "external", "file": "watermark.pdf", "anchor": "trim_center"},
        ]
    }
    response = client.post(
        "/v1/marks/apply-multipart",
        files=[
            ("input_pdf", ("in.pdf", printer_pdf, "application/pdf")),
            ("externals", ("watermark.pdf", _make_external_pdf(), "application/pdf")),
        ],
        data={"template": json.dumps(template)},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["marks_applied"] == 1
    out = pikepdf.open(io.BytesIO(base64.b64decode(body["output_pdf_b64"])))
    try:
        page = out.pages[0]
        assert Name.XObject in page.obj[Name.Resources]
    finally:
        out.close()


def test_multipart_round_trips_png_external(printer_pdf: bytes) -> None:
    client = TestClient(app)
    template = {
        "marks": [
            {"type": "external", "file": "logo.png", "anchor": "trim_center", "scale": 2.0},
        ]
    }
    response = client.post(
        "/v1/marks/apply-multipart",
        files=[
            ("input_pdf", ("in.pdf", printer_pdf, "application/pdf")),
            ("externals", ("logo.png", _make_external_png(), "image/png")),
        ],
        data={"template": json.dumps(template)},
    )
    assert response.status_code == 200, response.text


def test_multipart_rejects_template_with_missing_external(printer_pdf: bytes) -> None:
    client = TestClient(app)
    template = {
        "marks": [
            {"type": "external", "file": "missing.pdf", "anchor": "trim_center"},
        ]
    }
    response = client.post(
        "/v1/marks/apply-multipart",
        files=[
            ("input_pdf", ("in.pdf", printer_pdf, "application/pdf")),
        ],
        data={"template": json.dumps(template)},
    )
    assert response.status_code == 422
    assert "external_files_missing" in response.json()["detail"]


def test_multipart_rejects_invalid_template_json(printer_pdf: bytes) -> None:
    client = TestClient(app)
    response = client.post(
        "/v1/marks/apply-multipart",
        files=[
            ("input_pdf", ("in.pdf", printer_pdf, "application/pdf")),
        ],
        data={"template": "not-json"},
    )
    assert response.status_code == 422
    assert "template_invalid" in response.json()["detail"]


def test_multipart_rejects_template_with_unknown_mark_type(printer_pdf: bytes) -> None:
    client = TestClient(app)
    response = client.post(
        "/v1/marks/apply-multipart",
        files=[
            ("input_pdf", ("in.pdf", printer_pdf, "application/pdf")),
        ],
        data={"template": json.dumps({"marks": [{"type": "wat"}]})},
    )
    assert response.status_code == 422


def test_multipart_rejects_empty_input() -> None:
    client = TestClient(app)
    response = client.post(
        "/v1/marks/apply-multipart",
        files=[("input_pdf", ("in.pdf", b"", "application/pdf"))],
        data={"template": json.dumps({"marks": []})},
    )
    assert response.status_code == 400


def test_multipart_handles_inline_marks_only(printer_pdf: bytes) -> None:
    """Templates without external marks still work via the multipart route."""
    client = TestClient(app)
    template = {"marks": [{"type": "register", "anchor": "trim_corners"}]}
    response = client.post(
        "/v1/marks/apply-multipart",
        files=[("input_pdf", ("in.pdf", printer_pdf, "application/pdf"))],
        data={"template": json.dumps(template)},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["marks_applied"] == 4  # broadcast trim_corners → 4 stamps


def test_contract_endpoint_lists_apply_multipart() -> None:
    client = TestClient(app)
    response = client.get("/v1/contract")
    endpoints = response.json()["endpoints"]
    assert any("/v1/marks/apply-multipart" in e for e in endpoints)


# Module-level helper used by tests above; pytest needs it to be a real
# importable object. Keep at the bottom for readability.
_ = pytest  # silence "imported but unused" if a future test removes pytest usage
