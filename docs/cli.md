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

## Utility commands

### `compile-pdf version`

Prints package version, every producer schema version, the
codex-document schema version Compile is pinned to, the CJD schema
version, plus the Codex section versions Compile was built against:

```bash
$ compile-pdf version
{
  "compile_version": "0.5.1",
  "producer_schema_versions": { "rewrite": "1.0.0", … },
  "compile_document_schema_version": "1.0.0",
  "cjd_schema_version": "1.0.0",
  "codex_section_versions": { "color": "1.1.0", "geom": "1.1.0", … },
  "codex_pdf_package_version": "1.8.1"
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

### `compile-pdf cjd apply <job.json|job.xml>`

Submits a Compile Job Definition — a multi-producer envelope that
chains rewrite → marks → impose → trap in one call. JSON and XML
(JDF / PJTF style) bodies are both accepted.

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
