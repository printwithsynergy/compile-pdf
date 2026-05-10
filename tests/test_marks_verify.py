"""Marks verifier — four-layer post-condition checks."""

from __future__ import annotations

import io

import pikepdf
from pikepdf import Array, Name, String

from compile_pdf.marks.engine import apply_template
from compile_pdf.marks.template_schema import (
    MarksTemplate,
    ProofSlug,
    RegisterMark,
    SlugText,
)
from compile_pdf.marks.verify import verify_marks


def test_verify_passes_on_clean_apply(printer_pdf: bytes) -> None:
    template = MarksTemplate(marks=[RegisterMark(type="register", anchor="trim_corners")])
    result = apply_template(printer_pdf, template)
    v = verify_marks(
        input_bytes=printer_pdf,
        output_bytes=result.output_bytes,
        template=template,
    )
    assert v.passed, v.failures
    assert v.layer1_schema and v.layer2_determinism and v.layer3_unchanged and v.layer4_marks_layer


def test_verify_passes_on_empty_template(printer_pdf: bytes) -> None:
    template = MarksTemplate()
    result = apply_template(printer_pdf, template)
    v = verify_marks(input_bytes=printer_pdf, output_bytes=result.output_bytes, template=template)
    assert v.layer1_schema  # trivial pass for empty
    assert v.layer4_marks_layer  # trivial pass for empty


def test_verify_layer1_fails_when_overlay_missing(printer_pdf: bytes) -> None:
    """If we hand verify the original input as the 'output' it has no overlay."""
    template = MarksTemplate(marks=[RegisterMark(type="register", anchor="trim_corners")])
    v = verify_marks(
        input_bytes=printer_pdf,
        output_bytes=printer_pdf,  # no overlay
        template=template,
    )
    assert not v.layer1_schema
    assert any("L1" in f for f in v.failures)


def test_verify_layer3_detects_box_change(printer_pdf: bytes) -> None:
    """Mutate the output's TrimBox post-engine — L3 should catch it."""
    template = MarksTemplate(marks=[RegisterMark(type="register", anchor="trim_top_left")])
    result = apply_template(printer_pdf, template)
    pdf = pikepdf.open(io.BytesIO(result.output_bytes))
    pdf.pages[0].obj[Name.TrimBox] = Array([0, 0, 100, 100])
    out = io.BytesIO()
    pdf.save(out, deterministic_id=True, linearize=False)
    pdf.close()
    tampered = out.getvalue()

    v = verify_marks(
        input_bytes=printer_pdf,
        output_bytes=tampered,
        template=template,
    )
    assert not v.layer3_unchanged
    assert any("TrimBox" in f for f in v.failures)


def test_verify_layer3_detects_metadata_change(printer_pdf: bytes) -> None:
    template = MarksTemplate(marks=[ProofSlug(type="proof_slug")])
    result = apply_template(printer_pdf, template)
    pdf = pikepdf.open(io.BytesIO(result.output_bytes))
    pdf.docinfo[Name.Title] = String("Tampered title")
    out = io.BytesIO()
    pdf.save(out, deterministic_id=True, linearize=False)
    pdf.close()
    tampered = out.getvalue()

    v = verify_marks(
        input_bytes=printer_pdf,
        output_bytes=tampered,
        template=template,
    )
    assert not v.layer3_unchanged
    assert any("Info" in f for f in v.failures)


def test_verify_layer2_skip_when_replay_disabled(printer_pdf: bytes) -> None:
    template = MarksTemplate(marks=[SlugText(type="slug_text", anchor="slug_top", text="hi")])
    result = apply_template(printer_pdf, template)
    v = verify_marks(
        input_bytes=printer_pdf,
        output_bytes=result.output_bytes,
        template=template,
        determinism_replay=False,
    )
    assert v.layer2_determinism  # treated as pass when replay disabled
