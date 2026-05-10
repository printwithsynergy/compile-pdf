---
title: "Deploy"
description: "How to ship CompilePDF — Dockerfile, Railway envelope, the four producer services, and the sibling sidecar pattern."
group: "Reference"
order: 2
---

# Deploy

## Container

The repository ships a two-stage `Dockerfile` (build → runtime). The
runtime image runs as a non-root user and listens on `${PORT:-8000}`.

Build flags:

- `COMPILE_EXTRAS` — comma-separated list. `geom` is required for
  marks / impose / trap; `trap-gs` adds the Ghostscript trap engine.
- `PRODUCER` — `rewrite` | `marks` | `impose` | `trap` | `all`.
  Selects which router(s) the runtime mounts via `COMPILE_PRODUCER`.

## Railway envelope

Production runs four producer services in one Railway project, plus
shared infrastructure:

- `compile-rewrite`, `compile-marks`, `compile-impose`,
  `compile-trap` — one container per producer.
- `compile-redis` — Celery broker + cache backend.
- `compile-bucket` — S3-compatible (or Tigris) object store for
  lineage records and output artifacts.

The marketing site lives in a sibling Railway project
(`compile-pdf-marketing`) and includes its own
`compile-sidecar/` deployment that runs `COMPILE_PRODUCER=all` for
demo traffic only — it never serves production jobs. See
[`compile-pdf-marketing/compile-sidecar/railway.toml`](https://github.com/printwithsynergy/compile-pdf-marketing/blob/main/compile-sidecar/railway.toml).

## Auth modes

Set via `COMPILE_AUTH_MODE`:

| Mode | Behavior |
|---|---|
| `none` | No auth (dev only) |
| `bearer` | `Authorization: Bearer <token>` header required |
| `api-key` | `X-API-Key: <key>` header required |
| `internal` | Same-VPC traffic; honors `X-Compile-Source` provenance header |
| `basic` | HTTP Basic; tenant/secret pair |

Tokens / keys come from `COMPILE_BEARER_TOKEN`,
`COMPILE_API_KEY_LIST`, `COMPILE_BASIC_USER` /
`COMPILE_BASIC_PASS`. See `.env.example`.

## Required env

| Variable | Purpose |
|---|---|
| `COMPILE_PRODUCER` | Which router(s) to mount (`rewrite` / `marks` / `impose` / `trap` / `all`) |
| `COMPILE_AUTH_MODE` | See above |
| `COMPILE_REDIS_URL` | Celery broker + cache backend |
| `COMPILE_BUCKET_URL` | S3-compatible base URL for lineage |
| `COMPILE_BUCKET_KEY` / `_SECRET` | Bucket credentials |
| `CODEX_API_BASE` | Live Codex `/v1/extract` endpoint (used by version-skew check) |
| `CODEX_BEARER_TOKEN` | Codex auth |
| `INSTANCE_ID` | Optional override; auto-generated as ULID otherwise |
| `COMPILE_TRAP_ENGINE` | `pure_python` (default) / `ghostscript` / `external` — only honored on the trap container |

## Cascade rule

Any change to `codex-pdf` — code, schema, image tag, or
`codex_pdf.version.VERSION` — **MUST** cascade a redeploy of every
Compile container that calls codex. See
[`operations/multi-instance.md`](./operations/multi-instance.md).
