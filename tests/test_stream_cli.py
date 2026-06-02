"""CLI smoke tests for ``compile-pdf stream`` (Wave 3 PR-6 O3)."""

from __future__ import annotations

import base64
import json
from pathlib import Path

from click.testing import CliRunner

from compile_pdf.cli import cli


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def test_stream_cli_writes_pdf_to_file(tmp_path: Path, simple_pdf: bytes) -> None:
    payload = tmp_path / "payload.json"
    output = tmp_path / "out.pdf"
    payload.write_text(
        json.dumps(
            {
                "input_pdf_b64": _b64(simple_pdf),
                "plan": {"ops": []},
            }
        )
    )

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "stream",
            "--producer",
            "rewrite",
            "--payload",
            str(payload),
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 0, result.output
    # Metadata is emitted on stderr; CliRunner merges by default so
    # we get JSON in `output`.
    metadata = json.loads(result.output)
    assert metadata["producer"] == "rewrite"
    assert len(metadata["pdf_sha256"]) == 64
    assert metadata["output"] == str(output)
    assert output.read_bytes().startswith(b"%PDF")


def test_stream_cli_rejects_unknown_producer(tmp_path: Path) -> None:
    """Click's Choice validator catches the bad producer name
    before our code ever sees it. Exit code 2 is Click's default
    for usage errors."""
    payload = tmp_path / "payload.json"
    output = tmp_path / "out.pdf"
    payload.write_text("{}")

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "stream",
            "--producer",
            "nope",
            "--payload",
            str(payload),
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 2
    assert "Invalid value for '--producer'" in result.output


def test_stream_cli_reports_dispatch_failure(tmp_path: Path) -> None:
    """A malformed payload should exit 4 with a dispatch_failed message."""
    payload = tmp_path / "payload.json"
    output = tmp_path / "out.pdf"
    payload.write_text(json.dumps({"input_pdf_b64": "@@bad@@"}))

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "stream",
            "--producer",
            "rewrite",
            "--payload",
            str(payload),
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 4
    assert "dispatch failed" in result.output
