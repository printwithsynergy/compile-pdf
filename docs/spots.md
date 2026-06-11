---
title: "Spots lookup"
description: "Read-only PANTONE catalogue lookup — search, exact lookup, and library enumeration over codex-pdf's spot-colorant reference."
group: "Reference"
order: 18
---

# Spots lookup

The spots service is a read-only HTTP wrapper around codex-pdf's
PANTONE reference — search, exact lookup, and library enumeration.
It is not a producer; it writes nothing and consults no input PDF.

Ships in [`compile-pdf-core`](https://github.com/printwithsynergy/compile-pdf-core)
(`compile_pdf_core.spots`) rather than its own satellite — it's
shared plumbing every artwork-pdf editor instance needs at boot.
**Always-on** — mounted under `/v1/spots` regardless of
`COMPILE_PRODUCER`. As a read-only service it carries no producer
schema version and does not appear in `/v1/contract`'s
`producer_schema_versions`.

## Endpoints

### `GET /v1/spots/search?q=&library=&limit=`

Substring search on the *normalized* name (`PANTONE 485 C` matches
`PANTONE 485C` and case variants), optionally filtered to one
sub-library. `limit` defaults to 50, capped at 200; empty `q`
returns the first `limit` entries (an initial "browse" view).

```json
{
  "results": [
    {
      "name": "PANTONE 485 C",
      "library": "formula-guide-coated",
      "lab": [48.2, 68.5, 54.1],
      "cmyk_bridge": [0.0, 0.95, 1.0, 0.0],
      "lab_source": "…",
      "cmyk_source": "…"
    }
  ],
  "total": 1,
  "limit": 50
}
```

`total` is the pre-limit match count.

### `GET /v1/spots/lookup?name=`

Exact lookup with codex's alternate-key fallback
(`PANTONE 485 C` ↔ `PANTONE 485C`). Returns a single entry in the
same shape as a search result; 404 on miss.

### `GET /v1/spots/libraries`

Enumerates the sub-libraries (Formula Guide Coated, Color Bridge
Uncoated, …) with per-library entry counts:

```json
{ "libraries": [ { "id": "formula-guide-coated", "count": 2390 } ] }
```

`id` matches the `library` filter accepted by `/search`.

## Codex surface consumed

`codex_pdf.color.load_pantone_reference`,
`codex_pdf.color.normalize_pantone_name`,
`codex_pdf.color.lookup_pantone_spot` — Compile wraps; it never
vendors a Pantone JSON (the consume-surface audit bans it).

## Status

Shipped. Pure read of codex's catalogue — no state, no cache key,
no lineage record.
