"""FastAPI router for the streaming wrapper.

Mounts under ``/v1/stream`` from :mod:`compile_pdf.api.main`.
Single endpoint: ``POST /v1/stream/apply``. Accepts the same
envelope shape as :class:`compile_pdf.stream.schema.StreamApplyRequest`
and returns ``Content-Type: application/pdf`` with
``Transfer-Encoding: chunked`` plus ``X-Compile-*`` metadata
headers (pdf_sha256, input_sha256, cache_key, schema_version,
compile_version, producer).
"""

from __future__ import annotations

from collections.abc import Iterator

import structlog
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from compile_pdf.stream.engine import (
    StreamEngineError,
    dispatch_stream,
)
from compile_pdf.stream.schema import StreamApplyRequest
from compile_pdf.stream.verify import verify_stream_output

logger = structlog.get_logger(__name__)

router = APIRouter()


# Chunk size for the streaming response. 64 KiB is the same chunk
# size FastAPI's StreamingResponse uses by default for file-like
# iterables, and matches what most CDN edge caches expect. Pinning
# it explicitly keeps the wire shape stable across uvicorn / hypercorn
# tunables.
_STREAM_CHUNK_BYTES = 64 * 1024


def _chunked_iter(output_bytes: bytes) -> Iterator[bytes]:
    """Yield ``output_bytes`` in fixed-size chunks for streaming."""
    for start in range(0, len(output_bytes), _STREAM_CHUNK_BYTES):
        yield output_bytes[start : start + _STREAM_CHUNK_BYTES]


@router.post("/apply", status_code=status.HTTP_200_OK)
async def stream_apply(payload: StreamApplyRequest) -> StreamingResponse:
    """Run the named producer's engine and stream the resulting PDF.

    Errors map as:
      - 400 if the producer name is unknown or the payload doesn't
        carry a valid ``input_pdf_b64`` / schema-validated body.
      - 422 if the underlying engine rejects an otherwise valid
        payload (e.g. trap policy references unknown separations).
      - 500 if the engine produced bytes that don't pass the
        wrapper-level verify (no PDF header, empty output) — at
        that point the producer's own verify is suspect.
    """
    try:
        result = dispatch_stream(payload.producer, payload.payload)
    except StreamEngineError as exc:
        message = str(exc)
        # Heuristic: payload-shape errors are 400, engine-rejected
        # payloads are 422. The dispatch layer phrases the message
        # with "rejected" for the latter case so we can route
        # without a second exception type.
        if "rejected" in message:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=message) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message) from exc

    verify = verify_stream_output(result.output_bytes)
    if not verify.ok:
        logger.error("stream.apply.verify_failed", failures=verify.failures)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "stream verify failed", "failures": verify.failures},
        )

    logger.info(
        "stream.apply.ok",
        producer=payload.producer,
        pdf_sha256=result.metadata.pdf_sha256[:16],
        cache_key=result.metadata.cache_key[:16],
        bytes=len(result.output_bytes),
    )

    headers = {
        "X-Compile-Producer": result.metadata.producer,
        "X-Compile-PDF-SHA256": result.metadata.pdf_sha256,
        "X-Compile-Input-SHA256": result.metadata.input_sha256,
        "X-Compile-Cache-Key": result.metadata.cache_key,
        "X-Compile-Schema-Version": result.metadata.schema_version,
        "X-Compile-Compile-Version": result.metadata.compile_version,
        # Hint Content-Length when we know it; chunked transfer is
        # implied by FastAPI's StreamingResponse anyway.
        "Content-Length": str(len(result.output_bytes)),
    }

    return StreamingResponse(
        _chunked_iter(result.output_bytes),
        media_type="application/pdf",
        headers=headers,
    )
