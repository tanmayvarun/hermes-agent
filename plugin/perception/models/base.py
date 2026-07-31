"""Shared types for screen-perception model adapters."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Sequence, Tuple, runtime_checkable

Bounds = Tuple[float, float, float, float]


@dataclass
class ScreenElement:
    """One visual element extracted from a screenshot."""

    element_id: str = ""
    label: str = ""
    bbox: Bounds = (0.0, 0.0, 0.0, 0.0)
    text: str = ""
    icon_description: str = ""
    interactive: bool = False
    confidence: float = 0.0
    source: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ScreenModelRun:
    """One model invocation and its extracted elements."""

    model_id: str
    use_case: str = ""
    elements: List[ScreenElement] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)
    degraded: bool = False

    def mean_confidence(self) -> float:
        if not self.elements:
            return 0.0
        return sum(max(0.0, min(1.0, float(e.confidence))) for e in self.elements) / len(self.elements)

    def score(self) -> float:
        if not self.elements:
            return 0.0
        mean_conf = self.mean_confidence()
        density = min(1.0, len(self.elements) / 10.0)
        interactive = sum(1 for e in self.elements if e.interactive)
        interactive_bonus = min(0.25, interactive / max(1.0, len(self.elements)) * 0.25)
        return max(0.0, min(1.0, mean_conf * (0.55 + 0.35 * density) + interactive_bonus))

    def success(self) -> bool:
        return bool(self.elements) and self.score() >= 0.25

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id,
            "use_case": self.use_case,
            "elements": [e.to_dict() for e in self.elements],
            "meta": dict(self.meta),
            "degraded": self.degraded,
            "mean_confidence": round(self.mean_confidence(), 4),
            "score": round(self.score(), 4),
        }


@dataclass
class ScreenModelStats:
    attempts: int = 0
    successes: int = 0
    ema_score: float = 0.0
    last_score: float = 0.0

    def record(self, run: ScreenModelRun, *, alpha: float = 0.35) -> None:
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
class ScreenParser(Protocol):
    model_id: str

    def parse(self, screenshot_path: str, *, use_case: str = "") -> ScreenModelRun: ...
