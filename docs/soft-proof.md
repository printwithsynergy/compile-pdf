---
title: "Soft-proof producer"
description: "ICC soft-proof simulation — render the input PDF as it would appear under a destination ICC profile, with a ΔE accuracy summary."
group: "Reference"
order: 14
---

# Soft-proof producer

The soft-proof producer simulates an input PDF under a destination
ICC profile and reports an aggregate ΔE summary, so an editor host
(artwork-pdf's soft-proof overlay) can show "how far off will this
look on that press?" without a hardcopy proof.

Ships as the [`compile-pdf-soft-proof`](https://github.com/printwithsynergy/compile-pdf-soft-proof)
satellite package. Mounted under `/v1/soft-proof` when
`COMPILE_PRODUCER` is `soft_proof` or `all`. Schema version:
`SOFT_PROOF_SCHEMA_VERSION = "1.0.0"` (owned by the satellite's
`version.py`, re-exported into `/v1/contract`).

## Endpoint

`POST /v1/soft-proof/apply`

Request — input PDF plus **both** ICC profiles inline as base64
(no pre-upload step; the profile bytes are hashed into the cache
key, so identical requests hit cache):

```json
{
  "input_pdf_b64": "…",
  "source_icc_b64": "…",
  "destination_icc_b64": "…",
  "options": {
    "intent": "relative-colorimetric",
    "black_point_compensation": true,
    "delta_e_formula": "ciede2000"
  }
}
```

`intent` is one of `perceptual | relative-colorimetric | saturation |
absolute-colorimetric`; `delta_e_formula` one of `cie76 | cie94 |
ciede2000`. All options have defaults.

Response:

```json
{
  "output_pdf_b64": "…",
  "pdf_sha256": "…",
  "input_sha256": "…",
  "options_sha256": "…",
  "source_icc_sha256": "…",
  "destination_icc_sha256": "…",
  "cache_key": "…",
  "cache_hit": false,
  "delta_e": { "max": 0.0, "avg": 0.0, "p95": 0.0 },
  "schema_version": "1.0.0",
  "compile_version": "0.7.0"
}
```

Errors: 400 (malformed / empty base64, with the offending field
named), 422 (engine rejected the payload), 500 (post-condition
verify failed).

## Notes

- `delta_e` carries only `max` / `avg` / `p95` — the full per-pixel
  ΔE map is too heavy for the JSON envelope and is rendered
  separately by the editor host.
- Reachable through the streaming wrapper too:
  `POST /v1/stream/apply` with `producer: "soft_proof"` (see
  [`stream.md`](./stream.md)). There is no dedicated CLI
  subcommand; use `compile-pdf stream --producer soft_proof`.

## Status

Shipped (passthrough engine). The response shape is final; when the
real LCMS-based simulator lands, the only caller-visible change is
that the ΔE summary becomes meaningfully larger for mismatched
profile pairs.
