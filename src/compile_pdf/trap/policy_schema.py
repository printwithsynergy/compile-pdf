"""Trap policy schema — ink-pair spread/choke rules + declared trap zones.

A policy declares:

* ``ink_pair_rules`` — for each ordered ink pair, how wide the trap is
  and whether the ``from`` ink spreads into the ``to`` ink, chokes
  away from it, or follows automatic neutral-density-driven defaults.
* ``trap_zones`` — concrete rectangles on specific pages that trigger
  trapping, naming which ink pair to apply. v1 supports axis-aligned
  rectangles only; non-rectangular trap zones need ``codex-pdf[geom]``
  (pyclipr) and land in Phase 4.x once the dep is wired into CI.

The schema is intentionally explicit: real ink-pair-adjacency
extraction from the PDF (the production pipeline) is Phase 4.x.
v1 ships the codex consumption surface end-to-end (``polygon_offset``,
``resolve_spot_swatch_color``, ``delta_e_2000``) plus the trap-diff
artifact, with declared zones standing in for extracted boundaries.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, NonNegativeInt, PositiveFloat, RootModel


class _Strict(BaseModel):
    model_config = {"extra": "forbid", "frozen": True}


TrapDirection = Literal["spread", "choke", "auto"]


class InkPairRule(_Strict):
    """Per-ordered-ink-pair trap rule.

    ``direction='auto'`` defers to neutral-density defaults: the ink
    with lower neutral density spreads into the one with higher (i.e.
    the lighter spreads into the darker). When operator override is
    explicit, ``direction`` is honored regardless of densities.
    """

    from_ink: str = Field(min_length=1, description="Source ink name (PMS / process).")
    to_ink: str = Field(min_length=1, description="Adjacent ink name across the boundary.")
    width_pt: PositiveFloat = Field(description="Trap width in PDF points.")
    direction: TrapDirection = Field(default="auto")


class TrapZone(_Strict):
    """One axis-aligned rectangular trap target on a specific page.

    The zone's ink-pair labels (``from_ink``, ``to_ink``) must match an
    entry in ``policy.ink_pair_rules`` or fall back to the default
    width via ``policy.default_trap_width_pt``.
    """

    page_index: NonNegativeInt
    rect_pt: tuple[float, float, float, float] = Field(
        description="(llx, lly, urx, ury) in points; must satisfy llx<urx, lly<ury.",
    )
    from_ink: str = Field(min_length=1)
    to_ink: str = Field(min_length=1)


NeutralDensitySource = Literal["codex_extract", "operator"]
EngineSelector = Literal["auto", "pure_python", "ghostscript", "external"]


class TrapPolicy(BaseModel):
    """Top-level trap-policy document — schema-versioned envelope."""

    model_config = {"extra": "forbid"}

    schema_version: Literal["1.0.0"] = Field(
        default="1.0.0",
        description="Bumps when the policy-document schema changes (per producer; spec §6.2).",
    )
    default_trap_width_pt: PositiveFloat = Field(default=0.144)
    ink_pair_rules: list[InkPairRule] = Field(default_factory=list)
    trap_zones: list[TrapZone] = Field(default_factory=list)
    delta_e_tolerance: PositiveFloat = Field(
        default=5.0,
        description=(
            "Max acceptable CIEDE2000 delta_e between the trapping ink and "
            "either ink pair partner. Operations exceeding tolerance fail "
            "verify Layer 6 but still emit a diff record."
        ),
    )
    neutral_density_source: NeutralDensitySource = Field(default="codex_extract")
    engine: EngineSelector = Field(
        default="auto",
        description=(
            "auto → COMPILE_TRAP_ENGINE env var → pure_python. "
            "Override only when the operator wants a specific engine "
            "fingerprint locked into the lineage record."
        ),
    )


class TrapPolicyRoot(RootModel[TrapPolicy]):
    """Root model — emit JSON Schema directly without a wrapping object."""


def trap_policy_json_schema() -> dict[str, object]:
    """Return the JSON Schema for a trap-policy document.

    Surfaced via ``compile-pdf trap-schema`` and (once api/main mounts
    the schema endpoint) ``GET /v1/schema/trap``.
    """
    return TrapPolicy.model_json_schema()


__all__ = [
    "EngineSelector",
    "InkPairRule",
    "NeutralDensitySource",
    "TrapDirection",
    "TrapPolicy",
    "TrapPolicyRoot",
    "TrapZone",
    "trap_policy_json_schema",
]
