"""Mark renderers — produce PDF content-stream bytes for each of the 12
v1.0 mark types plus the external-file ingestion mark.

Each renderer takes a parsed ``Mark`` plus a :class:`PageGeometry` and
returns a list of :class:`RenderedMark` records. A renderer may emit
more than one record (broadcast anchors fan out at this layer).

Renderers are pure: they do not touch the ``Pdf`` object. The engine
appends the produced streams to each page and registers any extra
resources (fonts, image XObjects).

PDF coordinates are in points, origin at lower-left. All operator
sequences are wrapped in ``q ... Q`` so they don't leak graphics state
back into the host page.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from codex_pdf.geom import Box

from compile_pdf.marks.template_schema import (
    Anchor,
    BleedMark,
    CenterMark,
    ColorBar,
    CropMark,
    CustomShape,
    CutMark,
    ExternalMark,
    FoldMark,
    InkKeyBar,
    Mark,
    ProofSlug,
    RegisterMark,
    SingleAnchor,
    SlugText,
    StepRepeatMark,
    TileStitchMark,
)


class MarkRenderError(ValueError):
    """A mark references geometry that cannot be resolved against the
    current page (e.g. a slug anchor on a page with no slug area)."""


# --- Page geometry ------------------------------------------------------


@dataclass(frozen=True)
class PageGeometry:
    """Page-box snapshot used by anchor resolution.

    ``trim`` and ``bleed`` fall back to ``media`` when not declared on
    the page (matching PDF 1.7 §14.11.2 default behavior). Slug anchors
    only resolve when bleed is strictly inside media.
    """

    trim: Box
    bleed: Box
    media: Box

    @classmethod
    def from_boxes(
        cls,
        *,
        media: tuple[float, float, float, float],
        trim: tuple[float, float, float, float] | None = None,
        bleed: tuple[float, float, float, float] | None = None,
    ) -> PageGeometry:
        m = Box(*media)
        t = Box(*trim) if trim is not None else m
        b = Box(*bleed) if bleed is not None else t
        return cls(trim=t, bleed=b, media=m)

    def anchor_xy(self, anchor: SingleAnchor) -> tuple[float, float]:
        """Return the ``(x, y)`` anchor point in user-space points."""
        match anchor:
            case "trim_top_left":
                return (self.trim.x0, self.trim.y1)
            case "trim_top_right":
                return (self.trim.x1, self.trim.y1)
            case "trim_bottom_left":
                return (self.trim.x0, self.trim.y0)
            case "trim_bottom_right":
                return (self.trim.x1, self.trim.y0)
            case "trim_top":
                return ((self.trim.x0 + self.trim.x1) / 2, self.trim.y1)
            case "trim_bottom":
                return ((self.trim.x0 + self.trim.x1) / 2, self.trim.y0)
            case "trim_left":
                return (self.trim.x0, (self.trim.y0 + self.trim.y1) / 2)
            case "trim_right":
                return (self.trim.x1, (self.trim.y0 + self.trim.y1) / 2)
            case "trim_center":
                return ((self.trim.x0 + self.trim.x1) / 2, (self.trim.y0 + self.trim.y1) / 2)
            case "bleed_top_left":
                return (self.bleed.x0, self.bleed.y1)
            case "bleed_top_right":
                return (self.bleed.x1, self.bleed.y1)
            case "bleed_bottom_left":
                return (self.bleed.x0, self.bleed.y0)
            case "bleed_bottom_right":
                return (self.bleed.x1, self.bleed.y0)
            case "slug_top":
                self._require_slug("top")
                return (
                    (self.media.x0 + self.media.x1) / 2,
                    (self.bleed.y1 + self.media.y1) / 2,
                )
            case "slug_bottom":
                self._require_slug("bottom")
                return (
                    (self.media.x0 + self.media.x1) / 2,
                    (self.bleed.y0 + self.media.y0) / 2,
                )
            case "slug_left":
                self._require_slug("left")
                return (
                    (self.media.x0 + self.bleed.x0) / 2,
                    (self.media.y0 + self.media.y1) / 2,
                )
            case "slug_right":
                self._require_slug("right")
                return (
                    (self.bleed.x1 + self.media.x1) / 2,
                    (self.media.y0 + self.media.y1) / 2,
                )

    def expand(self, anchor: Anchor) -> list[SingleAnchor]:
        """Fan a broadcast anchor out into its concrete single anchors."""
        if anchor == "trim_corners":
            return ["trim_top_left", "trim_top_right", "trim_bottom_left", "trim_bottom_right"]
        if anchor == "bleed_corners":
            return ["bleed_top_left", "bleed_top_right", "bleed_bottom_left", "bleed_bottom_right"]
        if anchor == "trim_edges":
            return ["trim_top", "trim_bottom", "trim_left", "trim_right"]
        return [anchor]

    def _require_slug(self, side: str) -> None:
        if side == "top" and self.media.y1 <= self.bleed.y1:
            raise MarkRenderError("slug_top requires media.y1 > bleed.y1")
        if side == "bottom" and self.media.y0 >= self.bleed.y0:
            raise MarkRenderError("slug_bottom requires media.y0 < bleed.y0")
        if side == "left" and self.media.x0 >= self.bleed.x0:
            raise MarkRenderError("slug_left requires media.x0 < bleed.x0")
        if side == "right" and self.media.x1 <= self.bleed.x1:
            raise MarkRenderError("slug_right requires media.x1 > bleed.x1")


@dataclass(frozen=True)
class RenderedMark:
    """One rendered mark instance.

    ``stream`` is a content-stream fragment ready to append to a page.
    ``needs_font`` flags whether the page resource dictionary must
    include a Helvetica entry under ``/F1``. ``external_pdf`` /
    ``external_image`` are populated by external-file marks and consumed
    by the engine to register the necessary XObject resources.
    """

    stream: bytes
    needs_font: bool = False
    external_pdf: ExternalMark | None = None
    external_image: ExternalMark | None = None
    extent_hint: Box | None = None  # for verify Layer 3 (nothing-else)


# --- Helpers ------------------------------------------------------------

_BLACK = "0 0 0 RG\n0 0 0 rg\n"


def _line(x0: float, y0: float, x1: float, y1: float) -> str:
    return f"{_fmt(x0)} {_fmt(y0)} m {_fmt(x1)} {_fmt(y1)} l S\n"


def _rect_stroke(x: float, y: float, w: float, h: float) -> str:
    return f"{_fmt(x)} {_fmt(y)} {_fmt(w)} {_fmt(h)} re S\n"


def _fmt(n: float) -> str:
    """Deterministic numeric formatting — fixed 4 decimals, no trailing
    minus-zero. Stable across Python releases (round-half-even)."""
    s = f"{n:.4f}"
    if s == "-0.0000":
        s = "0.0000"
    return s


def _wrap(body: str, line_width_pt: float, dash: float | None = None) -> bytes:
    parts = ["q\n", _BLACK, f"{_fmt(line_width_pt)} w\n"]
    if dash is not None:
        parts.append(f"[{_fmt(dash)} {_fmt(dash)}] 0 d\n")
    parts.append(body)
    parts.append("Q\n")
    return "".join(parts).encode("ascii")


def _escape_pdf_string(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


# --- Production mark renderers -------------------------------------------


def render_register(mark: RegisterMark, geom: PageGeometry) -> list[RenderedMark]:
    """Cross-hair (+) at each requested corner, ``offset_pt`` outside trim."""
    out: list[RenderedMark] = []
    for anchor in geom.expand(mark.anchor):
        cx, cy = _offset_corner(geom.anchor_xy(anchor), anchor, mark.offset_pt)
        half = mark.line_length_pt / 2
        body = _line(cx - half, cy, cx + half, cy) + _line(cx, cy - half, cx, cy + half)
        out.append(
            RenderedMark(
                stream=_wrap(body, mark.line_width_pt),
                extent_hint=Box(cx - half, cy - half, cx + half, cy + half),
            )
        )
    return out


def render_crop(mark: CropMark, geom: PageGeometry) -> list[RenderedMark]:
    """Two short orthogonal ticks per corner — the classic crop tick."""
    return _corner_ticks(mark.anchor, mark.length_pt, mark.offset_pt, mark.line_width_pt, geom)


def render_bleed(mark: BleedMark, geom: PageGeometry) -> list[RenderedMark]:
    """Same shape as crop, against the bleed box."""
    return _corner_ticks(mark.anchor, mark.length_pt, mark.offset_pt, mark.line_width_pt, geom)


def render_color_bar(mark: ColorBar, geom: PageGeometry) -> list[RenderedMark]:
    """Outlined cells across the chosen slug edge — one cell per ink."""
    cx, cy = geom.anchor_xy(mark.anchor)
    horizontal = mark.anchor in ("slug_top", "slug_bottom")
    n = len(mark.inks)
    body_parts: list[str] = []
    needs_font = mark.label
    if horizontal:
        total_w = mark.cell_width_pt * n
        x0 = cx - total_w / 2
        y0 = cy - mark.cell_height_pt / 2
        for i, ink in enumerate(mark.inks):
            xi = x0 + i * mark.cell_width_pt
            body_parts.append(_rect_stroke(xi, y0, mark.cell_width_pt, mark.cell_height_pt))
            if mark.label:
                body_parts.append(_text(xi + 1, y0 + mark.cell_height_pt + 2, ink, 6.0))
        extent = Box(x0, y0, x0 + total_w, y0 + mark.cell_height_pt)
    else:
        total_h = mark.cell_height_pt * n
        x0 = cx - mark.cell_width_pt / 2
        y0 = cy - total_h / 2
        for i, ink in enumerate(mark.inks):
            yi = y0 + i * mark.cell_height_pt
            body_parts.append(_rect_stroke(x0, yi, mark.cell_width_pt, mark.cell_height_pt))
            if mark.label:
                body_parts.append(_text(x0 + mark.cell_width_pt + 2, yi + 1, ink, 6.0))
        extent = Box(x0, y0, x0 + mark.cell_width_pt, y0 + total_h)
    return [
        RenderedMark(
            stream=_wrap("".join(body_parts), 0.25),
            needs_font=needs_font,
            extent_hint=extent,
        )
    ]


# --- Proofing mark renderers --------------------------------------------


def render_fold(mark: FoldMark, geom: PageGeometry) -> list[RenderedMark]:
    """Dashed line at ``position_pt`` inset from the chosen edge."""
    t = geom.trim
    match mark.edge:
        case "top":
            y = t.y1 - mark.position_pt
            x_mid = (t.x0 + t.x1) / 2
            x0, x1 = x_mid - mark.length_pt / 2, x_mid + mark.length_pt / 2
            body = _line(x0, y, x1, y)
            extent = Box(x0, y, x1, y)
        case "bottom":
            y = t.y0 + mark.position_pt
            x_mid = (t.x0 + t.x1) / 2
            x0, x1 = x_mid - mark.length_pt / 2, x_mid + mark.length_pt / 2
            body = _line(x0, y, x1, y)
            extent = Box(x0, y, x1, y)
        case "left":
            x = t.x0 + mark.position_pt
            y_mid = (t.y0 + t.y1) / 2
            y0, y1 = y_mid - mark.length_pt / 2, y_mid + mark.length_pt / 2
            body = _line(x, y0, x, y1)
            extent = Box(x, y0, x, y1)
        case "right":
            x = t.x1 - mark.position_pt
            y_mid = (t.y0 + t.y1) / 2
            y0, y1 = y_mid - mark.length_pt / 2, y_mid + mark.length_pt / 2
            body = _line(x, y0, x, y1)
            extent = Box(x, y0, x, y1)
    return [
        RenderedMark(stream=_wrap(body, mark.line_width_pt, dash=mark.dash_pt), extent_hint=extent)
    ]


def render_center(mark: CenterMark, geom: PageGeometry) -> list[RenderedMark]:
    """Single tick at the midpoint of each requested trim edge."""
    out: list[RenderedMark] = []
    for anchor in geom.expand(mark.anchor):
        cx, cy = geom.anchor_xy(anchor)
        if anchor in ("trim_top", "trim_bottom"):
            outward = mark.offset_pt + mark.length_pt
            inward = mark.offset_pt
            if anchor == "trim_top":
                body = _line(cx, cy + inward, cx, cy + outward)
                ext = Box(cx, cy + inward, cx, cy + outward)
            else:
                body = _line(cx, cy - outward, cx, cy - inward)
                ext = Box(cx, cy - outward, cx, cy - inward)
        else:
            outward = mark.offset_pt + mark.length_pt
            inward = mark.offset_pt
            if anchor == "trim_left":
                body = _line(cx - outward, cy, cx - inward, cy)
                ext = Box(cx - outward, cy, cx - inward, cy)
            else:
                body = _line(cx + inward, cy, cx + outward, cy)
                ext = Box(cx + inward, cy, cx + outward, cy)
        out.append(RenderedMark(stream=_wrap(body, mark.line_width_pt), extent_hint=ext))
    return out


def render_slug_text(mark: SlugText, geom: PageGeometry) -> list[RenderedMark]:
    """Single line of Helvetica text along the chosen slug strip."""
    cx, cy = geom.anchor_xy(mark.anchor)
    body = _text(cx, cy, mark.text, mark.font_size_pt, anchor="center")
    return [
        RenderedMark(
            stream=_wrap(body, 0.25),
            needs_font=True,
            extent_hint=Box(cx, cy, cx, cy),
        )
    ]


def render_proof_slug(mark: ProofSlug, geom: PageGeometry) -> list[RenderedMark]:
    """Single rectangle outlining the trim with the configured inset."""
    t = geom.trim
    inset = mark.inset_pt
    body = _rect_stroke(t.x0 + inset, t.y0 + inset, t.width - 2 * inset, t.height - 2 * inset)
    return [
        RenderedMark(
            stream=_wrap(body, mark.line_width_pt),
            extent_hint=Box(t.x0 + inset, t.y0 + inset, t.x1 - inset, t.y1 - inset),
        )
    ]


# --- Universal mark renderers --------------------------------------------


def render_cut(mark: CutMark, geom: PageGeometry) -> list[RenderedMark]:
    """Single straight tick along the corner bisector."""
    out: list[RenderedMark] = []
    for anchor in geom.expand(mark.anchor):
        cx, cy = geom.anchor_xy(anchor)
        # Bisector unit vector points away from the page center.
        sign_x = -1.0 if "left" in anchor else 1.0
        sign_y = 1.0 if "top" in anchor else -1.0
        ux, uy = sign_x / math.sqrt(2), sign_y / math.sqrt(2)
        x0 = cx + ux * mark.offset_pt
        y0 = cy + uy * mark.offset_pt
        x1 = cx + ux * (mark.offset_pt + mark.length_pt)
        y1 = cy + uy * (mark.offset_pt + mark.length_pt)
        body = _line(x0, y0, x1, y1)
        out.append(
            RenderedMark(
                stream=_wrap(body, mark.line_width_pt),
                extent_hint=Box(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)),
            )
        )
    return out


def render_ink_key_bar(mark: InkKeyBar, geom: PageGeometry) -> list[RenderedMark]:
    """Outlined-cell step wedge across the chosen slug edge."""
    cx, cy = geom.anchor_xy(mark.anchor)
    n = mark.zones
    total_w = mark.cell_width_pt * n
    x0 = cx - total_w / 2
    y0 = cy - mark.cell_height_pt / 2
    body_parts: list[str] = []
    for i in range(n):
        xi = x0 + i * mark.cell_width_pt
        body_parts.append(_rect_stroke(xi, y0, mark.cell_width_pt, mark.cell_height_pt))
    return [
        RenderedMark(
            stream=_wrap("".join(body_parts), 0.25),
            extent_hint=Box(x0, y0, x0 + total_w, y0 + mark.cell_height_pt),
        )
    ]


def render_tile_stitch(mark: TileStitchMark, geom: PageGeometry) -> list[RenderedMark]:
    """Repeated short ticks along the chosen edge at ``pitch_pt`` spacing."""
    t = geom.trim
    body_parts: list[str] = []
    if mark.edge in ("top", "bottom"):
        y = t.y1 if mark.edge == "top" else t.y0
        outward = mark.length_pt if mark.edge == "top" else -mark.length_pt
        x = t.x0 + mark.pitch_pt
        while x < t.x1:
            body_parts.append(_line(x, y, x, y + outward))
            x += mark.pitch_pt
        extent = Box(
            t.x0, y if outward > 0 else y + outward, t.x1, y if outward < 0 else y + outward
        )
    else:
        x = t.x0 if mark.edge == "left" else t.x1
        outward = -mark.length_pt if mark.edge == "left" else mark.length_pt
        y = t.y0 + mark.pitch_pt
        while y < t.y1:
            body_parts.append(_line(x, y, x + outward, y))
            y += mark.pitch_pt
        extent = Box(
            x if outward > 0 else x + outward, t.y0, x if outward < 0 else x + outward, t.y1
        )
    return [RenderedMark(stream=_wrap("".join(body_parts), mark.line_width_pt), extent_hint=extent)]


def render_step_repeat(mark: StepRepeatMark, geom: PageGeometry) -> list[RenderedMark]:
    """Cut ticks at every cell boundary of a step-and-repeat grid on the trim,
    on all four sides, following the configured stagger.

    Cells tile the trim box (``cols`` x ``rows``, separated by ``gutter_pt``);
    ticks land at each cell's left/right edge (vertical cuts, ticked above the
    top and below the bottom trim) and top/bottom edge (horizontal cuts, ticked
    left and right). Coincident edges collapse when ``gutter_pt == 0``.

    Stagger shifts the edge that rides the staggered cells: ``brick`` offsets
    the top-edge ticks by half a cell when the top row is shifted; ``half_drop``
    offsets the right-edge ticks by half a cell when the last column is dropped.
    The bottom edge (row 0) and left edge (column 0) are never shifted, so they
    stay registered to the untranslated origin.
    """
    t = geom.trim
    cols, rows = mark.cols, mark.rows
    g = mark.gutter_pt
    cw = (t.width - (cols - 1) * g) / cols
    ch = (t.height - (rows - 1) * g) / rows

    # Cut-edge coordinates: every cell's two edges; coincident edges dedup.
    xs = sorted(
        {t.x0 + i * (cw + g) for i in range(cols)} | {t.x0 + i * (cw + g) + cw for i in range(cols)}
    )
    ys = sorted(
        {t.y0 + j * (ch + g) for j in range(rows)} | {t.y0 + j * (ch + g) + ch for j in range(rows)}
    )

    off, ln, w = mark.offset_pt, mark.tick_length_pt, mark.line_width_pt
    dx_top = cw / 2 if mark.stagger == "brick" and (rows - 1) % 2 == 1 else 0.0
    dx_bottom = 0.0  # bottom row (index 0) is never shifted in a brick layout
    dy_right = ch / 2 if mark.stagger == "half_drop" and (cols - 1) % 2 == 1 else 0.0
    dy_left = 0.0  # first column (index 0) is never dropped in a half-drop layout

    body_parts: list[str] = []
    for x in xs:
        body_parts.append(_line(x + dx_top, t.y1 + off, x + dx_top, t.y1 + off + ln))
        body_parts.append(_line(x + dx_bottom, t.y0 - off, x + dx_bottom, t.y0 - off - ln))
    for y in ys:
        body_parts.append(_line(t.x0 - off, y + dy_left, t.x0 - off - ln, y + dy_left))
        body_parts.append(_line(t.x1 + off, y + dy_right, t.x1 + off + ln, y + dy_right))

    extent = Box(t.x0 - off - ln, t.y0 - off - ln, t.x1 + off + ln, t.y1 + off + ln)
    return [RenderedMark(stream=_wrap("".join(body_parts), w), extent_hint=extent)]


def render_custom(mark: CustomShape, geom: PageGeometry) -> list[RenderedMark]:
    """Polyline / polygon at the chosen anchor."""
    ax, ay = geom.anchor_xy(mark.anchor)
    pts = mark.points
    body = f"{_fmt(ax + pts[0][0])} {_fmt(ay + pts[0][1])} m\n"
    xs = [ax + p[0] for p in pts]
    ys = [ay + p[1] for p in pts]
    for px, py in pts[1:]:
        body += f"{_fmt(ax + px)} {_fmt(ay + py)} l\n"
    body += "h S\n" if mark.closed else "S\n"
    return [
        RenderedMark(
            stream=_wrap(body, mark.line_width_pt),
            extent_hint=Box(min(xs), min(ys), max(xs), max(ys)),
        )
    ]


def render_external(mark: ExternalMark, geom: PageGeometry) -> list[RenderedMark]:
    """Schedule an external-file stamp. Engine handles XObject creation;
    this renderer only emits the placement-side metadata."""
    suffix = mark.file.lower().rsplit(".", 1)[-1]
    if suffix == "pdf":
        return [RenderedMark(stream=b"", external_pdf=mark)]
    if suffix in ("png",):
        return [RenderedMark(stream=b"", external_image=mark)]
    if suffix in ("svg",):
        raise MarkRenderError(
            f"external SVG not supported in v1 ({mark.file!r}); convert to PDF or PNG first"
        )
    raise MarkRenderError(f"unsupported external file extension: {mark.file!r}")


# --- Dispatch -----------------------------------------------------------


def render(mark: Mark, geom: PageGeometry) -> list[RenderedMark]:
    """Top-level dispatch — render any mark against a page geometry."""
    if isinstance(mark, RegisterMark):
        return render_register(mark, geom)
    if isinstance(mark, CropMark):
        return render_crop(mark, geom)
    if isinstance(mark, BleedMark):
        return render_bleed(mark, geom)
    if isinstance(mark, ColorBar):
        return render_color_bar(mark, geom)
    if isinstance(mark, FoldMark):
        return render_fold(mark, geom)
    if isinstance(mark, CenterMark):
        return render_center(mark, geom)
    if isinstance(mark, SlugText):
        return render_slug_text(mark, geom)
    if isinstance(mark, ProofSlug):
        return render_proof_slug(mark, geom)
    if isinstance(mark, CutMark):
        return render_cut(mark, geom)
    if isinstance(mark, InkKeyBar):
        return render_ink_key_bar(mark, geom)
    if isinstance(mark, TileStitchMark):
        return render_tile_stitch(mark, geom)
    if isinstance(mark, StepRepeatMark):
        return render_step_repeat(mark, geom)
    if isinstance(mark, CustomShape):
        return render_custom(mark, geom)
    if isinstance(mark, ExternalMark):
        return render_external(mark, geom)
    raise MarkRenderError(  # pragma: no cover — discriminated union prevents this
        f"no renderer for mark type {type(mark).__name__!r}"
    )


# --- Internal helpers ---------------------------------------------------


def _corner_ticks(
    anchor: Anchor,
    length: float,
    offset: float,
    width: float,
    geom: PageGeometry,
) -> list[RenderedMark]:
    out: list[RenderedMark] = []
    for a in geom.expand(anchor):
        cx, cy = geom.anchor_xy(a)
        sign_x = -1.0 if "left" in a else 1.0
        sign_y = 1.0 if "top" in a else -1.0
        # Two ticks: one horizontal away from the corner, one vertical.
        x_h0 = cx + sign_x * offset
        x_h1 = cx + sign_x * (offset + length)
        y_v0 = cy + sign_y * offset
        y_v1 = cy + sign_y * (offset + length)
        body = _line(x_h0, cy, x_h1, cy) + _line(cx, y_v0, cx, y_v1)
        out.append(
            RenderedMark(
                stream=_wrap(body, width),
                extent_hint=Box(min(cx, x_h1), min(cy, y_v1), max(cx, x_h1), max(cy, y_v1)),
            )
        )
    return out


def _offset_corner(
    xy: tuple[float, float], anchor: SingleAnchor, offset: float
) -> tuple[float, float]:
    """Push (x, y) outward from trim along the corner bisector by ``offset``."""
    sign_x = -1.0 if "left" in anchor else 1.0
    sign_y = 1.0 if "top" in anchor else -1.0
    ux, uy = sign_x / math.sqrt(2), sign_y / math.sqrt(2)
    return (xy[0] + ux * offset, xy[1] + uy * offset)


def _text(
    x: float,
    y: float,
    text: str,
    size: float,
    *,
    anchor: str = "left",
) -> str:
    """Emit a ``BT ... ET`` block. ``anchor='center'`` shifts the origin
    by the text width estimate (Helvetica avg-width approximation)."""
    if anchor == "center":
        # Helvetica avg-width ≈ 0.5 * font size per glyph (rough but stable).
        approx_width = 0.5 * size * len(text)
        x = x - approx_width / 2
        y = y - size / 3
    escaped = _escape_pdf_string(text)
    return f"BT\n/F1 {_fmt(size)} Tf\n{_fmt(x)} {_fmt(y)} Td\n({escaped}) Tj\nET\n"


__all__ = [
    "MarkRenderError",
    "PageGeometry",
    "RenderedMark",
    "render",
    "render_bleed",
    "render_center",
    "render_color_bar",
    "render_crop",
    "render_custom",
    "render_cut",
    "render_external",
    "render_fold",
    "render_ink_key_bar",
    "render_proof_slug",
    "render_register",
    "render_slug_text",
    "render_step_repeat",
    "render_tile_stitch",
]
