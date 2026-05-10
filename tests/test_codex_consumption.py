"""Smoke tests asserting the published codex-pdf surface compile depends on.

These lock the producer-side contract in CI: if a future codex release
removes or renames a symbol compile reaches for, these tests fail loud
before any producer engine code runs.
"""

from __future__ import annotations

import re


def _parse_semver(value: str) -> tuple[int, int, int]:
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", value)
    assert match is not None, f"not a semver string: {value!r}"
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def test_codex_pdf_version_is_at_or_above_floor() -> None:
    """codex-pdf must publish __version__ and be >= the pin floor (1.4.2)."""
    from codex_pdf import __version__ as codex_version

    assert isinstance(codex_version, str) and codex_version, codex_version
    assert _parse_semver(codex_version) >= (1, 4, 2), codex_version


def test_codex_color_schema_version_imports() -> None:
    from codex_pdf.color import COLOR_SCHEMA_VERSION

    assert isinstance(COLOR_SCHEMA_VERSION, str)
    _parse_semver(COLOR_SCHEMA_VERSION)


def test_codex_geom_schema_version_imports() -> None:
    from codex_pdf.geom import GEOM_SCHEMA_VERSION

    assert isinstance(GEOM_SCHEMA_VERSION, str)
    _parse_semver(GEOM_SCHEMA_VERSION)


def test_compile_health_resolves_real_codex_version() -> None:
    """The /v1/healthz codex_pdf_version field must reflect the real
    installed wheel version, never the legacy 'unknown' fallback."""
    from compile_pdf.api.main import _resolve_codex_pdf_version

    version = _resolve_codex_pdf_version()
    assert version != "unknown", "codex_pdf import should not fall back"
    _parse_semver(version)
