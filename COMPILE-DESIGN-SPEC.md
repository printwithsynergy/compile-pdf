# COMPILE-DESIGN-SPEC

> **Status:** Stub. The producer module docstrings, `cache.py`, and
> `api/main.py` reference this document by section number (§1.2,
> §1.4, §1.6, §1.6a, §1.9a, §1.10, §1.11a, §1.11b, §1.11c, §2.1,
> §2.2, §2.3, §3.1, §4.1, §4.5.2, §5.1–§5.7, §6.2, §6.7) but the
> document itself was never committed. This file holds the section
> headers so the references resolve and so future PRs have a place
> to drop the actual spec content. **Every section below is a TODO
> until the user fills it in or points at the canonical source.**

## §1 Engine architecture

### §1.2 — Mono-package layout

> *(Producer sub-packages under one `compile_pdf` mono-package; per
> producer container in production. Filled by Phase 0. See
> `src/compile_pdf/__init__.py` and the directory layout in
> `COMPILE-IMPL-PLAN.md`.)*

### §1.4 — Per-producer container topology

> *(Each producer ships its own Docker image / Railway service
> selecting via `COMPILE_PRODUCER` env. Routers share the FastAPI
> app at the code level. Filled by Phase 0.)*

### §1.6 — Cache-key components

> *(Already implemented in `src/compile_pdf/cache.py`. The
> composition order, dropped-keys policy, and round-half-even number
> normalization belong here.)*

### §1.6a — Cache-key composition rationale

> *(Why each component is in the key. See the docstring on
> `compute_cache_key()`.)*

### §1.9a — Sibling sidecars (read / write split)

> *(Codex sidecar + Compile sidecar in the marketing repo; shared
> Redis. See `compile-pdf-marketing/codex-sidecar/` and
> `compile-pdf-marketing/compile-sidecar/`.)*

### §1.10 — Auth modes

> *(`none`, `bearer`, `api-key`, `internal`, `basic`. See
> `src/compile_pdf/api/auth.py`.)*

### §1.11a — HealthResponse extension

> *(Compile's `/v1/healthz` shape extends Codex's. Producer,
> instance_id, queue_depth, version_skew. See `api/main.py`.)*

### §1.11b — Trap exception (ghostscript engine)

> *(Trap is the only producer allowed to declare external engine
> dependencies — pure_python is default once Codex 1.5+ lands;
> ghostscript is the bootstrap fallback gated by `[trap-gs]` extra.)*

### §1.11c — Compile contract guard

> *(Client-side check that compares the codex section versions
> Compile was built against vs. what the live Codex publishes;
> surfaces as `version_skew` boolean.)*

## §2 Rewrite producer

### §2.1 — 15 in-scope mutations

> *(Structural / hygiene / lifecycle / page-level. See producer
> docstring in `src/compile_pdf/rewrite/__init__.py`.)*

### §2.2 — Plan canonicalization

> *(Pure function on rewrite plans; sort + normalize numbers + drop
> decorative keys. Shipped in `cache.canonicalize_plan`.)*

### §2.3 — Three-layer post-condition checks

> *(Layer 1 schema, Layer 2 determinism, Layer 3 nothing-else-touched.
> Filled by Phase 1.)*

## §3 Marks producer

### §3.1 — 12 v1.0 essential mark types

> *(Production / proofing / universal categories. Programmatic +
> external-file ingestion. Filled by Phase 2.)*

## §4 Impose producer

### §4.1 — Sheet-level step-and-repeat

> *(Consumes `codex_pdf.geom.tile_grid`. No Compile-side layout math.
> Work-and-turn / tumble. Filled by Phase 3.)*

### §4.5.2 — CJD format

> *(Compile Job Definition — JSON / XML envelope bundling a
> multi-producer job. Filled by Phase 5.)*

## §5 Trap producer

### §5.1 — Trap producer scope

### §5.2 — Ink-pair spread / choke

### §5.3 — Engine slots (pure_python / ghostscript / external)

### §5.4 — Engine fingerprint

### §5.5 — Determinism per engine

### §5.6 — Neutral-density source (Codex extract)

### §5.7 — trap-diff artifact

> *(All Phase 4. Detail belongs here once the engines land.)*

## §6 Contract surface

### §6.2 — Per-producer schema versioning

> *(Independent semver bumps; aggregate exposed via
> `/v1/contract.producer_schema_versions`. Shipped in
> `src/compile_pdf/version.py`.)*

### §6.7 — CLI subcommand surface

> *(Producer subcommands plus utility commands: version, contract,
> health, schema, lineage, cjd, cache, trap-diff, pipeline. See
> `src/compile_pdf/cli/__init__.py`.)*
