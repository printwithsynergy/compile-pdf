"""Marks template schema — discriminated-union acceptance + JSON Schema export."""

from __future__ import annotations

import pytest
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
    MarksTemplate,
    ProofSlug,
    RegisterMark,
    SlugText,
    TileStitchMark,
    marks_template_json_schema,
)
from pydantic import ValidationError


def test_template_accepts_all_twelve_mark_types() -> None:
    template = MarksTemplate(
        marks=[
            RegisterMark(type="register", anchor="trim_corners"),
            CropMark(type="crop", anchor="trim_corners"),
            BleedMark(type="bleed", anchor="bleed_corners"),
            ColorBar(type="color_bar", anchor="slug_top", inks=["C", "M", "Y", "K"]),
            FoldMark(type="fold", edge="top", position_pt=100.0),
            CenterMark(type="center", anchor="trim_edges"),
            SlugText(type="slug_text", anchor="slug_bottom", text="Job 12345"),
            ProofSlug(type="proof_slug"),
            CutMark(type="cut", anchor="trim_corners"),
            InkKeyBar(type="ink_key_bar", anchor="slug_top"),
            TileStitchMark(type="tile_stitch", edge="top"),
            CustomShape(type="custom", anchor="trim_center", points=[(0, 0), (10, 10)]),
        ]
    )
    assert len(template.marks) == 12
    assert template.schema_version == "1.0.0"


def test_external_mark_accepted() -> None:
    template = MarksTemplate(
        marks=[ExternalMark(type="external", file="watermark.pdf", anchor="trim_center")]
    )
    assert template.marks[0].file == "watermark.pdf"


def test_extra_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        RegisterMark(type="register", anchor="trim_corners", bogus=True)  # type: ignore[call-arg]


def test_register_anchor_rejects_non_corner() -> None:
    with pytest.raises(ValidationError):
        RegisterMark(type="register", anchor="trim_center")  # type: ignore[arg-type]


def test_color_bar_requires_at_least_one_ink() -> None:
    with pytest.raises(ValidationError):
        ColorBar(type="color_bar", anchor="slug_top", inks=[])


def test_custom_shape_requires_at_least_two_points() -> None:
    with pytest.raises(ValidationError):
        CustomShape(type="custom", anchor="trim_center", points=[(0, 0)])


def test_fold_position_must_be_non_negative() -> None:
    with pytest.raises(ValidationError):
        FoldMark(type="fold", edge="top", position_pt=-1.0)


def test_unknown_type_rejected() -> None:
    with pytest.raises(ValidationError):
        MarksTemplate.model_validate({"marks": [{"type": "not_a_real_type"}]})


def test_template_round_trips_via_json() -> None:
    original = MarksTemplate(
        marks=[
            RegisterMark(type="register", anchor="trim_top_left", offset_pt=8.0),
            ColorBar(
                type="color_bar",
                anchor="slug_bottom",
                inks=["Process Cyan", "PMS 185"],
                cell_width_pt=20.0,
                label=False,
            ),
        ]
    )
    j = original.model_dump_json()
    restored = MarksTemplate.model_validate_json(j)
    assert restored == original


def test_json_schema_exports_discriminator() -> None:
    schema = marks_template_json_schema()
    assert "$defs" in schema
    assert "marks" in schema["properties"]
    items = schema["properties"]["marks"]["items"]
    assert "discriminator" in items
    assert items["discriminator"]["propertyName"] == "type"


def test_marks_default_to_empty_list() -> None:
    template = MarksTemplate()
    assert template.marks == []
