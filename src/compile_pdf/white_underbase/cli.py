"""Click subcommand registration for ``compile-pdf white-underbase``.

Local mode reads the input PDF + policy JSON from disk and runs
the engine in-process. HTTP mode (``COMPILE_API_BASE`` set) is
wired alongside the other producers when the sidecar deploy lights
up.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from compile_pdf.white_underbase.engine import (
    WhiteUnderbaseEngineError,
    apply_white_underbase,
)
from compile_pdf.white_underbase.schema import WhiteUnderbasePolicy
from compile_pdf.white_underbase.verify import verify_white_underbase


def register(group: click.Group) -> None:
    """Attach the ``white-underbase`` subcommand to the top-level CLI group."""

    @group.command(
        "white-underbase",
        help="Generate a white / underbase plate for a PDF.",
    )
    @click.option(
        "--policy",
        "policy_path",
        type=click.Path(exists=True, dir_okay=False, path_type=Path),
        required=False,
        help=(
            "JSON file matching WhiteUnderbasePolicy. Defaults are used "
            "when omitted (separation='White', strategy='auto')."
        ),
    )
    @click.option(
        "--verify/--no-verify",
        default=True,
        help="Run post-condition checks before writing output.",
    )
    @click.argument(
        "input_path",
        type=click.Path(exists=True, dir_okay=False, path_type=Path),
    )
    @click.argument(
        "output_path",
        type=click.Path(dir_okay=False, path_type=Path),
    )
    def white_underbase_cmd(
        policy_path: Path | None,
        input_path: Path,
        output_path: Path,
        verify: bool,
    ) -> None:
        if policy_path is not None:
            try:
                policy_dict = json.loads(policy_path.read_text(encoding="utf-8"))
                policy = WhiteUnderbasePolicy.model_validate(policy_dict)
            except (OSError, ValueError) as exc:
                click.echo(f"policy validation failed: {exc}", err=True)
                sys.exit(3)
        else:
            policy = WhiteUnderbasePolicy()

        input_bytes = input_path.read_bytes()
        try:
            result = apply_white_underbase(input_bytes, policy)
        except WhiteUnderbaseEngineError as exc:
            click.echo(f"engine rejected: {exc}", err=True)
            sys.exit(4)

        if verify:
            check = verify_white_underbase(input_bytes=input_bytes, result=result)
            if not check.ok:
                click.echo("verify failed:", err=True)
                for failure in check.failures:
                    click.echo(f"  - {failure}", err=True)
                sys.exit(4)

        output_path.write_bytes(result.output_bytes)
        click.echo(
            json.dumps(
                {
                    "pages_processed": result.summary.pages_processed,
                    "separation_name": result.summary.separation_name,
                    "plate_use": result.summary.plate_use,
                    "strategy_applied": result.summary.strategy_applied,
                    "output": str(output_path),
                },
                indent=2,
            )
        )
