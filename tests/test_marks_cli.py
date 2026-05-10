"""CLI tests for ``compile-pdf marks``."""

from __future__ import annotations

import json
from pathlib import Path

import pikepdf
from click.testing import CliRunner
from pikepdf import Name

from compile_pdf.cli import cli


def test_marks_cli_round_trips(tmp_path: Path, printer_pdf: bytes) -> None:
    in_path = tmp_path / "in.pdf"
    out_path = tmp_path / "out.pdf"
    template_path = tmp_path / "template.json"
    in_path.write_bytes(printer_pdf)
    template_path.write_text(
        json.dumps(
            {
                "marks": [
                    {"type": "register", "anchor": "trim_corners"},
                    {"type": "proof_slug", "inset_pt": 2.0},
                ]
            }
        )
    )

    runner = CliRunner()
    result = runner.invoke(
        cli, ["marks", "--template", str(template_path), str(in_path), str(out_path)]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["marks_applied"] >= 5  # 4 register + 1 proof_slug
    assert payload["pdf_sha256"]

    pdf = pikepdf.open(out_path)
    try:
        contents = pdf.pages[0].obj[Name.Contents]
        assert isinstance(contents, pikepdf.Array)
        assert len(contents) == 2
    finally:
        pdf.close()


def test_marks_cli_rejects_invalid_template(tmp_path: Path, printer_pdf: bytes) -> None:
    in_path = tmp_path / "in.pdf"
    out_path = tmp_path / "out.pdf"
    template_path = tmp_path / "template.json"
    in_path.write_bytes(printer_pdf)
    template_path.write_text(json.dumps({"marks": [{"type": "wat"}]}))

    runner = CliRunner()
    result = runner.invoke(
        cli, ["marks", "--template", str(template_path), str(in_path), str(out_path)]
    )
    assert result.exit_code == 3


def test_marks_cli_rejects_missing_external(tmp_path: Path, printer_pdf: bytes) -> None:
    in_path = tmp_path / "in.pdf"
    out_path = tmp_path / "out.pdf"
    template_path = tmp_path / "template.json"
    in_path.write_bytes(printer_pdf)
    template_path.write_text(
        json.dumps(
            {
                "marks": [
                    {
                        "type": "external",
                        "file": "missing.pdf",
                        "anchor": "trim_center",
                    }
                ]
            }
        )
    )

    runner = CliRunner()
    result = runner.invoke(
        cli, ["marks", "--template", str(template_path), str(in_path), str(out_path)]
    )
    assert result.exit_code == 4


def test_marks_schema_dumps_json_schema() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["marks-schema"])
    assert result.exit_code == 0
    schema = json.loads(result.output)
    assert "discriminator" in json.dumps(schema)


def test_top_level_help_lists_marks() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "marks" in result.output
