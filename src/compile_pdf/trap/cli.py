"""Click subcommand registration for ``compile-pdf trap`` + ``trap-diff``."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from compile_pdf.trap.engine import TrapEngineError, apply_policy
from compile_pdf.trap.policy_schema import TrapPolicy, trap_policy_json_schema
from compile_pdf.trap.verify import verify_trap


def register(group: click.Group) -> None:
    """Attach the ``trap``, ``trap-schema``, and ``trap-diff`` subcommands."""

    @group.command("trap", help="Apply a trap policy to a PDF.")
    @click.option(
        "--policy",
        "policy_path",
        type=click.Path(exists=True, dir_okay=False, path_type=Path),
        required=True,
        help="JSON trap-policy document.",
    )
    @click.option(
        "--trap-diff",
        "diff_path",
        type=click.Path(dir_okay=False, path_type=Path),
        default=None,
        help="Write the trap-diff JSON artifact to this path.",
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
    def trap_cmd(
        policy_path: Path,
        input_path: Path,
        output_path: Path,
        diff_path: Path | None,
        verify: bool,
    ) -> None:
        policy_dict = json.loads(policy_path.read_text(encoding="utf-8"))
        try:
            policy = TrapPolicy.model_validate(policy_dict)
        except Exception as exc:
            click.echo(f"policy validation failed: {exc}", err=True)
            sys.exit(3)

        input_bytes = input_path.read_bytes()
        try:
            result = apply_policy(input_bytes, policy)
        except TrapEngineError as exc:
            click.echo(f"policy rejected: {exc}", err=True)
            sys.exit(4)

        if verify:
            check = verify_trap(input_bytes=input_bytes, result=result, policy=policy)
            if not check.passed:
                click.echo("verify failed:", err=True)
                for failure in check.failures:
                    click.echo(f"  - {failure}", err=True)
                sys.exit(4)

        output_path.write_bytes(result.output_bytes)
        if diff_path is not None:
            diff_path.write_text(json.dumps(result.trap_diff, indent=2), encoding="utf-8")

        click.echo(
            json.dumps(
                {
                    "engine": result.engine,
                    "engine_fingerprint": result.engine_fingerprint,
                    "operations_count": len(result.operations),
                    "pdf_sha256": result.pdf_sha256,
                    "output": str(output_path),
                    "trap_diff": str(diff_path) if diff_path else None,
                },
                indent=2,
            )
        )

    @group.command("trap-schema", hidden=True, help="Dump the trap-policy JSON Schema.")
    def trap_schema_cmd() -> None:
        click.echo(json.dumps(trap_policy_json_schema(), indent=2))

    @group.command(
        "trap-diff",
        help="Print a previously-emitted trap-diff JSON artifact (lineage lookup is Phase 5).",
    )
    @click.argument(
        "diff_path",
        type=click.Path(exists=True, dir_okay=False, path_type=Path),
    )
    def trap_diff_cmd(diff_path: Path) -> None:
        """Phase 4 ships file-based trap-diff inspection; lineage-id
        lookup lands in Phase 5 once the lineage store is wired."""
        click.echo(diff_path.read_text(encoding="utf-8"))
