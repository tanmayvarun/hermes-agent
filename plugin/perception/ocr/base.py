"""Shared OCR engine types."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Sequence, Tuple, runtime_checkable

Bounds = Tuple[float, float, float, float]


@dataclass
class OCRSpan:
    text: str
    bbox: Bounds = (0.0, 0.0, 0.0, 0.0)
    confidence: float = 0.0
    engine: str = ""
    line_index: int = 0
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class OCRRun:
    engine_id: str
    use_case: str = ""
    spans: List[OCRSpan] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)
    degraded: bool = False

    def mean_confidence(self) -> float:
        if not self.spans:
            return 0.0
        return sum(max(0.0, min(1.0, float(s.confidence))) for s in self.spans) / len(self.spans)

    def score(self) -> float:
        if not self.spans:
            return 0.0
        mean_conf = self.mean_confidence()
        density = min(1.0, len(self.spans) / 8.0)
        return max(0.0, min(1.0, mean_conf * (0.6 + 0.4 * density)))

    def success(self) -> bool:
        return bool(self.spans) and self.score() >= 0.25

    def to_dict(self) -> Dict[str, Any]:
        return {
            "engine_id": self.engine_id,
            "use_case": self.use_case,
            "spans": [s.to_dict() for s in self.spans],
            "meta": dict(self.meta),
            "degraded": self.degraded,
            "mean_confidence": round(self.mean_confidence(), 4),
            "score": round(self.score(), 4),
        }


@dataclass
class OCREngineStats:
    attempts: int = 0
    successes: int = 0
    ema_score: float = 0.0
    last_score: float = 0.0

    def record(self, run: OCRRun, *, alpha: float = 0.35) -> None:
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
class OCREngine(Protocol):
    engine_id: str

    def recognize(self, screenshot_path: str, *, use_case: str = "") -> OCRRun: ...
