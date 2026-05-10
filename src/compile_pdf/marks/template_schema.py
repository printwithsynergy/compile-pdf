"""Marks template schema — 12 v1.0 mark types plus external-file ingestion,
expressed as a discriminated union over the ``type`` field.

Two ingestion modes (docs/marks.md):

* **Programmatic** — JSON-declared marks; each entry is one of the 12
  spec §3.1 mark types with anchor + per-type geometry.
* **External** — a tenant-uploaded PDF/PNG file stamped at a named
  anchor. Files are treated opaquely (no recoloring, no compositing).

Anchors resolve against page boxes at engine time. ``trim_corners``,
``bleed_corners``, ``trim_edges`` are *broadcast* anchors that expand
to four (corners) or four (edges) renderings respectively; concrete
anchors render exactly once. The schema does not pre-expand — that is
the engine's job.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, NonNegativeFloat, PositiveFloat, PositiveInt, RootModel

# --- Anchors -------------------------------------------------------------

#: Concrete single-shot anchors (one render per anchor).
SingleAnchor = Literal[
    "trim_top_left",
    "trim_top_right",
    "trim_bottom_left",
    "trim_bottom_right",
    "trim_top",
    "trim_bottom",
    "trim_left",
    "trim_right",
    "trim_center",
    "bleed_top_left",
    "bleed_top_right",
    "bleed_bottom_left",
    "bleed_bottom_right",
    "slug_top",
    "slug_bottom",
    "slug_left",
    "slug_right",
]

#: Broadcast anchors that fan out to multiple positions at engine time.
BroadcastAnchor = Literal["trim_corners", "bleed_corners", "trim_edges"]

Anchor = SingleAnchor | BroadcastAnchor


class _MarkBase(BaseModel):
    """Common envelope. Each subclass declares ``type`` as a ``Literal``
    so Pydantic builds the discriminated union without manual tags."""

    model_config = {"extra": "forbid", "frozen": True}


# --- Production marks ----------------------------------------------------


class RegisterMark(_MarkBase):
    """Cross-hair register mark — corner alignment target for plate
    registration. Renders a ``+`` centered ``offset_pt`` outside the
    chosen trim corner."""

    type: Literal["register"]
    anchor: Literal[
        "trim_top_left",
        "trim_top_right",
        "trim_bottom_left",
        "trim_bottom_right",
        "trim_corners",
    ]
    offset_pt: NonNegativeFloat = Field(default=6.0)
    line_length_pt: PositiveFloat = Field(default=6.0)
    line_width_pt: PositiveFloat = Field(default=0.25)


class CropMark(_MarkBase):
    """Trim-box corner indicator. Renders two short orthogonal ticks
    starting ``offset_pt`` outside the trim corner."""

    type: Literal["crop"]
    anchor: Literal[
        "trim_top_left",
        "trim_top_right",
        "trim_bottom_left",
        "trim_bottom_right",
        "trim_corners",
    ]
    length_pt: PositiveFloat = Field(default=9.0)
    offset_pt: NonNegativeFloat = Field(default=3.0)
    line_width_pt: PositiveFloat = Field(default=0.25)


class BleedMark(_MarkBase):
    """Bleed-extent corner indicator. Same shape as crop but anchored
    against the bleed box."""

    type: Literal["bleed"]
    anchor: Literal[
        "bleed_top_left",
        "bleed_top_right",
        "bleed_bottom_left",
        "bleed_bottom_right",
        "bleed_corners",
    ]
    length_pt: PositiveFloat = Field(default=9.0)
    offset_pt: NonNegativeFloat = Field(default=3.0)
    line_width_pt: PositiveFloat = Field(default=0.25)


class ColorBar(_MarkBase):
    """Process + spot-ink ladder. Each entry in ``inks`` becomes one
    cell in the bar; cells render in declaration order along the slug
    edge. Ink names are opaque labels stamped above each cell."""

    type: Literal["color_bar"]
    anchor: Literal["slug_top", "slug_bottom", "slug_left", "slug_right"]
    inks: list[str] = Field(min_length=1)
    cell_width_pt: PositiveFloat = Field(default=18.0)
    cell_height_pt: PositiveFloat = Field(default=12.0)
    label: bool = Field(default=True)


# --- Proofing marks ------------------------------------------------------


class FoldMark(_MarkBase):
    """Score / fold position indicator. Dashed line across the trim at
    ``position_pt`` measured from the chosen edge."""

    type: Literal["fold"]
    edge: Literal["top", "bottom", "left", "right"]
    position_pt: NonNegativeFloat = Field(
        description="Offset from the chosen edge into the trim, in points.",
    )
    length_pt: PositiveFloat = Field(default=12.0)
    line_width_pt: PositiveFloat = Field(default=0.25)
    dash_pt: PositiveFloat = Field(default=2.0)


class CenterMark(_MarkBase):
    """Centerline tickmark — short line at the midpoint of one or more
    trim edges. Used by sectional binding shops."""

    type: Literal["center"]
    anchor: Literal["trim_top", "trim_bottom", "trim_left", "trim_right", "trim_edges"]
    length_pt: PositiveFloat = Field(default=9.0)
    line_width_pt: PositiveFloat = Field(default=0.25)
    offset_pt: NonNegativeFloat = Field(default=3.0)


class SlugText(_MarkBase):
    """Operator metadata strip — single line of text along the slug.
    Font is the standard PDF Helvetica face (no embedding)."""

    type: Literal["slug_text"]
    anchor: Literal["slug_top", "slug_bottom"]
    text: str = Field(min_length=1)
    font_size_pt: PositiveFloat = Field(default=8.0)
    offset_pt: NonNegativeFloat = Field(default=3.0)


class ProofSlug(_MarkBase):
    """Single-cell proofing border — rectangle outlining the trim with
    a configurable inset. One per page."""

    type: Literal["proof_slug"]
    inset_pt: NonNegativeFloat = Field(default=0.0)
    line_width_pt: PositiveFloat = Field(default=0.5)


# --- Universal marks -----------------------------------------------------


class CutMark(_MarkBase):
    """Shop-floor cut indicator — a single straight tick anchored at the
    chosen corner, rendered ``offset_pt`` outside the trim and aimed
    along the corner bisector."""

    type: Literal["cut"]
    anchor: Literal[
        "trim_top_left",
        "trim_top_right",
        "trim_bottom_left",
        "trim_bottom_right",
        "trim_corners",
    ]
    length_pt: PositiveFloat = Field(default=9.0)
    offset_pt: NonNegativeFloat = Field(default=3.0)
    line_width_pt: PositiveFloat = Field(default=0.25)


class InkKeyBar(_MarkBase):
    """Densitometric step wedge — ``zones`` evenly-spaced cells along
    the chosen slug edge. Each cell renders an outlined rectangle (no
    fill — that is the operator's responsibility once they assign
    densities)."""

    type: Literal["ink_key_bar"]
    anchor: Literal["slug_top", "slug_bottom"]
    zones: PositiveInt = Field(default=10)
    cell_width_pt: PositiveFloat = Field(default=18.0)
    cell_height_pt: PositiveFloat = Field(default=10.0)


class TileStitchMark(_MarkBase):
    """Large-format stitching guide — repeated small tickmarks along the
    chosen edge at a fixed pitch."""

    type: Literal["tile_stitch"]
    edge: Literal["top", "bottom", "left", "right"]
    pitch_pt: PositiveFloat = Field(default=72.0)
    length_pt: PositiveFloat = Field(default=6.0)
    line_width_pt: PositiveFloat = Field(default=0.25)


class CustomShape(_MarkBase):
    """Operator-defined polygon at an anchor. ``points`` are in points,
    relative to the anchor origin (anchor is treated as (0, 0)). A
    closed shape connects the last point back to the first."""

    type: Literal["custom"]
    anchor: SingleAnchor
    points: list[tuple[float, float]] = Field(min_length=2)
    line_width_pt: PositiveFloat = Field(default=0.25)
    closed: bool = Field(default=True)


# --- External-file ingestion --------------------------------------------


class ExternalMark(_MarkBase):
    """Tenant-uploaded mark template — PDF or PNG stamped at the chosen
    anchor. The file is referenced by relative path (resolved against
    the request's working directory by the engine).

    PDF files: the first page is embedded as a Form XObject. PNG files:
    the bitmap is embedded as an Image XObject and placed at native
    resolution unless ``scale`` overrides. SVG support is deferred —
    convert to PDF or PNG before submission.
    """

    type: Literal["external"]
    file: str = Field(min_length=1)
    anchor: SingleAnchor
    scale: PositiveFloat = Field(default=1.0)
    dx_pt: float = Field(default=0.0)
    dy_pt: float = Field(default=0.0)


# --- Discriminated union ------------------------------------------------

Mark = Annotated[
    RegisterMark
    | CropMark
    | BleedMark
    | ColorBar
    | FoldMark
    | CenterMark
    | SlugText
    | ProofSlug
    | CutMark
    | InkKeyBar
    | TileStitchMark
    | CustomShape
    | ExternalMark,
    Field(discriminator="type"),
]


class MarksTemplate(BaseModel):
    """Top-level marks-template document — schema-versioned, ordered list
    of marks. Marks render in declaration order; later marks paint over
    earlier marks at the same coordinates."""

    model_config = {"extra": "forbid"}

    schema_version: Literal["1.0.0"] = Field(
        default="1.0.0",
        description="Bumps when the template-document schema changes (per producer; spec §6.2).",
    )
    marks: list[Mark] = Field(default_factory=list)


class MarksTemplateRoot(RootModel[MarksTemplate]):
    """Root model — emit JSON Schema directly without a wrapping object."""


def marks_template_json_schema() -> dict[str, object]:
    """Return the JSON Schema for a marks template document.

    Surfaced via ``compile-pdf marks-schema`` and (once api/main mounts
    the schema endpoint) ``GET /v1/schema/marks``.
    """
    return MarksTemplate.model_json_schema()
