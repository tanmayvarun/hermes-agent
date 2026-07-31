"""Shared reliability tracking for small decision-making components.

Components such as heuristic classifiers, capability selectors, and
LLM-backed tie-breakers should report each decision through this module so the
agent can measure how often a local decision agrees with the eventual
adjudicated outcome.
"""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass
import itertools
import threading
from typing import Any, Dict, Optional


@dataclass
class DecisionRecord:
    """One component decision awaiting or carrying adjudication."""

    decision_id: str
    component: str
    predicted: str
    context: Dict[str, Any]
    outcome: Optional[str] = None
    success: Optional[bool] = None
    metadata: Dict[str, Any] | None = None


@dataclass
class DecisionStats:
    """Aggregated reliability counters for one component."""

    component: str
    attempts: int = 0
    adjudicated: int = 0
    successes: int = 0
    failures: int = 0
    pending: int = 0

    @property
    def accuracy(self) -> Optional[float]:
        if self.adjudicated <= 0:
            return None
        return self.successes / float(self.adjudicated)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "component": self.component,
            "attempts": self.attempts,
            "adjudicated": self.adjudicated,
            "successes": self.successes,
            "failures": self.failures,
            "pending": self.pending,
            "accuracy": self.accuracy,
        }


class DecisionTracker:
    """Thread-safe tracker for component-level decision reliability."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counter = itertools.count(1)
        self._records: Dict[str, DecisionRecord] = {}
        self._stats: Dict[str, DecisionStats] = {}

    def reset(self) -> None:
        with self._lock:
            self._counter = itertools.count(1)
            self._records.clear()
            self._stats.clear()

    def record_attempt(
        self,
        *,
        component: str,
        predicted: str,
        context: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        with self._lock:
            decision_id = f"{component}:{next(self._counter)}"
            stats = self._stats.setdefault(component, DecisionStats(component=component))
            stats.attempts += 1
            stats.pending += 1
            self._records[decision_id] = DecisionRecord(
                decision_id=decision_id,
                component=component,
                predicted=predicted,
                context=dict(context or {}),
                metadata=dict(metadata or {}),
            )
            return decision_id

    def adjudicate(
        self,
        decision_id: str,
        *,
        outcome: str,
        success: Optional[bool] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        with self._lock:
            record = self._records.get(decision_id)
            if record is None or record.success is not None:
                return False
            record.outcome = outcome
            record.success = (record.predicted == outcome) if success is None else bool(success)
            if metadata:
                merged = dict(record.metadata or {})
                merged.update(metadata)
                record.metadata = merged
            stats = self._stats.setdefault(record.component, DecisionStats(component=record.component))
            stats.pending = max(0, stats.pending - 1)
            stats.adjudicated += 1
            if record.success:
                stats.successes += 1
            else:
                stats.failures += 1
            return True

    def get_stats(self, component: str) -> DecisionStats:
        with self._lock:
            stats = self._stats.get(component)
            return DecisionStats(**stats.__dict__) if stats is not None else DecisionStats(component=component)

    def all_stats(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return {
                name: DecisionStats(**stats.__dict__).to_dict()
                for name, stats in self._stats.items()
            }

    def get_record(self, decision_id: str) -> Optional[DecisionRecord]:
        with self._lock:
            record = self._records.get(decision_id)
            if record is None:
                return None
            return DecisionRecord(
                decision_id=record.decision_id,
                component=record.component,
                predicted=record.predicted,
                context=dict(record.context),
                outcome=record.outcome,
                success=record.success,
                metadata=dict(record.metadata or {}),
            )


decision_tracker = DecisionTracker()


class DecisionComponent(ABC):
    """Base helper for measurable decision-making subcomponents."""

    component_name: str = "decision_component"

    def record_decision(
        self,
        predicted: str,
        *,
        context: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        return decision_tracker.record_attempt(
            component=self.component_name,
            predicted=predicted,
            context=context,
            metadata=metadata,
        )

    def adjudicate_decision(
        self,
        decision_id: str,
        *,
        outcome: str,
        success: Optional[bool] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        return decision_tracker.adjudicate(
            decision_id,
            outcome=outcome,
            success=success,
            metadata=metadata,
        )

    def stats(self) -> Dict[str, Any]:
        return decision_tracker.get_stats(self.component_name).to_dict()
