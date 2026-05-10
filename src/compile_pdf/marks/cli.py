"""Click subcommand registration for ``compile-pdf marks``.

Local mode reads the input + template from disk and runs the engine
in-process. External-file marks resolve relative paths against the
template file's directory by default; ``--external-root`` overrides.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from compile_pdf.marks.engine import MarksTemplateError, apply_template
from compile_pdf.marks.template_schema import MarksTemplate, marks_template_json_schema
from compile_pdf.marks.verify import verify_marks


def register(group: click.Group) -> None:
    """Attach the ``marks`` subcommand to the top-level CLI group."""

    @group.command("marks", help="Stamp a marks template onto a PDF.")
    @click.option(
        "--template",
        "template_path",
        type=click.Path(exists=True, dir_okay=False, path_type=Path),
        required=True,
        help="JSON marks-template document.",
    )
    @click.option(
        "--external-root",
        "external_root",
        type=click.Path(exists=True, file_okay=False, path_type=Path),
        default=None,
        help="Root directory for resolving external file paths "
        "(defaults to the template's parent directory).",
    )
    @click.option(
        "--verify/--no-verify",
        default=True,
        help="Run four-layer post-condition checks before writing output.",
    )
    @click.argument(
        "input_path",
        type=click.Path(exists=True, dir_okay=False, path_type=Path),
    )
    @click.argument(
        "output_path",
        type=click.Path(dir_okay=False, path_type=Path),
    )
    def marks_cmd(
        template_path: Path,
        input_path: Path,
        output_path: Path,
        external_root: Path | None,
        verify: bool,
    ) -> None:
        template_dict = json.loads(template_path.read_text(encoding="utf-8"))
        try:
            template = MarksTemplate.model_validate(template_dict)
        except Exception as exc:
            click.echo(f"template validation failed: {exc}", err=True)
            sys.exit(3)

        root = external_root if external_root is not None else template_path.parent
        input_bytes = input_path.read_bytes()
        try:
            result = apply_template(input_bytes, template, external_root=root)
        except MarksTemplateError as exc:
            click.echo(f"template rejected: {exc}", err=True)
            sys.exit(4)

        if verify:
            check = verify_marks(
                input_bytes=input_bytes,
                output_bytes=result.output_bytes,
                template=template,
            )
            if not check.passed:
                click.echo("verify failed:", err=True)
                for failure in check.failures:
                    click.echo(f"  - {failure}", err=True)
                sys.exit(4)

        output_path.write_bytes(result.output_bytes)
        click.echo(
            json.dumps(
                {
                    "marks_applied": result.marks_applied,
                    "pdf_sha256": result.pdf_sha256,
                    "output": str(output_path),
                },
                indent=2,
            )
        )

    @group.command("marks-schema", hidden=True, help="Dump the marks-template JSON Schema.")
    def marks_schema_cmd() -> None:
        click.echo(json.dumps(marks_template_json_schema(), indent=2))
