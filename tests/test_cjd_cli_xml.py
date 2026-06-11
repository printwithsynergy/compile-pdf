"""``compile-pdf cjd --xml`` + ``cjd-xml-render`` CLI coverage."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
from click.testing import CliRunner
from compile_pdf_core.lineage.store import reset_default_store

from compile_pdf.cjd.schema import CjdJob
from compile_pdf.cjd.xml import render_cjd_xml
from compile_pdf.cli import cli


@pytest.fixture(autouse=True)
def _clear_lineage_store():
    reset_default_store()
    yield
    reset_default_store()


def _write_xml_job(tmp_path: Path, printer_pdf: bytes) -> Path:
    job = CjdJob.model_validate(
        {
            "input_pdf_b64": base64.b64encode(printer_pdf).decode("ascii"),
            "steps": [
                {"type": "rewrite", "plan": {"ops": []}},
                {"type": "marks", "template": {"marks": []}},
            ],
        }
    )
    path = tmp_path / "job.xml"
    path.write_bytes(render_cjd_xml(job))
    return path


def test_cjd_cli_runs_with_xml_flag(tmp_path: Path, printer_pdf: bytes) -> None:
    job_path = _write_xml_job(tmp_path, printer_pdf)
    out_path = tmp_path / "out.pdf"

    runner = CliRunner()
    result = runner.invoke(cli, ["cjd", "--job", str(job_path), "--xml", str(out_path)])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["lineage_id"]
    assert len(payload["steps"]) == 2


def test_cjd_cli_xml_with_input_override(
    tmp_path: Path, printer_pdf: bytes, simple_pdf: bytes
) -> None:
    """--input bytes override even when the XML payload encodes a different PDF."""
    job_path = _write_xml_job(tmp_path, simple_pdf)
    in_path = tmp_path / "real-input.pdf"
    in_path.write_bytes(printer_pdf)
    out_path = tmp_path / "out.pdf"

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["cjd", "--job", str(job_path), "--xml", "--input", str(in_path), str(out_path)],
    )
    assert result.exit_code == 0, result.output


def test_cjd_cli_rejects_invalid_xml(tmp_path: Path) -> None:
    job_path = tmp_path / "bad.xml"
    job_path.write_text("<cjd><unclosed>")
    out_path = tmp_path / "out.pdf"
    runner = CliRunner()
    result = runner.invoke(cli, ["cjd", "--job", str(job_path), "--xml", str(out_path)])
    assert result.exit_code == 3
    assert "XML job rejected" in result.output


def test_cjd_xml_render_round_trip(tmp_path: Path, printer_pdf: bytes) -> None:
    """cjd-xml-render emits a payload that --xml can parse back."""
    json_path = tmp_path / "job.json"
    json_path.write_text(
        json.dumps(
            {
                "input_pdf_b64": base64.b64encode(printer_pdf).decode("ascii"),
                "steps": [{"type": "rewrite", "plan": {"ops": []}}],
            }
        )
    )

    runner = CliRunner()
    rendered = runner.invoke(cli, ["cjd-xml-render", str(json_path)])
    assert rendered.exit_code == 0
    assert rendered.output.lstrip().startswith("<?xml")

    xml_path = tmp_path / "rendered.xml"
    xml_path.write_text(rendered.output)
    out_path = tmp_path / "out.pdf"
    result = runner.invoke(cli, ["cjd", "--job", str(xml_path), "--xml", str(out_path)])
    assert result.exit_code == 0


def test_cjd_xml_render_rejects_invalid_json(tmp_path: Path) -> None:
    json_path = tmp_path / "bad.json"
    json_path.write_text(json.dumps({"steps": []}))  # missing input + empty steps
    runner = CliRunner()
    result = runner.invoke(cli, ["cjd-xml-render", str(json_path)])
    assert result.exit_code == 3
