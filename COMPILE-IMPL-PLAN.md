# COMPILE-IMPL-PLAN

> **Status:** Working draft, synthesized from signals already in the
> repo (CHANGELOG, README, version.py, cache.py, the producer module
> docstrings, the `compile-pdf-marketing` 0.1.0 changelog entry, and
> the `consume_surface_audit.py` ban list). The README and the
> marketing site reference this file as if it exists; it now does.
> Revise as the real one.

## Why this plan exists

CompilePDF is the **only writer** in the Print With Synergy stack.
Codex tells the truth about a PDF (read-only); Compile writes the
bytes. The package has shipped its engine chassis (FastAPI app,
health/contract endpoints, request-id middleware, cache-key composer,
audit script) but **none of the four producers — `rewrite`, `marks`,
`impose`, `trap` — have any implementation yet.** They are docstring
stubs holding a schema-version constant.

This plan walks the producers from skeleton to v1.0 in dependency
order, with each phase ending at a hard gate that proves the producer
is real before the next one starts.

## Architectural invariants (locked)

These invariants are mechanically enforced by
`scripts/consume_surface_audit.py` and are not up for renegotiation
inside this plan. New phases inherit them:

1. **Compile is the only writer.** Codex stays read-only — its
   `produce_surface_audit.py` enforces.
2. **No re-implementation of Codex primitives.** Geometry (`Box`,
   `Matrix`, `Path`, `Polygon`, `TileGrid`, `polygon_*`) and color
   (`resolve_spot_swatch_color`, `match_nearest_pantone`,
   `delta_e_2000`, etc.) are consumed through `codex_pdf.geom` and
   `codex_pdf.color`. No private-data imports.
3. **Determinism.** Same input + same plan + same engine fingerprint
   → same SHA-256 output. The cache-key composer in
   `src/compile_pdf/cache.py` is the cross-language canonical form.
4. **Schema versioning is per-producer.** `rewrite` can ship a
   `1.1.0` feature without forcing `marks` / `impose` / `trap` to
   bump (`src/compile_pdf/version.py`).
5. **Compile builds against a Codex section pin.** Section bumps in
   Codex auto-invalidate affected cached outputs (cache key includes
   `color_schema_version` and `geom_schema_version`).

## Surface dependency map

| Producer | Codex surfaces consumed | Compile-side libs |
|---|---|---|
| `rewrite` | `codex_pdf.CodexDocument` (read-side context) | `pikepdf` (object-tree mutator), local validators |
| `marks` | `codex_pdf.geom.{Box, Point, Polygon, polygon_offset, polygon_union}` | `pikepdf`, `Pillow` |
| `impose` | `codex_pdf.geom.{tile_grid, TileGrid, TileResult, CellPlacement}` | `pikepdf` |
| `trap` | `codex_pdf.color.{CodexSpotIntent, resolve_spot_swatch_color, delta_e_2000}`, `codex_pdf.geom.polygon_offset` | `pikepdf`, optional `ghostscript` (via `[trap-gs]` extra), optional vendor (via `[trap-external]`) |

## Phase 0 — Engine chassis hardening

**Status:** mostly shipped in 0.1.0. Two open items.

* **0.A.** Remove the stale `# type: ignore[attr-defined]` from
  `src/compile_pdf/cli/__init__.py` line 50 — `codex_pdf.version.VERSION`
  is a real symbol.
* **0.B.** Replace the `getattr(codex_pdf, "__version__", "unknown")`
  fallback in `src/compile_pdf/api/main.py` line 76 with a direct
  attribute read. `codex_pdf.__version__` is a published symbol.
  Defensive `"unknown"` masks a real broken-import condition.
* **0.C.** Add `tests/test_codex_consumption.py` — a smoke test that
  asserts `codex_pdf.__version__` parses as semver and is
  `>= 1.4.2`, plus that `COLOR_SCHEMA_VERSION` and `GEOM_SCHEMA_VERSION`
  import. Locks the published-surface contract in CI.
* **0.D.** Producer module surface hookup (Phase 0 finalizer). Each
  of `compile_pdf/{rewrite,marks,impose,trap}/__init__.py` adds a
  type-only import block referencing the codex symbols it will
  consume, and re-exports the symbols it depends on so downstream
  engine code can `from compile_pdf.<producer> import …`. One
  surface test per producer asserts the imports resolve.

**Phase 0 gate:** `pytest -q` passes, the audit script passes, `pip
install -e .[dev,geom]` succeeds against the codex-pdf 1.7.0 wheel.

## Phase 1 — Rewrite producer

**Goal:** ship the 15 rewrite mutations (spec §2.1 — see
`src/compile_pdf/rewrite/__init__.py` docstring) end-to-end through
`pikepdf`, with the deterministic-bytes guarantee verified.

* **1.1 plan_schema.** JSON Schema document and Pydantic
  validator for `rewrite-plan` documents. Lives at
  `src/compile_pdf/rewrite/plan_schema.py`. Bumps
  `REWRITE_SCHEMA_VERSION`.
* **1.2 engine.** `src/compile_pdf/rewrite/engine.py` — `pikepdf`
  driver implementing the mutations grouped by category:
  - **Structural:** OCG flips, page lifecycle ops (insert / delete
    / reorder / rotate), trim/bleed box adjustments, page-label
    surgery.
  - **Hygiene:** metadata patches (Info dict + XMP), color-space
    swaps (DeviceRGB → DeviceCMYK pin), strip JS, strip embedded
    files, normalize page-tree fan-out.
  - **Lifecycle:** PDF/X version pin, Producer/Creator stamping.
* **1.3 verify.** Three-layer post-condition checks (spec §2.3):
  - **Layer 1 — Schema:** the output PDF's structural shape is
    parseable by Codex's reader and matches the requested mutation.
  - **Layer 2 — Determinism:** SHA-256(output) is stable across two
    independent runs of the same plan + input.
  - **Layer 3 — Nothing-else-touched:** any object NOT named in the
    plan must be byte-identical to the input.
* **1.4 api.** `src/compile_pdf/rewrite/api.py` — `router: APIRouter`
  exposing `POST /v1/rewrite/apply` with the standard envelope
  (`pdf_sha256`, `pre_rendered`, `lineage_id`, `cache_hit`).
* **1.5 cli.** `src/compile_pdf/rewrite/cli.py` — `register(group)`
  attaches the `compile-pdf rewrite` subcommand to the top-level CLI.
* **1.6 tests.** `tests/test_rewrite_*.py` — one test per mutation
  category, plus a determinism test that runs the same plan twice
  and compares `pdf_sha256`.

**Phase 1 gate:** all 15 mutations green; the example plan in
`docs/producers/rewrite.md` round-trips through the API; the audit
script still passes; `compile-pdf rewrite --plan plan.json in.pdf
out.pdf` works in local mode.

## Phase 2 — Marks producer

**Goal:** ship the 12 v1.0 mark types (spec §3.1 — see
`src/compile_pdf/marks/__init__.py` docstring) plus external-template
ingestion.

* **2.1 plan_schema.** `marks-template` document at
  `src/compile_pdf/marks/template_schema.py`. Two ingestion modes:
  - **Programmatic:** `{type: "register", anchor: "trim_top_left", offset_pt: 6, …}`
  - **External file:** `{type: "external", file: "path/to.pdf"}` for
    tenant-uploaded PDF/PNG/SVG stamped at anchor.
* **2.2 marks library.** `src/compile_pdf/marks/library.py` — the
  12 mark types as functions returning `pikepdf.Object` content
  streams + a `Box` at the right anchor. Geometry primitives are
  imported from `codex_pdf.geom` exclusively.
* **2.3 engine.** `src/compile_pdf/marks/engine.py` — composes the
  marks layer over the input PDF (page-by-page or single-stamp).
* **2.4 verify.** Three layers as in Phase 1, plus a marks-specific
  Layer 4: the rendered marks layer is bit-identical to a reference
  raster at 300 DPI for known templates.
* **2.5 api / cli.** `compile-pdf marks --template tmpl.json in.pdf
  out.pdf`; `POST /v1/marks/apply`.
* **2.6 tests.** Per-mark-type unit tests + one external-template
  ingestion test (PDF stamp from `tests/fixtures/external_marks.pdf`).

**Phase 2 gate:** all 12 marks visually correct; external-template
mode works for PDF and PNG; reference-raster comparison locked in CI.

## Phase 3 — Impose producer

**Goal:** ship sheet-level step-and-repeat with work-and-turn /
tumble support, consuming Codex's `tile_grid`.

* **3.1 layout_schema.** `impose-plan` document at
  `src/compile_pdf/impose/layout_schema.py`. Fields: sheet size,
  cell size, columns, rows, gutter, bleed_handling
  (`overlap` / `mirror` / `none`), cell_rotation, flip_per_row,
  back-side mode (`work-and-turn` / `work-and-tumble` / `none`).
* **3.2 engine.** `src/compile_pdf/impose/engine.py` — calls
  `codex_pdf.geom.tile_grid()` to compute `CellPlacement[]`, then
  drops each placement onto the sheet with `pikepdf`. **No
  Compile-side layout math** — every cell position comes from
  Codex.
* **3.3 verify.** Layer 1 (schema), Layer 2 (determinism), Layer 3
  (nothing-else-touched on each per-cell page extract), plus a
  Layer 5 specifically for impose: the inverse — extracting cell N
  from the imposed sheet must reproduce the original Nth input page
  byte-for-byte.
* **3.4 api / cli.** `compile-pdf impose --layout layout.json in.pdf
  out.pdf`; `POST /v1/impose/apply`.
* **3.5 tests.** Single-cell, 2x2 step-and-repeat, work-and-turn,
  bleed-handling=mirror.

**Phase 3 gate:** Codex `GEOM_SCHEMA_VERSION` >= `1.1.0` (which is
already shipped in codex 1.7.0); 4-up work-and-turn round-trips with
each cell extractable.

## Phase 4 — Trap producer

**Goal:** ship ink-pair spread/choke trap with three engine slots,
default `pure_python`.

* **4.1 policy_schema.** `trap-policy` document at
  `src/compile_pdf/trap/policy_schema.py`. Fields: trap_width_pt,
  ink_pair_rules (per-ink-pair spread vs choke), neutral_density
  source (defaults to Codex extract), engine override.
* **4.2 engines.**
  - `src/compile_pdf/trap/engines/pure_python.py` — uses
    `codex_pdf.geom.polygon_offset` + spot-color resolution from
    `codex_pdf.color.resolve_spot_swatch_color`. The default once
    Codex 1.5+ ships (already shipped — codex is at 1.7.0).
  - `src/compile_pdf/trap/engines/ghostscript.py` — gated by the
    `[trap-gs]` extra. Bootstrap fallback if the pure-python engine
    has gaps.
  - `src/compile_pdf/trap/engines/external.py` — vendor (Esko /
    Heidelberg) integration. Requires licensing; ships disabled.
* **4.3 selector.** `src/compile_pdf/trap/__init__.py` reads
  `COMPILE_TRAP_ENGINE` env var (`pure_python` | `ghostscript` |
  `external`); raises a clear error if the requested engine isn't
  installed.
* **4.4 verify.** Layer 1 (schema), Layer 2 (determinism is
  engine-fingerprint-scoped — pure_python is deterministic;
  ghostscript and external publish their fingerprint to lineage but
  don't claim cross-engine determinism), Layer 3 (only spot-ink
  pairs in policy were trapped). Plus a trap-specific Layer 6:
  delta_e_2000 of trapped ink pair against expected spread/choke
  target stays within tolerance.
* **4.5 trap-diff artifact.** Per spec §5.7 — a JSON artifact
  describing every trap operation applied (which ink pair, which
  page, which polygon, which engine fingerprint). Surfaced via
  `compile-pdf trap-diff <lineage_id>`.
* **4.6 api / cli.** `compile-pdf trap --policy policy.json in.pdf
  out.pdf`; `POST /v1/trap/apply`.

**Phase 4 gate:** pure_python engine traps a known
two-spot-ink fixture with delta_e within tolerance; trap-diff
artifact populates; lineage records the engine fingerprint.

## Phase 5 — CJD pipeline + lineage

**Goal:** Compile Job Definition (CJD) — JSON or XML envelope
bundling a multi-producer job (rewrite → marks → impose → trap)
into one submission, plus the lineage trail across the chain.

* **5.1 cjd schema.** `src/compile_pdf/cjd/schema.py` — JSON / XML
  envelope (per spec §4.5.2). XML branch uses `defusedxml`.
* **5.2 orchestrator.** Sequences producers in dependency order
  (rewrite → marks → impose → trap), threading `lineage_id` and
  cache keys through.
* **5.3 lineage store.** `src/compile_pdf/lineage/` — S3-backed
  records (one per producer step), Redis index for fast lookup,
  `compile-pdf lineage <id> [--chain]` CLI.
* **5.4 api.** `POST /v1/cjd/apply`; `GET /v1/lineage/{id}`.
* **5.5 trap-diff hooked into pipeline.** Per spec §5.7, trap-diff
  is automatically generated for any CJD job that contains a trap
  step.

**Phase 5 gate:** a four-producer CJD round-trips end to end; lineage
chain is queryable; queue-depth surfaces correctly in
`/v1/healthz.queue_depth` (Celery wired in this phase).

## Cross-phase concerns

* **Auth modes** (`COMPILE_AUTH_MODE`): `none`, `bearer`, `api-key`,
  `internal`, `basic` — already shipped in 0.1.0; each phase's API
  router inherits the existing middleware.
* **Multi-instance / version-skew:** every phase keeps the
  `version_skew` boolean in `/v1/healthz` honest by routing
  `_resolve_codex_section_versions()` through the live HttpClient
  contract guard once Phase 4 lights up the Codex client.
* **Cache invalidation:** the cache-key composer in
  `src/compile_pdf/cache.py` already includes every section version
  that matters; producers don't need to add their own keys.
* **Marketing surfacing:** each phase ends with a
  `compile-pdf-marketing/src/content/changelog/<version>.md` entry
  + (if the producer's demo route is ready) lifting the
  `coming-soon` flag on the relevant `/demo/<producer>` page.

## Open questions for the user

1. **Real spec.** The producer docstrings reference spec sections
   (§2.1, §3.1, §4.1, §5.1–§5.7, §6.2, etc.) that imply a
   `COMPILE-DESIGN-SPEC.md` exists. It does not. Either the spec is
   tribal knowledge that needs to be written down, or it lives
   somewhere else. **Confirm the source of truth before Phase 1
   starts** — otherwise we'll bake assumptions into engine code.
2. **Trap engine default.** Plan assumes `pure_python` becomes the
   default once Codex's `polygon_offset` ships. Codex is at 1.7.0
   so it's shipped; should `pure_python` be default in Phase 4
   from day one, or stage it behind a feature flag?
3. **CJD format priority.** JSON-only first, or JSON + XML in
   parallel? Spec §4.5.2 says both; XML is the print-shop
   integration story.

## Reference: file layout once all phases land

```
src/compile_pdf/
├── api/         # FastAPI app + router mounting (Phase 0 ✓)
├── cli/         # Top-level CLI group (Phase 0 ✓)
├── cache.py     # Cache-key composer (Phase 0 ✓)
├── version.py   # Version + schema constants (Phase 0 ✓)
├── rewrite/     # Phase 1
│   ├── api.py
│   ├── cli.py
│   ├── engine.py
│   ├── plan_schema.py
│   └── verify.py
├── marks/       # Phase 2
│   ├── api.py
│   ├── cli.py
│   ├── engine.py
│   ├── library.py
│   ├── template_schema.py
│   └── verify.py
├── impose/      # Phase 3
│   ├── api.py
│   ├── cli.py
│   ├── engine.py
│   ├── layout_schema.py
│   └── verify.py
├── trap/        # Phase 4
│   ├── api.py
│   ├── cli.py
│   ├── engines/
│   │   ├── pure_python.py
│   │   ├── ghostscript.py
│   │   └── external.py
│   ├── policy_schema.py
│   └── verify.py
├── cjd/         # Phase 5
│   ├── api.py
│   ├── orchestrator.py
│   └── schema.py
└── lineage/     # Phase 5
    ├── api.py
    ├── records.py
    └── store.py
```
