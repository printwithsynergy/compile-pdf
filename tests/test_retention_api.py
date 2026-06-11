"""POST /v1/retention/delete — bulk erasure endpoint."""

from __future__ import annotations

from typing import Any

import pytest
from compile_pdf_core.retention import store as retention_store
from fastapi.testclient import TestClient

from compile_pdf.api.main import app


class _FakeS3:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.deleted_calls: list[list[str]] = []

    def put_object(  # noqa: N803
        self, *, Bucket: str, Key: str, Body: bytes, ContentType: str, Tagging: str
    ) -> None:
        self.objects[Key] = Body

    def get_paginator(self, name: str) -> _FakePaginator:  # noqa: ARG002
        return _FakePaginator(self.objects)

    def delete_objects(  # noqa: N803
        self, *, Bucket: str, Delete: dict[str, Any]
    ) -> dict[str, Any]:
        keys = [e["Key"] for e in Delete["Objects"]]
        self.deleted_calls.append(keys)
        for k in keys:
            self.objects.pop(k, None)
        return {"Deleted": [{"Key": k} for k in keys]}


class _FakePaginator:
    def __init__(self, objects: dict[str, bytes]) -> None:
        self._objects = objects

    def paginate(self, *, Bucket: str, Prefix: str):  # noqa: N803, ARG002
        yield {"Contents": [{"Key": k} for k in self._objects if k.startswith(Prefix)]}


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch) -> _FakeS3:
    fake = _FakeS3()
    monkeypatch.setenv("COMPILE_RETAIN_BUCKET", "test-bucket")
    monkeypatch.setenv("COMPILE_RETAIN_PREFIX", "retain")
    monkeypatch.setattr(
        retention_store.RetentionStore,
        "_ensure_client",
        lambda self: fake,  # noqa: ARG005
    )
    return fake


def _seed(fake: _FakeS3, sha: str, *, tenant: str = "anonymous", producer: str = "rewrite") -> None:
    """Drop a fake triplet under the marker key path."""
    root = f"retain/{tenant}/{producer}/2026-05-01/{sha}"
    for name in ("input.pdf", "output.pdf", "result.json"):
        fake.objects[f"{root}/{name}"] = b"blob"


def test_delete_endpoint_removes_all_matching(configured: _FakeS3) -> None:
    sha = "a" * 64
    _seed(configured, sha)
    # An unrelated sha that must survive.
    _seed(configured, "b" * 64)
    client = TestClient(app)
    response = client.post("/v1/retention/delete", json={"sha256": sha})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["deleted"] == 3
    assert all(sha in k for k in body["keys"])
    assert all(sha not in k for k in configured.objects)


def test_delete_endpoint_zero_hits_is_not_an_error(configured: _FakeS3) -> None:  # noqa: ARG001
    client = TestClient(app)
    response = client.post("/v1/retention/delete", json={"sha256": "f" * 64})
    assert response.status_code == 200
    assert response.json() == {"deleted": 0, "keys": []}


def test_delete_endpoint_rejects_non_hex_and_partial_sha() -> None:
    # The store matches keys by the substring "/{sha256}/", so a short or
    # non-hex value would over-match unrelated objects. Both must 422.
    client = TestClient(app)
    for bad in ("a" * 63, "a" * 65, "z" * 64, "abc", "../../etc"):
        response = client.post("/v1/retention/delete", json={"sha256": bad})
        assert response.status_code == 422, f"{bad!r} -> {response.status_code}"


def test_delete_endpoint_503_when_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COMPILE_RETAIN_BUCKET", raising=False)
    client = TestClient(app)
    response = client.post("/v1/retention/delete", json={"sha256": "a" * 64})
    assert response.status_code == 503


def test_delete_endpoint_rejects_empty_sha() -> None:
    client = TestClient(app)
    response = client.post("/v1/retention/delete", json={"sha256": ""})
    assert response.status_code == 422


def test_delete_endpoint_rejects_unknown_fields() -> None:
    client = TestClient(app)
    response = client.post(
        "/v1/retention/delete",
        json={"sha256": "a" * 64, "wat": True},
    )
    assert response.status_code == 422
