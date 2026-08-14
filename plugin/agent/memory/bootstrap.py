"""Memory bootstrap lifecycle — open store early; ingest asynchronously."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Sequence

from plugin.agent.memory.local_store import LocalMemorySystem, default_memory_root
from plugin.agent.memory.pipeline import MemoryPipeline
from plugin.agent.memory.sources import (
    MemorySourceAdapter,
    SourceObservationBatch,
    WhatsAppBridgeSourceAdapter,
)

logger = logging.getLogger(__name__)


class MemoryBootstrapState(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    IDENTITY_READY = "IDENTITY_READY"
    INTERACTION_READY = "INTERACTION_READY"
    FULLY_CAUGHT_UP = "FULLY_CAUGHT_UP"
    STALE = "STALE"


@dataclass
class MemoryBootstrapCoordinator:
    """Owns Day-0 / incremental source ingestion via cursors.

    Does not block Hermes startup. Prefer:
      open LocalMemorySystem → schedule run_incremental()
    """

    store: LocalMemorySystem
    adapters: Optional[Sequence[MemorySourceAdapter]] = None
    pipeline: Optional[MemoryPipeline] = None
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _thread: Optional[threading.Thread] = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.pipeline is None:
            self.pipeline = MemoryPipeline(self.store)
        if self.adapters is None:
            object.__setattr__(
                self, "adapters", (WhatsAppBridgeSourceAdapter(),)
            )

    @property
    def state(self) -> MemoryBootstrapState:
        raw = self.store.get_bootstrap_state()
        try:
            return MemoryBootstrapState(raw)
        except ValueError:
            return MemoryBootstrapState.NOT_STARTED

    def set_state(self, state: MemoryBootstrapState) -> None:
        self.store.set_bootstrap_state(state.value)

    def run_incremental(self, *, blocking: bool = False) -> dict[str, Any]:
        """Ingest new observations since each adapter cursor."""
        if blocking:
            return self._run_once()
        with self._lock:
            if self._thread and self._thread.is_alive():
                return {"status": "already_running", "state": self.state.value}

            def _target() -> None:
                try:
                    self._run_once()
                except Exception:
                    logger.exception("memory bootstrap failed")
                    self.set_state(MemoryBootstrapState.STALE)

            self._thread = threading.Thread(
                target=_target, name="hermes-memory-bootstrap", daemon=True
            )
            self._thread.start()
            return {"status": "scheduled", "state": self.state.value}

    def _run_once(self) -> dict[str, Any]:
        assert self.pipeline is not None
        summary: dict[str, Any] = {"adapters": {}}
        any_identity = False
        any_interaction = False
        for adapter in self.adapters:
            name = adapter.source_name
            cursor = self.store.get_source_cursor(name)
            try:
                batch: SourceObservationBatch = adapter.scan(cursor)
            except Exception as exc:
                logger.warning("memory source %s scan failed: %s", name, exc)
                summary["adapters"][name] = {"error": str(exc)}
                continue
            if not batch.observations:
                summary["adapters"][name] = {
                    "ingested": 0,
                    "cursor": batch.next_cursor,
                }
                if batch.next_cursor:
                    self.store.set_source_cursor(name, batch.next_cursor)
                continue
            result = self.pipeline.ingest_contacts(
                name,
                batch.observations,
                cursor_value=batch.next_cursor or f"{name}:done",
            )
            any_identity = (
                any_identity
                or result.entities > 0
                or result.links > 0
                or result.source_identities > 0
            )
            any_interaction = any_interaction or result.aggregates > 0
            summary["adapters"][name] = {
                "source_identities": result.source_identities,
                "entities": result.entities,
                "aggregates": result.aggregates,
                "cursor": batch.next_cursor,
            }
        if any_interaction:
            self.set_state(MemoryBootstrapState.INTERACTION_READY)
        elif any_identity:
            self.set_state(MemoryBootstrapState.IDENTITY_READY)
        elif self.state == MemoryBootstrapState.NOT_STARTED:
            self.set_state(MemoryBootstrapState.IDENTITY_READY)

        if summary["adapters"] and all(
            "error" not in v for v in summary["adapters"].values()
        ):
            if self.state == MemoryBootstrapState.INTERACTION_READY:
                self.set_state(MemoryBootstrapState.FULLY_CAUGHT_UP)
        summary["state"] = self.state.value
        return summary


def open_local_memory(
    *,
    root: Optional[str] = None,
    start_bootstrap: bool = True,
    blocking_bootstrap: bool = False,
    adapters: Optional[Sequence[MemorySourceAdapter]] = None,
) -> tuple[LocalMemorySystem, MemoryBootstrapCoordinator]:
    """Composition helper for AgentRuntime / TUI startup."""
    store = LocalMemorySystem(root=root or default_memory_root())
    if adapters is None:
        coord = MemoryBootstrapCoordinator(store=store)
    else:
        coord = MemoryBootstrapCoordinator(store=store, adapters=tuple(adapters))
    if start_bootstrap:
        coord.run_incremental(blocking=blocking_bootstrap)
    return store, coord
