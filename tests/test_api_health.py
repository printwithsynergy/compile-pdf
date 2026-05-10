"""Smoke tests for the FastAPI surface."""

from __future__ import annotations

from fastapi.testclient import TestClient

from compile_pdf.api.main import app
from compile_pdf.version import VERSION


def test_healthz_root_returns_ok():
    client = TestClient(app)
    response = client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == VERSION
    assert "instance_id" in body
    assert "version_skew" in body


def test_v1_healthz_canonical_path():
    client = TestClient(app)
    response = client.get("/v1/healthz")
    assert response.status_code == 200


def test_v1_version_returns_string():
    client = TestClient(app)
    response = client.get("/v1/version")
    assert response.status_code == 200
    assert response.json() == {"version": VERSION}


def test_v1_contract_includes_producer_versions():
    client = TestClient(app)
    response = client.get("/v1/contract")
    assert response.status_code == 200
    body = response.json()
    assert body["contract_name"] == "compile-pdf"
    assert body["package_version"] == VERSION
    for producer in ("rewrite", "marks", "impose", "trap", "cjd"):
        assert producer in body["producer_schema_versions"]


def test_request_id_propagates_through_response():
    client = TestClient(app)
    response = client.get("/healthz", headers={"X-Compile-Request-Id": "test-req-12345"})
    assert response.status_code == 200
    assert response.headers.get("X-Compile-Request-Id") == "test-req-12345"
    # Instance ID is always stamped.
    assert response.headers.get("X-Compile-Instance-Id")


def test_request_id_generated_when_absent():
    client = TestClient(app)
    response = client.get("/healthz")
    assert response.status_code == 200
    rid = response.headers.get("X-Compile-Request-Id")
    assert rid and len(rid) >= 8


def test_healthz_exposes_celery_workers_field():
    """Field defaults to 0 with no broker configured; presence is the
    operational signal we care about."""
    client = TestClient(app)
    body = client.get("/v1/healthz").json()
    assert "celery_workers" in body
    assert body["celery_workers"] == 0


def test_healthz_exposes_queue_depth_field():
    client = TestClient(app)
    body = client.get("/v1/healthz").json()
    assert "queue_depth" in body
    assert body["queue_depth"] == 0
