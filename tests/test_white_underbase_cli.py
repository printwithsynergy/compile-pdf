"""CLI smoke tests for ``compile-pdf white-underbase``."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from compile_pdf.cli import cli


def test_cli_writes_output_with_default_policy(
    tmp_path: Path, simple_pdf: bytes
) -> None:
    input_path = tmp_path / "in.pdf"
    output_path = tmp_path / "out.pdf"
    input_path.write_bytes(simple_pdf)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["white-underbase", str(input_path), str(output_path)],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["separation_name"] == "White"
    assert payload["pages_processed"] == 1
    assert output_path.read_bytes().startswith(b"%PDF")


def test_cli_accepts_policy_file(tmp_path: Path, simple_pdf: bytes) -> None:
    input_path = tmp_path / "in.pdf"
    output_path = tmp_path / "out.pdf"
    policy_path = tmp_path / "policy.json"
    input_path.write_bytes(simple_pdf)
    policy_path.write_text(
        json.dumps({"separation_name": "Varnish", "plate_use": "varnish"})
    )

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "white-underbase",
            "--policy",
            str(policy_path),
            str(input_path),
            str(output_path),
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["separation_name"] == "Varnish"
    assert payload["plate_use"] == "varnish"


def test_cli_rejects_malformed_input(tmp_path: Path) -> None:
    input_path = tmp_path / "in.pdf"
    output_path = tmp_path / "out.pdf"
    input_path.write_bytes(b"NOT-A-PDF")

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["white-underbase", str(input_path), str(output_path)],
    )
    assert result.exit_code == 4
    assert "engine rejected" in result.output


def test_cli_rejects_invalid_policy_json(tmp_path: Path, simple_pdf: bytes) -> None:
    input_path = tmp_path / "in.pdf"
    output_path = tmp_path / "out.pdf"
    policy_path = tmp_path / "policy.json"
    input_path.write_bytes(simple_pdf)
    policy_path.write_text("{ not valid json")

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "white-underbase",
            "--policy",
            str(policy_path),
            str(input_path),
            str(output_path),
        ],
    )
    assert result.exit_code == 3
    assert "policy validation failed" in result.output
