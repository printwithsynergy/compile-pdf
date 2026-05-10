"""CJD (Compile Job Definition) — schema for multi-producer job envelopes.

A CJD bundles an input PDF + an ordered list of producer steps into a
single submission. Steps execute in dependency order
(``rewrite → marks → impose → trap``) — the orchestrator reorders
out-of-spec submissions silently unless ``strict_order=True`` is set,
which makes any departure from the canonical order a 422.

JSON is the canonical encoding for v1; the XML branch is reserved for
Phase 5.x once the JDF/PJTF interop story is finalized.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, RootModel

from compile_pdf.impose.layout_schema import ImposePlan
from compile_pdf.marks.template_schema import MarksTemplate
from compile_pdf.rewrite.plan_schema import RewritePlan
from compile_pdf.trap.policy_schema import TrapPolicy


class _StepBase(BaseModel):
    model_config = {"extra": "forbid", "frozen": True}


class CjdRewriteStep(_StepBase):
    type: Literal["rewrite"]
    plan: RewritePlan


class CjdMarksStep(_StepBase):
    type: Literal["marks"]
    template: MarksTemplate


class CjdImposeStep(_StepBase):
    type: Literal["impose"]
    plan: ImposePlan


class CjdTrapStep(_StepBase):
    type: Literal["trap"]
    policy: TrapPolicy


CjdStep = Annotated[
    CjdRewriteStep | CjdMarksStep | CjdImposeStep | CjdTrapStep,
    Field(discriminator="type"),
]


# Canonical execution order (spec §4.5.2). Out-of-order submissions are
# reordered to match unless the caller opts into strict mode.
PRODUCER_ORDER: tuple[str, ...] = ("rewrite", "marks", "impose", "trap")


class CjdJob(BaseModel):
    """Top-level CJD document — schema-versioned envelope."""

    model_config = {"extra": "forbid"}

    schema_version: Literal["1.0.0"] = Field(
        default="1.0.0",
        description="Bumps when the CJD-document schema changes (per producer; spec §6.2).",
    )
    job_id: str | None = Field(
        default=None,
        description=(
            "Operator-assigned job identifier. When omitted the orchestrator "
            "synthesizes a deterministic ULID-style id from the input + steps."
        ),
    )
    input_pdf_b64: str = Field(min_length=1)
    steps: list[CjdStep] = Field(min_length=1)
    strict_order: bool = Field(
        default=False,
        description=(
            "When True, reject any step ordering that doesn't match the "
            "canonical rewrite→marks→impose→trap order with a 422. When "
            "False (default), the orchestrator reorders silently."
        ),
    )


class CjdJobRoot(RootModel[CjdJob]):
    """Root model — emit JSON Schema directly without a wrapping object."""


def cjd_job_json_schema() -> dict[str, object]:
    """Return the JSON Schema for a CJD document.

    Surfaced via ``compile-pdf cjd-schema`` and (once api/main mounts
    the schema endpoint) ``GET /v1/schema/cjd``.
    """
    return CjdJob.model_json_schema()


__all__ = [
    "PRODUCER_ORDER",
    "CjdImposeStep",
    "CjdJob",
    "CjdJobRoot",
    "CjdMarksStep",
    "CjdRewriteStep",
    "CjdStep",
    "CjdTrapStep",
    "cjd_job_json_schema",
]
