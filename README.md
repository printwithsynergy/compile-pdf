# compile-pdf

[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/deploy/compilepdf)

CompilePDF — programmatic PDF assembly: a deterministic API build step for rewriting and generating print-ready PDFs.

One orchestrator + integration shell (this repo), a constellation of published satellite producer packages, one FastAPI app per deployment, one Redis-backed Celery broker, one S3-compatible object bucket. Every producer's source lives in its own satellite PyPI package, pinned in `pyproject.toml` and imported by the orchestrator — this repo mounts the routers and ships the CLI; it vendors no producer code.

| Producer | Package | Endpoint(s) | Purpose |
|---|---|---|---|
| rewrite | [`compile-pdf-rewrite`](https://github.com/printwithsynergy/compile-pdf-rewrite) | `POST /v1/rewrite/apply` | OCG flips, metadata patches, color-space swaps, hygiene strips, page lifecycle ops on a single PDF |
| marks | [`compile-pdf-marks`](https://github.com/printwithsynergy/compile-pdf-marks) | `POST /v1/marks/apply`, `POST /v1/marks/apply-multipart` | Register / crop / color-bar / fold marks; 1-up proofing slugs; external mark template ingestion |
| impose | [`compile-pdf-impose`](https://github.com/printwithsynergy/compile-pdf-impose) | `POST /v1/impose/apply` | Sheet-level step-and-repeat layout; work-and-turn / tumble; bleed handling; sift-pdf `explicit_placements` |
| trap | [`compile-pdf-trap`](https://github.com/printwithsynergy/compile-pdf-trap) | `POST /v1/trap/apply` | Ink-pair spread / choke trap with three engine slots (pure_python / ghostscript / external) |
| cjd | [`compile-pdf-cjd`](https://github.com/printwithsynergy/compile-pdf-cjd) | `POST /v1/cjd/apply`, `POST /v1/cjd/apply-xml`, `GET /v1/lineage/*` | Multi-producer Compile Job Definition envelope (rewrite → marks → impose → trap) + lineage reads |
| stream | [`compile-pdf-stream`](https://github.com/printwithsynergy/compile-pdf-stream) | `POST /v1/stream/apply` | Producer-agnostic streaming wrapper — runs rewrite / marks / impose / trap / soft_proof and chunk-streams the PDF (always-on) |
| soft-proof | [`compile-pdf-soft-proof`](https://github.com/printwithsynergy/compile-pdf-soft-proof) | `POST /v1/soft-proof/apply` | ICC soft-proof simulation with a ΔE summary (max / avg / p95) |
| white-underbase | [`compile-pdf-white-underbase`](https://github.com/printwithsynergy/compile-pdf-white-underbase) | `POST /v1/white-underbase/apply` | White-ink / underbase / varnish / foil plate generation as a named separation |
| spots *(metadata)* | [`compile-pdf-core`](https://github.com/printwithsynergy/compile-pdf-core) | `GET /v1/spots/{search,lookup,libraries}` | Read-only PANTONE catalogue lookup over codex-pdf's spot-colorant reference (always-on) |
| separations *(metadata)* | [`compile-pdf-separations`](https://github.com/printwithsynergy/compile-pdf-separations) | `POST /v1/separations/list` | Read-only named-ink enumeration of an input PDF (always-on) |

Shared plumbing — cache-key composition, lineage store, retention, auth, middleware, queue status, the rewrite/marks/impose/trap/cjd schema versions — lives in [`compile-pdf-core`](https://github.com/printwithsynergy/compile-pdf-core). Core producer routers mount lazily, gated by the `COMPILE_PRODUCER` env var (per-producer sidecar deployments); the spots / separations / stream routers are always-on.

**Architectural invariants** (mechanically enforced by `scripts/consume_surface_audit.py`):

- CompilePDF is the writer — it produces PDF bytes and never re-extracts them.
- [codex-pdf](https://github.com/printwithsynergy/codex-pdf) stays read-only — its `produce_surface_audit.py` enforces.
- Every producer consumes Codex primitives through published surfaces; re-implementation is forbidden.
- Every producer emits deterministic bytes; same input + same plan + same engine fingerprint → same SHA-256 output.

## Status

`compile-pdf 0.7.0` on PyPI, built against `codex-pdf 1.21.1+`. All producers live in their satellite packages and are imported, not vendored — a producer fix lands in its satellite, is published, and this repo bumps the pin. The CJD batch runner + lineage store are wired, and retention-for-training is opt-in per request. See [`CHANGELOG.md`](./CHANGELOG.md) for the release log and [`docs/`](./docs) for operator + integrator documentation.

## Install

```bash
uv pip install compile-pdf
```

For producers that need geometry primitives (marks, impose, trap):

```bash
uv pip install 'compile-pdf[geom]'
```

For the trap producer with Ghostscript engine fallback:

```bash
uv pip install 'compile-pdf[geom,trap-gs]'
```

## CLI

```bash
compile-pdf rewrite         --plan plan.json       input.pdf output.pdf
compile-pdf marks           --template tmpl.json   input.pdf output.pdf
compile-pdf impose          --layout layout.json   input.pdf output.pdf
compile-pdf trap            --policy policy.json   input.pdf output.pdf
compile-pdf white-underbase --policy policy.json   input.pdf output.pdf
compile-pdf stream          --producer trap --payload req.json --output out.pdf

compile-pdf version
compile-pdf contract
compile-pdf health
compile-pdf schema {rewrite|marks|impose|trap|cjd}
compile-pdf cjd --job job.json [--xml] [--trap-diff diff.json] output.pdf
compile-pdf lineage <id> [--chain]
```

Producer subcommands register themselves from the satellite packages' `cli` modules at import time; a satellite absent from the build simply doesn't contribute its subcommand.

### Opting in to retention-for-training

Every producer endpoint (and the CJD orchestrator) accepts an
explicit opt-in signal that retains the call's inputs and outputs
for engine training. Off by default; engaged per-request.

```bash
curl -X POST $COMPILE_BASE/v1/rewrite/apply \
  -H "X-Compile-Retain-For-Training: true" \
  -H "Content-Type: application/json" \
  --data-binary @request.json
```

Operators wire it up by setting `COMPILE_RETAIN_BUCKET` and friends
(see [`docs/operations/retention.md`](./docs/operations/retention.md)). With no bucket configured the consent header is parsed and logged but nothing is written.

CLI defaults to local-mode (in-process) when `COMPILE_API_BASE` is unset; otherwise POSTs to the configured central or sidecar URL.

## Docs

- Operator + integrator docs: [`docs/`](./docs)
- Per-release log: [`CHANGELOG.md`](./CHANGELOG.md)

## License

AGPL-3.0-or-later. See [LICENSE](./LICENSE).
