"""CJD orchestrator — sequence the four producers in dependency order.

The orchestrator validates step ordering, runs each producer in turn,
threads ``lineage_id`` + cache keys into the lineage store, and
auto-emits the trap-diff artifact when a trap step is present (spec
§5.7).

Cache keys are computed via :func:`compile_pdf.cache.compute_cache_key`
exactly as the standalone producer endpoints do, so a CJD job that
re-runs the same input + same producer plan hits the same cache key
that a direct ``POST /v1/<producer>/apply`` would.
"""

from __future__ import annotations

import base64
import hashlib
import io
from dataclasses import dataclass

from compile_pdf.cache import compute_cache_key, hash_canonical_plan
from compile_pdf.cjd.schema import (
    PRODUCER_ORDER,
    CjdImposeStep,
    CjdJob,
    CjdMarksStep,
    CjdRewriteStep,
    CjdStep,
    CjdTrapStep,
)
from compile_pdf.impose.engine import apply_plan as apply_impose
from compile_pdf.lineage.store import LineageStep, LineageStore, default_store
from compile_pdf.marks.engine import apply_template as apply_marks
from compile_pdf.rewrite.engine import apply_plan as apply_rewrite
from compile_pdf.trap.engine import apply_policy as apply_trap
from compile_pdf.version import CODEX_DOCUMENT_SCHEMA_VERSION_PIN


@dataclass(frozen=True)
class CjdResult:
    """Outcome of a CJD orchestration run."""

    output_pdf_bytes: bytes
    output_pdf_sha256: str
    lineage_id: str
    steps: tuple[LineageStep, ...]
    trap_diff: dict[str, object] | None


class CjdOrderError(ValueError):
    """Steps were not in canonical producer order and ``strict_order=True``.

    Raised before any producer runs.
    """


def execute(
    job: CjdJob,
    *,
    store: LineageStore | None = None,
) -> CjdResult:
    """Run a CJD job end-to-end and return the final PDF + chain.

    ``store`` defaults to the process-wide :func:`default_store` so a
    subsequent ``GET /v1/lineage/{id}`` in the same process surfaces
    the chain.
    """
    store = store or default_store()
    ordered_steps = _validate_ordering(job.steps, strict=job.strict_order)
    lineage_id = job.job_id or _derive_lineage_id(job)

    current_bytes = base64.b64decode(job.input_pdf_b64, validate=True)
    chain: list[LineageStep] = []
    trap_diff: dict[str, object] | None = None
    codex_versions = _resolve_codex_versions()

    for step_index, step in enumerate(ordered_steps):
        before_sha = hashlib.sha256(current_bytes).hexdigest()
        producer_name, plan_dict, output_bytes, output_sha, extras, step_trap_diff = _run_step(
            step, current_bytes
        )
        plan_sha = hash_canonical_plan(plan_dict)
        cache_key = compute_cache_key(
            producer=producer_name,
            input_sha256=before_sha,
            canonical_plan_sha256=plan_sha,
            **codex_versions,
        )
        record = LineageStep(
            lineage_id=lineage_id,
            step_index=step_index,
            producer=producer_name,
            input_sha256=before_sha,
            output_sha256=output_sha,
            cache_key=cache_key,
            plan_sha256=plan_sha,
            extras=extras,
            trap_diff=step_trap_diff,
        )
        store.put(record)
        chain.append(record)
        current_bytes = output_bytes
        if step_trap_diff is not None:
            trap_diff = step_trap_diff

    return CjdResult(
        output_pdf_bytes=current_bytes,
        output_pdf_sha256=hashlib.sha256(current_bytes).hexdigest(),
        lineage_id=lineage_id,
        steps=tuple(chain),
        trap_diff=trap_diff,
    )


# --- Step ordering ------------------------------------------------------


def _validate_ordering(steps: list[CjdStep], *, strict: bool) -> list[CjdStep]:
    """Reorder to canonical producer order; reject under strict mode."""
    type_index = {name: i for i, name in enumerate(PRODUCER_ORDER)}
    if strict:
        seen_indices = [type_index[s.type] for s in steps]
        if seen_indices != sorted(seen_indices):
            raise CjdOrderError(
                f"strict_order=True but steps were not in canonical order: "
                f"{[s.type for s in steps]} "
                f"(expected subset of {list(PRODUCER_ORDER)})"
            )
        return steps
    return sorted(steps, key=lambda s: type_index[s.type])


# --- Per-step dispatch --------------------------------------------------


def _run_step(
    step: CjdStep,
    input_bytes: bytes,
) -> tuple[
    str,
    dict[str, object],
    bytes,
    str,
    dict[str, object],
    dict[str, object] | None,
]:
    """Dispatch one step. Returns
    ``(producer, plan_dict, output_bytes, output_sha, extras, trap_diff)``.
    """
    if isinstance(step, CjdRewriteStep):
        rw = apply_rewrite(input_bytes, step.plan)
        return (
            "rewrite",
            step.plan.model_dump(mode="json"),
            rw.output_bytes,
            rw.pdf_sha256,
            {"ops_applied": rw.ops_applied},
            None,
        )
    if isinstance(step, CjdMarksStep):
        mk = apply_marks(input_bytes, step.template)
        return (
            "marks",
            step.template.model_dump(mode="json"),
            mk.output_bytes,
            mk.pdf_sha256,
            {"marks_applied": mk.marks_applied},
            None,
        )
    if isinstance(step, CjdImposeStep):
        im = apply_impose(input_bytes, step.plan)
        return (
            "impose",
            step.plan.model_dump(mode="json"),
            im.output_bytes,
            im.pdf_sha256,
            {
                "sheets_written": im.sheets_written,
                "cells_per_sheet": im.cells_per_sheet,
                "input_pages": im.input_pages,
            },
            None,
        )
    if isinstance(step, CjdTrapStep):
        tr = apply_trap(input_bytes, step.policy)
        return (
            "trap",
            step.policy.model_dump(mode="json"),
            tr.output_bytes,
            tr.pdf_sha256,
            {
                "engine": tr.engine,
                "engine_fingerprint": tr.engine_fingerprint,
                "operations_count": len(tr.operations),
            },
            tr.trap_diff,
        )
    raise CjdOrderError(  # pragma: no cover — discriminated union prevents this
        f"unknown CJD step type {type(step).__name__!r}"
    )


# --- Helpers ------------------------------------------------------------


def _derive_lineage_id(job: CjdJob) -> str:
    """Synthesize a deterministic lineage_id from the input + steps.

    Same ``input_pdf_b64`` + same step list → same lineage_id. Two
    distinct calls with identical bodies will overwrite each other in
    the store; that's the intended cache-friendly behavior.
    """
    h = hashlib.sha256()
    h.update(job.input_pdf_b64.encode("ascii"))
    for step in job.steps:
        h.update(step.model_dump_json().encode("utf-8"))
    return f"cjd-{h.hexdigest()[:24]}"


def _resolve_codex_versions() -> dict[str, str]:
    try:
        from codex_pdf import __version__ as codex_version
        from codex_pdf.color import COLOR_SCHEMA_VERSION
        from codex_pdf.geom import GEOM_SCHEMA_VERSION
    except ImportError:  # pragma: no cover — codex-pdf is a hard dep
        return {
            "codex_pdf_package_version": "unknown",
            "color_schema_version": "unknown",
            "geom_schema_version": "unknown",
            "codex_document_schema_version": CODEX_DOCUMENT_SCHEMA_VERSION_PIN,
        }
    return {
        "codex_pdf_package_version": str(codex_version),
        "color_schema_version": COLOR_SCHEMA_VERSION,
        "geom_schema_version": GEOM_SCHEMA_VERSION,
        "codex_document_schema_version": CODEX_DOCUMENT_SCHEMA_VERSION_PIN,
    }


# Mirror imposes _ used to surface the underlying io.BytesIO module
# in case Phase 5.x wires streaming variants. Keep the import so the
# typing stays explicit.
_ = io


__all__ = [
    "CjdOrderError",
    "CjdResult",
    "execute",
]
