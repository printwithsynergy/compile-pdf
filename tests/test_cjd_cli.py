"""CLI tests for ``compile-pdf cjd`` + ``lineage``."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from compile_pdf.cli import cli
from compile_pdf.lineage.store import reset_default_store


@pytest.fixture(autouse=True)
def _clear_lineage_store():
    reset_default_store()
    yield
    reset_default_store()


def test_cjd_cli_round_trips(tmp_path: Path, printer_pdf: bytes) -> None:
    job_path = tmp_path / "job.json"
    out_path = tmp_path / "out.pdf"
    job_path.write_text(
        json.dumps(
            {
                "input_pdf_b64": base64.b64encode(printer_pdf).decode("ascii"),
                "steps": [
                    {"type": "rewrite", "plan": {"ops": []}},
                    {
                        "type": "marks",
                        "template": {"marks": [{"type": "register", "anchor": "trim_corners"}]},
                    },
                ],
            }
        )
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["cjd", "--job", str(job_path), str(out_path)])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["lineage_id"]
    assert len(payload["steps"]) == 2


def test_cjd_cli_input_flag_overrides_inline_payload(
    tmp_path: Path, printer_pdf: bytes, simple_pdf: bytes
) -> None:
    """--input overrides job.input_pdf_b64."""
    job_path = tmp_path / "job.json"
    in_path = tmp_path / "in.pdf"
    out_path = tmp_path / "out.pdf"
    in_path.write_bytes(printer_pdf)
    job_path.write_text(
        json.dumps(
            {
                # Inline says simple_pdf; --input overrides with printer_pdf.
                "input_pdf_b64": base64.b64encode(simple_pdf).decode("ascii"),
                "steps": [{"type": "rewrite", "plan": {"ops": []}}],
            }
        )
    )

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "cjd",
            "--job",
            str(job_path),
            "--input",
            str(in_path),
            str(out_path),
        ],
    )
    assert result.exit_code == 0, result.output


def test_cjd_cli_writes_trap_diff_when_step_present(tmp_path: Path, simple_pdf: bytes) -> None:
    job_path = tmp_path / "job.json"
    out_path = tmp_path / "out.pdf"
    diff_path = tmp_path / "trap-diff.json"
    job_path.write_text(
        json.dumps(
            {
                "input_pdf_b64": base64.b64encode(simple_pdf).decode("ascii"),
                "steps": [
                    {
                        "type": "trap",
                        "policy": {
                            "trap_zones": [
                                {
                                    "page_index": 0,
                                    "rect_pt": [50, 50, 100, 100],
                                    "from_ink": "Y",
                                    "to_ink": "K",
                                }
                            ]
                        },
                    }
                ],
            }
        )
    )
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "cjd",
            "--job",
            str(job_path),
            "--trap-diff",
            str(diff_path),
            str(out_path),
        ],
    )
    assert result.exit_code == 0
    diff = json.loads(diff_path.read_text())
    assert diff["operations"][0]["from_ink"] == "Y"


def test_cjd_cli_invalid_job_returns_exit_3(tmp_path: Path) -> None:
    job_path = tmp_path / "job.json"
    out_path = tmp_path / "out.pdf"
    job_path.write_text(json.dumps({"steps": []}))  # missing input + empty steps

    runner = CliRunner()
    result = runner.invoke(cli, ["cjd", "--job", str(job_path), str(out_path)])
    assert result.exit_code == 3


def test_cjd_cli_strict_order_violation_returns_exit_4(tmp_path: Path, printer_pdf: bytes) -> None:
    job_path = tmp_path / "job.json"
    out_path = tmp_path / "out.pdf"
    job_path.write_text(
        json.dumps(
            {
                "input_pdf_b64": base64.b64encode(printer_pdf).decode("ascii"),
                "strict_order": True,
                "steps": [
                    {"type": "marks", "template": {"marks": []}},
                    {"type": "rewrite", "plan": {"ops": []}},
                ],
            }
        )
    )
    runner = CliRunner()
    result = runner.invoke(cli, ["cjd", "--job", str(job_path), str(out_path)])
    assert result.exit_code == 4


def test_lineage_cli_summary_after_cjd(tmp_path: Path, printer_pdf: bytes) -> None:
    runner = CliRunner()
    job_path = tmp_path / "job.json"
    out_path = tmp_path / "out.pdf"
    job_path.write_text(
        json.dumps(
            {
                "input_pdf_b64": base64.b64encode(printer_pdf).decode("ascii"),
                "steps": [
                    {"type": "rewrite", "plan": {"ops": []}},
                    {"type": "marks", "template": {"marks": []}},
                ],
            }
        )
    )
    cjd_result = runner.invoke(cli, ["cjd", "--job", str(job_path), str(out_path)])
    lineage_id = json.loads(cjd_result.output)["lineage_id"]

    summary = runner.invoke(cli, ["lineage", lineage_id])
    assert summary.exit_code == 0
    payload = json.loads(summary.output)
    assert payload["step_count"] == 2
    assert payload["producers"] == ["rewrite", "marks"]


def test_lineage_cli_chain_after_cjd(tmp_path: Path, printer_pdf: bytes) -> None:
    runner = CliRunner()
    job_path = tmp_path / "job.json"
    out_path = tmp_path / "out.pdf"
    job_path.write_text(
        json.dumps(
            {
                "input_pdf_b64": base64.b64encode(printer_pdf).decode("ascii"),
                "steps": [{"type": "rewrite", "plan": {"ops": []}}],
            }
        )
    )
    cjd_result = runner.invoke(cli, ["cjd", "--job", str(job_path), str(out_path)])
    lineage_id = json.loads(cjd_result.output)["lineage_id"]

    chain = runner.invoke(cli, ["lineage", lineage_id, "--chain"])
    assert chain.exit_code == 0
    payload = json.loads(chain.output)
    assert payload["lineage_id"] == lineage_id
    assert len(payload["steps"]) == 1


def test_lineage_cli_unknown_id_exit_5() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["lineage", "no-such-id"])
    assert result.exit_code == 5


def test_cjd_schema_dumps_json_schema() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["cjd-schema"])
    assert result.exit_code == 0
    schema = json.loads(result.output)
    assert "$defs" in schema


def test_top_level_help_lists_cjd() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "cjd" in result.output
    assert "lineage" in result.output
