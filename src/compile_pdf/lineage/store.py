"""Lineage record store — abstract interface + in-memory v1 backend.

Per spec §1.6a + §4.5.2 a CJD job emits one lineage record per producer
step, keyed by ``lineage_id`` and ordered by ``step_index``. The store
is the persistence layer for those records; this module ships the
abstract interface plus a memory backend (default in v1) and stubs for
the S3 + Redis backends that land in Phase 5.x once the operational
story is finalized.

The memory backend is process-local and intentionally non-durable —
it's appropriate for development, single-instance deployments, and
the in-process test suite. Production traffic should configure
``COMPILE_LINEAGE_BACKEND=s3``.
"""

from __future__ import annotations

import threading
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class LineageStep:
    """One per-producer step record. Persistence-layer agnostic.

    ``trap_diff`` is populated only for trap steps (auto-emitted per
    spec §5.7). Other producers leave it ``None``.
    """

    lineage_id: str
    step_index: int
    producer: str
    input_sha256: str
    output_sha256: str
    cache_key: str
    plan_sha256: str
    extras: dict[str, object] = field(default_factory=dict)
    trap_diff: dict[str, object] | None = None


@dataclass(frozen=True)
class LineageChain:
    """All lineage records for a single ``lineage_id``, ordered by step."""

    lineage_id: str
    steps: tuple[LineageStep, ...]

    def step(self, index: int) -> LineageStep:
        return self.steps[index]


class LineageStore(Protocol):
    """Persistence interface for lineage records."""

    def put(self, record: LineageStep) -> None: ...
    def get(self, lineage_id: str) -> LineageChain: ...
    def list_ids(self, *, limit: int = 50) -> list[str]: ...


class LineageNotFoundError(KeyError):
    """The requested lineage_id has no records in this store."""


# --- Memory backend -----------------------------------------------------


class MemoryLineageStore:
    """In-process dict-backed store. Default for v1.

    Thread-safe (orchestrator may run multi-step jobs on a worker pool
    in Phase 5.x; the lock keeps insertions atomic per lineage_id).
    """

    def __init__(self) -> None:
        self._data: dict[str, list[LineageStep]] = {}
        self._lock = threading.Lock()

    def put(self, record: LineageStep) -> None:
        with self._lock:
            chain = self._data.setdefault(record.lineage_id, [])
            chain.append(record)
            chain.sort(key=lambda s: s.step_index)

    def get(self, lineage_id: str) -> LineageChain:
        with self._lock:
            steps = self._data.get(lineage_id)
            if steps is None:
                raise LineageNotFoundError(lineage_id)
            return LineageChain(lineage_id=lineage_id, steps=tuple(steps))

    def list_ids(self, *, limit: int = 50) -> list[str]:
        with self._lock:
            return list(self._data.keys())[:limit]

    def clear(self) -> None:
        """Test-only helper. Production stores never expose this."""
        with self._lock:
            self._data.clear()


# --- Stubs for the durable backends -------------------------------------


class _UnimplementedStore:
    """Base class for backends that need infra to be configured."""

    backend_name: str = "<override>"

    def put(self, record: LineageStep) -> None:
        raise NotImplementedError(self._error_message())

    def get(self, lineage_id: str) -> LineageChain:
        raise NotImplementedError(self._error_message())

    def list_ids(self, *, limit: int = 50) -> list[str]:
        raise NotImplementedError(self._error_message())

    def _error_message(self) -> str:
        return (
            f"{self.backend_name} lineage backend is configured but the "
            f"{self.backend_name}-side wiring has not landed yet "
            "(Phase 5.x). Use COMPILE_LINEAGE_BACKEND=memory for development."
        )


class S3LineageStore(_UnimplementedStore):
    """S3-backed lineage store. Shipping in Phase 5.x."""

    backend_name = "S3"


class RedisLineageStore(_UnimplementedStore):
    """Redis-backed lineage store. Shipping in Phase 5.x."""

    backend_name = "Redis"


# --- Backend selection --------------------------------------------------


_DEFAULT_STORE: MemoryLineageStore = MemoryLineageStore()


def default_store() -> MemoryLineageStore:
    """Process-wide singleton for the in-memory store. The API + CLI
    both read/write through this so a CJD job's lineage is visible to
    a subsequent ``GET /v1/lineage/{id}`` in the same process."""
    return _DEFAULT_STORE


def reset_default_store() -> None:
    """Test-only helper — clears the singleton between test runs."""
    _DEFAULT_STORE.clear()


def select_store(backend: str) -> LineageStore:
    """Resolve a backend name to a store instance."""
    if backend == "memory":
        return _DEFAULT_STORE
    if backend == "s3":
        return S3LineageStore()
    if backend == "redis":
        return RedisLineageStore()
    raise ValueError(f"unknown lineage backend {backend!r}; expected one of memory | s3 | redis")


def serialize_chain(chain: LineageChain) -> dict[str, object]:
    """Render a chain as a JSON-friendly dict."""
    return {
        "lineage_id": chain.lineage_id,
        "steps": [_serialize_step(step) for step in chain.steps],
    }


def _serialize_step(step: LineageStep) -> dict[str, object]:
    payload: dict[str, object] = {
        "step_index": step.step_index,
        "producer": step.producer,
        "input_sha256": step.input_sha256,
        "output_sha256": step.output_sha256,
        "cache_key": step.cache_key,
        "plan_sha256": step.plan_sha256,
    }
    if step.extras:
        payload["extras"] = dict(step.extras)
    if step.trap_diff is not None:
        payload["trap_diff"] = step.trap_diff
    return payload


def serialize_steps(steps: Iterable[LineageStep]) -> list[dict[str, object]]:
    return [_serialize_step(s) for s in steps]


__all__ = [
    "LineageChain",
    "LineageNotFoundError",
    "LineageStep",
    "LineageStore",
    "MemoryLineageStore",
    "RedisLineageStore",
    "S3LineageStore",
    "default_store",
    "reset_default_store",
    "select_store",
    "serialize_chain",
    "serialize_steps",
]
