"""CJD orchestration honours the retention-for-training opt-in.

Threads ``X-Compile-Retain-For-Training: true`` through every step:
each step persists its (input, output, plan) triplet, and the per-step
lineage record stamps the decision so ``GET /v1/lineage/{id}`` reflects
what was retained.
"""

from __future__ import annotations

import base64
from typing import Any

import pytest
from fastapi.testclient import TestClient

from compile_pdf.api.main import app
from compile_pdf.lineage.store import reset_default_store
from compile_pdf.retention import store as retention_store


class _FakeS3:
    def __init__(self) -> None:
        self.objects: dict[str, dict[str, Any]] = {}

    def put_object(  # noqa: N803
        self, *, Bucket: str, Key: str, Body: bytes, ContentType: str, Tagging: str
    ) -> None:
        self.objects[Key] = {"Body": Body, "Tagging": Tagging}


@pytest.fixture(autouse=True)
def _clear_lineage_store():
    reset_default_store()
    yield
    reset_default_store()


@pytest.fixture
def fake_s3(monkeypatch: pytest.MonkeyPatch) -> _FakeS3:
    fake = _FakeS3()
    monkeypatch.setenv("COMPILE_RETAIN_BUCKET", "test-bucket")
    monkeypatch.setenv("COMPILE_RETAIN_PREFIX", "retain")
    monkeypatch.setattr(
        retention_store.RetentionStore,
        "_ensure_client",
        lambda self: fake,  # noqa: ARG005
    )
    return fake


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def test_cjd_apply_persists_every_step_when_opted_in(
    printer_pdf: bytes, fake_s3: _FakeS3
) -> None:
    client = TestClient(app)
    response = client.post(
        "/v1/cjd/apply",
        json={
            "input_pdf_b64": _b64(printer_pdf),
            "steps": [
                {
                    "type": "rewrite",
                    "plan": {
                        "ops": [{"op": "metadata_set", "key": "Title", "value": "x"}]
                    },
                },
                {
                    "type": "marks",
                    "template": {"marks": [{"type": "register", "anchor": "trim_corners"}]},
                },
            ],
        },
        headers={"X-Compile-Retain-For-Training": "true"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    # Three blobs per step × two steps.
    assert len(fake_s3.objects) == 6
    # Both rewrite + marks land under distinct producer paths.
    assert any("/rewrite/" in k for k in fake_s3.objects)
    assert any("/marks/" in k for k in fake_s3.objects)
    # Lineage steps reflect the decision.
    assert all(s["retained_for_training"] is True for s in body["steps"])


def test_cjd_apply_no_persist_without_consent(printer_pdf: bytes, fake_s3: _FakeS3) -> None:
    client = TestClient(app)
    response = client.post(
        "/v1/cjd/apply",
        json={
            "input_pdf_b64": _b64(printer_pdf),
            "steps": [
                {
                    "type": "rewrite",
                    "plan": {
                        "ops": [{"op": "metadata_set", "key": "Title", "value": "x"}]
                    },
                },
            ],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert fake_s3.objects == {}
    assert body["steps"][0]["retained_for_training"] is False


def test_cjd_lineage_get_surfaces_retained_flag(
    printer_pdf: bytes, fake_s3: _FakeS3
) -> None:
    client = TestClient(app)
    apply = client.post(
        "/v1/cjd/apply",
        json={
            "input_pdf_b64": _b64(printer_pdf),
            "steps": [
                {
                    "type": "rewrite",
                    "plan": {
                        "ops": [{"op": "metadata_set", "key": "Title", "value": "x"}]
                    },
                },
            ],
        },
        headers={"X-Compile-Retain-For-Training": "yes"},
    )
    assert apply.status_code == 200
    lineage_id = apply.json()["lineage_id"]
    fetched = client.get(f"/v1/lineage/{lineage_id}")
    assert fetched.status_code == 200
    chain = fetched.json()
    assert chain["steps"][0]["retained_for_training"] is True
