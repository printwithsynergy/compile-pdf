"""Surface test: marks producer must re-export codex_pdf.geom primitives."""

from __future__ import annotations


def test_marks_module_reexports_geom_primitives() -> None:
    from compile_pdf import marks

    for symbol in ("Box", "Point", "Polygon", "polygon_offset", "polygon_union"):
        assert hasattr(marks, symbol), f"marks must re-export {symbol}"
        assert symbol in marks.__all__


def test_marks_geom_symbols_match_canonical_imports() -> None:
    from codex_pdf import geom as codex_geom

    from compile_pdf import marks

    assert marks.Box is codex_geom.Box
    assert marks.Point is codex_geom.Point
    assert marks.Polygon is codex_geom.Polygon
    assert marks.polygon_offset is codex_geom.polygon_offset
    assert marks.polygon_union is codex_geom.polygon_union
