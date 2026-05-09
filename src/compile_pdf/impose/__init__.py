"""Impose producer — sheet-level step-and-repeat layout.

Per spec §4.1 — consumes ``codex_pdf.geom.tile_grid`` (with the
GEOM_SCHEMA_VERSION 1.1.0 extension for ``cell_rotation``,
``flip_per_row``, ``bleed_handling``, ``CellPlacement``) as the
canonical layout primitive. No Compile-side layout math.
"""

from compile_pdf.version import IMPOSE_SCHEMA_VERSION

__all__ = ["IMPOSE_SCHEMA_VERSION"]
