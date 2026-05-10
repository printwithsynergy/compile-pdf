"""Marks producer — register / crop / color-bar / fold marks plus 1-up
proofing slugs and external mark template ingestion.

Per spec §3.1 — 12 v1.0 essential mark types across production +
proofing + universal categories. Two ingestion modes: programmatic
(JSON-declared marks) and external file (tenant-uploaded PDF/PNG/SVG
stamped at anchor).

Codex surface consumed (geometry primitives — no Compile-side math):

- :class:`codex_pdf.geom.Box` — bounding rectangles for mark anchors.
- :class:`codex_pdf.geom.Point` — anchor points.
- :class:`codex_pdf.geom.Polygon` — non-rectangular mark zones.
- :func:`codex_pdf.geom.polygon_offset` — bleed expansion / contraction.
- :func:`codex_pdf.geom.polygon_union` — multi-mark merging.
"""

from __future__ import annotations

from codex_pdf.geom import Box, Point, Polygon, polygon_offset, polygon_union

from compile_pdf.version import MARKS_SCHEMA_VERSION

__all__ = [
    "Box",
    "MARKS_SCHEMA_VERSION",
    "Point",
    "Polygon",
    "polygon_offset",
    "polygon_union",
]
