---
title: "Retention-for-training"
description: "Engine-side counterpart to the marketing demo's opt-in: per-call retention of input/output PDFs and producer responses to S3-compatible storage with a TTL tag."
group: "Reference"
order: 3
---

# Retention-for-training

Compile retains a call's inputs and outputs only when the caller
explicitly opts in **and** the operator has configured a bucket.
Default-off, fail-soft.

## Wire signal

| Channel | Header / field | Truthy |
|---|---|---|
| Per request (any endpoint) | `X-Compile-Retain-For-Training` | `true`, `1`, `yes` |
| Multipart endpoints only | `retain_for_training` form field | `true`, `1`, `yes` |
| Tenant label (optional) | `X-Compile-Tenant` | any string — slugified |

Trimmed + case-insensitive. The header takes precedence over the
form field when both are present. Anything else — `false`, `0`,
`no`, empty string, missing header — is a default-off opt-out.

## Operator configuration

Set on the producer container. All env vars are optional; with no
`COMPILE_RETAIN_BUCKET`, retention is silently disabled even on
opted-in calls.

| Env var | Default | Purpose |
|---|---|---|
| `COMPILE_RETAIN_BUCKET` | _(unset)_ | S3-compatible bucket name. Empty → feature disabled. |
| `COMPILE_RETAIN_PREFIX` | `retain` | Top-level key prefix inside the bucket. |
| `COMPILE_RETAIN_TTL_DAYS` | `90` | Value written to the `ttl-days` object tag for the bucket's lifecycle rule. |
| `COMPILE_RETAIN_ENDPOINT_URL` | _(unset)_ | S3-compatible endpoint (MinIO, R2, etc.). Defaults to AWS S3. |
| `COMPILE_RETAIN_REGION` | _(unset)_ | AWS region for the S3 client. |
| `COMPILE_RETAIN_AWS_ACCESS_KEY_ID` | _(unset)_ | Override for default boto3 credential discovery. |
| `COMPILE_RETAIN_AWS_SECRET_ACCESS_KEY` | _(unset)_ | Override for default boto3 credential discovery. |

## Object layout

```
{prefix}/{tenant}/{producer}/{YYYY-MM-DD}/{input_sha256}/input.pdf
{prefix}/{tenant}/{producer}/{YYYY-MM-DD}/{input_sha256}/output.pdf
{prefix}/{tenant}/{producer}/{YYYY-MM-DD}/{input_sha256}/result.json
```

* `tenant` — slugified `X-Compile-Tenant`, or `anonymous`.
* `producer` — `rewrite` / `marks` / `impose` / `trap`.
* `YYYY-MM-DD` — UTC date the call was retained.
* `input_sha256` — SHA-256 of the input bytes the producer received.

Every object is tagged `ttl-days=<COMPILE_RETAIN_TTL_DAYS>` so the
bucket's lifecycle policy can sweep at expiry — Compile itself
never deletes by age.

`result.json` is the JSON response body the producer returned to
the caller, **with `output_pdf_b64` stripped** (those bytes already
live in `output.pdf`).

## CJD orchestration

Every step in a CJD job inherits the same consent + tenant from
the inbound request. Each step writes its own
(input, output, plan) triplet, and the corresponding
`LineageStep.retained_for_training` flag flips true. Operators can
audit who opted in via `GET /v1/lineage/{id}` — the chain returns
the flag per step.

## Erasure (`POST /v1/retention/delete`)

```bash
curl -sS -X POST $COMPILE_BASE/v1/retention/delete \
  -H "Authorization: Bearer $COMPILE_BEARER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"sha256": "abc123…"}' | jq
```

```json
{ "deleted": 3, "keys": [
  "retain/acme/rewrite/2026-05-11/abc123…/input.pdf",
  "retain/acme/rewrite/2026-05-11/abc123…/output.pdf",
  "retain/acme/rewrite/2026-05-11/abc123…/result.json"
]}
```

Behaviours:

* Walks the configured bucket + prefix, deletes every key whose
  string contains `/{sha256}/`. Matches across all tenants /
  producers / dates.
* Zero hits → `200 {"deleted": 0, "keys": []}`. Not an error.
* `COMPILE_RETAIN_BUCKET` unset → `503`.
* Any `boto3` exception → `500`.

## Failure model

Producer endpoints **never** fail on retention errors. If
persistence hits an S3 exception, the failure is swallowed,
`retained_for_training` stays false on the lineage record, and the
producer response is returned untouched. A transient bucket outage
cannot break a producer call.

## Example lifecycle policy

A minimal bucket-side rule that honours the `ttl-days` tag (AWS
S3 / R2 / MinIO compatible):

```json
{
  "Rules": [
    {
      "ID": "compile-retain-90d",
      "Status": "Enabled",
      "Filter": { "Tag": { "Key": "ttl-days", "Value": "90" } },
      "Expiration": { "Days": 90 }
    }
  ]
}
```

For multiple TTL classes, add one rule per `ttl-days` value the
fleet writes.
