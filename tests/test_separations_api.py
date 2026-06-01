# SPDX-License-Identifier: AGPL-3.0-or-later
"""Integration tests for the /v1/separations/* endpoints.

The router wraps :mod:`compile_pdf.separations.extract`; tests
assert request validation, the wire shape, and a couple of
behavioural cases against fixture PDFs synthesised in-test.
"""

from __future__ import annotations

import base64
import io

import pikepdf
from fastapi.testclient import TestClient
from pikepdf import Name

from compile_pdf.api.main import app

CLIENT = TestClient(app)


def _empty_pdf() -> bytes:
    """A minimal one-page PDF with no separations."""
    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=(612, 792))
    buf = io.BytesIO()
    pdf.save(buf)
    return buf.getvalue()


def _spot_pdf(spot_names: list[str], pages: int = 1) -> bytes:
    """A PDF with ``pages`` pages, each declaring every name in
    ``spot_names`` as a /Separation color space in its resources."""
    pdf = pikepdf.new()
    for _ in range(pages):
        page = pdf.add_blank_page(page_size=(612, 792))
        cs_dict = pikepdf.Dictionary()
        for i, name in enumerate(spot_names):
            sep_array = pikepdf.Array([Name.Separation, Name(f"/{name}"), Name.DeviceCMYK])
            cs_dict[f"/Cs{i}"] = sep_array
        resources = pikepdf.Dictionary({"/ColorSpace": cs_dict})
        page.Resources = resources
    buf = io.BytesIO()
    pdf.save(buf)
    return buf.getvalue()


def test_list_empty_pdf_returns_no_separations() -> None:
    body = {"input_pdf_b64": base64.b64encode(_empty_pdf()).decode()}
    response = CLIENT.post("/v1/separations/list", json=body)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload == {"separations": [], "total": 0}


def test_list_pdf_with_spots_returns_each_ink_once() -> None:
    body = {"input_pdf_b64": base64.b64encode(_spot_pdf(["PANTONE 185 C", "Silver"])).decode()}
    response = CLIENT.post("/v1/separations/list", json=body)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total"] == 2
    names = {s["name"] for s in payload["separations"]}
    assert names == {"PANTONE 185 C", "Silver"}
    for entry in payload["separations"]:
        assert entry["color_space"] == "Separation"
        assert entry["occurs_on_pages"] == [0]


def test_list_aggregates_across_pages() -> None:
    body = {
        "input_pdf_b64": base64.b64encode(_spot_pdf(["PANTONE 185 C"], pages=3)).decode(),
    }
    response = CLIENT.post("/v1/separations/list", json=body)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total"] == 1
    [entry] = payload["separations"]
    assert entry["name"] == "PANTONE 185 C"
    assert entry["occurs_on_pages"] == [0, 1, 2]


def test_list_rejects_invalid_base64() -> None:
    response = CLIENT.post("/v1/separations/list", json={"input_pdf_b64": "!!!not-base64!!!"})
    assert response.status_code == 400
    assert "valid base64" in response.json()["detail"]


def test_list_rejects_missing_field() -> None:
    response = CLIENT.post("/v1/separations/list", json={})
    assert response.status_code == 422  # FastAPI/Pydantic validation


def test_list_rejects_extra_field() -> None:
    body = {
        "input_pdf_b64": base64.b64encode(_empty_pdf()).decode(),
        "unexpected": "value",
    }
    response = CLIENT.post("/v1/separations/list", json=body)
    # `extra: forbid` on the request model
    assert response.status_code == 422


def test_response_shape_pins_extras_forbid() -> None:
    """Belt-and-braces — confirm the response model rejects extras
    so future fields land via additive PRs, not silent additions."""
    body = {"input_pdf_b64": base64.b64encode(_spot_pdf(["X"])).decode()}
    response = CLIENT.post("/v1/separations/list", json=body)
    payload = response.json()
    assert set(payload.keys()) == {"separations", "total"}
    for entry in payload["separations"]:
        assert set(entry.keys()) == {"name", "color_space", "occurs_on_pages"}
