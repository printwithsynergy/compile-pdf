"""Trap producer — ink-pair spread/choke trap with three engine slots.

Per spec §5.1–§5.7 + §1.11b trap exception:

- ``pure_python`` (default) — uses Codex ``polygon_offset`` (1.1.0)
- ``ghostscript`` — gated by the optional ``[trap-gs]`` extra
- ``external`` — gated by ``[trap-external]``; vendor licensing required

Engine selected via ``COMPILE_TRAP_ENGINE`` env var. Default
``pure_python`` once Codex 1.5 lands; ``ghostscript`` as documented
bootstrap fallback if the bump slips.
"""

from compile_pdf.version import TRAP_SCHEMA_VERSION

__all__ = ["TRAP_SCHEMA_VERSION"]
