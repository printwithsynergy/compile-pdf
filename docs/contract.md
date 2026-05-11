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
| `POST` | `/v1/rewrite/apply` | Apply a rewrite plan |
| `POST` | `/v1/marks/apply` | Apply a marks template (inline) |
| `POST` | `/v1/marks/apply-multipart` | Apply a marks template (multipart upload — supports external-file marks) |
| `POST` | `/v1/impose/apply` | Apply an impose layout |
| `POST` | `/v1/trap/apply` | Apply a trap policy |
| `POST` | `/v1/cjd/apply` | Apply a multi-producer CJD envelope (JSON) |
| `POST` | `/v1/cjd/apply-xml` | Apply a CJD envelope (XML / JDF / PJTF body) |
| `GET` | `/v1/lineage/{id}` | Read a lineage chain by id |
| `GET` | `/v1/lineage` | List known lineage ids (paginated) |
| `POST` | `/v1/retention/delete` | Data-subject erasure: bulk-delete every retention object containing `/{sha256}/` |

## `/v1/healthz` shape

```json
{
  "status": "ok",
  "version": "0.5.1",
  "producer": "all",
  "instance_id": "01HZ…",
  "cache_backend": "memory",
  "queue_depth": 0,
  "celery_workers": 0,
  "ghostscript": false,
  "codex_pdf_version": "1.8.1",
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
  "package_version": "0.5.1",
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
`codex-pdf>=1.8.1,<2.0`. Cross-major bumps require code review.

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

All start at `1.0.0`; each bumps independently.

## Retention-for-training opt-in

Every producer endpoint (and the CJD orchestrator) honours an
explicit opt-in signal that retains the call's inputs and outputs
for engine training. Off by default; engaged per-request.

| Channel | Where | Truthy values |
|---|---|---|
| Header | `X-Compile-Retain-For-Training` (every producer endpoint) | `true`, `1`, `yes` (case-insensitive, trimmed) |
| Form field | `retain_for_training` (multipart endpoints only) | same as header |
| Tenant slug | `X-Compile-Tenant` header (optional, slugified) | any string → slug; absent → `anonymous` |

When the signal is truthy **and** `COMPILE_RETAIN_BUCKET` is set,
the endpoint persists three blobs per call:

```
{prefix}/{tenant}/{producer}/{YYYY-MM-DD}/{input_sha256}/input.pdf
{prefix}/{tenant}/{producer}/{YYYY-MM-DD}/{input_sha256}/output.pdf
{prefix}/{tenant}/{producer}/{YYYY-MM-DD}/{input_sha256}/result.json
```

Each object is tagged `ttl-days={COMPILE_RETAIN_TTL_DAYS}` so the
bucket's lifecycle policy can sweep at expiry. The
`output_pdf_b64` field is stripped from `result.json` (bytes already
live in `output.pdf`).

`POST /v1/retention/delete` bulk-deletes every object whose key
contains `/{sha256}/`. Zero hits is **not** an error (200 with
`deleted: 0`). Misconfiguration → 503; boto3 errors → 500.

See [`operations/retention.md`](./operations/retention.md) for the
operator-side env-var inventory and lifecycle-policy template.

## Lineage record schema

Lineage records (one per producer step, S3-stored) carry:

```json
{
  "lineage_id": "01HZ…",
  "step_index": 0,
  "producer": "trap",
  "input_sha256": "…",
  "output_sha256": "…",
  "plan_sha256": "…",
  "cache_key": "…",
  "retained_for_training": false,
  "engine_fingerprint": { "engine": "pure_python", "geom_schema_version": "1.1.0", "color_schema_version": "1.1.0" },
  "compile_version": "0.5.1",
  "codex_pdf_version": "1.8.1",
  "parent_lineage_id": "01HZ…",
  "started_at": "…",
  "duration_ms": 1234
}
```

`retained_for_training` reflects the per-step retention decision —
the consent header + bucket configuration in effect when the
producer ran. The flag is preserved through the store and surfaced
on `GET /v1/lineage/{id}`.

The `parent_lineage_id` field is what lets `compile-pdf lineage <id>
--chain` walk the full producer history of a final artifact.
