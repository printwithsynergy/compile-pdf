"""Marks determinism — re-running the engine produces byte-identical output."""

from __future__ import annotations

from compile_pdf_marks.engine import apply_template
from compile_pdf_marks.template_schema import (
    BleedMark,
    CenterMark,
    ColorBar,
    CropMark,
    CustomShape,
    CutMark,
    FoldMark,
    InkKeyBar,
    MarksTemplate,
    ProofSlug,
    RegisterMark,
    SlugText,
    TileStitchMark,
)


def _full_template() -> MarksTemplate:
    """All 12 v1.0 mark types in one template — exercises every renderer."""
    return MarksTemplate(
        marks=[
            RegisterMark(type="register", anchor="trim_corners"),
            CropMark(type="crop", anchor="trim_corners"),
            BleedMark(type="bleed", anchor="bleed_corners"),
            ColorBar(
                type="color_bar",
                anchor="slug_top",
                inks=["C", "M", "Y", "K", "PMS 185"],
            ),
            FoldMark(type="fold", edge="top", position_pt=120.0),
            CenterMark(type="center", anchor="trim_edges"),
            SlugText(type="slug_text", anchor="slug_bottom", text="Job 12345"),
            ProofSlug(type="proof_slug"),
            CutMark(type="cut", anchor="trim_corners"),
            InkKeyBar(type="ink_key_bar", anchor="slug_top", zones=8),
            TileStitchMark(type="tile_stitch", edge="top", pitch_pt=72.0),
            CustomShape(
                type="custom",
                anchor="trim_center",
                points=[(-20, -20), (20, -20), (20, 20), (-20, 20)],
            ),
        ]
    )


def test_determinism_full_template(printer_pdf: bytes) -> None:
    template = _full_template()
    a = apply_template(printer_pdf, template)
    b = apply_template(printer_pdf, template)
    assert a.output_bytes == b.output_bytes
    assert a.pdf_sha256 == b.pdf_sha256


def test_determinism_across_multi_page(two_page_printer_pdf: bytes) -> None:
    template = _full_template()
    a = apply_template(two_page_printer_pdf, template)
    b = apply_template(two_page_printer_pdf, template)
    assert a.output_bytes == b.output_bytes


def test_determinism_for_single_register_corner(printer_pdf: bytes) -> None:
    template = MarksTemplate(marks=[RegisterMark(type="register", anchor="trim_top_left")])
    runs = [apply_template(printer_pdf, template).pdf_sha256 for _ in range(3)]
    assert len(set(runs)) == 1
