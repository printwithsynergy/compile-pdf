"""Spots — read-only PANTONE catalogue lookup wrapping ``codex_pdf.color``.

Codex-pdf owns the source-of-truth PANTONE reference data
(``codex_pdf/color/data/pantone_reference.json``, ~23k entries across
16 sub-libraries). This module exposes a thin HTTP surface on top so
TypeScript / non-Python consumers (notably the artwork-pdf editor's
SwatchesPicker) can query without bundling the catalogue themselves.

Trademark note: the catalogue is community-measured public-domain
colour science, not proprietary Pantone data. The "PANTONE" wordmark
is referenced descriptively (per-entry ``name`` like
``"PANTONE 185 C"``); responses don't claim Pantone licensing.

This is not a producer — there's no PDF transform, no engine, no
verify, no cache key. The router mounts unconditionally in
``api/main.py`` (independent of ``COMPILE_PRODUCER``) because
metadata lookup is always-on.
"""

from compile_pdf.spots.api import router

__all__ = ["router"]
