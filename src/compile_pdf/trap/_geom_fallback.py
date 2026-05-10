"""Pyclipr-driven polygon offset — TEMPORARY upstream workaround.

.. warning::

    This module exists **only** because codex_pdf 1.7.0's
    :func:`codex_pdf.geom.polygon_offset` calls
    ``pyclipr.ClipperOffset(miterLimit=…)`` but pyclipr 0.1.8's
    constructor takes no kwargs. The upstream call raises a
    ``TypeError`` on every non-rectangular polygon, blocking
    non-rect trap zones end-to-end.

    The audit (``scripts/consume_surface_audit.py``) normally forbids
    ``import pyclipr``; this file has a documented per-file carve-out
    in ``EXEMPT_FILES``. **Remove the carve-out and this module
    together once codex-pdf ships a fixed polygon_offset.**

The implementation mirrors codex's intended call shape — miter join,
``polygon`` end-type, scale-aware coordinates — so once the upstream
patch lands, callers can swap to ``codex_pdf.geom.polygon_offset`` with
zero behavior change.
"""

from __future__ import annotations

import pyclipr  # noqa: I001  # ruff: isort the third-party group; see module docstring

_SCALE = 100_000.0
"""pyclipr operates on integer coordinates; scale floats to ints with
enough precision for sub-pt trap geometry (5 fractional digits ≈ 7 nm
at PDF user-space scale — well below printable resolution)."""


def polygon_offset(
    points: tuple[tuple[float, float], ...],
    distance: float,
    *,
    miter_limit: float = 2.0,
) -> list[tuple[float, float]]:
    """Inflate (positive ``distance``) or deflate (negative) a closed
    polygon by ``distance`` PDF points and return the first resulting
    ring.

    Returns an empty list when the offset collapses the polygon (typical
    for chokes wider than the polygon's inscribed circle). The caller
    decides whether to treat that as a hard error or a silent skip.
    """
    if not points:
        return []
    scaled = [(int(round(x * _SCALE)), int(round(y * _SCALE))) for x, y in points]
    offsetter = pyclipr.ClipperOffset()
    offsetter.miterLimit = miter_limit
    offsetter.addPaths(
        [scaled],
        pyclipr.JoinType.Miter,
        pyclipr.EndType.Polygon,
    )
    result = offsetter.execute(distance * _SCALE)
    if not result:
        return []
    first_ring = result[0]
    # pyclipr returns numpy float64; coerce to plain Python floats so
    # downstream content-stream serialization stays stable across numpy
    # versions and so the values JSON-serialize without a default helper.
    return [(float(x) / _SCALE, float(y) / _SCALE) for x, y in first_ring]


__all__ = [
    "polygon_offset",
]
