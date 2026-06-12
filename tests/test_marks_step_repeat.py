"""Step-and-repeat (SNR) cut marks — render geometry + stagger behaviour."""

from __future__ import annotations

import pytest
from compile_pdf_marks.library import PageGeometry, render, render_step_repeat
from compile_pdf_marks.template_schema import (
    MarksTemplate,
    StepRepeatMark,
    marks_template_json_schema,
)

TRIM = (36.0, 36.0, 576.0, 756.0)  # 540 x 720


@pytest.fixture
def geom() -> PageGeometry:
    return PageGeometry.from_boxes(
        media=(0, 0, 612, 792),
        trim=TRIM,
        bleed=(18, 18, 594, 774),
    )


def _tick_count(stream: bytes) -> int:
    """Number of stroked tick lines (each `_line` ends with ``S\\n``)."""
    return stream.count(b"S\n")


def _coord(n: float) -> bytes:
    """Format a coordinate the way the renderer does (fixed 4 decimals)."""
    return f"{n:.4f}".encode("ascii")


def test_grid_2x2_ticks_all_sides(geom: PageGeometry) -> None:
    out = render_step_repeat(StepRepeatMark(type="step_repeat", rows=2, cols=2), geom)
    assert len(out) == 1
    # 3 vertical cut edges (×top+bottom) + 3 horizontal cut edges (×left+right).
    assert _tick_count(out[0].stream) == 12


def test_single_cell_is_outer_edges(geom: PageGeometry) -> None:
    out = render_step_repeat(StepRepeatMark(type="step_repeat", rows=1, cols=1), geom)
    # 2 x-edges ×2 sides + 2 y-edges ×2 sides.
    assert _tick_count(out[0].stream) == 8


def test_gutter_adds_cut_edges(geom: PageGeometry) -> None:
    flush = render_step_repeat(StepRepeatMark(type="step_repeat", cols=2, rows=1), geom)[0]
    gutter = render_step_repeat(
        StepRepeatMark(type="step_repeat", cols=2, rows=1, gutter_pt=20.0), geom
    )[0]
    assert _tick_count(gutter.stream) > _tick_count(flush.stream)


def test_brick_shifts_top_and_anchors_bottom(geom: PageGeometry) -> None:
    base = render_step_repeat(StepRepeatMark(type="step_repeat", rows=2, cols=2), geom)[0]
    brick = render_step_repeat(
        StepRepeatMark(type="step_repeat", rows=2, cols=2, stagger="brick"), geom
    )[0]
    assert brick.stream != base.stream
    cw = (TRIM[2] - TRIM[0]) / 2
    # Top row (index 1, odd) shifts right by cw/2 → left x-edge moves; absent in base.
    assert _coord(TRIM[0] + cw / 2) in brick.stream
    assert _coord(TRIM[0] + cw / 2) not in base.stream
    # Bottom row (index 0) is never shifted — the unshifted x-edge stays present.
    assert _coord(TRIM[0]) in brick.stream


def test_half_drop_shifts_right_and_anchors_left(geom: PageGeometry) -> None:
    base = render_step_repeat(StepRepeatMark(type="step_repeat", rows=2, cols=2), geom)[0]
    drop = render_step_repeat(
        StepRepeatMark(type="step_repeat", rows=2, cols=2, stagger="half_drop"), geom
    )[0]
    assert drop.stream != base.stream
    ch = (TRIM[3] - TRIM[1]) / 2
    # Last column (index 1, odd) drops by ch/2 → bottom y-edge moves; absent in base.
    assert _coord(TRIM[1] + ch / 2) in drop.stream
    assert _coord(TRIM[1] + ch / 2) not in base.stream
    # First column (index 0) is never dropped — the unshifted y-edge stays present.
    assert _coord(TRIM[1]) in drop.stream


def test_brick_noop_when_top_row_even(geom: PageGeometry) -> None:
    # rows=3 → top row index 2 (even) → brick stagger is a no-op.
    base = render_step_repeat(StepRepeatMark(type="step_repeat", rows=3, cols=2), geom)[0]
    brick = render_step_repeat(
        StepRepeatMark(type="step_repeat", rows=3, cols=2, stagger="brick"), geom
    )[0]
    assert brick.stream == base.stream


def test_half_drop_noop_when_last_col_even(geom: PageGeometry) -> None:
    # cols=3 → last column index 2 (even) → half_drop stagger is a no-op.
    base = render_step_repeat(StepRepeatMark(type="step_repeat", rows=2, cols=3), geom)[0]
    drop = render_step_repeat(
        StepRepeatMark(type="step_repeat", rows=2, cols=3, stagger="half_drop"), geom
    )[0]
    assert drop.stream == base.stream


def test_dispatch_via_render(geom: PageGeometry) -> None:
    mark = StepRepeatMark(type="step_repeat", rows=2, cols=2)
    assert render(mark, geom) == render_step_repeat(mark, geom)


def test_schema_accepts_step_repeat() -> None:
    template = MarksTemplate(
        marks=[StepRepeatMark(type="step_repeat", rows=4, cols=3, stagger="brick")]
    )
    assert template.marks[0].type == "step_repeat"


def test_json_schema_exposes_step_repeat_variant() -> None:
    schema = marks_template_json_schema()
    defs = schema.get("$defs", {})
    assert "StepRepeatMark" in defs
    type_schema = defs["StepRepeatMark"]["properties"]["type"]
    # Pydantic v2 emits a single Literal as `const` (older versions: 1-item enum).
    assert type_schema.get("const") == "step_repeat" or type_schema.get("enum") == ["step_repeat"]
