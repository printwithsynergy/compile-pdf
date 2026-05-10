"""FastAPI router for the CJD pipeline + lineage lookup.

Mounts:

* ``POST /v1/cjd/apply`` — execute a CJD job
* ``GET  /v1/lineage/{lineage_id}`` — fetch a chain by id
* ``GET  /v1/lineage`` — list known lineage ids (paginated)
"""

from __future__ import annotations

import base64

import structlog
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from compile_pdf.cjd.orchestrator import CjdOrderError, execute
from compile_pdf.cjd.schema import CjdJob
from compile_pdf.lineage.store import (
    LineageNotFoundError,
    default_store,
    serialize_chain,
)
from compile_pdf.version import (
    CJD_SCHEMA_VERSION,
    VERSION,
)

logger = structlog.get_logger(__name__)

cjd_router = APIRouter()
lineage_router = APIRouter()


class CjdApplyResponse(BaseModel):
    model_config = {"extra": "forbid"}

    output_pdf_b64: str
    output_pdf_sha256: str
    lineage_id: str
    steps: list[dict[str, object]]
    trap_diff: dict[str, object] | None = None
    schema_version: str = CJD_SCHEMA_VERSION
    compile_version: str = VERSION


@cjd_router.post("/apply", response_model=CjdApplyResponse, status_code=status.HTTP_200_OK)
async def cjd_apply(job: CjdJob) -> CjdApplyResponse:
    """Execute a CJD job: orchestrate the four producers in dependency
    order, persist lineage records, return the final PDF + chain."""
    try:
        result = execute(job)
    except CjdOrderError as exc:
        raise HTTPException(status_code=422, detail=f"CJD ordering rejected: {exc}") from exc
    except (ValueError, TypeError) as exc:
        # Includes base64 errors from inside execute().
        raise HTTPException(status_code=400, detail=f"CJD job rejected: {exc}") from exc

    logger.info(
        "cjd.apply.ok",
        lineage_id=result.lineage_id,
        steps=len(result.steps),
        output_sha=result.output_pdf_sha256[:16],
    )

    return CjdApplyResponse(
        output_pdf_b64=base64.b64encode(result.output_pdf_bytes).decode("ascii"),
        output_pdf_sha256=result.output_pdf_sha256,
        lineage_id=result.lineage_id,
        steps=[_step_to_dict(s) for s in result.steps],
        trap_diff=result.trap_diff,
    )


class LineageListResponse(BaseModel):
    model_config = {"extra": "forbid"}

    lineage_ids: list[str]


@lineage_router.get("/{lineage_id}", status_code=status.HTTP_200_OK)
async def lineage_get(lineage_id: str) -> dict[str, object]:
    """Fetch a lineage chain by id."""
    try:
        chain = default_store().get(lineage_id)
    except LineageNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"lineage_id not found: {lineage_id}") from exc
    return serialize_chain(chain)


@lineage_router.get(
    "",
    response_model=LineageListResponse,
    status_code=status.HTTP_200_OK,
)
async def lineage_list(limit: int = Query(default=50, ge=1, le=500)) -> LineageListResponse:
    """List known lineage ids (best-effort; backend may paginate)."""
    return LineageListResponse(lineage_ids=default_store().list_ids(limit=limit))


def _step_to_dict(step) -> dict[str, object]:  # type: ignore[no-untyped-def]
    payload: dict[str, object] = {
        "step_index": step.step_index,
        "producer": step.producer,
        "input_sha256": step.input_sha256,
        "output_sha256": step.output_sha256,
        "cache_key": step.cache_key,
        "plan_sha256": step.plan_sha256,
    }
    if step.extras:
        payload["extras"] = dict(step.extras)
    if step.trap_diff is not None:
        payload["trap_diff"] = step.trap_diff
    return payload
