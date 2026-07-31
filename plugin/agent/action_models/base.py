"""Shared types for action-prior model adapters."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Sequence, Tuple, runtime_checkable


@dataclass
class ActionProposal:
    """One model-backed suggestion for the next UI action."""

    action_family: str = ""
    semantic_target: str = ""
    action: str = ""
    confidence: float = 0.0
    risk: float = 0.0
    reversible: bool = True
    reason: str = ""
    coordinate: Optional[Tuple[float, float]] = None
    model_id: str = ""
    predicted_state: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ActionModelRun:
    """One model invocation and its ranked proposals."""

    model_id: str
    use_case: str = ""
    proposals: List[ActionProposal] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)
    degraded: bool = False

    def mean_confidence(self) -> float:
        if not self.proposals:
            return 0.0
        return sum(max(0.0, min(1.0, float(p.confidence))) for p in self.proposals) / len(self.proposals)

    def score(self) -> float:
        if not self.proposals:
            return 0.0
        mean_conf = self.mean_confidence()
        density = min(1.0, len(self.proposals) / 5.0)
        risk_penalty = min(0.35, sum(max(0.0, float(p.risk)) for p in self.proposals[:3]) / max(1.0, len(self.proposals[:3])) * 0.15)
        return max(0.0, min(1.0, mean_conf * (0.60 + 0.30 * density) - risk_penalty))

    def success(self) -> bool:
        return bool(self.proposals) and self.score() >= 0.25

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id,
            "use_case": self.use_case,
            "proposals": [p.to_dict() for p in self.proposals],
            "meta": dict(self.meta),
            "degraded": self.degraded,
            "mean_confidence": round(self.mean_confidence(), 4),
            "score": round(self.score(), 4),
        }


@dataclass
class ActionModelStats:
    attempts: int = 0
    successes: int = 0
    ema_score: float = 0.0
    last_score: float = 0.0

    def record(self, run: ActionModelRun, *, alpha: float = 0.35) -> None:
        self.attempts += 1
        self.successes += 1 if run.success() else 0
        self.last_score = run.score()
        if self.attempts == 1:
            self.ema_score = self.last_score
        else:
            self.ema_score = (alpha * self.last_score) + ((1.0 - alpha) * self.ema_score)

    @property
    def success_rate(self) -> float:
        if self.attempts <= 0:
            return 0.0
        return self.successes / float(self.attempts)


@runtime_checkable
class ActionModel(Protocol):
    model_id: str

    def propose(
        self,
        *,
        goal: Any,
        world: Any,
        features: Any,
        candidates: Sequence[Any] = (),
        use_case: str = "",
    ) -> ActionModelRun: ...
