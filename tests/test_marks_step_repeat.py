"""Step-and-repeat (SNR) cut marks — render geometry + stagger behaviour."""

from __future__ import annotations

import pytest

from compile_pdf.marks.library import PageGeometry, render, render_step_repeat
from compile_pdf.marks.template_schema import (
    MarksTemplate,
    StepRepeatMark,
    marks_template_json_schema,
)


@pytest.fixture
def geom() -> PageGeometry:
    # trim 540 x 720 (from 36,36 to 576,756).
    return PageGeometry.from_boxes(
        media=(0, 0, 612, 792),
        trim=(36, 36, 576, 756),
        bleed=(18, 18, 594, 774),
    )


def _tick_count(stream: bytes) -> int:
    """Number of stroked tick lines (each `_line` ends with ``S\\n``)."""
    return stream.count(b"S\n")


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


def test_brick_shifts_top_edge(geom: PageGeometry) -> None:
    base = render_step_repeat(StepRepeatMark(type="step_repeat", rows=2, cols=2), geom)[0]
    brick = render_step_repeat(
        StepRepeatMark(type="step_repeat", rows=2, cols=2, stagger="brick"), geom
    )[0]
    assert brick.stream != base.stream
    # Top row (index 1) shifts right by cw/2 = 135 → x edge 36 → 171.
    assert b"171.0000" in brick.stream
    assert b"171.0000" not in base.stream


def test_half_drop_shifts_right_edge(geom: PageGeometry) -> None:
    base = render_step_repeat(StepRepeatMark(type="step_repeat", rows=2, cols=2), geom)[0]
    drop = render_step_repeat(
        StepRepeatMark(type="step_repeat", rows=2, cols=2, stagger="half_drop"), geom
    )[0]
    assert drop.stream != base.stream
    # Last column (index 1) dropped by ch/2 = 180 → right-edge y 36 → 216.
    assert b"216.0000" in drop.stream


def test_dispatch_via_render(geom: PageGeometry) -> None:
    mark = StepRepeatMark(type="step_repeat", rows=2, cols=2)
    assert render(mark, geom) == render_step_repeat(mark, geom)


def test_schema_accepts_step_repeat() -> None:
    template = MarksTemplate(
        marks=[StepRepeatMark(type="step_repeat", rows=4, cols=3, stagger="brick")]
    )
    assert template.marks[0].type == "step_repeat"


def test_json_schema_includes_step_repeat() -> None:
    assert "StepRepeatMark" in str(marks_template_json_schema())
