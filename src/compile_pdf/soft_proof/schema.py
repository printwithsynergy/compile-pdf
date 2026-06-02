"""Pydantic schemas for the soft-proof producer.

These types are the wire shape for ``POST /v1/soft-proof/apply``;
they're imported by both :mod:`compile_pdf.soft_proof.api` (the
FastAPI router) and :mod:`compile_pdf.soft_proof.engine` so the
request envelope and the engine entrypoint stay coupled at the
type level.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# ICC v4 rendering intents. Kept as a string union so the wire
# format reads naturally; the engine maps these onto codex-pdf's
# numeric LCMS intent codes when actually performing the
# simulation.
RenderingIntent = Literal[
    "perceptual",
    "relative-colorimetric",
    "saturation",
    "absolute-colorimetric",
]


class SoftProofOptions(BaseModel):
    """Per-request options for the soft-proof simulation.

    These are the knobs an artwork-pdf editor host might want to
    expose; profile bytes themselves live on the surrounding
    request envelope so the cache key can hash them independently
    from the rest of the options object.
    """

    model_config = ConfigDict(extra="forbid")

    intent: RenderingIntent = Field(
        default="relative-colorimetric",
        description=(
            "ICC rendering intent applied during the simulation. "
            "Defaults to relative-colorimetric — the conventional "
            "choice for print soft-proofing because it preserves "
            "in-gamut colours and clips out-of-gamut ones."
        ),
    )
    black_point_compensation: bool = Field(
        default=True,
        description=(
            "Apply black-point compensation. Almost always desired "
            "for print proofing; exposed because Wave 2 PR-6's C5 "
            "overlay surfaces it as a checkbox in the soft-proof "
            "controls."
        ),
    )
    delta_e_formula: Literal["cie76", "cie94", "ciede2000"] = Field(
        default="ciede2000",
        description=(
            "Distance formula used when computing the per-pixel ΔE "
            "summary. CIEDE2000 is the modern default; CIE76 is "
            "retained for parity with legacy proofing reports."
        ),
    )


class SoftProofApplyRequest(BaseModel):
    """Request envelope.

    The two ICC profiles are passed inline as base64 so callers
    don't need to upload them ahead of time; the engine hashes
    each profile's bytes into the cache key so subsequent
    identical requests hit cache.
    """

    model_config = ConfigDict(extra="forbid")

    input_pdf_b64: str = Field(min_length=1)
    source_icc_b64: str = Field(
        min_length=1,
        description="Source ICC profile bytes, base64-encoded.",
    )
    destination_icc_b64: str = Field(
        min_length=1,
        description="Destination ICC profile bytes, base64-encoded.",
    )
    options: SoftProofOptions = Field(default_factory=SoftProofOptions)


class DeltaESummary(BaseModel):
    """Aggregate ΔE stats returned alongside the simulated PDF.

    The full per-pixel ΔE map is too heavy for the JSON envelope —
    artwork-pdf editor renders it from a separately fetched
    ImageData / PNG, not from this response. These three numbers
    are enough to drive the footer chip on the soft-proof overlay.
    """

    model_config = ConfigDict(extra="forbid")

    max: float = Field(description="Worst-case ΔE across the simulated raster.")
    avg: float = Field(description="Mean ΔE across the simulated raster.")
    p95: float = Field(
        description=(
            "95th percentile ΔE — the value below which 95% of "
            "sampled pixels sit. Useful because ``max`` is often "
            "dominated by a single out-of-gamut speck."
        )
    )


class SoftProofApplyResponse(BaseModel):
    """Response envelope.

    Field names mirror the trap / impose / marks producers so
    operator tooling can treat every producer's response the same
    way (lineage extraction, cache-key recording, etc.).
    """

    model_config = ConfigDict(extra="forbid")

    output_pdf_b64: str
    pdf_sha256: str
    input_sha256: str
    options_sha256: str
    source_icc_sha256: str
    destination_icc_sha256: str
    cache_key: str
    cache_hit: bool = False
    delta_e: DeltaESummary
    schema_version: str
    compile_version: str
