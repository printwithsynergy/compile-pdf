---
title: "Contract"
description: "Compile's published contract surface — endpoints, per-producer schema versions, and the Codex sections Compile pins against."
group: "Reference"
order: 1
---

# Contract

This document is the canonical pointer for Compile's contract
surface, the versioning policy that governs each producer, and how
the cache key composes from Codex's section versions.

## HTTP contract endpoints

The FastAPI app mounts at the configured base URL (Railway service
domain or custom apex). Auth modes are documented in
[`deploy.md`](./deploy.md).

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/healthz` | Liveness + identity (alias of `/v1/healthz`) |
| `GET` | `/v1/healthz` | Liveness + identity + version skew |
| `GET` | `/v1/version` | Bare version string |
| `GET` | `/v1/contract` | Full contract surface (this document, JSON) |
| `GET` | `/v1/schema/{name}` | JSON Schema for a producer plan |
| `GET` | `/metrics` | Prometheus exposition |
| `POST` | `/v1/rewrite/apply` | Apply a rewrite plan (Phase 1) |
| `POST` | `/v1/marks/apply` | Apply a marks template (Phase 2) |
| `POST` | `/v1/impose/apply` | Apply an impose layout (Phase 3) |
| `POST` | `/v1/trap/apply` | Apply a trap policy (Phase 4) |
| `POST` | `/v1/cjd/apply` | Apply a multi-producer CJD envelope (Phase 5) |
| `GET` | `/v1/lineage/{id}` | Read a lineage record (Phase 5) |

## `/v1/healthz` shape

```json
{
  "status": "ok",
  "version": "0.1.0",
  "producer": "all",
  "instance_id": "01HZ…",
  "cache_backend": "memory",
  "queue_depth": 0,
  "ghostscript": false,
  "codex_pdf_version": "1.7.0",
  "codex_section_versions": { "color": "1.1.0", "geom": "1.1.0", "codex-document": "1.0.0" },
  "codex_live_section_versions": { "color": "1.1.0", "geom": "1.1.0", "codex-document": "1.0.0" },
  "version_skew": false
}
```

The `version_skew` boolean flips true when the codex section versions
Compile was **built** against drift from what the live Codex
**publishes**. Operators should drain the affected instance and
redeploy when this trips.

## `/v1/contract` shape

```json
{
  "contract_name": "compile-pdf",
  "schema_version": "1.0.0",
  "package_version": "0.1.0",
  "schema_id": "https://printwithsynergy.com/schemas/compile/v1",
  "endpoints": ["/healthz", "/v1/healthz", "/v1/version", "/v1/contract", … ],
  "producer_schema_versions": { "rewrite": "1.0.0", "marks": "1.0.0", "impose": "1.0.0", "trap": "1.0.0", "cjd": "1.0.0" },
  "codex_section_versions": { "color": "1.1.0", "geom": "1.1.0", "codex-document": "1.0.0" }
}
```

## Versioning policy

Each producer's schema version bumps independently:

- **Additive** (`1.0.0` → `1.1.0`) — new optional fields, new
  enum values, no client breakage.
- **Breaking** (`1.x` → `2.x`) — moves to `/v2/<producer>/apply`;
  `/v1` stays live during the transition window.

The Codex pin is broader: Compile's `pyproject.toml` declares
`codex-pdf>=1.4.2,<2.0`. Cross-major bumps require code review.

## Codex section versions Compile cares about

Defined in `src/compile_pdf/version.py`:

| Section | Source | Purpose |
|---|---|---|
| `color` | `codex_pdf.color.COLOR_SCHEMA_VERSION` | Spot-color resolver, Pantone reference |
| `geom` | `codex_pdf.geom.GEOM_SCHEMA_VERSION` | Geometry primitives, `tile_grid` |
| `codex-document` | `compile_pdf.version.CODEX_DOCUMENT_SCHEMA_VERSION_PIN` (Codex doesn't yet publish a constant) | Document model shape |

A bump to any of these auto-invalidates affected cached outputs via
the cache-key composer in `src/compile_pdf/cache.py`.

## Producer schema versions

| Producer | Constant | Schema |
|---|---|---|
| `rewrite` | `REWRITE_SCHEMA_VERSION` | `compile-pdf schema rewrite` |
| `marks` | `MARKS_SCHEMA_VERSION` | `compile-pdf schema marks` |
| `impose` | `IMPOSE_SCHEMA_VERSION` | `compile-pdf schema impose` |
| `trap` | `TRAP_SCHEMA_VERSION` | `compile-pdf schema trap` |
| `cjd` | `CJD_SCHEMA_VERSION` | `compile-pdf schema cjd` |

All start at `1.0.0` in 0.1.0; each bumps independently.

## Lineage record schema

Lineage records (one per producer step, S3-stored) carry:

```json
{
  "lineage_id": "01HZ…",
  "producer": "trap",
  "input_sha256": "…",
  "output_sha256": "…",
  "plan_sha256": "…",
  "cache_key": "…",
  "engine_fingerprint": { "engine": "pure_python", "geom_schema_version": "1.1.0", "color_schema_version": "1.1.0" },
  "compile_version": "0.1.0",
  "codex_pdf_version": "1.7.0",
  "parent_lineage_id": "01HZ…",
  "started_at": "…",
  "duration_ms": 1234
}
```

The `parent_lineage_id` field is what lets `compile-pdf lineage <id>
--chain` walk the full producer history of a final artifact.
