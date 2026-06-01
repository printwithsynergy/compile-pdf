"""Integration tests for POST /v1/trap/preview.

The preview endpoint shares the analysis path with /v1/trap/apply
but returns metadata only — no output_pdf_b64. Used by the editor's
D1 background trap-preview overlay (Wave 1 PR-12).
"""

from __future__ import annotations

import base64

from fastapi.testclient import TestClient

from compile_pdf.api.main import app


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def test_trap_preview_returns_metadata_without_pdf(simple_pdf: bytes) -> None:
    """Preview returns the same trap-diff + operations_count as apply,
    but never emits output_pdf_b64 or pdf_sha256."""
    client = TestClient(app)
    response = client.post(
        "/v1/trap/preview",
        json={
            "input_pdf_b64": _b64(simple_pdf),
            "policy": {
                "default_trap_width_pt": 0.5,
                "trap_zones": [
                    {
                        "page_index": 0,
                        "rect_pt": [100, 100, 300, 300],
                        "from_ink": "Y",
                        "to_ink": "K",
                    }
                ],
            },
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["engine"] == "pure_python"
    assert body["operations_count"] == 1
    assert body["trap_diff"]["operations"][0]["from_ink"] == "Y"
    assert body["cache_key"]
    assert body["input_sha256"]
    assert body["policy_sha256"]
    # Crucially, no PDF body — that's the whole point of preview.
    assert "output_pdf_b64" not in body
    assert "pdf_sha256" not in body


def test_trap_preview_rejects_invalid_base64() -> None:
    client = TestClient(app)
    response = client.post(
        "/v1/trap/preview",
        json={"input_pdf_b64": "not-valid!!!", "policy": {}},
    )
    assert response.status_code == 400


def test_trap_preview_rejects_unknown_field(simple_pdf: bytes) -> None:
    client = TestClient(app)
    response = client.post(
        "/v1/trap/preview",
        json={"input_pdf_b64": _b64(simple_pdf), "policy": {"bogus": True}},
    )
    assert response.status_code == 422


def test_trap_preview_empty_policy_returns_zero_operations(simple_pdf: bytes) -> None:
    """Empty policy (no trap_zones, no ink_pair_rules) produces zero
    operations — preview should still succeed and report the cache key."""
    client = TestClient(app)
    response = client.post(
        "/v1/trap/preview",
        json={"input_pdf_b64": _b64(simple_pdf), "policy": {}},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["operations_count"] == 0
    assert body["trap_findings"] == []


def test_trap_preview_cache_key_differs_from_apply(simple_pdf: bytes) -> None:
    """Preview and apply use different producer names in their cache
    keys so identical inputs don't collide across the two endpoints."""
    client = TestClient(app)
    json_payload = {
        "input_pdf_b64": _b64(simple_pdf),
        "policy": {
            "trap_zones": [
                {
                    "page_index": 0,
                    "rect_pt": [10, 10, 20, 20],
                    "from_ink": "C",
                    "to_ink": "M",
                }
            ],
        },
    }
    apply_response = client.post("/v1/trap/apply", json=json_payload)
    preview_response = client.post("/v1/trap/preview", json=json_payload)
    assert apply_response.status_code == 200
    assert preview_response.status_code == 200
    assert apply_response.json()["cache_key"] != preview_response.json()["cache_key"]


def test_trap_preview_findings_match_apply(simple_pdf: bytes) -> None:
    """Preview's trap_findings should be byte-identical to apply's
    — same analysis, just no PDF emit."""
    client = TestClient(app)
    json_payload = {
        "input_pdf_b64": _b64(simple_pdf),
        "policy": {
            "trap_zones": [
                {
                    "page_index": 0,
                    "rect_pt": [50, 50, 150, 150],
                    "from_ink": "M",
                    "to_ink": "K",
                }
            ],
        },
    }
    apply_body = client.post("/v1/trap/apply", json=json_payload).json()
    preview_body = client.post("/v1/trap/preview", json=json_payload).json()
    assert preview_body["trap_findings"] == apply_body["trap_findings"]
    assert preview_body["operations_count"] == apply_body["operations_count"]
    assert preview_body["trap_diff"]["operations"] == apply_body["trap_diff"]["operations"]
