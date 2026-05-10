"""CJD schema — discriminated-union acceptance + JSON Schema export."""

from __future__ import annotations

import base64

import pytest
from pydantic import ValidationError

from compile_pdf.cjd.schema import (
    PRODUCER_ORDER,
    CjdImposeStep,
    CjdJob,
    CjdMarksStep,
    CjdRewriteStep,
    CjdTrapStep,
    cjd_job_json_schema,
)


def _b64(payload: bytes = b"%PDF-1.4\n%EOF") -> str:
    return base64.b64encode(payload).decode("ascii")


def test_full_job_round_trips() -> None:
    job = CjdJob(
        input_pdf_b64=_b64(),
        steps=[
            CjdRewriteStep(type="rewrite", plan={"ops": []}),  # type: ignore[arg-type]
            CjdMarksStep(type="marks", template={"marks": []}),  # type: ignore[arg-type]
            CjdImposeStep(
                type="impose",
                plan={  # type: ignore[arg-type]
                    "sheet": {"width_pt": 612, "height_pt": 792},
                    "cell": {"width_pt": 612, "height_pt": 792},
                },
            ),
            CjdTrapStep(type="trap", policy={}),  # type: ignore[arg-type]
        ],
    )
    j = job.model_dump_json()
    restored = CjdJob.model_validate_json(j)
    assert restored == job


def test_minimum_job_requires_at_least_one_step() -> None:
    with pytest.raises(ValidationError):
        CjdJob(input_pdf_b64=_b64(), steps=[])


def test_unknown_step_type_rejected() -> None:
    with pytest.raises(ValidationError):
        CjdJob.model_validate(
            {
                "input_pdf_b64": _b64(),
                "steps": [{"type": "lasso"}],
            }
        )


def test_strict_order_field_defaults_false() -> None:
    job = CjdJob(
        input_pdf_b64=_b64(),
        steps=[CjdMarksStep(type="marks", template={"marks": []})],  # type: ignore[arg-type]
    )
    assert job.strict_order is False


def test_producer_order_constant_is_canonical() -> None:
    assert PRODUCER_ORDER == ("rewrite", "marks", "impose", "trap")


def test_json_schema_exports() -> None:
    schema = cjd_job_json_schema()
    assert "$defs" in schema
    items = schema["properties"]["steps"]["items"]
    assert "discriminator" in items
    assert items["discriminator"]["propertyName"] == "type"
