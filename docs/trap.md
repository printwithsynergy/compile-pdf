---
title: "Trap producer"
description: "Ink-pair spread / choke trap with three engine slots — pure_python, ghostscript, external. Color resolution comes from codex_pdf.color; geometry from codex_pdf.geom.polygon_offset."
group: "Reference"
order: 13
---

# Trap producer

`compile_pdf.trap` applies ink-pair spread / choke trap to a PDF.
"Trap" compensates for press registration error by overlapping
adjacent inks slightly, so a thin white seam doesn't appear at the
boundary if the press drifts a hair off.

## Three engine slots

| Engine | Default? | Source | When to use |
|---|---|---|---|
| `pure_python` | yes (when Codex polygon_offset is available, i.e. codex 1.5+) | `codex_pdf.geom.polygon_offset` + `codex_pdf.color.*` | Default for all production traffic |
| `ghostscript` | no | Ghostscript via `[trap-gs]` extra | Bootstrap fallback, parity testing |
| `external` | no | Vendor (Esko / Heidelberg) via `[trap-external]` | Print-shops with vendor licensing |

Engine selected via `COMPILE_TRAP_ENGINE` env on the trap container.
Mismatched engines produce different output bytes — the
`engine_fingerprint` field in the lineage record makes that
observable.

## Policy schema

```json
{
  "schema_version": "1.0.0",
  "default_trap_width_pt": 0.144,
  "ink_pair_rules": [
    { "from": "PMS 185", "to": "K",       "width_pt": 0.144, "direction": "spread" },
    { "from": "Y",        "to": "PMS 185", "width_pt": 0.072, "direction": "choke"  }
  ],
  "neutral_density_source": "codex_extract",
  "engine": "auto",
  "output_trap_layer": true
}
```

`direction`:
- **spread** — the lighter ink expands into the darker.
- **choke**  — the lighter ink contracts away from the darker.

`output_trap_layer`:
- When `true` (default for the marketing demo), the trapped PDF includes a named
  **Optional Content Group (OCG) layer** called `Trap` that can be toggled on/off
  in any OCG-aware viewer (Acrobat, lens-pdf, etc.). This makes trap coverage
  visually inspectable without re-running the engine.
- Set to `false` to suppress the extra OCG and produce a flat-merged output PDF.

Direction defaults can be derived from neutral-density values, which
Compile reads from the Codex extract — no Compile-side density math.

## Codex surface consumed

- `codex_pdf.color.CodexSpotIntent` — spot-ink declaration on the input.
- `codex_pdf.color.resolve_spot_swatch_color` — intent → device color.
- `codex_pdf.color.delta_e_2000` — color-difference metric used to
  verify trap quality (the trapped ink pair must satisfy a delta_e
  budget).
- `codex_pdf.geom.polygon_offset` — spread / choke offsets on the
  ink-pair boundary polygon.

No Compile-side color or geometry math.

### Sparse field projection (Codex 1.18.0+)

The trap producer only needs `color_spaces` and `spot_colors` from
the Codex extract. When calling the Codex sidecar, pass
`X-Codex-Fields: color_spaces` to skip all other extractors and
receive only the colour-world section. This cuts the sidecar
round-trip by ~40 % on typical files:

```http
POST /v1/extract HTTP/1.1
X-Codex-Fields: color_spaces
Content-Type: application/pdf
```

```ts
const doc = await codex.extract(pdfBytes, { fields: ["color_spaces"] });
```

## trap-diff artifact

Every `trap apply` emits a JSON artifact describing every trap
operation applied — which ink pair, which page, which polygon, which
engine fingerprint, what delta_e was achieved. Surfaced via:

```bash
compile-pdf trap-diff <lineage_id>
```

Lineage references the engine fingerprint, so a trap-diff can be
re-verified against the same engine version even months later.

## Determinism guarantee

`pure_python` engine is bit-deterministic. `ghostscript` and
`external` are deterministic per-engine-fingerprint but not
cross-engine — switching engines on the same input produces a
different (still valid) output PDF. The lineage record makes the
choice explicit.

## Status

Shipped. `POST /v1/trap/apply` is live; all three engine slots
(`pure_python`, `ghostscript`, `external`) are wired, with
`pure_python` as the default. Real PDF ink-pair adjacency
extraction and non-rectangular trap polygons (via codex
`polygon_offset`) shipped alongside Codex 1.7.1+.

## Retention-for-training

`POST /v1/trap/apply` honours `X-Compile-Retain-For-Training`. See
[`operations/retention.md`](./operations/retention.md).
