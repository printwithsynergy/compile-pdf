---
title: "Architecture"
description: "How CompilePDF splits four producers across one Python package, four containers, and one Codex read-side authority."
group: "Getting started"
order: 2
---

# Architecture

CompilePDF is the **only writer** in the Print With Synergy stack.
Codex tells the truth of a PDF (read-only); Compile writes the bytes.
Four producers ship under one Python package and one FastAPI app, one
container per producer in production.

## Boundary

- **Compile writes.** `pikepdf.new()`, `Pdf.save()`, content-stream
  emission, page-tree mutation. All happens inside Compile.
- **Codex describes.** Document model, color resolver, geometry
  primitives. Compile **never** re-implements these — the
  `scripts/consume_surface_audit.py` AST walker fails CI on attempts.
- **Determinism is contractual.** Same input + same plan + same
  engine fingerprint → same SHA-256 output bytes.

## The four producers

| Producer | Codex surface consumed | What it writes |
|---|---|---|
| `compile_pdf.rewrite` | `CodexDocument` | Object-tree mutations on a single PDF: OCG flips, metadata patches, color-space swaps, hygiene strips, page lifecycle ops |
| `compile_pdf.marks` | `Box`, `Point`, `Polygon`, `polygon_offset`, `polygon_union` | Register / crop / color-bar / fold / proofing marks; external mark-template ingestion |
| `compile_pdf.impose` | `tile_grid`, `TileGrid`, `TileResult`, `CellPlacement` | Sheet-level step-and-repeat; work-and-turn / tumble; bleed handling |
| `compile_pdf.trap` | `CodexSpotIntent`, `resolve_spot_swatch_color`, `delta_e_2000`, `polygon_offset` | Ink-pair spread / choke trap with three engine slots (`pure_python` / `ghostscript` / `external`) |

## Deployment topology

Per producer container in production. The same FastAPI app boots in
every container; `COMPILE_PRODUCER` selects which router mounts:

- `COMPILE_PRODUCER=rewrite` → only `/v1/rewrite/*`
- `COMPILE_PRODUCER=marks`   → only `/v1/marks/*`
- `COMPILE_PRODUCER=impose`  → only `/v1/impose/*`
- `COMPILE_PRODUCER=trap`    → only `/v1/trap/*`
- `COMPILE_PRODUCER=all`     → all four (used by `compile-sidecar`)

Shared infrastructure (one of each per Railway project):

- **Redis** — Celery broker + cache backend.
- **S3-compatible bucket** — lineage records + output artifacts.
- **Codex sidecar** — read-side `/v1/extract` for plan validation
  context. Each producer requests only the Codex fields it needs via
  `X-Codex-Fields` (Codex 1.18.0+); see
  [`trap.md`](./trap.md#sparse-field-projection-codex-1180) for an
  example. Omitting the header returns the full document (backward
  compatible).

## Cache-key composition

Per `src/compile_pdf/cache.py`, the per-job cache key concatenates
(alphabetical-by-name, `|` separator, then SHA-256):

1. `codex_document_schema_version`
2. `codex_pdf_package_version`
3. `color_schema_version`
4. `geom_schema_version`
5. `compile_version`
6. `producer`
7. `sha256(canonical_plan)`
8. `sha256(input_bytes)`

Codex section bumps auto-invalidate affected cached outputs. This is
load-bearing — operators rely on it for clean rollouts.

## Multi-instance + version skew

Compile may run multiple instances of the same producer in parallel
(scale-out for queue depth, multi-region for latency). Two instances
of the same producer **must** produce byte-identical output for the
same input + plan. The `version_skew` boolean in `/v1/healthz` flips
true if the codex section versions Compile was built against drift
from what the live Codex publishes.

## Audit invariants

`scripts/consume_surface_audit.py` walks every Python file in the
repo and fails CI on:

- `import pyclipr` — must go through `codex_pdf.geom.polygon_*`
- `from codex_pdf.color.data ...` — must use the resolver surface
- defining a function named `resolve_spot_swatch_color`,
  `match_nearest_pantone`, `load_pantone_reference`, `load_inkbook`
- defining a class named `Box`, `Matrix`, `Path`, `TileGrid`,
  `TileResult`, `MarksZone`, `CellPlacement`, `CodexDocument`,
  `CodexPage`, `CodexPageBoxes`, `CodexPageResourcesRef`,
  `CodexInfoDict`, `CodexColorSpace`, `CodexSpotColorant`,
  `CodexOCG`, `CodexTrapEvidence`, `CodexDocumentSummary`

These names are reserved Codex types. Compile imports them; it never
defines them.
