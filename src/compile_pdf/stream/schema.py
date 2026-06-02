"""Pydantic envelopes for the streaming wrapper.

The wrapper accepts a discriminated-union envelope that names the
underlying producer and carries that producer's existing request
payload verbatim. Keeping the payload sub-models as the
producer's own request models means a payload that validates here
also validates against the producer's ``/apply`` endpoint — no
divergence risk.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from compile_pdf.impose.api import ImposeApplyRequest
from compile_pdf.marks.api import MarksApplyRequest
from compile_pdf.rewrite.api import RewriteApplyRequest
from compile_pdf.soft_proof.schema import SoftProofApplyRequest
from compile_pdf.trap.api import TrapApplyRequest

SUPPORTED_PRODUCERS = ("rewrite", "marks", "impose", "trap", "soft_proof")
"""Producers whose output is a PDF and thus eligible for streaming.

``spots`` / ``separations`` / ``cjd`` / ``retention`` return JSON
metadata, not PDFs — streaming them adds no value, so they're
excluded by design rather than by oversight.
"""

ProducerName = Literal["rewrite", "marks", "impose", "trap", "soft_proof"]


class _RewriteStreamRequest(BaseModel):
    model_config = {"extra": "forbid"}
    producer: Literal["rewrite"]
    payload: RewriteApplyRequest


class _MarksStreamRequest(BaseModel):
    model_config = {"extra": "forbid"}
    producer: Literal["marks"]
    payload: MarksApplyRequest


class _ImposeStreamRequest(BaseModel):
    model_config = {"extra": "forbid"}
    producer: Literal["impose"]
    payload: ImposeApplyRequest


class _TrapStreamRequest(BaseModel):
    model_config = {"extra": "forbid"}
    producer: Literal["trap"]
    payload: TrapApplyRequest


class _SoftProofStreamRequest(BaseModel):
    model_config = {"extra": "forbid"}
    producer: Literal["soft_proof"]
    payload: SoftProofApplyRequest


class StreamApplyRequest(BaseModel):
    """Envelope POSTed to ``/v1/stream/apply``.

    Tagged-union discrimination on the ``producer`` field routes to
    one of the per-producer payload models. Pydantic enforces the
    payload matches the named producer's request schema.
    """

    model_config = {"extra": "forbid"}

    producer: ProducerName = Field(
        ...,
        description=(
            "Which producer's engine to invoke. Must be one of: "
            "rewrite, marks, impose, trap, soft_proof."
        ),
    )
    payload: dict[str, object] = Field(
        ...,
        description=(
            "The underlying producer's request body, identical to what "
            "you would POST to /v1/{producer}/apply."
        ),
    )


class StreamMetadata(BaseModel):
    """Metadata surfaced as response headers on the streamed response.

    Exposed as a Pydantic model so the CLI and HTTP layer can share
    the same field set without copy-paste.
    """

    model_config = {"extra": "forbid"}

    producer: ProducerName
    pdf_sha256: str
    input_sha256: str
    cache_key: str
    schema_version: str
    compile_version: str
