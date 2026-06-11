---
title: "White / underbase producer"
description: "White-ink / underbase / varnish / foil plate generation — adds a named DeviceN separation derived from the input's ink coverage."
group: "Reference"
order: 15
---

# White / underbase producer

The white-underbase producer generates a white-ink (or underbase /
varnish / foil) plate for an input PDF and registers it as a named
separation, for label / garment / foil work on dark or specialty
substrates.

Ships as the [`compile-pdf-white-underbase`](https://github.com/printwithsynergy/compile-pdf-white-underbase)
satellite package. Mounted under `/v1/white-underbase` when
`COMPILE_PRODUCER` is `white_underbase` or `all`. Schema version:
`WHITE_UNDERBASE_SCHEMA_VERSION = "1.0.0"` (owned by the satellite's
`version.py`, re-exported into `/v1/contract`).

## Endpoint

`POST /v1/white-underbase/apply`

Request — input PDF inline as base64 plus a generation policy (every
knob optional; the common real-world request is just
`{"separation_name": "White"}`):

```json
{
  "input_pdf_b64": "…",
  "policy": {
    "separation_name": "White",
    "plate_use": "white",
    "strategy": "auto",
    "knockout_threshold_pct": 5.0,
    "choke_pt": 0.0,
    "page_indices": null
  }
}
```

- `strategy` — `auto` (white wherever coverage exceeds the
  threshold), `union` (white wherever any ink prints), `knockout`
  (white where artwork is *absent*), or `manual` (register the
  separation, trace nothing).
- `plate_use` — `white | underbase | varnish | foil`; recorded as
  DeviceN colorant metadata so downstream RIPs treat the plate
  correctly.
- `choke_pt` — shrink (negative) / grow (positive) the plate
  relative to source geometry, ±2pt.
- `page_indices` — restrict to these 0-indexed pages; `null` means
  every page.

Response:

```json
{
  "output_pdf_b64": "…",
  "pdf_sha256": "…",
  "input_sha256": "…",
  "policy_sha256": "…",
  "cache_key": "…",
  "cache_hit": false,
  "summary": {
    "pages_processed": 4,
    "separation_name": "White",
    "plate_use": "white",
    "strategy_applied": "auto"
  },
  "schema_version": "1.0.0",
  "compile_version": "0.7.0"
}
```

Errors: 400 (malformed / empty base64), 422 (engine rejected the
policy), 500 (post-condition verify failed, with the failure list).

## CLI

```bash
compile-pdf white-underbase --policy policy.json input.pdf output.pdf
```

`--policy` is optional (defaults apply); `--no-verify` skips
post-condition checks.

## Status

Shipped (passthrough engine). The response shape is final; once the
real coverage tracer lands, the only caller-visible change is that
`output_pdf_b64` differs from the input when the policy selects any
pages.
