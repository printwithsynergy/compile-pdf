"""LineageStep.retained_for_training survives round-trips through the store."""

from __future__ import annotations

from compile_pdf_core.lineage.store import (
    LineageStep,
    MemoryLineageStore,
    serialize_chain,
)


def _step(*, retained: bool) -> LineageStep:
    return LineageStep(
        lineage_id="job-1",
        step_index=0,
        producer="rewrite",
        input_sha256="a" * 64,
        output_sha256="b" * 64,
        cache_key="c" * 64,
        plan_sha256="d" * 64,
        retained_for_training=retained,
    )


def test_default_retained_for_training_is_false() -> None:
    step = LineageStep(
        lineage_id="job-x",
        step_index=0,
        producer="rewrite",
        input_sha256="a" * 64,
        output_sha256="b" * 64,
        cache_key="c" * 64,
        plan_sha256="d" * 64,
    )
    assert step.retained_for_training is False


def test_memory_store_preserves_retained_flag() -> None:
    store = MemoryLineageStore()
    store.put(_step(retained=True))
    chain = store.get("job-1")
    assert chain.steps[0].retained_for_training is True


def test_serialize_chain_emits_retained_flag() -> None:
    store = MemoryLineageStore()
    store.put(_step(retained=True))
    payload = serialize_chain(store.get("job-1"))
    assert payload["steps"][0]["retained_for_training"] is True
