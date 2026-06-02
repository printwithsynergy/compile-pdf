"""Pydantic schemas for the white / underbase producer.

These types are the wire shape for ``POST /v1/white-underbase/apply``.
They're imported by both :mod:`compile_pdf.white_underbase.api`
(the FastAPI router) and :mod:`compile_pdf.white_underbase.engine`
so the request envelope and the engine entrypoint stay coupled at
the type level.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# White-plate generation strategies. Kept as a string union so
# the wire format reads naturally; the engine maps these onto
# the underlying pikepdf operations once the tracer lands.
GenerationStrategy = Literal[
    "auto",
    "union",
    "knockout",
    "manual",
]
"""How to derive the white plate from the existing ink coverage.

- ``auto`` (default) — lay down white wherever any ink coverage
  exceeds ``knockout_threshold_pct``. Most common for label /
  garment / foil work.
- ``union`` — lay down white wherever any ink prints, regardless
  of coverage. Maximises opacity on dark substrates.
- ``knockout`` — invert the auto behaviour: lay down white where
  the artwork is *absent*. Used for "spot varnish over content"
  workflows.
- ``manual`` — engine adds the named separation entry but does not
  trace content; caller is responsible for supplying the white
  geometry via a follow-up trap/marks pass.
"""

PlateUse = Literal["white", "underbase", "varnish", "foil"]
"""Semantic role for the generated plate.

Surfaced as DeviceN colorant metadata so downstream RIPs / proofing
tools know whether to treat the plate as opaque white ink, a screen
underbase, a UV varnish overlay, or a foil-stamp mask. Affects the
``type`` field on the registered separation, not the geometry.
"""


class WhiteUnderbasePolicy(BaseModel):
    """Generation policy controlling the white-plate output.

    All knobs are optional with sensible defaults; the most common
    real-world request is ``{"separation_name": "White"}`` with
    everything else inherited.
    """

    model_config = ConfigDict(extra="forbid")

    separation_name: str = Field(
        default="White",
        min_length=1,
        max_length=64,
        description=(
            "Name of the new DeviceN separation to add to the "
            "output PDF. Conventionally 'White' for white ink, "
            "'Underbase' for screen printing, 'Varnish' for spot "
            "UV, or 'Foil' for foil-stamp masks."
        ),
    )
    plate_use: PlateUse = Field(
        default="white",
        description=(
            "Semantic role of the plate. Affects DeviceN colorant "
            "metadata so downstream RIPs treat the plate correctly."
        ),
    )
    strategy: GenerationStrategy = Field(
        default="auto",
        description=(
            "How to derive the plate from existing ink coverage. "
            "See :data:`GenerationStrategy` for the strategy "
            "catalogue."
        ),
    )
    knockout_threshold_pct: float = Field(
        default=5.0,
        ge=0.0,
        le=100.0,
        description=(
            "Minimum cumulative CMYK ink coverage (%, 0-100) to "
            "trigger white plate deposition under 'auto' / "
            "'knockout' strategies. 5% is the practical floor for "
            "most flexo / offset workflows; lower values risk "
            "noise from rasterized anti-aliasing edges."
        ),
    )
    choke_pt: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description=(
            "Shrink (negative) or grow (positive) the generated "
            "white plate by this many points relative to the source "
            "geometry. Used to compensate for press misregistration; "
            "0pt is the default (exact match). Typical print-shop "
            "values are -0.3pt for white-under-colour, +0.5pt for "
            "underbase-with-bleed."
        ),
    )
    page_indices: list[int] | None = Field(
        default=None,
        description=(
            "Restrict generation to these 0-indexed pages. None "
            "means every page in the input PDF gets a white plate. "
            "Useful when a multi-page job has only some pages "
            "printing on dark substrate."
        ),
    )

    def page_indices_or_all(self, total_pages: int) -> list[int]:
        """Helper for the engine: return the explicit page list or
        the default all-pages list."""
        if self.page_indices is None:
            return list(range(total_pages))
        return list(self.page_indices)


class WhiteUnderbaseApplyRequest(BaseModel):
    """Request envelope.

    Mirrors the trap / soft-proof / impose request shape: input PDF
    inline as base64, policy as a typed Pydantic object.
    """

    model_config = ConfigDict(extra="forbid")

    input_pdf_b64: str = Field(min_length=1)
    policy: WhiteUnderbasePolicy = Field(default_factory=WhiteUnderbasePolicy)


class WhiteUnderbaseSummary(BaseModel):
    """Engine-side telemetry surfaced on the response so callers
    can show 'how much white did this generate?' in the editor UI."""

    model_config = ConfigDict(extra="forbid")

    pages_processed: int = Field(
        ge=0,
        description="Number of pages a white plate was added to.",
    )
    separation_name: str = Field(
        description="Name the separation was registered under in the output PDF.",
    )
    plate_use: PlateUse = Field(
        description="Semantic role recorded on the separation.",
    )
    strategy_applied: GenerationStrategy = Field(
        description="Strategy actually applied (matches the request).",
    )


class WhiteUnderbaseApplyResponse(BaseModel):
    """Response envelope.

    Mirrors the soft-proof / trap response shape so operator
    tooling can treat every producer the same way.
    """

    model_config = ConfigDict(extra="forbid")

    output_pdf_b64: str
    pdf_sha256: str
    input_sha256: str
    policy_sha256: str
    cache_key: str
    cache_hit: bool = False
    summary: WhiteUnderbaseSummary
    schema_version: str
    compile_version: str
