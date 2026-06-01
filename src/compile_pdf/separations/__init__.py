# SPDX-License-Identifier: AGPL-3.0-or-later
"""Separations enumeration — read-only metadata service.

Mirrors the :mod:`compile_pdf.spots` package layout. Walks an input
PDF's ``/Resources/ColorSpace`` entries and returns every named
separation found, aggregated by ink across pages.

Editor surface: artwork-pdf's C1 ("inks palette", Wave 2 PR-5) calls
``POST /v1/separations/list`` after a compose render to populate its
per-page ink list. The endpoint is always-on regardless of
``COMPILE_PRODUCER`` since it carries no producer-side state — it's
metadata over the input PDF.
"""
