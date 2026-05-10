---
title: "Marks producer"
description: "Register / crop / color-bar / fold / proofing marks plus external mark-template ingestion. Geometry comes from codex_pdf.geom."
group: "Reference"
order: 11
---

# Marks producer

`compile_pdf.marks` stamps printer marks onto an input PDF. Twelve
v1.0 mark types across three categories, plus an external-template
ingestion mode.

## Mark types

### Production

- **Register marks** — four-corner cross-hairs for plate alignment.
- **Crop marks** — trim-box corner indicators.
- **Bleed marks** — bleed-extent indicators.
- **Color bars** — process + spot-ink ladder along the slug.

### Proofing

- **Fold marks** — score / fold position indicators.
- **Center marks** — sheet/section centerline tickmarks.
- **Slug text** — operator metadata strip (job ID, date, plate).
- **1-up proofing slug** — a single-cell proofing border.

### Universal

- **Cut marks** — shop-floor cut indicators.
- **Ink-key bars** — densitometric step wedge.
- **Tile-stitch marks** — large-format stitching guides.
- **Custom anchored shape** — operator-defined polygon at anchor.

## Ingestion modes

### Programmatic (JSON template)

Each mark is a JSON record:

```json
{
  "schema_version": "1.0.0",
  "marks": [
    { "type": "register",   "anchor": "trim_top_left", "offset_pt": 6 },
    { "type": "crop",       "anchor": "trim_corners",  "length_pt": 9 },
    { "type": "color_bar",  "anchor": "slug_top",      "inks": ["C","M","Y","K","PMS 185"] }
  ]
}
```

### External file

Operators can upload a PDF / PNG / SVG to be stamped at a named anchor:

```json
{ "type": "external", "file": "uploads/customer-watermark.pdf", "anchor": "trim_center" }
```

External files are treated opaquely — no compositing, no recoloring.

## Codex surface consumed

- `codex_pdf.geom.Box` — bounding rectangles for anchor lookup.
- `codex_pdf.geom.Point` — anchor points.
- `codex_pdf.geom.Polygon` — non-rectangular mark zones.
- `codex_pdf.geom.polygon_offset` — bleed expansion / contraction.
- `codex_pdf.geom.polygon_union` — multi-mark merging.

No Compile-side geometry math.

## Determinism guarantee

The same template + same input produces byte-identical output.
Reference rasters at 300 DPI lock visual fidelity in CI.

## Status

Skeleton. Lands in Phase 2 of
[`COMPILE-IMPL-PLAN.md`](../COMPILE-IMPL-PLAN.md).
