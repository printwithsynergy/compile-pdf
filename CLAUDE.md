# compile-pdf — agent notes

 > **Cross-stack context**: see [`lint-pdf/STACK.md`](https://github.com/printwithsynergy/lint-pdf/blob/main/STACK.md) for the org-level overview of the 6-repo stack — who-calls-whom, where shared things live (codex), cross-stack conventions (RFC 7807 Problem Details + `/healthz`+`/readyz`+`/v1/contract` + the service-skip pattern + service-ownership tripwires), and the explicit "no monorepo" rationale.

## Scope

CompilePDF is **the only PDF writer in the Print With Synergy stack**.
Four schema-versioned producers — **rewrite**, **marks**, **impose**,
**trap** — consume `codex-pdf` read-only primitives and emit
deterministic, audit-logged PDF bytes with content-addressed cache
keys and per-job lineage chains.

Non-goals:
- **Don't** re-implement extraction primitives that codex-pdf already
  exposes (geometry, color, document introspection). The repo's
  consume-surface audit (`scripts/consume_surface_audit.py`) is the
  mechanical guardrail; see "Surface audits" below.
- **Don't** encode policy / pass-fail verdicts. Those belong to
  lint-pdf. Compile *applies* the writer policy it's handed (a trap
  policy, a marks template, an impose plan); it does not decide
  whether the result is acceptable.
- **Don't** drive viewer/UI decisions. Lens-pdf owns presentation.

## Public contracts

The repo ships three publish-able artifacts:

- **PyPI `compile-pdf`** — the producer engines + CLI + CJD orchestrator
  + lineage store. Version pinned via `pyproject.toml`; consumers
  (synergy gateway, hosts) should pin `compile-pdf>=X.Y,<MAJOR+1`,
  matching lint-pdf's discipline.
- **HTTP API** (FastAPI) — endpoints listed by `/v1/contract`. Per-
  producer apply endpoints (`POST /v1/{rewrite,marks,impose,trap}/apply`)
  are mounted lazily, gated by the `COMPILE_PRODUCER` env var (see
  "Lazy router mounting").
- **Compile CLI** — `compile-pdf {rewrite|marks|impose|trap|cjd|lineage|
  schema|contract|health|version}`. Same surface as the HTTP routes;
  good for batch runs and local dev.

## Cross-repo contracts

### codex-pdf (mandatory, in-process Python import)

Pinned via `pyproject.toml`: `codex-pdf>=1.15.0,<2.0`. The `<2.0` cap
is **load-bearing** — codex's `/v1/contract` + cache-key VERSION
scheme rotate on major bumps. Don't drop the cap without coordinating
with the codex maintainers about the breaking-change semantics.

Imported surfaces (cite at the use site):
- `CodexDocument`, `CodexSpotIntent`, `delta_e_2000`,
  `resolve_spot_swatch_color` — used by `trap/`.
- `Box`, `Point`, `Polygon`, `polygon_offset`, `polygon_union` — used
  by `marks/`.
- `tile_grid`, `TileGrid`, `TileResult`, `CellPlacement` — used by
  `impose/`.

`CODEX_DOCUMENT_SCHEMA_VERSION_PIN` (`src/compile_pdf/version.py`) is
recorded in every lineage record so a future codex bump can detect
skew.

### Other org repos
- **lint-pdf**, **lens-pdf**, **synergy**, **platform** — no imports,
  no HTTP calls. Compile is consumed *by* synergy (HTTP) and via the
  CLI; it never consumes them.

## Surface audits (mechanical, CI-enforced)

`scripts/consume_surface_audit.py` runs in CI (`.github/workflows/
ci.yml`) and **bans** patterns that would reimplement codex:

- Direct `pyclipr` imports outside the audit-allowed list. Geometry
  primitives come from codex.
- Direct access to a vendored Pantone JSON. Spot colors come from
  codex's spot-colorant model.
- Re-defining `Box` / `Point` / `Polygon` classes that codex already
  exports.

When a new symbol from codex is consumed, add it to the audit allow-
list in the same commit. The CI artifact (`consume_surface_audit
report`) is the record.

## CJD orchestrator — canonical order

CJD (`src/compile_pdf/cjd/`) bundles multi-producer jobs into a single
envelope. The canonical order is fixed:

```
rewrite  →  marks  →  impose  →  trap
```

`cjd/orchestrator.py` enforces this. With `strict_order=true`, jobs
submitted out of order are rejected (422). Without it, jobs are
silently reordered into canonical order and a `reordered_steps` field
is emitted in the response. The reorder is **silent in lineage** — a
consumer can detect it by comparing the input `steps` to the lineage
`steps_executed`.

## Determinism + lineage

Every producer apply call is content-addressed. The cache key is the
SHA-256 of:

- Input PDF bytes (sha256).
- Producer name + producer schema version.
- Engine fingerprint (`src/compile_pdf/version.py` exposes per-engine
  fingerprints — bump these when an engine's output bits would change).
- Codex section versions (`CODEX_DOCUMENT_SCHEMA_VERSION_PIN` +
  per-extracted-section versions consumed).
- Config hash (the apply request JSON, normalized).

Same inputs → same SHA-256 output. **Don't** introduce a non-
deterministic engine path; if you must (e.g. external tool with
random salt), surface the salt in the cache key.

Lineage records (`src/compile_pdf/lineage/store.py`) persist per
cache_key:

- Input/output sha256.
- Engine fingerprint.
- Codex section versions consumed.
- Timestamps + duration.
- HMAC chain link to the previous lineage entry (don't break the
  chain — chain validation is how downstream proves no record was
  silently dropped or rewritten).

S3-backed in prod; local fallback for offline dev.

## Producer packaging — imported, not vendored

**No producer source lives in this repo's `src/` anymore.** Every producer
is a published satellite package, pinned in `pyproject.toml` and imported
by `api/main.py` / `cli/`:

- Core producers: `compile-pdf-{rewrite,marks,impose,trap}`.
- Meta-producers (depend on the producers they dispatch):
  `compile-pdf-cjd`, `compile-pdf-stream`.
- Standalone producers: `compile-pdf-{separations,soft-proof,
  white-underbase}` — each owns its own `version.py` schema version,
  which main's `version.py` re-exports into the `/v1/contract`
  aggregate.
- `spots` (read-only PANTONE lookup; not a producer) lives in
  `compile-pdf-core` (`compile_pdf_core.spots`).

This repo is the **orchestrator + integration shell**: it mounts the
satellite routers (gated by `COMPILE_PRODUCER`), the always-on metadata
routers (spots / separations / stream), and the shared `compile-pdf-core`
plumbing (cache, lineage, retention, auth, schema versions). A producer
fix lands in its satellite, is published, and main bumps the pin — there
is no second vendored copy to keep in sync (that duplication caused the
same bug to be fixed twice). Each satellite was reconciled to be a
**superset** of what main previously vendored, so consolidation lost no
capability.

## Lazy router mounting

`src/compile_pdf/api/main.py` mounts producer routers on
demand (imported from the satellite packages), gated by `COMPILE_PRODUCER`:

- `COMPILE_PRODUCER=all` (default) — mounts all four producers + CJD
  + lineage + retention.
- `COMPILE_PRODUCER=rewrite|marks|impose|trap` — mounts only that
  producer's `/v1/{name}/apply` endpoints. CJD + lineage + retention
  are excluded.

This gates **per-producer sidecar** deployments: ship the trap-only
image with `COMPILE_PRODUCER=trap`, the marks-only image with
`COMPILE_PRODUCER=marks`, etc. Synergy's gateway routes accordingly.

## Three-layer verification

Every producer apply enforces:

1. **Input validation** — Pydantic schema rejects malformed plans
   (`rewrite/plan_schema.py`, `marks/template_schema.py`,
   `impose/layout_schema.py`, `trap/policy_schema.py`).
2. **Engine output integrity** — the engine's emitter checks its own
   invariants (e.g. trap policy applied produces non-empty trap zones
   when input had ink boundaries).
3. **Post-condition checks** — runs **before** the response. If the
   output PDF doesn't pass post-conditions, the apply call returns a
   5xx (not a successful response with bad bytes).

When adding a new engine path, add a post-condition test that catches
the failure mode you'd be embarrassed to ship.

## Retention + GDPR

`src/compile_pdf/retention/` writes input/output PDFs to S3 when the
caller opts in via header `X-Compile-Retain-For-Training: true`. The
write is async and **doesn't block the apply response**. Records are
hive-partitioned (`compile/{tenant}/{dt}/{sha256}/`) with a 90-day
TTL.

`POST /v1/retention/delete` is the GDPR erasure endpoint. It accepts
a sha256 and removes the matching S3 object + lineage references.
Erasure is synchronous — the call returns when S3 confirms the
delete.

## Sandbox + process hygiene

Apply calls execute under per-job subprocess rlimits (memory, CPU
seconds, file descriptors). `tasks.py` configures the limits;
`Dockerfile` uses `tini` for PID-1 signal handling so child processes
get reaped on container shutdown.

## Service-skip pattern (intentional asymmetry)

When a producer would consume an optional engine (Ghostscript fallback
for trap; OCG flips needing pyclipr) and it's not installed, the
producer **fails fast with a clear error code** (e.g. `TRAP_GS_MISSING`)
— not a generic 500, and not a silent empty-output skip like
lint-pdf's analyzers do. Compile is a writer; "skip silently" would
emit a PDF that lies about what was applied.

## Public-API discipline

- Every FastAPI route handler must have a docstring + `responses=`
  mapping listing every non-200 status it can emit. The summary line
  becomes the OpenAPI operation summary.
- No raw `dict[str, Any]` in route signatures. Define a Pydantic
  response model — even single-field.
- `/v1/contract` is the org-aligned contract endpoint (matches
  codex's pattern). Don't drop or rename it.

## Local dev

```bash
uv sync --extra dev                                          # install
uv run ruff check src tests scripts                          # lint
uv run ruff format src tests scripts                         # format
uv run mypy src                                              # strict types
uv run pytest --cov=compile_pdf --cov-fail-under=70          # tests
uv run python scripts/consume_surface_audit.py               # surface check
uvicorn compile_pdf.api.main:app --reload                    # local server
```

CI gate: ruff + mypy + consume_surface_audit + pytest >=70% coverage.

## Code review & blast-radius protocol

- Run code-review-graph impact tools on changed symbols before edits.
- Ensure tests pass + coverage doesn't drop before commit.
- CodeRabbit reviews PRs automatically; Cursor BugBot is the second
  opinion.
- Never disable the code-review-graph Launch Agent.
