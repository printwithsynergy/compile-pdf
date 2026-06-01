# SPDX-License-Identifier: AGPL-3.0-or-later
"""Determinism contract — listing the separations of an identical
PDF three times in a row must produce byte-equal responses.

Read-only metadata endpoints are easy to make deterministic, but
adding the same coverage as the producer-side tests catches
accidental nondeterminism (e.g., dict ordering, randomized output)
that would otherwise slip in.
"""

from __future__ import annotations

import base64
import io

import pikepdf
from fastapi.testclient import TestClient
from pikepdf import Name

from compile_pdf.api.main import app


def _spot_pdf(spot_names: list[str]) -> bytes:
    pdf = pikepdf.new()
    page = pdf.add_blank_page(page_size=(612, 792))
    cs_dict = pikepdf.Dictionary()
    for i, name in enumerate(spot_names):
        cs_dict[f"/Cs{i}"] = pikepdf.Array(
            [Name.Separation, Name(f"/{name}"), Name.DeviceCMYK]
        )
    page.Resources = pikepdf.Dictionary({"/ColorSpace": cs_dict})
    buf = io.BytesIO()
    pdf.save(buf)
    return buf.getvalue()


def test_three_runs_identical_response() -> None:
    client = TestClient(app)
    body = {
        "input_pdf_b64": base64.b64encode(
            _spot_pdf(["PANTONE 185 C", "Silver", "White"]),
        ).decode(),
    }

    responses = [client.post("/v1/separations/list", json=body).json() for _ in range(3)]

    assert responses[0] == responses[1] == responses[2]
    # And the ordering of separations is stable (sorted by name).
    names = [s["name"] for s in responses[0]["separations"]]
    assert names == sorted(names)
