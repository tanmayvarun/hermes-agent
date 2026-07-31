"""Persistent trajectory memory — learn from successful and failed paths.

This is intentionally generic: it records goal-family + state-bucket + action
family outcomes, so later runs can reuse broad trajectory knowledge across
related goals without encoding app-specific flows in the selector.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from plugin.agent.action import Action
from plugin.agent.features import StateFeatures
from plugin.agent.goal import Goal
from plugin.agent.transition.types import TransitionOutcome

DEFAULT_TRAJECTORY_MEMORY_PATH = (
    Path(__file__).resolve().parents[2] / "experiments" / "runs" / "trajectory_memory.jsonl"
)

_POSITIVE_OUTCOMES = {
    TransitionOutcome.PROGRESS.value,
    TransitionOutcome.PROMISING_UNRESOLVED.value,
    TransitionOutcome.GOAL_SATISFIED.value,
}
_NEGATIVE_OUTCOMES = {
    TransitionOutcome.NO_EFFECT.value,
    TransitionOutcome.REGRESSION.value,
}


def _norm(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def _memory_key(goal_family: str, state_bucket: str, action_family: str) -> str:
    return "|".join([goal_family or "unknown", state_bucket or "unknown", action_family or "unknown"])


@dataclass
class TrajectoryStepRecord:
    step_index: int
    state_signature: str
    state_bucket: str
    action: str
    action_family: str
    family_bucket: str = ""
    next_state_signature: str = ""
    next_state_bucket: str = ""
    semantic_target: str = ""
    outcome: str = ""
    progress_delta: float = 0.0
    surface: str = ""
    reversible: bool = True
    score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TrajectoryStat:
    successes: float = 0.0
    failures: float = 0.0
    last_success_ts: float = 0.0
    last_failure_ts: float = 0.0

    def observe(self, *, success: bool, weight: float = 1.0, ts: float = 0.0) -> None:
        if success:
            self.successes += weight
            self.last_success_ts = max(self.last_success_ts, ts or time.time())
        else:
            self.failures += weight
            self.last_failure_ts = max(self.last_failure_ts, ts or time.time())

    @property
    def total(self) -> float:
        return self.successes + self.failures

    @property
    def success_rate(self) -> float:
        total = self.total
        if total <= 0:
            return 0.0
        return self.successes / total

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TrajectoryMemory:
    """Persistent success/failure memory from past trajectories."""

    path: Path = field(default_factory=lambda: DEFAULT_TRAJECTORY_MEMORY_PATH)
    _loaded: bool = False
    _exact_stats: Dict[str, TrajectoryStat] = field(default_factory=dict)
    _family_stats: Dict[str, TrajectoryStat] = field(default_factory=dict)
    _successor_stats: Dict[str, TrajectoryStat] = field(default_factory=dict)

    def ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self.path.is_file():
            return
        try:
            for line in self.path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                self._ingest_run(ev)
        except OSError:
            pass

    def _stat(self, key: str, *, exact: bool = True) -> TrajectoryStat:
        store = self._exact_stats if exact else self._family_stats
        if key not in store:
            store[key] = TrajectoryStat()
        return store[key]

    def _successor_stat(self, key: str) -> TrajectoryStat:
        if key not in self._successor_stats:
            self._successor_stats[key] = TrajectoryStat()
        return self._successor_stats[key]

    def _ingest_step(
        self,
        *,
        goal_family: str,
        goal_signature: str,
        step: Dict[str, Any],
        success: bool,
        ts: float,
    ) -> None:
        state_bucket = _norm(str(step.get("state_bucket") or "unknown")) or "unknown"
        family_bucket = _norm(str(step.get("family_bucket") or state_bucket)) or state_bucket
        next_state_bucket = _norm(str(step.get("next_state_bucket") or "")) or ""
        action_family = _norm(str(step.get("action_family") or ""))
        if not action_family:
            return
        outcome = _norm(str(step.get("outcome") or ""))
        if outcome in _POSITIVE_OUTCOMES:
            step_success = True
        elif outcome in _NEGATIVE_OUTCOMES:
            step_success = False
        else:
            return
        # Successful trajectories strengthen positive outcomes; failures still
        # record negative evidence for the exact step that was unhelpful.
        family_key = _memory_key(goal_family, state_bucket, action_family)
        family_bucket_key = _memory_key(goal_family, family_bucket, action_family)
        exact_key = _memory_key(goal_signature, state_bucket, action_family)
        self._stat(family_key, exact=False).observe(success=step_success, ts=ts)
        if family_bucket_key != family_key:
            self._stat(family_bucket_key, exact=False).observe(success=step_success, ts=ts)
        self._stat(exact_key, exact=True).observe(success=step_success, ts=ts)
        if next_state_bucket:
            successor_family_key = _memory_key(goal_family, state_bucket, action_family) + "|" + next_state_bucket
            successor_family_bucket_key = _memory_key(goal_family, family_bucket, action_family) + "|" + next_state_bucket
            successor_exact_key = _memory_key(goal_signature, state_bucket, action_family) + "|" + next_state_bucket
            self._successor_stat(successor_family_key).observe(success=step_success, ts=ts)
            if successor_family_bucket_key != successor_family_key:
                self._successor_stat(successor_family_bucket_key).observe(success=step_success, ts=ts)
            self._successor_stat(successor_exact_key).observe(success=step_success, ts=ts)

    def _ingest_run(self, ev: Dict[str, Any]) -> None:
        goal = ev.get("goal") or {}
        goal_family = _norm(str(goal.get("family") or goal.get("kind") or "unknown")) or "unknown"
        goal_signature = _norm(str(goal.get("signature") or goal.get("kind") or "unknown")) or "unknown"
        ts = float(ev.get("ts") or time.time())
        for step in ev.get("steps") or []:
            if isinstance(step, dict):
                self._ingest_step(
                    goal_family=goal_family,
                    goal_signature=goal_signature,
                    step=step,
                    success=bool(ev.get("success", True)),
                    ts=ts,
                )

    def record_run(
        self,
        *,
        goal: Goal,
        steps: Iterable[TrajectoryStepRecord],
        success: bool,
        reason: str = "",
        evidence: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.ensure_loaded()
        step_dicts = [s.to_dict() if hasattr(s, "to_dict") else dict(s) for s in steps]
        rec = {
            "ts": time.time(),
            "goal": {
                "kind": goal.kind,
                "family": goal.family_key(),
                "signature": goal.signature_key(),
                "app": goal.app,
                "contact": goal.contact,
                "target_contact": goal.target_contact,
                "link_query": goal.link_query,
            },
            "success": bool(success),
            "reason": reason,
            "evidence": evidence or {},
            "steps": step_dicts,
        }
        self._ingest_run(rec)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, default=str) + "\n")
        except OSError:
            pass

    def score(
        self,
        goal: Goal,
        features: StateFeatures,
        action_family: str,
        *,
        state_signature: str = "",
    ) -> float:
        """Return a small signed boost in [-0.25, 0.25] from past trajectories."""
        self.ensure_loaded()
        fam = _norm(goal.family_key()) or _norm(goal.kind)
        exact_goal = _norm(goal.signature_key()) or _norm(goal.kind)
        state_bucket = _norm(features.bucket_key(goal.kind)) or "unknown"
        family_bucket = _norm(features.bucket_key(goal.family_key())) or state_bucket
        action_family = _norm(action_family)
        if not action_family:
            return 0.0

        candidates = [
            _memory_key(exact_goal, state_bucket, action_family),
            _memory_key(exact_goal, family_bucket, action_family),
            _memory_key(fam, state_bucket, action_family),
            _memory_key(fam, family_bucket, action_family),
            _memory_key(exact_goal, "unknown", action_family),
            _memory_key(fam, "unknown", action_family),
            _memory_key(fam, state_bucket, "observe"),
            _memory_key(fam, family_bucket, "observe"),
        ]
        stat = None
        for key in candidates:
            stat = self._exact_stats.get(key) or self._family_stats.get(key)
            if stat is not None and stat.total > 0:
                break
        if stat is None or stat.total <= 0:
            return 0.0

        # More observations => stronger signal, but keep the effect bounded.
        confidence = min(1.0, stat.total / 5.0)
        centered = stat.success_rate - 0.5
        boost = max(-0.35, min(0.35, centered * 0.75 * confidence))
        if state_signature:
            state_signature = _norm(state_signature)
            if state_signature and state_signature.endswith("|ringing"):
                boost *= 0.9
        boost += self._transition_bonus(exact_goal, fam, state_bucket, family_bucket, action_family)
        return max(-0.35, min(0.35, boost))

    def _transition_bonus(
        self,
        exact_goal: str,
        family_goal: str,
        state_bucket: str,
        family_bucket: str,
        action_family: str,
    ) -> float:
        prefixes = [
            _memory_key(exact_goal, state_bucket, action_family),
            _memory_key(exact_goal, family_bucket, action_family),
            _memory_key(family_goal, state_bucket, action_family),
            _memory_key(family_goal, family_bucket, action_family),
        ]
        best = 0.0
        for prefix in prefixes:
            best = max(best, self._successor_bonus(prefix))
        return max(-0.15, min(0.15, best))

    def _successor_bonus(self, prefix: str) -> float:
        matched = [
            stat
            for key, stat in self._successor_stats.items()
            if key.startswith(prefix + "|") and stat.total > 0
        ]
        if not matched:
            return 0.0
        total = sum(stat.total for stat in matched)
        if total <= 0:
            return 0.0
        best = max(matched, key=lambda stat: stat.total)
        concentration = min(1.0, best.total / max(1.0, total))
        confidence = min(1.0, total / 8.0)
        centered = best.success_rate - 0.5
        return centered * concentration * confidence * 0.45


_DEFAULT_TRAJECTORY_MEMORY: Optional[TrajectoryMemory] = None


def get_trajectory_memory() -> TrajectoryMemory:
    global _DEFAULT_TRAJECTORY_MEMORY
    if _DEFAULT_TRAJECTORY_MEMORY is None:
        _DEFAULT_TRAJECTORY_MEMORY = TrajectoryMemory()
    return _DEFAULT_TRAJECTORY_MEMORY
