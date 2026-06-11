# SPDX-License-Identifier: AGPL-3.0-or-later
"""Surface test: separations module's public surface.

This module wraps pikepdf for color-space introspection and does NOT
redefine any of the codex_pdf banned-symbol set. The
``consume_surface_audit`` script will assert that; this test just
pins the public surface so a future refactor doesn't accidentally
re-export forbidden names.
"""

from __future__ import annotations


def test_extract_module_public_surface() -> None:
    from compile_pdf_separations import extract

    # Public API: SeparationInfo dataclass + list_separations fn.
    assert hasattr(extract, "SeparationInfo")
    assert hasattr(extract, "list_separations")


def test_api_module_public_surface() -> None:
    from compile_pdf_separations import api

    # Public API: the FastAPI router + the request/response models.
    assert hasattr(api, "router")
    assert hasattr(api, "SeparationsListRequest")
    assert hasattr(api, "SeparationsListResponse")
    assert hasattr(api, "SeparationEntry")


def test_separations_router_mounted_on_app() -> None:
    """The /v1/separations/list endpoint must show up on the app's
    route list — guards against the always-on mount block in
    api/main.py silently failing under the ImportError shield."""
    from compile_pdf.api.main import app

    paths = {route.path for route in app.routes}  # type: ignore[attr-defined]
    assert "/v1/separations/list" in paths
