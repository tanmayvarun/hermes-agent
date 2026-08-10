"""Select an OCR engine from use case and observed success rates."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .base import OCREngineStats, OCRRun


def _norm_use_case(use_case: str) -> str:
    return " ".join((use_case or "").strip().lower().split())


# Cold-start order for live UI screens, before any success rate is observed.
_UI_ENGINE_PREFERENCE = {"visionkit": 0, "easyocr": 1, "paddleocr": 2}


def _use_case_hint(use_case: str) -> str:
    low = _norm_use_case(use_case)
    if any(token in low for token in ("pdf", "doc", "document", "scan", "invoice", "receipt", "table")):
        return "document"
    return "ui"


@dataclass
class OCRSelector:
    """Choose an OCR engine from task shape plus rolling success rate."""

    stats: Dict[str, Dict[str, OCREngineStats]] = field(default_factory=dict)
    min_accept_score: float = 0.3
    min_learn_attempts: int = 3

    def _stats_for(self, use_case: str, engine_id: str) -> OCREngineStats:
        uc = _norm_use_case(use_case)
        bucket = self.stats.setdefault(uc, {})
        return bucket.setdefault(engine_id, OCREngineStats())

    def rank(self, engines: Sequence[Any], *, use_case: str = "") -> List[Any]:
        uc = _norm_use_case(use_case)
        hint = _use_case_hint(uc)
        annotated = []
        for idx, engine in enumerate(engines):
            stats = self._stats_for(uc, getattr(engine, "engine_id", f"engine_{idx}"))
            if stats.attempts >= self.min_learn_attempts:
                rank = (
                    0,
                    -stats.success_rate,
                    -stats.ema_score,
                    -stats.last_score,
                    idx,
                )
            else:
                engine_id = getattr(engine, "engine_id", "")
                if hint == "document":
                    prefer = 0 if engine_id == "paddleocr" else 1
                else:
                    # A UI screen is read against a clock: the agent acts on what
                    # it saw, so a read that takes fifteen seconds describes a
                    # screen fifteen seconds gone. VisionKit returns the same
                    # text in about one, which is why it leads here rather than
                    # easyocr. Measured stats override this after a few attempts.
                    prefer = _UI_ENGINE_PREFERENCE.get(engine_id, len(_UI_ENGINE_PREFERENCE))
                rank = (1, prefer, idx)
            annotated.append((rank, engine))
        annotated.sort(key=lambda item: item[0])
        return [engine for _, engine in annotated]

    def choose(self, engines: Sequence[Any], *, use_case: str = "") -> Optional[Any]:
        ranked = self.rank(list(engines), use_case=use_case)
        return ranked[0] if ranked else None

    def record(self, use_case: str, run: OCRRun) -> None:
        self._stats_for(use_case, run.engine_id).record(run)

    def best_score(self, use_case: str, engine_id: str) -> float:
        return self._stats_for(use_case, engine_id).ema_score

    def success_rate(self, use_case: str, engine_id: str) -> float:
        return self._stats_for(use_case, engine_id).success_rate


_GLOBAL_SELECTOR = OCRSelector()


def get_ocr_selector() -> OCRSelector:
    return _GLOBAL_SELECTOR
