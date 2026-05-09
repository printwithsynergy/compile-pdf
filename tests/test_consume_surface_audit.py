"""Tests for the consume-surface audit script (spec §7.5)."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

# Load the audit module directly so we can call its public surface.
_audit_path = Path(__file__).resolve().parent.parent / "scripts" / "consume_surface_audit.py"
_spec = importlib.util.spec_from_file_location("consume_surface_audit", _audit_path)
assert _spec and _spec.loader
audit = importlib.util.module_from_spec(_spec)
sys.modules["consume_surface_audit"] = audit
_spec.loader.exec_module(audit)


def test_audit_runs_on_clean_tree():
    """The current source tree must pass the audit by default."""
    result = audit.run_audit()
    assert result.passed, f"Unexpected violations: {result.violations}"
    assert result.files_scanned > 0


def test_banned_import_detected_via_synthetic_source(tmp_path, monkeypatch):
    """Synthesize a violating Python file under the repo root and confirm
    the audit flags it. (Uses a temporary subdir of the repo root that is
    not on the EXEMPT list.)"""
    bad_file = audit.ROOT / "src" / "compile_pdf" / "_temp_audit_test_violation.py"
    try:
        bad_file.write_text(
            "from codex_pdf.color.data import pantone_reference\n"
            "_ = pantone_reference\n",
            encoding="utf-8",
        )
        result = audit.run_audit()
        violations = [v for v in result.violations if v.file.endswith(bad_file.name)]
        assert violations, "expected the synthetic banned import to be flagged"
        assert violations[0].kind == "banned_import"
    finally:
        if bad_file.exists():
            bad_file.unlink()


def test_banned_class_def_detected(tmp_path):
    bad_file = audit.ROOT / "src" / "compile_pdf" / "_temp_audit_test_class.py"
    try:
        bad_file.write_text(
            "class Box:\n"
            "    pass\n",
            encoding="utf-8",
        )
        result = audit.run_audit()
        violations = [v for v in result.violations if v.file.endswith(bad_file.name)]
        assert violations, "expected the synthetic banned class def to be flagged"
        assert violations[0].kind == "banned_class_def"
    finally:
        if bad_file.exists():
            bad_file.unlink()


def test_exempt_paths_skipped():
    """Files under tests/ may stub Codex types; audit must not flag them."""
    # The current tests/ tree includes this very file, which never re-implements
    # Codex types; absence of violations is the relevant signal.
    result = audit.run_audit()
    test_violations = [v for v in result.violations if v.file.startswith("tests/")]
    assert not test_violations
