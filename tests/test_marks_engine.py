"""Marks engine — end-to-end stamping behavior and resource wiring."""

from __future__ import annotations

import io

import pikepdf
import pytest
from pikepdf import Name

from compile_pdf.marks.engine import MarksTemplateError, apply_template
from compile_pdf.marks.template_schema import (
    BleedMark,
    ColorBar,
    CropMark,
    MarksTemplate,
    ProofSlug,
    RegisterMark,
    SlugText,
)


def test_empty_template_is_noop(printer_pdf: bytes) -> None:
    result = apply_template(printer_pdf, MarksTemplate())
    assert result.marks_applied == 0
    # Bytes will differ (pikepdf rewrites the xref) but page count is preserved.
    out_pdf = pikepdf.open(io.BytesIO(result.output_bytes))
    try:
        assert len(out_pdf.pages) == 1
    finally:
        out_pdf.close()


def test_register_marks_appended_as_overlay_stream(printer_pdf: bytes) -> None:
    template = MarksTemplate(marks=[RegisterMark(type="register", anchor="trim_corners")])
    result = apply_template(printer_pdf, template)
    out_pdf = pikepdf.open(io.BytesIO(result.output_bytes))
    try:
        page = out_pdf.pages[0]
        contents = page.obj.get(Name.Contents)
        assert isinstance(contents, pikepdf.Array)
        assert len(contents) == 2  # original + overlay
    finally:
        out_pdf.close()


def test_text_marks_inject_helvetica_font(printer_pdf: bytes) -> None:
    template = MarksTemplate(
        marks=[SlugText(type="slug_text", anchor="slug_bottom", text="Job 12345")]
    )
    result = apply_template(printer_pdf, template)
    out_pdf = pikepdf.open(io.BytesIO(result.output_bytes))
    try:
        page = out_pdf.pages[0]
        fonts = page.obj[Name.Resources][Name.Font]
        assert Name("/F1") in fonts
        assert fonts[Name("/F1")][Name.BaseFont] == Name("/Helvetica")
    finally:
        out_pdf.close()


def test_engine_preserves_page_boxes(printer_pdf: bytes) -> None:
    """L3 invariant: MediaBox/TrimBox/BleedBox unchanged on every page."""
    template = MarksTemplate(
        marks=[
            RegisterMark(type="register", anchor="trim_corners"),
            CropMark(type="crop", anchor="trim_corners"),
            BleedMark(type="bleed", anchor="bleed_corners"),
        ]
    )
    in_pdf = pikepdf.open(io.BytesIO(printer_pdf))
    in_boxes = {
        k: list(in_pdf.pages[0].obj[Name(f"/{k}")]) for k in ("MediaBox", "TrimBox", "BleedBox")
    }
    in_pdf.close()
    result = apply_template(printer_pdf, template)
    out_pdf = pikepdf.open(io.BytesIO(result.output_bytes))
    try:
        out_boxes = {
            k: list(out_pdf.pages[0].obj[Name(f"/{k}")])
            for k in ("MediaBox", "TrimBox", "BleedBox")
        }
    finally:
        out_pdf.close()
    assert in_boxes == out_boxes


def test_engine_applies_marks_to_every_page(two_page_printer_pdf: bytes) -> None:
    template = MarksTemplate(marks=[ProofSlug(type="proof_slug")])
    result = apply_template(two_page_printer_pdf, template)
    assert result.marks_applied == 2  # one mark per page
    out_pdf = pikepdf.open(io.BytesIO(result.output_bytes))
    try:
        for page in out_pdf.pages:
            contents = page.obj.get(Name.Contents)
            assert isinstance(contents, pikepdf.Array)
            assert len(contents) == 2
    finally:
        out_pdf.close()


def test_engine_is_deterministic(printer_pdf: bytes) -> None:
    template = MarksTemplate(
        marks=[
            RegisterMark(type="register", anchor="trim_corners"),
            ColorBar(type="color_bar", anchor="slug_top", inks=["C", "M", "Y", "K"]),
        ]
    )
    a = apply_template(printer_pdf, template)
    b = apply_template(printer_pdf, template)
    assert a.output_bytes == b.output_bytes
    assert a.pdf_sha256 == b.pdf_sha256


def test_external_file_missing_raises(printer_pdf: bytes, tmp_path) -> None:
    from compile_pdf.marks.template_schema import ExternalMark

    template = MarksTemplate(
        marks=[ExternalMark(type="external", file="does-not-exist.pdf", anchor="trim_center")]
    )
    with pytest.raises(MarksTemplateError, match="not found"):
        apply_template(printer_pdf, template, external_root=tmp_path)


def test_engine_count_includes_broadcast_expansion(printer_pdf: bytes) -> None:
    """trim_corners → 4 stamps, but template only declares one mark."""
    template = MarksTemplate(marks=[RegisterMark(type="register", anchor="trim_corners")])
    result = apply_template(printer_pdf, template)
    assert result.marks_applied == 4
