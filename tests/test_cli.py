"""CLI smoke tests — exercise each top-level subcommand to lock the
console-script entrypoint and the contract/health/version JSON shape.
"""

from __future__ import annotations

import json

from click.testing import CliRunner

from compile_pdf.cli import cli


def test_cli_version_emits_payload() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["version"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["compile_version"]
    assert "rewrite" in payload["producer_schema_versions"]
    assert payload["compile_document_schema_version"]
    # codex section versions populate when codex-pdf is installed (which it is in CI).
    assert payload["codex_section_versions"]
    assert payload["codex_pdf_package_version"] != "unknown"


def test_cli_contract_emits_payload() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["contract"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["contract_name"] == "compile-pdf"
    assert payload["package_version"]
    assert "/v1/healthz" in payload["endpoints"]


def test_cli_health_emits_payload() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["health"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "ok"
    assert payload["version"]
    assert payload["instance_id"]
    assert payload["codex_pdf_version"] != "unknown"


def test_cli_schema_placeholder() -> None:
    runner = CliRunner()
    for name in ("rewrite", "marks", "impose", "trap", "cjd"):
        result = runner.invoke(cli, ["schema", name])
        assert result.exit_code == 0, result.output
        assert name in result.output


def test_cli_schema_rejects_unknown_name() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["schema", "nope"])
    assert result.exit_code != 0


def test_cli_top_level_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    for sub in ("version", "contract", "health", "schema"):
        assert sub in result.output


def test_cli_main_entrypoint_callable() -> None:
    """Imports the entry-point referenced by [project.scripts]."""
    from compile_pdf.cli import main

    assert callable(main)
