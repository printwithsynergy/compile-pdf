# compile-pdf

CompilePDF — the only writer in the Print With Synergy stack.

Four producers under one Python package, four FastAPI services in one Railway project, one Redis-backed Celery broker, one S3-compatible object bucket.

| Producer | Purpose |
|---|---|
| `compile_pdf.rewrite` | OCG flips, metadata patches, color-space swaps, hygiene strips, page lifecycle ops on a single PDF |
| `compile_pdf.marks` | Register / crop / color-bar / fold marks; 1-up proofing slugs; external mark template ingestion |
| `compile_pdf.impose` | Sheet-level step-and-repeat layout; work-and-turn / tumble; bleed handling |
| `compile_pdf.trap` | Ink-pair spread / choke trap with three engine slots (pure_python / ghostscript / external) |

**Architectural invariants** (mechanically enforced by `scripts/consume_surface_audit.py`):

- CompilePDF is the *only* writer in the stack.
- [codex-pdf](https://github.com/printwithsynergy/codex-pdf) stays read-only — its `produce_surface_audit.py` enforces.
- Every producer consumes Codex primitives through published surfaces; re-implementation is forbidden.
- Every producer emits deterministic bytes; same input + same plan + same engine fingerprint → same SHA-256 output.

## Status

`compile-pdf 0.5.1` on PyPI, built against `codex-pdf 1.8.1`. All four producers (`rewrite`, `marks`, `impose`, `trap`) are live, the CJD orchestrator + lineage store are wired, and retention-for-training is opt-in per request. See [`CHANGELOG.md`](./CHANGELOG.md) for the release log and [`docs/`](./docs) for operator + integrator documentation.

## Install

```bash
pip install compile-pdf
```

For producers that need geometry primitives (marks, impose, trap):

```bash
pip install 'compile-pdf[geom]'
```

For the trap producer with Ghostscript engine fallback:

```bash
pip install 'compile-pdf[geom,trap-gs]'
```

## CLI

```bash
compile-pdf rewrite  --plan plan.json     input.pdf output.pdf
compile-pdf marks    --template tmpl.json input.pdf output.pdf
compile-pdf impose   --layout layout.json input.pdf output.pdf
compile-pdf trap     --policy policy.json input.pdf output.pdf

compile-pdf version
compile-pdf contract
compile-pdf health
compile-pdf cjd apply <job.json|job.xml>
compile-pdf lineage <id> [--chain]
```

### Opting in to retention-for-training

Every producer endpoint (and the CJD orchestrator) accepts an
explicit opt-in signal that retains the call's inputs and outputs
for engine training. Off by default; engaged per-request.

```bash
curl -X POST $COMPILE_BASE/v1/rewrite/apply \
  -H "X-Compile-Retain-For-Training: true" \
  -H "X-Compile-Tenant: acme-co" \
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
