"""Per-producer retention smoke tests.

Each producer endpoint must:

* Persist three blobs (input.pdf, output.pdf, result.json) when the
  caller sets ``X-Compile-Retain-For-Training: true`` and a bucket is
  configured.
* Persist nothing when the header is absent / falsy.

We monkeypatch the boto3 client construction inside
:class:`compile_pdf.retention.store.RetentionStore` to point at an
in-memory fake so the tests run with no real S3.
"""

from __future__ import annotations

import base64
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from compile_pdf.api.main import app
from compile_pdf.retention import store as retention_store


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


class _FakeS3:
    def __init__(self) -> None:
        self.objects: dict[str, dict[str, Any]] = {}

    def put_object(  # noqa: N803
        self,
        *,
        Bucket: str,
        Key: str,
        Body: bytes,
        ContentType: str,
        Tagging: str,
    ) -> None:
        self.objects[Key] = {
            "Bucket": Bucket,
            "Body": Body,
            "ContentType": ContentType,
            "Tagging": Tagging,
        }


@pytest.fixture
def fake_s3(monkeypatch: pytest.MonkeyPatch) -> _FakeS3:
    """Configure the bucket env + redirect every RetentionStore to the fake."""
    fake = _FakeS3()
    monkeypatch.setenv("COMPILE_RETAIN_BUCKET", "test-bucket")
    monkeypatch.setenv("COMPILE_RETAIN_PREFIX", "retain")
    monkeypatch.setenv("COMPILE_RETAIN_TTL_DAYS", "30")

    def _patched_ensure_client(self: retention_store.RetentionStore) -> Any:  # noqa: ARG001
        return fake

    monkeypatch.setattr(
        retention_store.RetentionStore,
        "_ensure_client",
        _patched_ensure_client,
    )
    return fake


@pytest.fixture
def no_retain_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Belt-and-braces: ensure no leftover retention env is in effect."""
    monkeypatch.delenv("COMPILE_RETAIN_BUCKET", raising=False)
    monkeypatch.delenv("COMPILE_RETAIN_PREFIX", raising=False)


def _assert_triplet(fake: _FakeS3, *, producer: str, count: int = 3) -> None:
    keys = list(fake.objects)
    assert len(keys) == count, keys
    assert all(f"/{producer}/" in k for k in keys), keys
    assert {k.rsplit("/", 1)[1] for k in keys} == {
        "input.pdf",
        "output.pdf",
        "result.json",
    }
    result_key = next(k for k in keys if k.endswith("result.json"))
    payload = json.loads(fake.objects[result_key]["Body"])
    # The big base64 blob never lands in result.json.
    assert "output_pdf_b64" not in payload


# --- rewrite -------------------------------------------------------------


def test_rewrite_apply_persists_when_opted_in(simple_pdf: bytes, fake_s3: _FakeS3) -> None:
    client = TestClient(app)
    response = client.post(
        "/v1/rewrite/apply",
        json={
            "input_pdf_b64": _b64(simple_pdf),
            "plan": {"ops": [{"op": "metadata_set", "key": "Title", "value": "x"}]},
        },
        headers={"X-Compile-Retain-For-Training": "true"},
    )
    assert response.status_code == 200, response.text
    _assert_triplet(fake_s3, producer="rewrite")


def test_rewrite_apply_does_not_persist_without_consent(
    simple_pdf: bytes, fake_s3: _FakeS3
) -> None:
    client = TestClient(app)
    response = client.post(
        "/v1/rewrite/apply",
        json={
            "input_pdf_b64": _b64(simple_pdf),
            "plan": {"ops": [{"op": "metadata_set", "key": "Title", "value": "x"}]},
        },
    )
    assert response.status_code == 200, response.text
    assert fake_s3.objects == {}


def test_rewrite_apply_does_not_persist_when_unconfigured(
    simple_pdf: bytes, no_retain_env: None
) -> None:
    """Even with consent=true, no bucket → no-op."""
    client = TestClient(app)
    response = client.post(
        "/v1/rewrite/apply",
        json={
            "input_pdf_b64": _b64(simple_pdf),
            "plan": {"ops": [{"op": "metadata_set", "key": "Title", "value": "x"}]},
        },
        headers={"X-Compile-Retain-For-Training": "true"},
    )
    assert response.status_code == 200, response.text


# --- marks ---------------------------------------------------------------


def test_marks_apply_persists_when_opted_in(printer_pdf: bytes, fake_s3: _FakeS3) -> None:
    client = TestClient(app)
    response = client.post(
        "/v1/marks/apply",
        json={
            "input_pdf_b64": _b64(printer_pdf),
            "template": {"marks": [{"type": "register", "anchor": "trim_corners"}]},
        },
        headers={"X-Compile-Retain-For-Training": "yes"},
    )
    assert response.status_code == 200, response.text
    _assert_triplet(fake_s3, producer="marks")


def test_marks_apply_no_persist_without_header(printer_pdf: bytes, fake_s3: _FakeS3) -> None:
    client = TestClient(app)
    response = client.post(
        "/v1/marks/apply",
        json={
            "input_pdf_b64": _b64(printer_pdf),
            "template": {"marks": [{"type": "register", "anchor": "trim_corners"}]},
        },
    )
    assert response.status_code == 200, response.text
    assert fake_s3.objects == {}


def test_marks_multipart_persists_via_form_field(printer_pdf: bytes, fake_s3: _FakeS3) -> None:
    client = TestClient(app)
    response = client.post(
        "/v1/marks/apply-multipart",
        files={"input_pdf": ("in.pdf", printer_pdf, "application/pdf")},
        data={
            "template": json.dumps(
                {"marks": [{"type": "register", "anchor": "trim_corners"}]}
            ),
            "retain_for_training": "true",
        },
    )
    assert response.status_code == 200, response.text
    _assert_triplet(fake_s3, producer="marks")


def test_marks_multipart_header_overrides_form_field(printer_pdf: bytes, fake_s3: _FakeS3) -> None:
    """Header 'false' + form 'true' → header wins → no-op."""
    client = TestClient(app)
    response = client.post(
        "/v1/marks/apply-multipart",
        files={"input_pdf": ("in.pdf", printer_pdf, "application/pdf")},
        data={
            "template": json.dumps(
                {"marks": [{"type": "register", "anchor": "trim_corners"}]}
            ),
            "retain_for_training": "true",
        },
        headers={"X-Compile-Retain-For-Training": "false"},
    )
    assert response.status_code == 200, response.text
    assert fake_s3.objects == {}


# --- impose --------------------------------------------------------------


def test_impose_apply_persists_when_opted_in(
    four_page_content_pdf: bytes, fake_s3: _FakeS3
) -> None:
    client = TestClient(app)
    response = client.post(
        "/v1/impose/apply",
        json={
            "input_pdf_b64": _b64(four_page_content_pdf),
            "plan": {
                "sheet": {"width_pt": 1782, "height_pt": 1700},
                "cell": {"width_pt": 612, "height_pt": 792},
                "gutter": {"x_pt": 12, "y_pt": 12},
            },
        },
        headers={"X-Compile-Retain-For-Training": "1"},
    )
    assert response.status_code == 200, response.text
    _assert_triplet(fake_s3, producer="impose")


# --- trap ----------------------------------------------------------------


def test_trap_apply_persists_when_opted_in(simple_pdf: bytes, fake_s3: _FakeS3) -> None:
    client = TestClient(app)
    response = client.post(
        "/v1/trap/apply",
        json={
            "input_pdf_b64": _b64(simple_pdf),
            "policy": {
                "engine": "pure_python",
                "default_trap_width_pt": 0.144,
                "trap_zones": [],
            },
        },
        headers={"X-Compile-Retain-For-Training": "true"},
    )
    assert response.status_code == 200, response.text
    _assert_triplet(fake_s3, producer="trap")


# --- tenant slug --------------------------------------------------------


def test_tenant_header_lands_in_key_path(simple_pdf: bytes, fake_s3: _FakeS3) -> None:
    client = TestClient(app)
    response = client.post(
        "/v1/rewrite/apply",
        json={
            "input_pdf_b64": _b64(simple_pdf),
            "plan": {"ops": [{"op": "metadata_set", "key": "Title", "value": "x"}]},
        },
        headers={
            "X-Compile-Retain-For-Training": "true",
            "X-Compile-Tenant": "Acme Co",
        },
    )
    assert response.status_code == 200, response.text
    assert all("/acme-co/" in k for k in fake_s3.objects), list(fake_s3.objects)
