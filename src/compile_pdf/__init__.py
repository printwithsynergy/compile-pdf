"""CompilePDF — the only writer in the Print With Synergy stack.

Four producers under one package:

- :mod:`compile_pdf.rewrite` — single-PDF-in/out object-tree mutations
  (OCG flips, metadata, color-space swap, hygiene strips, lifecycle ops)
- :mod:`compile_pdf.marks` — register/crop/color-bar/fold marks plus
  1-up proofing slugs and external mark template ingestion
- :mod:`compile_pdf.impose` — sheet-level step-and-repeat layout
- :mod:`compile_pdf.trap` — ink-pair spread/choke trap with three
  engine slots (pure_python / ghostscript / external)

Architectural invariants:

- CompilePDF is the *only* writer. Codex stays read-only.
- Every producer consumes Codex primitives through published surfaces;
  re-implementation is forbidden by ``scripts/consume_surface_audit.py``.
- Every producer emits deterministic bytes; same input + same plan +
  same engine fingerprint → same SHA-256 output.

See ``docs/`` (architecture, contract, deploy, per-producer pages,
``operations/``) for the operator + integrator reference and
``CHANGELOG.md`` for the per-release log.
"""

from compile_pdf.version import (
    COMPILE_DOCUMENT_SCHEMA_VERSION,
    IMPOSE_SCHEMA_VERSION,
    MARKS_SCHEMA_VERSION,
    REWRITE_SCHEMA_VERSION,
    TRAP_SCHEMA_VERSION,
    VERSION,
)

__all__ = [
    "VERSION",
    "REWRITE_SCHEMA_VERSION",
    "MARKS_SCHEMA_VERSION",
    "IMPOSE_SCHEMA_VERSION",
    "TRAP_SCHEMA_VERSION",
    "COMPILE_DOCUMENT_SCHEMA_VERSION",
]
__version__ = VERSION
