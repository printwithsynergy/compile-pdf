---
title: "Separations lookup"
description: "Read-only named-ink enumeration — list every /Separation and /DeviceN colorant in an input PDF, with the pages each ink appears on."
group: "Reference"
order: 17
---

# Separations lookup

The separations service enumerates the **named inks** in an input
PDF: one entry per distinct separation declared via `/Separation` or
`/DeviceN` color-space arrays, aggregated by ink name with the set
of 0-indexed pages each ink appears on. It is read-only metadata —
not a producer; it writes nothing.

Ships as the [`compile-pdf-separations`](https://github.com/printwithsynergy/compile-pdf-separations)
satellite package. **Always-on** — mounted under `/v1/separations`
regardless of `COMPILE_PRODUCER`. As a read-only service it carries
no producer schema version and does not appear in `/v1/contract`'s
`producer_schema_versions`.

Editor surface: artwork-pdf's inks palette calls this after a
compose render to populate its per-page ink list.

## Endpoint

`POST /v1/separations/list`

```json
{ "input_pdf_b64": "…" }
```

Response:

```json
{
  "separations": [
    { "name": "PANTONE 485 C", "color_space": "Separation", "occurs_on_pages": [0, 2] },
    { "name": "White",         "color_space": "DeviceN",    "occurs_on_pages": [1] }
  ],
  "total": 2
}
```

`color_space` is `"Separation"` or `"DeviceN"`. Process colors
(DeviceCMYK / DeviceGray / ICCBased) are **not** enumerated — only
named separations.

Errors: 400 (malformed base64).

## Status

Shipped. Pure function of the input bytes — no state, no cache key,
no lineage record.
