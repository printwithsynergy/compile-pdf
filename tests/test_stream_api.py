"""Integration tests for POST /v1/stream/apply (Wave 3 PR-6 O3).

Pins the wire contract: chunked PDF response, ``X-Compile-*``
metadata headers present, byte parity with the JSON ``/apply``
endpoint, error-shape conformance (400 / 422 / 500).
"""

from __future__ import annotations

import base64
import os

import pytest
from fastapi.testclient import TestClient

# The stream router is always-on (not gated by COMPILE_PRODUCER),
# but the rewrite producer used in the byte-parity test below is
# gated. ``all`` mounts both so the parity check can compare.
os.environ.setdefault("COMPILE_PRODUCER", "all")

from compile_pdf.api.main import app  # noqa: E402 — env tweaked above


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def test_rewrite_stream_returns_pdf_with_headers(client: TestClient, simple_pdf: bytes) -> None:
    response = client.post(
        "/v1/stream/apply",
        json={
            "producer": "rewrite",
            "payload": {
                "input_pdf_b64": _b64(simple_pdf),
                "plan": {"ops": []},
            },
        },
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["x-compile-producer"] == "rewrite"
    assert len(response.headers["x-compile-pdf-sha256"]) == 64
    assert len(response.headers["x-compile-input-sha256"]) == 64
    assert len(response.headers["x-compile-cache-key"]) == 64
    assert response.headers["x-compile-schema-version"]
    assert response.headers["x-compile-compile-version"]
    assert response.content.startswith(b"%PDF")


def test_stream_byte_parity_with_json_apply(client: TestClient, simple_pdf: bytes) -> None:
    """The streamed bytes must equal ``base64.b64decode`` of the
    JSON endpoint's ``output_pdf_b64`` for the same input. This is
    the central guarantee of the wrapper: same engine, same bytes,
    different transport."""
    payload = {
        "input_pdf_b64": _b64(simple_pdf),
        "plan": {"ops": []},
    }

    json_response = client.post("/v1/rewrite/apply", json=payload)
    assert json_response.status_code == 200, json_response.text

    stream_response = client.post(
        "/v1/stream/apply",
        json={"producer": "rewrite", "payload": payload},
    )
    assert stream_response.status_code == 200, stream_response.text

    json_bytes = base64.b64decode(json_response.json()["output_pdf_b64"])
    assert stream_response.content == json_bytes
    # Cache keys must also match — wrapper computes the same key.
    assert stream_response.headers["x-compile-cache-key"] == json_response.json()["cache_key"]


def test_stream_unknown_producer_returns_400(client: TestClient, simple_pdf: bytes) -> None:
    response = client.post(
        "/v1/stream/apply",
        json={
            "producer": "no-such-producer",
            "payload": {"input_pdf_b64": _b64(simple_pdf)},
        },
    )
    # Pydantic discriminator catches this at request validation
    # (422 from FastAPI); the engine guard is a defense-in-depth
    # check for callers that bypass validation.
    assert response.status_code in (400, 422)


def test_stream_missing_input_pdf_returns_400(client: TestClient) -> None:
    response = client.post(
        "/v1/stream/apply",
        json={
            "producer": "rewrite",
            "payload": {"plan": {"ops": []}},
        },
    )
    assert response.status_code == 400
    assert "input_pdf_b64" in response.text


def test_stream_malformed_base64_returns_400(client: TestClient) -> None:
    response = client.post(
        "/v1/stream/apply",
        json={
            "producer": "rewrite",
            "payload": {"input_pdf_b64": "@@not-base64@@", "plan": {"ops": []}},
        },
    )
    assert response.status_code == 400
    assert "base64" in response.text


def test_stream_extra_envelope_field_rejected(client: TestClient, simple_pdf: bytes) -> None:
    """``extra="forbid"`` on the envelope guards against typos
    like ``producers`` (plural) silently being ignored."""
    response = client.post(
        "/v1/stream/apply",
        json={
            "producer": "rewrite",
            "payload": {"input_pdf_b64": _b64(simple_pdf), "plan": {"ops": []}},
            "unexpected_field": "oops",
        },
    )
    assert response.status_code == 422
