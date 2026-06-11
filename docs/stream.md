---
title: "Stream wrapper"
description: "Producer-agnostic streaming — run rewrite / marks / impose / trap / soft_proof and receive the PDF as a chunked application/pdf response."
group: "Reference"
order: 16
---

# Stream wrapper

The stream meta-producer wraps the PDF-producing producers behind a
single streaming endpoint: the caller names a producer, supplies
that producer's normal `/apply` request body, and receives the
resulting PDF as chunked `application/pdf` instead of a base64-in-JSON
envelope. It runs no engine of its own — it dispatches.

Ships as the [`compile-pdf-stream`](https://github.com/printwithsynergy/compile-pdf-stream)
satellite package. **Always-on** — mounted under `/v1/stream`
regardless of `COMPILE_PRODUCER`, so a single deploy serves both
JSON-shaped `/apply` and chunked streaming. Schema version:
`STREAM_SCHEMA_VERSION = "1.0.0"` (owned by the satellite's
`version.py`, re-exported into `/v1/contract`).

## Endpoint

`POST /v1/stream/apply`

```json
{
  "producer": "trap",
  "payload": { /* identical to the body you'd POST to /v1/trap/apply */ }
}
```

`producer` is one of `rewrite | marks | impose | trap | soft_proof`.
`spots` / `separations` / `cjd` / `retention` return JSON metadata,
not PDFs — they're excluded by design.

Response: the PDF bytes, chunked (64 KiB chunks), with metadata
surfaced as headers instead of a JSON envelope:

```
Content-Type: application/pdf
X-Compile-Producer: trap
X-Compile-PDF-SHA256: …
X-Compile-Input-SHA256: …
X-Compile-Cache-Key: …
X-Compile-Schema-Version: 1.0.0
X-Compile-Compile-Version: 0.7.0
Content-Length: …
```

Errors: 400 (unknown producer / payload doesn't validate), 422
(the underlying engine rejected an otherwise-valid payload), 500
(the streamed bytes failed the wrapper-level verify — no PDF header
or empty output).

## CLI

```bash
compile-pdf stream --producer trap --payload request.json --output out.pdf
```

Runs the dispatch in-process; `--output -` writes raw PDF bytes to
stdout with the metadata JSON on stderr, so a `> out.pdf` redirect
keeps the PDF clean.

## Status

Shipped. Determinism and cache keys are the dispatched producer's
own — the wrapper adds no key components.
