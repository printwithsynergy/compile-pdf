"""Wave 3 PR-6 — O3 streaming render wrapper.

Producer-agnostic streaming wrapper that lets callers POST an
existing producer's request envelope and receive the resulting PDF
back as ``Content-Type: application/pdf`` with
``Transfer-Encoding: chunked``, skipping the base64 round-trip that
doubles PDF byte size on the wire.

Why a separate producer instead of per-producer ``apply-stream``
endpoints? Two reasons:

1. The streaming surface is uniform across producers (same headers,
   same delivery semantics), so a single endpoint with a
   producer-name discriminator keeps the contract honest and avoids
   drift between five near-identical endpoints.
2. Adding ``apply-stream`` to each producer would touch every
   producer's ``api.py`` and bloat the surface area of producer
   modules that today are intentionally minimal.

The wrapper dispatches in-process to each underlying producer's
engine (no HTTP loopback), so cache keys and verify hooks land
exactly the same as the JSON-shaped ``/apply`` endpoints.

Supported producers (PDF-out only): ``rewrite``, ``marks``,
``impose``, ``trap``, ``soft_proof``.

Module surface (mirrors the trap / impose / marks producers so ops
tooling treats every producer the same way):

- ``STREAM_SCHEMA_VERSION`` — bumped per spec §6.2 when the request
  envelope or response header set changes.
- ``router`` — FastAPI router mounted under ``/v1/stream``.
- ``dispatch_stream`` — engine entry point.
"""

from __future__ import annotations

from compile_pdf.stream.api import router
from compile_pdf.version import STREAM_SCHEMA_VERSION

__all__ = ["STREAM_SCHEMA_VERSION", "router"]
