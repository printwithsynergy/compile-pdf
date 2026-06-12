---
title: "Multi-instance + version-skew"
description: "How Compile runs multiple instances per producer safely, why version_skew matters, and the cascade rule for Codex bumps."
group: "Operations"
order: 5
slug: "multi-instance"
---

# Multi-instance + version-skew

Compile may run multiple instances of the same producer in parallel:

- **Scale-out** — many instances behind a load balancer to absorb
  queue depth.
- **Multi-region** — separate instances per Railway region for
  latency.
- **Blue/green** — old + new at the same time during rollout.

Because Compile guarantees deterministic bytes, **two instances of
the same producer must produce byte-identical output for the same
input + plan, every time.** Anything else corrupts the cache.

## What the determinism guarantee depends on

The cache key (`compile_pdf_core.cache`; main keeps a mirror in `src/compile_pdf/cache.py`) includes:

1. `compile_version` — the Compile package version
2. `codex_pdf_package_version` — the Codex wheel version
3. `color_schema_version` — `codex_pdf.color.COLOR_SCHEMA_VERSION`
4. `geom_schema_version` — `codex_pdf.geom.GEOM_SCHEMA_VERSION`
5. `codex_document_schema_version` — pinned in `compile_pdf.version`
6. `producer` — `rewrite` / `marks` / `impose` / `trap`
7. `sha256(canonical_plan)`
8. `sha256(input_bytes)`

If any of (1)–(5) differ between instances, the cache key differs
and the same input + plan can hit different cached entries. That's
fine when correct; it's a corruption when one instance has been
rebuilt against a newer Codex but another hasn't.

## The `version_skew` health field

`/v1/healthz.version_skew` flips true when the codex section
versions Compile was **built against** drift from what Codex
**publishes live**. Operators watch this field and:

1. **Drain** the affected instance from the load balancer.
2. **Rebuild** against the new Codex.
3. **Redeploy** and re-add to the LB.

Skew on a single instance is a recoverable state. Skew on **all
instances** of a producer is an outage signal.

## Codex change ripple rule

Any change to `codex-pdf` — code, schema, image tag, or
`codex_pdf.version.VERSION` — **MUST** cascade a redeploy of every
Compile container that calls codex. Skipping the cascade silently
pins consumers to a stale contract.

Cascade order:

1. Bump `codex-pdf` and verify Codex's `produce_surface_audit.py`
   passes.
2. Bump the codex pin in `compile-pdf/pyproject.toml` if the major
   moved (otherwise the existing range is fine).
3. Rebuild and redeploy `compile-rewrite`, `compile-marks`,
   `compile-impose`, `compile-trap` (any order).
4. Rebuild and redeploy `compile-sidecar` in
   `compile-pdf-marketing`.
5. Run `compile-pdf health` against each environment and confirm
   `version_skew: false`.

## Operator runbook

| Symptom | Likely cause | Action |
|---|---|---|
| `version_skew: true` on one instance | Partial rollout in progress | Wait or drain that instance |
| `version_skew: true` on all instances | Codex changed but Compile not rebuilt | Run cascade |
| `cache_hit_rate` drops to ~0% | Codex section bump invalidated everything | Expected; will recover as new entries fill |
| `queue_depth` grows unboundedly | Trap engine selection failure (especially `ghostscript` on a container without the extra) | Check `COMPILE_TRAP_ENGINE` against installed extras |
