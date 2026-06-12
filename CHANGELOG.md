# Changelog

All notable changes to compile-pdf will be documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions adhere to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.6] — 2026-06-04

### Security

- **XXE (CJD XML parser)**: `src/compile_pdf/cjd/xml.py` imported
  `tostring` from `xml.etree.ElementTree`. Although parsing was already
  routed through `defusedxml.ElementTree`, the residual stdlib import
  was flagged by Semgrep (`python.lang.security.use-defused-xml`).
  `tostring` now comes from `defusedxml.ElementTree` (which re-exports
  it). `Element` and `SubElement` are retained from stdlib — they are
  write-only constructors with no external-entity parsing surface; a
  `# nosemgrep` annotation with justification suppresses the residual
  warning on that line.
- **CI hardening**: added `persist-credentials: false` to the
  `actions/checkout` step; added a blocking `security` job that runs
  Semgrep (`--error`, `p/security-audit` + `p/secrets` + `p/python`)
  and Bandit (medium severity + confidence) on every push and PR.

## [0.5.2] — 2026-05-12

### Changed

- Bump `codex-pdf` floor to `>=1.9.0,<2.0`. Codex 1.9.0 completes the
  unified extraction campaign (text-regions / conformance / renders
  endpoints, tenant scoping, rate limiting, observability metrics).
  The compile-pdf surface is consumer-only — additive on the codex
  side, no behavior change here.
- Bump `CODEX_DOCUMENT_SCHEMA_VERSION_PIN` to `1.2.0` (was `1.0.0`).
  Reflects the additive schema bump in codex-pdf 1.9.0
  (`CodexPage.detected_text_regions`, `CodexDocument.conformance_verdicts`,
  `CodexDocument.stage_durations_ms`). Compile-document shape unchanged.

## [0.5.1] — 2026-05-11

### Changed

- Bump `codex-pdf` floor to `>=1.8.1,<2.0`. Codex 1.8.0 bumped both
  `COLOR_SCHEMA_VERSION` and `GEOM_SCHEMA_VERSION` to `1.1.0`; 1.8.1
  is the current patch. Compile already runs cleanly against the
  new surface (465/465 tests pass); this just raises the floor so
  new installs always pick up the section-version bump.
- Refresh `CODEX_REQUIRED_SECTION_VERSIONS` default in `.env.example`
  to `{"color":"1.1.0","geom":"1.1.0"}` (was `1.0.0` for both).

## [0.5.0] — 2026-05-11

### Added

- Retention-for-training opt-in surface (`compile_pdf.retention`).
  When a producer call carries `X-Compile-Retain-For-Training: true`
  (or, on multipart endpoints, form field `retain_for_training=true`)
  **and** `COMPILE_RETAIN_BUCKET` is set, Compile persists three blobs
  per call (`input.pdf`, `output.pdf`, `result.json`) under
  `{prefix}/{tenant}/{producer}/{YYYY-MM-DD}/{input_sha256}/` with a
  `ttl-days` object tag. Tenant arrives via `X-Compile-Tenant`
  (slugified, defaults to `anonymous`).
- `POST /v1/retention/delete` — data-subject erasure endpoint that
  bulk-deletes every object whose key contains `/{sha256}/`.
- `LineageStep.retained_for_training` flag, threaded through the CJD
  orchestrator and surfaced on `GET /v1/lineage/{id}`.
- New env vars: `COMPILE_RETAIN_BUCKET`, `COMPILE_RETAIN_PREFIX`,
  `COMPILE_RETAIN_TTL_DAYS`, `COMPILE_RETAIN_ENDPOINT_URL`,
  `COMPILE_RETAIN_REGION`, `COMPILE_RETAIN_AWS_{ACCESS,SECRET}_KEY*`.
- 50 new tests across consent parsing, S3 store fakes, per-producer
  wiring, CJD orchestration, retention API, and lineage flag
  round-trips.

### Notes

- Default behaviour is unchanged: with no env config the consent
  header is parsed and logged but nothing is written. Producer
  endpoints never fail on retention errors — backend hiccups
  downgrade to a silent no-op so a transient S3 outage cannot
  break a producer call.

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
  have landed yet. The rewrite engine is the next milestone.
- Codex 1.5 (Phase 0) prerequisites — `polygon_offset`, neutral-density
  fields, TileGrid extensions, server-side `instance_id` + request-id
  middleware — are tracked separately and gated by spec STOP-gate 0-A.
