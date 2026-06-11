"""Click subcommand registration for ``compile-pdf cjd`` + ``lineage``."""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

import click
from compile_pdf_core.lineage.store import (
    LineageNotFoundError,
    default_store,
    serialize_chain,
)

from compile_pdf.cjd.orchestrator import CjdOrderError, execute
from compile_pdf.cjd.schema import CjdJob, cjd_job_json_schema
from compile_pdf.cjd.xml import CjdXmlError, parse_cjd_xml, render_cjd_xml


def register(group: click.Group) -> None:
    """Attach ``cjd``, ``cjd-schema``, and ``lineage`` subcommands."""

    @group.command("cjd", help="Execute a CJD job (multi-producer pipeline).")
    @click.option(
        "--job",
        "job_path",
        type=click.Path(exists=True, dir_okay=False, path_type=Path),
        required=True,
        help="JSON CJD-job document.",
    )
    @click.option(
        "--input",
        "input_path",
        type=click.Path(exists=True, dir_okay=False, path_type=Path),
        default=None,
        help=(
            "Optional. When set, the input PDF bytes are read from this "
            "path and replace job.input_pdf_b64 (handy for large inputs)."
        ),
    )
    @click.option(
        "--trap-diff",
        "trap_diff_path",
        type=click.Path(dir_okay=False, path_type=Path),
        default=None,
        help="Write the trap-diff artifact to this path (no-op if no trap step).",
    )
    @click.option(
        "--xml/--json",
        "use_xml",
        default=False,
        help="Read the job document as XML (default: JSON).",
    )
    @click.argument(
        "output_path",
        type=click.Path(dir_okay=False, path_type=Path),
    )
    def cjd_cmd(
        job_path: Path,
        input_path: Path | None,
        trap_diff_path: Path | None,
        use_xml: bool,
        output_path: Path,
    ) -> None:
        if use_xml:
            try:
                job = parse_cjd_xml(job_path.read_bytes())
            except CjdXmlError as exc:
                click.echo(f"XML job rejected: {exc}", err=True)
                sys.exit(3)
            if input_path is not None:
                # Re-serialize with the override and re-parse via JSON path.
                payload = job.model_dump(mode="json")
                payload["input_pdf_b64"] = base64.b64encode(input_path.read_bytes()).decode("ascii")
                job = CjdJob.model_validate(payload)
        else:
            job_dict = json.loads(job_path.read_text(encoding="utf-8"))
            if input_path is not None:
                job_dict["input_pdf_b64"] = base64.b64encode(input_path.read_bytes()).decode(
                    "ascii"
                )
            try:
                job = CjdJob.model_validate(job_dict)
            except Exception as exc:
                click.echo(f"job validation failed: {exc}", err=True)
                sys.exit(3)

        try:
            result = execute(job)
        except CjdOrderError as exc:
            click.echo(f"job rejected: {exc}", err=True)
            sys.exit(4)

        output_path.write_bytes(result.output_pdf_bytes)
        if trap_diff_path is not None and result.trap_diff is not None:
            trap_diff_path.write_text(json.dumps(result.trap_diff, indent=2), encoding="utf-8")

        click.echo(
            json.dumps(
                {
                    "lineage_id": result.lineage_id,
                    "output_pdf_sha256": result.output_pdf_sha256,
                    "steps": [
                        {
                            "step_index": s.step_index,
                            "producer": s.producer,
                            "output_sha256": s.output_sha256[:16],
                            "cache_key": s.cache_key[:16],
                        }
                        for s in result.steps
                    ],
                    "output": str(output_path),
                    "trap_diff": str(trap_diff_path)
                    if trap_diff_path and result.trap_diff is not None
                    else None,
                },
                indent=2,
            )
        )

    @group.command("cjd-schema", hidden=True, help="Dump the CJD-job JSON Schema.")
    def cjd_schema_cmd() -> None:
        click.echo(json.dumps(cjd_job_json_schema(), indent=2))

    @group.command(
        "cjd-xml-render",
        hidden=True,
        help="Convert a JSON CJD job to XML and print the result.",
    )
    @click.argument(
        "job_path",
        type=click.Path(exists=True, dir_okay=False, path_type=Path),
    )
    def cjd_xml_render_cmd(job_path: Path) -> None:
        job_dict = json.loads(job_path.read_text(encoding="utf-8"))
        try:
            job = CjdJob.model_validate(job_dict)
        except Exception as exc:
            click.echo(f"job validation failed: {exc}", err=True)
            sys.exit(3)
        click.echo(render_cjd_xml(job).decode("utf-8"))

    @group.command("lineage", help="Print the lineage chain for a previously-run CJD job.")
    @click.argument("lineage_id", type=str)
    @click.option(
        "--chain/--summary",
        default=False,
        help="Print the full chain (default) vs. just the lineage_id + step count.",
    )
    def lineage_cmd(lineage_id: str, chain: bool) -> None:
        try:
            ch = default_store().get(lineage_id)
        except LineageNotFoundError:
            click.echo(f"lineage_id not found: {lineage_id}", err=True)
            sys.exit(5)
        if chain:
            click.echo(json.dumps(serialize_chain(ch), indent=2))
        else:
            click.echo(
                json.dumps(
                    {
                        "lineage_id": ch.lineage_id,
                        "step_count": len(ch.steps),
                        "producers": [s.producer for s in ch.steps],
                    },
                    indent=2,
                )
            )
