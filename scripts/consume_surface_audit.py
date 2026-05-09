"""compile-pdf consume-surface audit — the inverse lock to codex's produce-surface audit.

Per spec §7.5 — Compile MUST write (pikepdf.new, Pdf.save are legal
everywhere); Compile MUST NOT re-implement Codex (Pantone JSON, Clipper2
wrappers, color-resolver precedence ladder, geometry primitives).

Walks the source tree with the AST module, fails CI on any banned
import, function name, or class name. Mirrors the shape of
codex-pdf/scripts/produce_surface_audit.py.

Usage:

    python scripts/consume_surface_audit.py            # exits non-zero on violation
    python scripts/consume_surface_audit.py --report-only  # prints, exits 0

Output: ``reports/audit/consume_surface.json``.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# --- Ban list (per spec §7.5) -----------------------------------------------

BANNED_IMPORTS: frozenset[str] = frozenset({
    # Direct Pantone JSON access bypasses the resolver — must use
    # codex_pdf.color.load_pantone_reference() instead.
    "codex_pdf.color.data.pantone_reference",
    "codex_pdf.color.data",
    # Clipper2 must go through codex_pdf.geom.polygon_* surfaces.
    "pyclipr",
})
"""Modules Compile MUST NOT import directly. Each is a re-implementation
shortcut that bypasses Codex's published surface."""

BANNED_FUNCTION_NAMES: frozenset[str] = frozenset({
    # Re-defining this would mimic codex_pdf.color.resolver's precedence
    # ladder — a Codex surface, not a Compile concern.
    "resolve_spot_swatch_color",
    "match_nearest_pantone",
    "load_pantone_reference",
    "load_inkbook",
})
"""Function names that, if defined in Compile code, indicate
Codex re-implementation. Allowed only inside ``tests/`` (test
fixtures may name-shadow for stubbing)."""

BANNED_CLASS_NAMES: frozenset[str] = frozenset({
    # Geometry primitives — consume from codex_pdf.geom directly.
    "Box", "Matrix", "Path", "TileGrid", "TileResult", "MarksZone", "CellPlacement",
    # Document-shape — Compile reads CodexDocument; never defines its own.
    "CodexDocument", "CodexPage", "CodexPageBoxes", "CodexPageResourcesRef",
    "CodexInfoDict", "CodexColorSpace", "CodexSpotColorant", "CodexOCG",
    "CodexTrapEvidence", "CodexDocumentSummary",
})
"""Class names that re-define Codex types. Allowed only inside ``tests/``."""

EXEMPT_PATHS: tuple[str, ...] = (
    "tests/",
    "scripts/",
    "docs/",
    ".venv/",
    "build/",
    "dist/",
)
"""Path prefixes (relative to repo root) excluded from the audit.
- ``tests/`` may stub Codex types.
- ``scripts/`` may need bare access for diagnostics (this audit included).
- ``docs/`` is markdown.
- ``.venv/``/``build/``/``dist/`` are vendored / build artifacts.
"""

# --- Audit data structures --------------------------------------------------


@dataclass
class Violation:
    file: str
    line: int
    kind: str
    detail: str

    def to_dict(self) -> dict[str, object]:
        return {"file": self.file, "line": self.line, "kind": self.kind, "detail": self.detail}


@dataclass
class AuditResult:
    violations: list[Violation] = field(default_factory=list)
    files_scanned: int = 0

    @property
    def passed(self) -> bool:
        return not self.violations


# --- Walker -----------------------------------------------------------------


def _is_exempt(path: Path) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    return any(rel.startswith(prefix) for prefix in EXEMPT_PATHS)


def _flatten_attribute(node: ast.AST) -> str:
    """Flatten ``a.b.c`` (Attribute over Attribute over Name) to ``"a.b.c"``."""
    parts: list[str] = []
    current: ast.AST | None = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    return ".".join(reversed(parts))


def _check_import(node: ast.Import | ast.ImportFrom, file: str) -> Iterable[Violation]:
    if isinstance(node, ast.ImportFrom):
        if not node.module:
            return
        full = node.module
        if full in BANNED_IMPORTS:
            yield Violation(
                file=file,
                line=node.lineno,
                kind="banned_import",
                detail=f"`from {full} import ...` bypasses the published Codex surface",
            )
            return
        # Catch sub-imports like `from codex_pdf.color.data import pantone_reference`.
        for alias in node.names:
            joined = f"{full}.{alias.name}" if alias.name else full
            if joined in BANNED_IMPORTS:
                yield Violation(
                    file=file,
                    line=node.lineno,
                    kind="banned_import",
                    detail=f"`from {full} import {alias.name}` bypasses the published surface",
                )
    else:
        # bare `import x.y.z`
        for alias in node.names:
            if alias.name in BANNED_IMPORTS:
                yield Violation(
                    file=file,
                    line=node.lineno,
                    kind="banned_import",
                    detail=f"`import {alias.name}` bypasses the published surface",
                )


def _check_definitions(tree: ast.AST, file: str) -> Iterable[Violation]:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in BANNED_FUNCTION_NAMES:
                yield Violation(
                    file=file,
                    line=node.lineno,
                    kind="banned_function_def",
                    detail=f"function name `{node.name}` re-implements a Codex surface",
                )
        elif isinstance(node, ast.ClassDef):
            if node.name in BANNED_CLASS_NAMES:
                yield Violation(
                    file=file,
                    line=node.lineno,
                    kind="banned_class_def",
                    detail=f"class name `{node.name}` re-defines a Codex type",
                )


def _check_file(path: Path) -> Iterable[Violation]:
    rel = path.relative_to(ROOT).as_posix()
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        yield Violation(file=rel, line=exc.lineno or 0, kind="syntax_error", detail=str(exc))
        return
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            yield from _check_import(node, rel)
    yield from _check_definitions(tree, rel)


def run_audit() -> AuditResult:
    result = AuditResult()
    for path in ROOT.rglob("*.py"):
        if _is_exempt(path):
            continue
        result.files_scanned += 1
        result.violations.extend(_check_file(path))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0] if __doc__ else "")
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Always exit 0; useful during development",
    )
    parser.add_argument(
        "--report-path",
        default=str(ROOT / "reports" / "audit" / "consume_surface.json"),
        help="Where to write the JSON report (default: reports/audit/consume_surface.json)",
    )
    args = parser.parse_args()

    result = run_audit()
    payload = {
        "files_scanned": result.files_scanned,
        "violations": [v.to_dict() for v in result.violations],
        "passed": result.passed,
    }

    report_path = Path(args.report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    if result.violations:
        for violation in result.violations:
            print(
                f"[{violation.kind}] {violation.file}:{violation.line} — {violation.detail}",
                file=sys.stderr,
            )
        if not args.report_only:
            print(
                f"\n{len(result.violations)} consume-surface violation(s) detected. "
                f"See {report_path} for full report.",
                file=sys.stderr,
            )
            return 1
    else:
        print(f"consume-surface audit OK: {result.files_scanned} files scanned, no violations.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
