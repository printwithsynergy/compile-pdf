"""Click subcommand registration for ``compile-pdf stream``.

Local mode reads the input PDF + producer payload JSON from disk,
runs the dispatch engine in-process, and writes the resulting PDF
to ``--output`` (or stdout if ``--output -``). Metadata is dumped
to stderr as JSON so a ``> out.pdf`` redirect keeps the PDF clean.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import cast

import click

from compile_pdf.stream.engine import StreamEngineError, dispatch_stream
from compile_pdf.stream.schema import SUPPORTED_PRODUCERS, ProducerName


def register(group: click.Group) -> None:
    """Attach the ``stream`` subcommand to the top-level CLI group."""

    @group.command("stream", help="Run a producer's engine and stream the PDF locally.")
    @click.option(
        "--producer",
        type=click.Choice(SUPPORTED_PRODUCERS, case_sensitive=False),
        required=True,
        help="Underlying producer to invoke.",
    )
    @click.option(
        "--payload",
        "payload_path",
        type=click.Path(exists=True, dir_okay=False, path_type=Path),
        required=True,
        help=(
            "JSON file matching the producer's /v1/{producer}/apply "
            "request body (already-base64'd input_pdf_b64 inline)."
        ),
    )
    @click.option(
        "--output",
        "output_path",
        type=click.Path(dir_okay=False, path_type=Path),
        required=True,
        help="Destination for the resulting PDF. Use '-' to write to stdout.",
    )
    def stream_cmd(
        producer: str,
        payload_path: Path,
        output_path: Path,
    ) -> None:
        try:
            payload = json.loads(payload_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            click.echo(f"failed to read payload: {exc}", err=True)
            sys.exit(3)

        # Click's Choice validator already restricts `producer` to
        # SUPPORTED_PRODUCERS, so the cast is safe — it just lets
        # mypy see the narrowed type at the dispatch_stream call site.
        try:
            result = dispatch_stream(cast(ProducerName, producer), payload)
        except StreamEngineError as exc:
            click.echo(f"dispatch failed: {exc}", err=True)
            sys.exit(4)

        if str(output_path) == "-":
            # Click resolves ``-`` into a Path('-') — we want raw
            # binary stdout, not a file at literal path "-".
            sys.stdout.buffer.write(result.output_bytes)
        else:
            output_path.write_bytes(result.output_bytes)

        click.echo(
            json.dumps(
                {
                    "producer": result.metadata.producer,
                    "pdf_sha256": result.metadata.pdf_sha256,
                    "input_sha256": result.metadata.input_sha256,
                    "cache_key": result.metadata.cache_key,
                    "schema_version": result.metadata.schema_version,
                    "compile_version": result.metadata.compile_version,
                    "bytes": len(result.output_bytes),
                    "output": str(output_path),
                },
                indent=2,
            ),
            err=True,
        )
