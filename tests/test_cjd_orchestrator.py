"""CJD orchestrator — multi-producer execution + lineage emission."""

from __future__ import annotations

import base64

import pytest
from compile_pdf_core.lineage.store import MemoryLineageStore

from compile_pdf.cjd.orchestrator import CjdOrderError, execute
from compile_pdf.cjd.schema import CjdJob


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _job(input_bytes: bytes, **overrides) -> CjdJob:
    payload = {
        "input_pdf_b64": _b64(input_bytes),
        "steps": [
            {"type": "rewrite", "plan": {"ops": []}},
            {"type": "marks", "template": {"marks": []}},
        ],
    }
    payload.update(overrides)
    return CjdJob.model_validate(payload)


def test_executes_in_canonical_order(printer_pdf: bytes) -> None:
    job = _job(
        printer_pdf,
        steps=[
            # intentionally out of order
            {
                "type": "marks",
                "template": {"marks": [{"type": "register", "anchor": "trim_corners"}]},
            },
            {
                "type": "rewrite",
                "plan": {"ops": [{"op": "metadata_set", "key": "Title", "value": "x"}]},
            },
        ],
    )
    store = MemoryLineageStore()
    result = execute(job, store=store)
    producers = [s.producer for s in result.steps]
    assert producers == ["rewrite", "marks"]


def test_strict_order_rejects_out_of_order(printer_pdf: bytes) -> None:
    job = _job(
        printer_pdf,
        strict_order=True,
        steps=[
            {"type": "marks", "template": {"marks": []}},
            {"type": "rewrite", "plan": {"ops": []}},
        ],
    )
    with pytest.raises(CjdOrderError):
        execute(job, store=MemoryLineageStore())


def test_strict_order_accepts_canonical_order(printer_pdf: bytes) -> None:
    job = _job(
        printer_pdf,
        strict_order=True,
        steps=[
            {"type": "rewrite", "plan": {"ops": []}},
            {"type": "marks", "template": {"marks": []}},
        ],
    )
    result = execute(job, store=MemoryLineageStore())
    assert [s.producer for s in result.steps] == ["rewrite", "marks"]


def test_lineage_records_persist_to_store(printer_pdf: bytes) -> None:
    job = _job(printer_pdf)
    store = MemoryLineageStore()
    result = execute(job, store=store)
    chain = store.get(result.lineage_id)
    assert len(chain.steps) == len(result.steps)
    assert [s.producer for s in chain.steps] == ["rewrite", "marks"]


def test_chain_threads_input_output_hashes(printer_pdf: bytes) -> None:
    """Each step's input_sha256 must equal the previous step's output_sha256."""
    job = _job(
        printer_pdf,
        steps=[
            {"type": "rewrite", "plan": {"ops": []}},
            {"type": "marks", "template": {"marks": []}},
            {"type": "trap", "policy": {}},
        ],
    )
    result = execute(job, store=MemoryLineageStore())
    for prev, nxt in zip(result.steps[:-1], result.steps[1:], strict=True):
        assert prev.output_sha256 == nxt.input_sha256


def test_trap_diff_auto_emitted_when_trap_step_present(simple_pdf: bytes) -> None:
    job = CjdJob.model_validate(
        {
            "input_pdf_b64": _b64(simple_pdf),
            "steps": [
                {
                    "type": "trap",
                    "policy": {
                        "trap_zones": [
                            {
                                "page_index": 0,
                                "rect_pt": [50, 50, 100, 100],
                                "from_ink": "Y",
                                "to_ink": "K",
                            }
                        ]
                    },
                }
            ],
        }
    )
    result = execute(job, store=MemoryLineageStore())
    assert result.trap_diff is not None
    assert result.trap_diff["operations"][0]["from_ink"] == "Y"
    # The corresponding lineage record also carries the diff.
    assert result.steps[-1].trap_diff is not None


def test_trap_diff_absent_when_no_trap_step(printer_pdf: bytes) -> None:
    job = _job(printer_pdf)
    result = execute(job, store=MemoryLineageStore())
    assert result.trap_diff is None


def test_lineage_id_is_deterministic(printer_pdf: bytes) -> None:
    job_a = _job(printer_pdf)
    job_b = _job(printer_pdf)
    a = execute(job_a, store=MemoryLineageStore())
    b = execute(job_b, store=MemoryLineageStore())
    assert a.lineage_id == b.lineage_id


def test_explicit_job_id_honored(printer_pdf: bytes) -> None:
    job = _job(printer_pdf, job_id="acme-12345")
    result = execute(job, store=MemoryLineageStore())
    assert result.lineage_id == "acme-12345"


def test_full_four_producer_chain_round_trips(simple_pdf: bytes) -> None:
    """Rewrite → marks → impose → trap end-to-end."""
    job = CjdJob.model_validate(
        {
            "input_pdf_b64": _b64(simple_pdf),
            "steps": [
                {
                    "type": "rewrite",
                    "plan": {"ops": [{"op": "metadata_set", "key": "Title", "value": "PWS Job"}]},
                },
                {
                    "type": "marks",
                    "template": {"marks": [{"type": "proof_slug"}]},
                },
                {
                    "type": "impose",
                    "plan": {
                        "sheet": {"width_pt": 612, "height_pt": 792},
                        "cell": {"width_pt": 612, "height_pt": 792},
                    },
                },
                {
                    "type": "trap",
                    "policy": {
                        "trap_zones": [
                            {
                                "page_index": 0,
                                "rect_pt": [10, 10, 100, 100],
                                "from_ink": "C",
                                "to_ink": "M",
                            }
                        ]
                    },
                },
            ],
        }
    )
    result = execute(job, store=MemoryLineageStore())
    assert [s.producer for s in result.steps] == ["rewrite", "marks", "impose", "trap"]
    assert result.trap_diff is not None
