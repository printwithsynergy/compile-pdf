"""CompilePDF CLI — single ``compile-pdf`` console-script with subcommands.

Per spec §6.7 — producer subcommands plus utility commands (version,
contract, health, schema, lineage, cjd, cache, trap-diff, pipeline).

Two execution modes per subcommand: local (default when
``COMPILE_API_BASE`` is unset; in-process via codex_pdf.local_fallback
patterns) and HTTP (POSTs to the configured base).
"""

from __future__ import annotations

import json
import sys

import click

from compile_pdf.version import (
    CJD_SCHEMA_VERSION,
    CODEX_DOCUMENT_SCHEMA_VERSION_PIN,
    COMPILE_DOCUMENT_SCHEMA_VERSION,
    PRODUCER_SCHEMA_VERSIONS,
    VERSION,
)


@click.group(help="CompilePDF — the only writer in the PWS stack.")
@click.version_option(VERSION, "-V", "--version", prog_name="compile-pdf")
def cli() -> None:
    """Top-level group; subcommands attached below."""


@cli.command("version")
def version_cmd() -> None:
    """Print Compile package version + producer schema versions + Codex section versions."""
    payload = {
        "compile_version": VERSION,
        "producer_schema_versions": PRODUCER_SCHEMA_VERSIONS,
        "compile_document_schema_version": COMPILE_DOCUMENT_SCHEMA_VERSION,
        "cjd_schema_version": CJD_SCHEMA_VERSION,
    }
    try:
        from codex_pdf.color import COLOR_SCHEMA_VERSION
        from codex_pdf.geom import GEOM_SCHEMA_VERSION

        payload["codex_section_versions"] = {
            "color": COLOR_SCHEMA_VERSION,
            "geom": GEOM_SCHEMA_VERSION,
            "codex-document": CODEX_DOCUMENT_SCHEMA_VERSION_PIN,
        }
        from codex_pdf.version import VERSION as CODEX_VERSION

        payload["codex_pdf_package_version"] = CODEX_VERSION
    except ImportError:
        payload["codex_pdf_package_version"] = "unknown"
        payload["codex_section_versions"] = {}
    click.echo(json.dumps(payload, indent=2))


@cli.command("contract")
def contract_cmd() -> None:
    """Dump the full Compile contract (mirrors GET /v1/contract)."""
    try:
        # FastAPI handlers are async; run synchronously for CLI use.
        import asyncio

        from compile_pdf.api.main import contract_endpoint

        result = asyncio.run(contract_endpoint())
        click.echo(json.dumps(result.model_dump(), indent=2))
    except Exception as exc:
        click.echo(f"contract resolution failed: {exc}", err=True)
        sys.exit(5)


@cli.command("health")
def health_cmd() -> None:
    """Mirror GET /healthz against the configured API base or local in-process."""
    try:
        import asyncio

        from compile_pdf.api.main import healthz

        result = asyncio.run(healthz())
        click.echo(json.dumps(result.model_dump(), indent=2))
    except Exception as exc:
        click.echo(f"health probe failed: {exc}", err=True)
        sys.exit(5)


@cli.command("schema")
@click.argument("name", type=click.Choice(["rewrite", "marks", "impose", "trap", "cjd"]))
def schema_cmd(name: str) -> None:
    """Dump the JSON Schema for a producer or the CJD format.

    Schemas land in Phase 1.x as each producer ships; this command
    surfaces ``compile_pdf.schemas.v1.{name}.schema.json`` from package data.
    """
    click.echo(f"# schema/{name} — placeholder until {name} producer ships its plan_schema.py")
    sys.exit(0)


# Per-producer subcommands live in compile_pdf.{producer}.cli; they register
# themselves onto this group when imported. Phase 1.x lands rewrite first.
def _register_producer_subcommands() -> None:
    for module_name, _sub_name in (
        ("compile_pdf.rewrite.cli", "rewrite"),
        ("compile_pdf.marks.cli", "marks"),
        ("compile_pdf.impose.cli", "impose"),
        ("compile_pdf.trap.cli", "trap"),
        ("compile_pdf.cjd.cli", "cjd"),
        ("compile_pdf.stream.cli", "stream"),
        ("compile_pdf.white_underbase.cli", "white-underbase"),
    ):
        try:
            mod = __import__(module_name, fromlist=["register"])
            register = getattr(mod, "register", None)
            if callable(register):
                register(cli)
        except ImportError:
            # Producer not yet imported in this build; CLI subcommand absent.
            continue


_register_producer_subcommands()


def main() -> None:
    """Entry point referenced by ``[project.scripts] compile-pdf``."""
    cli()


if __name__ == "__main__":
    main()
