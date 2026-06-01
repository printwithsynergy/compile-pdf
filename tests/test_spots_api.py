"""Integration tests for the /v1/spots/* endpoints.

The router wraps :mod:`codex_pdf.color`; tests assert the wire shape
+ basic behaviors. The catalogue size (~23k entries) is treated as
a black box — we don't pin a row count, we just assert non-empty
and the structural shape Pydantic enforces.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from compile_pdf.api.main import app

CLIENT = TestClient(app)


def test_libraries_lists_named_sub_libraries() -> None:
    response = CLIENT.get("/v1/spots/libraries")
    assert response.status_code == 200, response.text
    body = response.json()
    assert "libraries" in body
    assert isinstance(body["libraries"], list)
    # Catalogue declares ~16 sub-libraries (Formula Guide Coated/Uncoated,
    # Color Bridge C/U, Extended Gamut, Metallics, ...). Don't pin the
    # exact count — just assert non-trivial.
    assert len(body["libraries"]) > 0
    first = body["libraries"][0]
    assert "id" in first
    assert "count" in first
    assert isinstance(first["count"], int)
    assert first["count"] > 0


def test_search_with_no_query_returns_first_page_of_results() -> None:
    response = CLIENT.get("/v1/spots/search", params={"limit": 5})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["limit"] == 5
    assert len(body["results"]) == 5
    # `total` is the unbounded match count (pre-limit).
    assert body["total"] > 5
    # Each result has the full SpotEntry shape.
    for entry in body["results"]:
        assert "name" in entry
        assert isinstance(entry["name"], str)


def test_search_filters_by_substring() -> None:
    response = CLIENT.get("/v1/spots/search", params={"q": "185", "limit": 10})
    assert response.status_code == 200, response.text
    body = response.json()
    # All matching names contain "185" (case + spacing variants are
    # handled via normalize_pantone_name in the API).
    assert body["total"] >= 1
    for entry in body["results"]:
        # Strip non-alphanumerics + uppercase to match the normalization
        # codex applies under the hood.
        normalized = "".join(c for c in entry["name"] if c.isalnum()).upper()
        assert "185" in normalized


def test_search_respects_library_filter() -> None:
    # Pick a library off the catalogue dynamically — don't hard-code a
    # name that might change with a codex catalogue update.
    libs_response = CLIENT.get("/v1/spots/libraries")
    libs = libs_response.json()["libraries"]
    if not libs:
        return  # empty catalogue (defensive — shouldn't happen in practice)
    target = libs[0]["id"]

    response = CLIENT.get("/v1/spots/search", params={"library": target, "limit": 20})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] > 0
    for entry in body["results"]:
        assert entry["library"] == target


def test_lookup_resolves_a_canonical_name() -> None:
    # PANTONE 185 C is a well-known Formula Guide entry, present in
    # every shipped codex-pdf catalogue.
    response = CLIENT.get("/v1/spots/lookup", params={"name": "PANTONE 185 C"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert "185" in body["name"]


def test_lookup_falls_back_to_alternate_key() -> None:
    # Without spaces — codex's normalize handles the variant.
    response = CLIENT.get("/v1/spots/lookup", params={"name": "PANTONE 185C"})
    assert response.status_code == 200, response.text


def test_lookup_404s_unknown_name() -> None:
    response = CLIENT.get("/v1/spots/lookup", params={"name": "DEFINITELY NOT A REAL PANTONE"})
    assert response.status_code == 404


def test_search_limit_is_clamped_via_validation() -> None:
    # FastAPI's Query(ge=1, le=200) — out-of-range should 422.
    response = CLIENT.get("/v1/spots/search", params={"limit": 999})
    assert response.status_code == 422
