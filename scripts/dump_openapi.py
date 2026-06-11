"""Regenerate ``docs/openapi.yaml`` from the live FastAPI app.

Run after changing any route/schema; CI re-runs this and fails if the
committed spec is stale (``git diff --exit-code docs/openapi.yaml``).
"""

from __future__ import annotations

from pathlib import Path

import yaml

from compile_pdf.api.main import app


def main() -> None:
    spec = app.openapi()
    out = Path(__file__).resolve().parent.parent / "docs" / "openapi.yaml"
    out.write_text(
        yaml.safe_dump(spec, sort_keys=False, allow_unicode=True, width=100),
        encoding="utf-8",
    )
    print(f"wrote {out} ({len(spec.get('paths', {}))} paths)")


if __name__ == "__main__":
    main()
