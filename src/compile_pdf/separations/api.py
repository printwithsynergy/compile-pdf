# SPDX-License-Identifier: AGPL-3.0-or-later
"""FastAPI router for the separations metadata-lookup service.

Mounts under ``/v1/separations`` from :mod:`compile_pdf.api.main`.

Endpoints
---------

- ``POST /v1/separations/list`` — accepts a base64-encoded input PDF
  and returns one entry per named separation found across the
  document, aggregated by ink name with the set of pages each ink
  appears on.

Editor surface: the artwork-pdf "inks palette" (Wave 2 PR-5 / C1)
calls this after a compose render to populate its per-page ink
list. Always-on regardless of ``COMPILE_PRODUCER`` — it's read-only
metadata over the supplied PDF and carries no producer-side state.
"""

from __future__ import annotations

import base64
import binascii

import structlog
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from compile_pdf.separations.extract import list_separations

logger = structlog.get_logger(__name__)

router = APIRouter()


class SeparationsListRequest(BaseModel):
    """Request envelope for ``POST /v1/separations/list``."""

    model_config = {"extra": "forbid"}

    input_pdf_b64: str = Field(min_length=1, description="Base64-encoded PDF bytes.")


class SeparationEntry(BaseModel):
    """One named ink found in the input PDF."""

    model_config = {"extra": "forbid"}

    name: str
    color_space: str = Field(description='One of "Separation", "DeviceN".')
    occurs_on_pages: list[int] = Field(
        description="0-indexed page numbers on which this ink appears."
    )


class SeparationsListResponse(BaseModel):
    """Response envelope for ``POST /v1/separations/list``."""

    model_config = {"extra": "forbid"}

    separations: list[SeparationEntry]
    total: int = Field(description="Number of distinct named inks discovered.")


@router.post(
    "/list",
    response_model=SeparationsListResponse,
    summary="Enumerate named separations in an input PDF",
)
def list_endpoint(req: SeparationsListRequest) -> SeparationsListResponse:
    """Walk every page of ``req.input_pdf_b64`` and return one entry
    per distinct named separation.

    Process colors (DeviceCMYK / DeviceGray / ICCBased) are NOT
    enumerated — only named separations declared via ``/Separation``
    or ``/DeviceN`` color-space arrays in ``/Resources/ColorSpace``.
    """
    try:
        input_bytes = base64.b64decode(req.input_pdf_b64, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"input_pdf_b64 is not valid base64: {exc}",
        ) from exc

    seps = list_separations(input_bytes)
    return SeparationsListResponse(
        separations=[
            SeparationEntry(
                name=s.name,
                color_space=s.color_space,
                occurs_on_pages=list(s.occurs_on_pages),
            )
            for s in seps
        ],
        total=len(seps),
    )
