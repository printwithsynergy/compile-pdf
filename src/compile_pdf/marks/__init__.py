"""Marks producer — register / crop / color-bar / fold marks plus 1-up
proofing slugs and external mark template ingestion.

Per spec §3.1 — 12 v1.0 essential mark types across production +
proofing + universal categories. Two ingestion modes: programmatic
(JSON-declared marks) and external file (tenant-uploaded PDF/PNG/SVG
stamped at anchor).
"""

from compile_pdf.version import MARKS_SCHEMA_VERSION

__all__ = ["MARKS_SCHEMA_VERSION"]
