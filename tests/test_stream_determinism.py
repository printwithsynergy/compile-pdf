"""Determinism guard for the stream wrapper.

Same input + same producer payload across three runs must yield
identical output bytes, identical pdf_sha256, and identical
cache_key. Catches regressions where dispatch or cache-key
computation depends on hidden state (time, env, randomness).
"""

from __future__ import annotations

import base64

from compile_pdf_stream.engine import dispatch_stream


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def test_rewrite_determinism(simple_pdf: bytes) -> None:
    payload = {"input_pdf_b64": _b64(simple_pdf), "plan": {"ops": []}}
    runs = [dispatch_stream("rewrite", payload) for _ in range(3)]
    first = runs[0]
    for run in runs[1:]:
        assert run.output_bytes == first.output_bytes
        assert run.metadata.pdf_sha256 == first.metadata.pdf_sha256
        assert run.metadata.cache_key == first.metadata.cache_key
        assert run.metadata.input_sha256 == first.metadata.input_sha256
