"""External-file ingestion — PDF + PNG stamp at anchor."""

from __future__ import annotations

import io
from pathlib import Path

import pikepdf
import pytest
from compile_pdf_marks.engine import MarksTemplateError, apply_template
from compile_pdf_marks.template_schema import ExternalMark, MarksTemplate
from pikepdf import Array, Dictionary, Name
from PIL import Image


def _make_external_pdf() -> bytes:
    """A 72×72 pt single-page PDF (1×1 inch stamp)."""
    pdf = pikepdf.new()
    page = pikepdf.Page(
        pdf.make_indirect(
            Dictionary(
                Type=Name.Page,
                MediaBox=Array([0, 0, 72, 72]),
                Resources=Dictionary(),
                Contents=pdf.make_stream(b"q 0 0 72 72 re S Q"),
            )
        )
    )
    pdf.pages.append(page)
    buf = io.BytesIO()
    pdf.save(buf, deterministic_id=True, linearize=False)
    pdf.close()
    return buf.getvalue()


def _make_external_png() -> bytes:
    """Tiny 8×8 RGB PNG."""
    img = Image.new("RGB", (8, 8), color=(64, 128, 192))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_external_pdf_stamps_form_xobject(printer_pdf: bytes, tmp_path: Path) -> None:
    stamp_path = tmp_path / "stamp.pdf"
    stamp_path.write_bytes(_make_external_pdf())
    template = MarksTemplate(
        marks=[ExternalMark(type="external", file="stamp.pdf", anchor="trim_center")]
    )
    result = apply_template(printer_pdf, template, external_root=tmp_path)
    out = pikepdf.open(io.BytesIO(result.output_bytes))
    try:
        # add_overlay registers an XObject in page resources.
        resources = out.pages[0].obj[Name.Resources]
        assert Name.XObject in resources
        xobjects = resources[Name.XObject]
        assert len(xobjects.keys()) >= 1
    finally:
        out.close()


def test_external_png_stamps_image_xobject(printer_pdf: bytes, tmp_path: Path) -> None:
    stamp_path = tmp_path / "logo.png"
    stamp_path.write_bytes(_make_external_png())
    template = MarksTemplate(
        marks=[ExternalMark(type="external", file="logo.png", anchor="trim_center", scale=2.0)]
    )
    result = apply_template(printer_pdf, template, external_root=tmp_path)
    out = pikepdf.open(io.BytesIO(result.output_bytes))
    try:
        xobjects = out.pages[0].obj[Name.Resources][Name.XObject]
        assert Name("/MarkExt0") in xobjects
        img = xobjects[Name("/MarkExt0")]
        assert img.get(Name.Subtype) == Name.Image
        assert int(img.get(Name.Width)) == 8
        assert int(img.get(Name.Height)) == 8
    finally:
        out.close()


def test_external_pdf_is_deterministic(printer_pdf: bytes, tmp_path: Path) -> None:
    stamp_path = tmp_path / "stamp.pdf"
    stamp_path.write_bytes(_make_external_pdf())
    template = MarksTemplate(
        marks=[ExternalMark(type="external", file="stamp.pdf", anchor="trim_center")]
    )
    a = apply_template(printer_pdf, template, external_root=tmp_path)
    b = apply_template(printer_pdf, template, external_root=tmp_path)
    assert a.output_bytes == b.output_bytes


def test_external_unreadable_pdf_rejected(printer_pdf: bytes, tmp_path: Path) -> None:
    bogus = tmp_path / "broken.pdf"
    bogus.write_bytes(b"not actually a pdf")
    template = MarksTemplate(
        marks=[ExternalMark(type="external", file="broken.pdf", anchor="trim_center")]
    )
    with pytest.raises(MarksTemplateError, match="unreadable"):
        apply_template(printer_pdf, template, external_root=tmp_path)
