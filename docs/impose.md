---
title: "Impose producer"
description: "Sheet-level step-and-repeat. Layout solved by codex_pdf.geom.tile_grid; Compile drops cells onto sheets via pikepdf. No Compile-side layout math."
group: "Reference"
order: 12
---

# Impose producer

The impose producer ([`compile-pdf-impose`](https://github.com/printwithsynergy/compile-pdf-impose)) takes a 1-up input PDF and produces a sheet-level
imposition: step-and-repeat across columns × rows, with optional
work-and-turn / tumble back-side handling and bleed expansion.

The layout itself comes from Codex. Compile asks
`codex_pdf.geom.tile_grid()` for the per-cell placement plan, then
drops each cell onto the sheet with `pikepdf`. **No Compile-side
layout math** — that's a hard architectural rule, enforced by the
audit script.

## Layout schema

```json
{
  "schema_version": "1.0.0",
  "sheet": { "width_pt": 1782, "height_pt": 1224 },
  "cell":  { "width_pt":  612, "height_pt":  792 },
  "grid":  { "cols": 3, "rows": 2, "gutter_pt": 12 },
  "bleed_handling": "overlap",
  "cell_rotation": 0,
  "flip_per_row": false,
  "back_side": { "mode": "work-and-turn" }
}
```

Fields:

| Field | Values | Notes |
|---|---|---|
| `bleed_handling` | `overlap` / `mirror` / `none` | `overlap` = shared bleed across cells; `mirror` = reflected bleed; `none` = hard cut |
| `cell_rotation` | `0` / `90` / `180` / `270` | Per-cell rotation, applied uniformly |
| `flip_per_row` | `true` / `false` | Useful for fold-after layouts |
| `back_side.mode` | `work-and-turn` / `work-and-tumble` / `none` | How the back side relates to the front |

The combination of these fields exercises codex 1.4.0+'s GEOM
schema 1.1.0 extension (`cell_rotation`, `flip_per_row`,
`bleed_handling`, `CellPlacement`).

## Codex surface consumed

- `codex_pdf.geom.tile_grid` — the canonical step-and-repeat solver.
- `codex_pdf.geom.TileGrid` — input shape.
- `codex_pdf.geom.TileResult` — output container with
  `cell_placements: list[CellPlacement]`.
- `codex_pdf.geom.CellPlacement` — per-cell anchor + transform.

## Cell-extract round-trip

A determinism property unique to impose: extracting cell N from the
imposed sheet must reproduce the original Nth input page
byte-for-byte. The verifier runs this check in CI for every
`impose --layout` test fixture.

## Retention-for-training

`POST /v1/impose/apply` honours `X-Compile-Retain-For-Training`. See
[`operations/retention.md`](./operations/retention.md).

## Status

Shipped. `POST /v1/impose/apply` is live; cell-extract round-trip
verification runs in CI on every release.
