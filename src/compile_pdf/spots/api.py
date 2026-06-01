"""FastAPI router for the spots metadata-lookup service.

Mounts under ``/v1/spots`` from :mod:`compile_pdf.api.main`. Three
endpoints, all read-only, all wrap codex-pdf's PANTONE reference.

Endpoints:

- ``GET /v1/spots/search?q=&library=&limit=`` — substring + library
  filter; returns up to ``limit`` entries (default 50, cap 200).
  Matching is on the *normalized* name (uses
  :func:`codex_pdf.color.normalize_pantone_name` so the same key
  ``PANTONE 485 C`` matches ``PANTONE 485C`` and case variants).
- ``GET /v1/spots/lookup?name=`` — exact lookup with the codex
  alternate-key fallback (404 on miss).
- ``GET /v1/spots/libraries`` — enumerate the sub-libraries with
  per-library entry counts.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)

router = APIRouter()


class SpotEntry(BaseModel):
    """Wire shape for one PANTONE entry. Mirrors
    :class:`codex_pdf.color.PantoneEntry` but as a Pydantic model so
    FastAPI can validate the response envelope.
    """

    model_config = {"extra": "forbid"}

    name: str
    library: str | None = None
    lab: tuple[float, float, float] | None = None
    cmyk_bridge: tuple[float, float, float, float] | None = None
    lab_source: str | None = None
    cmyk_source: str | None = None


class SearchResponse(BaseModel):
    """Search response envelope."""

    model_config = {"extra": "forbid"}

    results: list[SpotEntry]
    total: int = Field(
        description="Number of catalogue entries that matched the query (pre-limit)."
    )
    limit: int


class LibrariesResponse(BaseModel):
    """Library enumeration response."""

    model_config = {"extra": "forbid"}

    libraries: list[dict[str, Any]]


def _entry_to_wire(entry: Any) -> SpotEntry:
    """Convert a :class:`codex_pdf.color.PantoneEntry` into the wire shape.

    Kept defensive: codex emits frozen dataclasses; we read fields by
    attribute and let SpotEntry's Pydantic validation enforce shape.
    """
    return SpotEntry(
        name=entry.name,
        library=entry.library,
        lab=entry.lab,
        cmyk_bridge=entry.cmyk_bridge,
        lab_source=getattr(entry, "lab_source", None),
        cmyk_source=getattr(entry, "cmyk_source", None),
    )


@router.get(
    "/search",
    response_model=SearchResponse,
    summary="Search the PANTONE catalogue",
)
def search(
    q: str | None = Query(default=None, description="Substring match on normalized name."),
    library: str | None = Query(default=None, description="Filter to one sub-library."),
    limit: int = Query(default=50, ge=1, le=200),
) -> SearchResponse:
    """Substring + library search over codex-pdf's catalogue.

    Empty / missing ``q`` returns the first ``limit`` entries; useful
    for an initial "browse" view in the editor's SwatchesPicker.
    """
    from codex_pdf.color import load_pantone_reference, normalize_pantone_name

    ref = load_pantone_reference()
    needle = normalize_pantone_name(q) if q else None

    matches: list[Any] = []
    for entry in ref.entries:
        if library is not None and entry.library != library:
            continue
        if needle is not None:
            if needle not in normalize_pantone_name(entry.name):
                continue
        matches.append(entry)

    total = len(matches)
    capped = matches[:limit]
    return SearchResponse(
        results=[_entry_to_wire(e) for e in capped],
        total=total,
        limit=limit,
    )


@router.get(
    "/lookup",
    response_model=SpotEntry,
    summary="Exact lookup by canonical name",
    responses={404: {"description": "Unknown PANTONE name"}},
)
def lookup(name: str = Query(min_length=1)) -> SpotEntry:
    """Resolve a canonical name to a :class:`SpotEntry`.

    Uses :func:`codex_pdf.color.lookup_pantone_spot` which falls back
    to the alternate-key form (``PANTONE 485 C`` ↔ ``PANTONE 485C``).
    """
    from codex_pdf.color import lookup_pantone_spot

    entry = lookup_pantone_spot(name)
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"unknown PANTONE name: {name!r}",
        )
    return _entry_to_wire(entry)


@router.get(
    "/libraries",
    response_model=LibrariesResponse,
    summary="List the sub-libraries in the catalogue",
)
def libraries() -> LibrariesResponse:
    """Enumerate the sub-libraries (Formula Guide Coated, Color
    Bridge Uncoated, etc.) with per-library entry counts.

    Returned in declaration order from the loaded reference. ``id``
    matches the ``library`` filter accepted by ``/search``.
    """
    from codex_pdf.color import load_pantone_reference

    ref = load_pantone_reference()
    counts: dict[str | None, int] = {}
    order: list[str | None] = []
    for entry in ref.entries:
        lib = entry.library
        if lib not in counts:
            order.append(lib)
        counts[lib] = counts.get(lib, 0) + 1

    libs = [{"id": lib, "count": counts[lib]} for lib in order if lib is not None]
    return LibrariesResponse(libraries=libs)
