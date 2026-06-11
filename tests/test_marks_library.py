"""Mark library — per-renderer tests for all 12 mark types + external dispatch."""

from __future__ import annotations

import pytest
from compile_pdf_marks.library import (
    MarkRenderError,
    PageGeometry,
    render,
    render_bleed,
    render_center,
    render_color_bar,
    render_crop,
    render_custom,
    render_cut,
    render_external,
    render_fold,
    render_ink_key_bar,
    render_proof_slug,
    render_register,
    render_slug_text,
    render_tile_stitch,
)
from compile_pdf_marks.template_schema import (
    BleedMark,
    CenterMark,
    ColorBar,
    CropMark,
    CustomShape,
    CutMark,
    ExternalMark,
    FoldMark,
    InkKeyBar,
    ProofSlug,
    RegisterMark,
    SlugText,
    TileStitchMark,
)


@pytest.fixture
def geom() -> PageGeometry:
    return PageGeometry.from_boxes(
        media=(0, 0, 612, 792),
        trim=(36, 36, 576, 756),
        bleed=(18, 18, 594, 774),
    )


# --- Anchor resolution ---------------------------------------------------


def test_anchor_xy_trim_corners(geom: PageGeometry) -> None:
    assert geom.anchor_xy("trim_top_left") == (36, 756)
    assert geom.anchor_xy("trim_top_right") == (576, 756)
    assert geom.anchor_xy("trim_bottom_left") == (36, 36)
    assert geom.anchor_xy("trim_bottom_right") == (576, 36)


def test_anchor_xy_trim_edges_midpoints(geom: PageGeometry) -> None:
    assert geom.anchor_xy("trim_top") == (306, 756)
    assert geom.anchor_xy("trim_bottom") == (306, 36)
    assert geom.anchor_xy("trim_left") == (36, 396)
    assert geom.anchor_xy("trim_right") == (576, 396)
    assert geom.anchor_xy("trim_center") == (306, 396)


def test_anchor_xy_slug_strips(geom: PageGeometry) -> None:
    # slug_top sits between bleed.y1=774 and media.y1=792 → midpoint 783.
    assert geom.anchor_xy("slug_top") == (306, 783)
    assert geom.anchor_xy("slug_bottom") == (306, 9)


def test_slug_anchor_requires_slug_strip() -> None:
    g = PageGeometry.from_boxes(media=(0, 0, 100, 100))  # no slug
    with pytest.raises(MarkRenderError):
        g.anchor_xy("slug_top")


def test_broadcast_expansion(geom: PageGeometry) -> None:
    assert geom.expand("trim_corners") == [
        "trim_top_left",
        "trim_top_right",
        "trim_bottom_left",
        "trim_bottom_right",
    ]
    assert geom.expand("bleed_corners") == [
        "bleed_top_left",
        "bleed_top_right",
        "bleed_bottom_left",
        "bleed_bottom_right",
    ]
    assert geom.expand("trim_edges") == [
        "trim_top",
        "trim_bottom",
        "trim_left",
        "trim_right",
    ]
    assert geom.expand("trim_top_left") == ["trim_top_left"]


# --- Per-renderer behavior ----------------------------------------------


def test_register_broadcast_emits_four(geom: PageGeometry) -> None:
    out = render_register(RegisterMark(type="register", anchor="trim_corners"), geom)
    assert len(out) == 4
    for r in out:
        assert b" m " in r.stream and b" l S" in r.stream  # contains line ops


def test_register_single_anchor_emits_one(geom: PageGeometry) -> None:
    out = render_register(RegisterMark(type="register", anchor="trim_top_left"), geom)
    assert len(out) == 1


def test_crop_emits_two_perpendicular_ticks_per_corner(geom: PageGeometry) -> None:
    out = render_crop(CropMark(type="crop", anchor="trim_top_left"), geom)
    assert len(out) == 1
    # Body has two `m...l S` line operators.
    assert out[0].stream.count(b" l S") == 2


def test_bleed_uses_bleed_box(geom: PageGeometry) -> None:
    out = render_bleed(BleedMark(type="bleed", anchor="bleed_top_left"), geom)
    assert len(out) == 1
    # 18, 774 = bleed.x0, bleed.y1 — should appear in formatted form.
    assert b"18.0000" in out[0].stream and b"774.0000" in out[0].stream


def test_color_bar_horizontal_emits_one_rect_per_ink(geom: PageGeometry) -> None:
    inks = ["C", "M", "Y", "K"]
    out = render_color_bar(
        ColorBar(type="color_bar", anchor="slug_top", inks=inks, label=False), geom
    )
    assert len(out) == 1
    assert out[0].stream.count(b" re S") == len(inks)


def test_color_bar_label_pulls_in_font(geom: PageGeometry) -> None:
    out = render_color_bar(
        ColorBar(type="color_bar", anchor="slug_top", inks=["C"], label=True), geom
    )
    assert out[0].needs_font is True
    assert b"BT" in out[0].stream


def test_color_bar_vertical_orientation(geom: PageGeometry) -> None:
    out = render_color_bar(
        ColorBar(type="color_bar", anchor="slug_left", inks=["C", "M"], label=False), geom
    )
    assert out[0].stream.count(b" re S") == 2


def test_fold_dashed_line(geom: PageGeometry) -> None:
    out = render_fold(FoldMark(type="fold", edge="top", position_pt=100.0), geom)
    assert len(out) == 1
    assert b" d\n" in out[0].stream  # dash operator present


def test_center_mark_broadcast_emits_four(geom: PageGeometry) -> None:
    out = render_center(CenterMark(type="center", anchor="trim_edges"), geom)
    assert len(out) == 4


def test_slug_text_needs_font(geom: PageGeometry) -> None:
    out = render_slug_text(
        SlugText(type="slug_text", anchor="slug_bottom", text="Hello (operator)"), geom
    )
    assert out[0].needs_font is True
    assert b"Hello \\(operator\\)" in out[0].stream  # parens escaped


def test_proof_slug_single_rect(geom: PageGeometry) -> None:
    out = render_proof_slug(ProofSlug(type="proof_slug", inset_pt=2.0), geom)
    assert len(out) == 1
    assert out[0].stream.count(b" re S") == 1


def test_cut_diagonal_along_bisector(geom: PageGeometry) -> None:
    out = render_cut(CutMark(type="cut", anchor="trim_top_left"), geom)
    assert len(out) == 1
    assert b" l S" in out[0].stream


def test_ink_key_bar_zone_count(geom: PageGeometry) -> None:
    out = render_ink_key_bar(InkKeyBar(type="ink_key_bar", anchor="slug_top", zones=8), geom)
    assert len(out) == 1
    assert out[0].stream.count(b" re S") == 8


def test_tile_stitch_pitched_ticks(geom: PageGeometry) -> None:
    out = render_tile_stitch(TileStitchMark(type="tile_stitch", edge="top", pitch_pt=72.0), geom)
    assert len(out) == 1
    # Trim is 540 pt wide, pitch 72 → 7 internal ticks (at 108, 180, 252, 324, 396, 468, 540).
    # 540 not strictly less than x1=576, so it is included; first tick at x=108.
    assert out[0].stream.count(b" l S") == 7


def test_custom_open_polyline(geom: PageGeometry) -> None:
    out = render_custom(
        CustomShape(
            type="custom",
            anchor="trim_center",
            points=[(0, 0), (10, 10), (20, 0)],
            closed=False,
        ),
        geom,
    )
    assert b"\nS\n" in out[0].stream  # open: ends with S, no h


def test_custom_closed_polygon(geom: PageGeometry) -> None:
    out = render_custom(
        CustomShape(
            type="custom",
            anchor="trim_center",
            points=[(0, 0), (10, 10), (20, 0)],
            closed=True,
        ),
        geom,
    )
    assert b"h S\n" in out[0].stream


def test_external_pdf_returns_metadata_only(geom: PageGeometry) -> None:
    out = render_external(ExternalMark(type="external", file="x.pdf", anchor="trim_center"), geom)
    assert len(out) == 1
    assert out[0].external_pdf is not None
    assert out[0].external_image is None
    assert out[0].stream == b""


def test_external_png_returns_metadata_only(geom: PageGeometry) -> None:
    out = render_external(
        ExternalMark(type="external", file="logo.png", anchor="trim_center"), geom
    )
    assert out[0].external_image is not None
    assert out[0].external_pdf is None


def test_external_svg_rejected(geom: PageGeometry) -> None:
    with pytest.raises(MarkRenderError, match="SVG"):
        render_external(ExternalMark(type="external", file="x.svg", anchor="trim_center"), geom)


def test_external_unknown_extension_rejected(geom: PageGeometry) -> None:
    with pytest.raises(MarkRenderError, match="unsupported"):
        render_external(ExternalMark(type="external", file="x.tiff", anchor="trim_center"), geom)


# --- Top-level dispatch -------------------------------------------------


def test_top_level_render_dispatches_correctly(geom: PageGeometry) -> None:
    register = RegisterMark(type="register", anchor="trim_top_left")
    out = render(register, geom)
    assert len(out) == 1


def test_renderers_are_pure(geom: PageGeometry) -> None:
    """Re-rendering the same mark twice yields byte-identical output."""
    mark = ColorBar(type="color_bar", anchor="slug_top", inks=["C", "M", "Y", "K"])
    a = render_color_bar(mark, geom)
    b = render_color_bar(mark, geom)
    assert a[0].stream == b[0].stream
