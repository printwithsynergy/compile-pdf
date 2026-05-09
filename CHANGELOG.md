# Changelog

All notable changes to compile-pdf will be documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions adhere to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-05-09

### Added

- Initial scaffolding for compile-pdf, the only writer in the Print With Synergy stack.
- Package layout per spec §1.2: single mono-repo with sub-packages
  `compile_pdf.{rewrite, marks, impose, trap}`.
- `compile-pdf` CLI console-script entry point with subcommands
  (`version`, `contract`, `health`, `schema`, plus per-producer commands wired
  in as producer modules ship).
- FastAPI app skeleton (`compile_pdf.api.main`) exposing `/healthz`,
  `/v1/healthz`, `/v1/version`, `/v1/contract`, `/metrics`.
- Health response shape extends codex's pattern with `producer`, `instance_id`,
  `queue_depth`, `codex_pdf_version`, `codex_section_versions`,
  `codex_live_section_versions`, `version_skew` fields per spec §1.11a.
- Auth modes lifted from codex pattern (`COMPILE_AUTH_MODE` env var):
  `none`, `bearer`, `api-key`, `internal`, `basic` (per spec §1.10).
- Request-id middleware (`compile_pdf.api.middleware.RequestIdMiddleware`)
  honoring `X-Compile-Request-Id`, propagating to logs and response headers,
  and capturing upstream `X-Codex-Request-Id` for full chain traceability.
- Cache-key composer with deterministic plan canonicalization
  (`compile_pdf.cache.canonicalize_plan` and `compute_cache_key`) per spec §1.6 / §1.6a.
- Per-producer schema versioning constants in `compile_pdf.version`
  (`REWRITE_SCHEMA_VERSION`, `MARKS_SCHEMA_VERSION`, `IMPOSE_SCHEMA_VERSION`,
  `TRAP_SCHEMA_VERSION`, `CJD_SCHEMA_VERSION`, `COMPILE_DOCUMENT_SCHEMA_VERSION`).
- Two-stage `Dockerfile` per spec §1.11b: builder stage carries native
  toolchain when needed; runtime stays slim (`python:3.12-slim` + tini); runs
  as non-root user `compile`; healthcheck against `/healthz`.
- Consume-surface audit (`scripts/consume_surface_audit.py`) per spec §7.5 —
  AST walker that fails CI on banned imports, function names, and class names
  that would re-implement Codex primitives.
- GitHub Actions CI workflow running ruff lint, mypy strict typing, pytest
  (with coverage), and the consume-surface audit.
- Test scaffolding with smoke coverage of the audit, cache canonicalization,
  and FastAPI healthz/contract endpoints.

### Internal

- Pinned `codex-pdf>=1.4.2,<2.0` as the upstream wheel.
- pyproject ruff/mypy/pytest config.
- Apache 2.0 license.

### Notes

- This release is **scaffolding only** — no producer engine implementations
  have landed yet. Phase 1 (rewrite engine) is the next milestone per
  [`COMPILE-IMPL-PLAN.md`](../COMPILE-IMPL-PLAN.md) §3.
- Codex 1.5 (Phase 0) prerequisites — `polygon_offset`, neutral-density
  fields, TileGrid extensions, server-side `instance_id` + request-id
  middleware — are tracked separately and gated by spec STOP-gate 0-A.
