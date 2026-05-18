"""Tests for the async job store and ?async=true endpoint parameters.

Uses ``unittest.mock.patch`` to replace Redis calls so the tests
run without a live broker.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from compile_pdf_core.async_jobs import (
    AsyncJobAccepted,
    AsyncJobStatus,
    JobStatus,
    create_job,
    get_job,
    update_job,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_redis_mock(stored: dict[str, str] | None = None) -> MagicMock:
    """Build a fake Redis client backed by an in-process dict."""
    store: dict[str, str] = stored if stored is not None else {}

    mock = MagicMock()

    def _setex(key: str, ttl: int, value: str) -> None:
        store[key] = value

    def _get(key: str) -> str | None:
        return store.get(key)

    mock.setex.side_effect = _setex
    mock.get.side_effect = _get
    mock._store = store  # expose for assertions
    return mock


# ---------------------------------------------------------------------------
# Unit tests — job store
# ---------------------------------------------------------------------------


def test_create_job_returns_uuid() -> None:
    mock = _make_redis_mock()
    with patch("compile_pdf_core.async_jobs._redis_client", return_value=mock):
        job_id = create_job(kind="trap", payload_hash="abc123")

    assert len(job_id) == 36  # UUID4 canonical form
    assert mock.setex.called
    key = f"compile:job:{job_id}"
    raw = mock._store[key]
    data = json.loads(raw)
    assert data["job_id"] == job_id
    assert data["kind"] == "trap"
    assert data["status"] == JobStatus.pending
    assert data["result"] is None
    assert data["error"] is None


def test_get_job_returns_none_when_missing() -> None:
    mock = _make_redis_mock()
    with patch("compile_pdf_core.async_jobs._redis_client", return_value=mock):
        result = get_job("no-such-id")
    assert result is None


def test_get_job_returns_stored_data() -> None:
    mock = _make_redis_mock()
    with patch("compile_pdf_core.async_jobs._redis_client", return_value=mock):
        job_id = create_job(kind="impose", payload_hash="def456")
        result = get_job(job_id)

    assert result is not None
    assert result["job_id"] == job_id
    assert result["kind"] == "impose"
    assert result["status"] == JobStatus.pending


def test_update_job_sets_status() -> None:
    mock = _make_redis_mock()
    with patch("compile_pdf_core.async_jobs._redis_client", return_value=mock):
        job_id = create_job(kind="cjd", payload_hash="ghi789")
        update_job(job_id, JobStatus.running)
        data = get_job(job_id)

    assert data is not None
    assert data["status"] == JobStatus.running
    assert data["result"] is None


def test_update_job_sets_result() -> None:
    mock = _make_redis_mock()
    with patch("compile_pdf_core.async_jobs._redis_client", return_value=mock):
        job_id = create_job(kind="trap", payload_hash="jkl000")
        update_job(job_id, JobStatus.complete, result={"pdf_sha256": "abc"})
        data = get_job(job_id)

    assert data is not None
    assert data["status"] == JobStatus.complete
    assert data["result"] == {"pdf_sha256": "abc"}
    assert data["error"] is None


def test_update_job_sets_error() -> None:
    mock = _make_redis_mock()
    with patch("compile_pdf_core.async_jobs._redis_client", return_value=mock):
        job_id = create_job(kind="trap", payload_hash="mno111")
        update_job(job_id, JobStatus.failed, error="engine blew up")
        data = get_job(job_id)

    assert data is not None
    assert data["status"] == JobStatus.failed
    assert data["error"] == "engine blew up"


def test_update_job_noop_when_missing() -> None:
    """update_job on a non-existent job must not raise."""
    mock = _make_redis_mock()
    with patch("compile_pdf_core.async_jobs._redis_client", return_value=mock):
        update_job("ghost-id", JobStatus.complete)  # should not raise


# ---------------------------------------------------------------------------
# Unit tests — Pydantic models
# ---------------------------------------------------------------------------


def test_async_job_accepted_model() -> None:
    obj = AsyncJobAccepted(job_id="abc", poll_url="/v1/jobs/abc")
    assert obj.status == "pending"
    assert obj.poll_url == "/v1/jobs/abc"


def test_async_job_status_model() -> None:
    obj = AsyncJobStatus(job_id="abc", kind="trap", status="complete", result={"x": 1})
    assert obj.result == {"x": 1}
    assert obj.error is None


# ---------------------------------------------------------------------------
# Integration tests — GET /v1/jobs/{job_id}
# ---------------------------------------------------------------------------


def test_get_job_status_404_when_not_found() -> None:
    from fastapi.testclient import TestClient

    from compile_pdf.api.main import app

    mock = _make_redis_mock()
    with patch("compile_pdf_core.async_jobs._redis_client", return_value=mock):
        client = TestClient(app)
        resp = client.get("/v1/jobs/no-such-job")
    assert resp.status_code == 404


def test_get_job_status_200_when_found() -> None:
    from fastapi.testclient import TestClient

    from compile_pdf.api.main import app

    mock = _make_redis_mock()
    with patch("compile_pdf_core.async_jobs._redis_client", return_value=mock):
        job_id = create_job(kind="trap", payload_hash="test-hash")
        client = TestClient(app)
        resp = client.get(f"/v1/jobs/{job_id}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["job_id"] == job_id
    assert body["kind"] == "trap"
    assert body["status"] == "pending"


# ---------------------------------------------------------------------------
# Integration tests — ?async=true on producer endpoints
# ---------------------------------------------------------------------------


def test_trap_apply_async_returns_202(simple_pdf: bytes) -> None:
    """?async=true on POST /v1/trap/apply returns 202 with job_id."""
    import base64

    from fastapi.testclient import TestClient

    from compile_pdf.api.main import app

    mock = _make_redis_mock()
    with (
        patch("compile_pdf_core.async_jobs._redis_client", return_value=mock),
        patch("compile_pdf_core.async_tasks.async_wrap_trap.apply_async") as mock_task,
    ):
        client = TestClient(app)
        resp = client.post(
            "/v1/trap/apply?async=true",
            json={
                "input_pdf_b64": base64.b64encode(simple_pdf).decode("ascii"),
                "policy": {
                    "default_trap_width_pt": 0.5,
                    "trap_zones": [],
                },
            },
        )

    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert "job_id" in body
    assert body["status"] == "pending"
    assert body["poll_url"].startswith("/v1/jobs/")
    mock_task.assert_called_once()


def test_impose_apply_async_returns_202(four_page_content_pdf: bytes) -> None:
    """?async=true on POST /v1/impose/apply returns 202 with job_id."""
    import base64

    from fastapi.testclient import TestClient

    from compile_pdf.api.main import app

    mock = _make_redis_mock()
    with (
        patch("compile_pdf_core.async_jobs._redis_client", return_value=mock),
        patch("compile_pdf_core.async_tasks.async_wrap_impose.apply_async") as mock_task,
    ):
        client = TestClient(app)
        resp = client.post(
            "/v1/impose/apply?async=true",
            json={
                "input_pdf_b64": base64.b64encode(four_page_content_pdf).decode("ascii"),
                "plan": {
                    "sheet": {"width_pt": 1782, "height_pt": 1700},
                    "cell": {"width_pt": 612, "height_pt": 792},
                    "gutter": {"x_pt": 12, "y_pt": 12},
                },
            },
        )

    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert "job_id" in body
    assert body["status"] == "pending"
    assert body["poll_url"].startswith("/v1/jobs/")
    mock_task.assert_called_once()


def test_cjd_apply_async_returns_202(printer_pdf: bytes) -> None:
    """?async=true on POST /v1/cjd/apply returns 202 with job_id."""
    import base64

    from fastapi.testclient import TestClient

    from compile_pdf.api.main import app

    mock = _make_redis_mock()
    with (
        patch("compile_pdf_core.async_jobs._redis_client", return_value=mock),
        patch("compile_pdf_core.async_tasks.async_wrap_cjd.apply_async") as mock_task,
    ):
        client = TestClient(app)
        resp = client.post(
            "/v1/cjd/apply?async=true",
            json={
                "input_pdf_b64": base64.b64encode(printer_pdf).decode("ascii"),
                "steps": [
                    {
                        "type": "rewrite",
                        "plan": {"ops": [{"op": "metadata_set", "key": "Title", "value": "T"}]},
                    }
                ],
            },
        )

    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert "job_id" in body
    assert body["status"] == "pending"
    assert body["poll_url"].startswith("/v1/jobs/")
    mock_task.assert_called_once()


def test_trap_apply_sync_still_works(simple_pdf: bytes) -> None:
    """Sync path (no ?async) is unchanged after the async wiring."""
    import base64

    from fastapi.testclient import TestClient

    from compile_pdf.api.main import app

    client = TestClient(app)
    resp = client.post(
        "/v1/trap/apply",
        json={
            "input_pdf_b64": base64.b64encode(simple_pdf).decode("ascii"),
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
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["engine"] == "pure_python"
