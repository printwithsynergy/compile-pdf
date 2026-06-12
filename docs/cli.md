---
title: "CLI"
description: "Command reference for compile-pdf — producer subcommands plus utility commands for version, contract, health, schema, lineage, and CJD pipelines."
group: "Getting started"
order: 3
---

# CLI

`compile-pdf` is a Click-based console-script. The same code path the
HTTP API uses runs in-process when `COMPILE_API_BASE` is unset, so
local-mode output is byte-identical to the deployed surface.

Producer subcommands are **registered from the satellite packages**
(`compile_pdf_rewrite.cli`, `compile_pdf_marks.cli`,
`compile_pdf_impose.cli`, `compile_pdf_trap.cli`, `compile_pdf_cjd.cli`,
`compile_pdf_stream.cli`, `compile_pdf_white_underbase.cli`) when the
top-level group loads — a satellite absent from the build simply
doesn't contribute its subcommand. The full roster:
`compile-pdf {rewrite|marks|impose|trap|cjd|stream|white-underbase|lineage|schema|contract|health|version}`.

## Modes

- **Local mode (default).** No `COMPILE_API_BASE` env var set; the
  CLI invokes producer engines in-process.
- **HTTP mode.** Set `COMPILE_API_BASE=https://compile.example.com`
  and the CLI POSTs to the configured central or sidecar URL.

## Producer subcommands

### `compile-pdf rewrite`

```bash
compile-pdf rewrite --plan plan.json input.pdf output.pdf
```

Apply the 15 rewrite mutations described in
[`docs/rewrite.md`](./rewrite.md). Plan documents validate against
the `rewrite-plan` schema (`compile-pdf schema rewrite`).

### `compile-pdf marks`

```bash
compile-pdf marks --template tmpl.json input.pdf output.pdf
```

Stamp register / crop / color-bar / fold / proofing marks. Templates
support both programmatic (JSON-declared) and external (PDF / PNG /
SVG) ingestion.

### `compile-pdf impose`

```bash
compile-pdf impose --layout layout.json input.pdf output.pdf
```

Sheet-level step-and-repeat. Layout documents drive
`codex_pdf.geom.tile_grid` directly — no Compile-side layout math.

### `compile-pdf trap`

```bash
compile-pdf trap --policy policy.json input.pdf output.pdf
```

Ink-pair spread / choke. Engine selected via `COMPILE_TRAP_ENGINE`
env (`pure_python` | `ghostscript` | `external`).

### `compile-pdf white-underbase`

```bash
compile-pdf white-underbase --policy policy.json input.pdf output.pdf
```

Generate a white / underbase / varnish / foil plate as a named
separation. `--policy` is optional — omitting it uses the defaults
(`separation_name="White"`, `strategy="auto"`). `--no-verify` skips
the post-condition checks. See
[`docs/white-underbase.md`](./white-underbase.md).

### `compile-pdf stream`

```bash
compile-pdf stream --producer trap --payload request.json --output out.pdf
```

Run a producer's engine in-process and write the resulting PDF to
`--output` (use `-` for raw stdout). `--producer` is one of
`rewrite | marks | impose | trap | soft_proof`; `--payload` is the
same JSON body you would POST to `/v1/{producer}/apply`. Metadata
(sha256s, cache key, schema version) is printed as JSON. See
[`docs/stream.md`](./stream.md).

## Utility commands

### `compile-pdf version`

Prints package version, every producer schema version, the
codex-document schema version Compile is pinned to, the CJD schema
version, plus the Codex section versions Compile was built against:

```bash
$ compile-pdf version
{
  "compile_version": "0.7.0",
  "producer_schema_versions": {
    "rewrite": "1.0.0", "marks": "1.1.0", "impose": "1.1.0", "trap": "1.0.0",
    "soft_proof": "1.0.0", "stream": "1.0.0", "white_underbase": "1.0.0", "cjd": "1.0.0"
  },
  "compile_document_schema_version": "1.0.0",
  "cjd_schema_version": "1.0.0",
  "codex_section_versions": { "color": "1.1.0", "geom": "1.1.0", … },
  "codex_pdf_package_version": "1.21.1"
}
```

### `compile-pdf contract`

Mirrors `GET /v1/contract`. Use it as a single source of truth for
what the local Compile install can do.

### `compile-pdf health`

Mirrors `GET /v1/healthz` (instance_id, queue_depth, version_skew,
ghostscript availability, …). Pair with `--api-base` (planned) to
probe a remote instance.

### `compile-pdf schema {rewrite|marks|impose|trap|cjd}`

Dumps the JSON Schema document for the named producer (or for the
CJD envelope). Schemas live under `compile_pdf.schemas.v1.*`.

### `compile-pdf cjd --job job.json [--xml] output.pdf`

Executes a Compile Job Definition — a multi-producer envelope that
chains rewrite → marks → impose → trap in one call. `--xml` reads
the job document as XML (JDF / PJTF style) instead of JSON;
`--input` overrides the job's inline `input_pdf_b64` from a file;
`--trap-diff` writes the trap-diff artifact when the job has a trap
step.

### `compile-pdf lineage <id> [--chain]`

Reads a lineage record from the configured backend (memory / Redis
/ S3). `--chain` walks every producer step that contributed to the
final artifact, including the `retained_for_training` flag per step.

## Exit codes

- `0` — success
- `2` — invalid arguments
- `3` — schema validation failed
- `4` — engine failed (look at stderr / lineage)
- `5` — health / contract probe failed (used by `health`, `contract`)
