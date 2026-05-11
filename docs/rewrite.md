---
title: "Rewrite producer"
description: "Object-tree mutations on a single PDF — OCG flips, metadata patches, color-space swaps, hygiene strips, page lifecycle ops. No content-stream surgery."
group: "Reference"
order: 10
---

# Rewrite producer

`compile_pdf.rewrite` applies object-tree mutations to a single PDF
input. The output is a single PDF with the requested mutations
applied and **everything else byte-identical** to the input — that
"nothing else touched" guarantee is mechanically verified.

## What it does

15 in-scope mutations grouped by category:

### Structural

- **OCG flips** — toggle Optional Content Group visibility per layer.
- **Page lifecycle ops** — insert / delete / reorder / rotate pages.
- **Box adjustments** — trim, bleed, art, crop, media boxes.
- **Page-label surgery** — fix `1, 2, i, ii, …` numbering.

### Hygiene

- **Metadata patches** — Info dict + XMP. Strip / set / replace.
- **Color-space swaps** — DeviceRGB → DeviceCMYK pin (or inverse).
- **Strip JS** — remove `/JavaScript` actions and `/JS` keys.
- **Strip embedded files** — remove `/EmbeddedFiles`.
- **Normalize page-tree fan-out** — flatten deep trees.

### Lifecycle

- **PDF/X version pin** — declare conformance level.
- **Producer / Creator stamping** — operator provenance.

## What it doesn't do

Out of scope, gated by a hard STOP-gate in the audit:

- Content-stream surgery
- Font subsetting / embedding changes
- Image recompression
- Color reflow

These belong to a future producer (or never — see the design spec
for the rationale).

## Plan schema

A rewrite plan is a JSON document. Top-level fields:

```json
{
  "schema_version": "1.0.0",
  "ops": [
    { "op": "ocg_flip",          "layer": "Bleed",            "visible": false },
    { "op": "metadata_set",      "key": "Title",              "value": "Job 12345" },
    { "op": "metadata_strip",    "keys": ["JS", "JavaScript"] },
    { "op": "page_rotate",       "page": 1, "degrees": 90 },
    { "op": "box_set",           "page": 2, "box": "TrimBox",  "rect_pt": [0, 0, 612, 792] }
  ]
}
```

Schema documented at `compile-pdf schema rewrite`. Validation runs
client-side (CLI) and server-side (`POST /v1/rewrite/apply`).

## Determinism guarantee

Same input + same plan produces byte-identical output (verified by
SHA-256). The cache key composer (`src/compile_pdf/cache.py`)
includes the canonical plan hash, so re-running an identical request
short-circuits to the cached output.

## Codex surface consumed

- `codex_pdf.CodexDocument` — Compile reads the document to validate
  page-index references in the plan ("you can't delete page 12 of a
  10-page PDF").

No re-implementation; the audit script enforces.

## Retention-for-training

`POST /v1/rewrite/apply` honours the `X-Compile-Retain-For-Training`
header. When truthy and `COMPILE_RETAIN_BUCKET` is configured, the
call's input/output/result triplet is persisted to S3-compatible
storage with a TTL tag. The decision is reflected on the lineage
record. See [`operations/retention.md`](./operations/retention.md).

## Status

Shipped. The mutation engine (`pikepdf`) + three-layer verify +
`POST /v1/rewrite/apply` are live; determinism is enforced in CI.
