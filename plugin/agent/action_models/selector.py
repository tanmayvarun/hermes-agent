"""Select an action-prior model from use case and observed success rates."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from .base import ActionModelRun, ActionModelStats


def _norm_use_case(use_case: str) -> str:
    return " ".join((use_case or "").strip().lower().split())


def _use_case_hint(use_case: str) -> str:
    low = _norm_use_case(use_case)
    if any(token in low for token in ("browser", "web", "url", "link", "site")):
        return "browser"
    if any(token in low for token in ("ground", "coordinate", "point", "bbox", "element")):
        return "grounding"
    return "desktop"


@dataclass
class ActionModelSelector:
    """Choose an action-prior model from task shape plus rolling success rate."""

    stats: Dict[str, Dict[str, ActionModelStats]] = field(default_factory=dict)
    min_accept_score: float = 0.3
    min_learn_attempts: int = 3

    def _stats_for(self, use_case: str, model_id: str) -> ActionModelStats:
        uc = _norm_use_case(use_case)
        bucket = self.stats.setdefault(uc, {})
        return bucket.setdefault(model_id, ActionModelStats())

    def rank(self, models: Sequence[Any], *, use_case: str = "") -> List[Any]:
        uc = _norm_use_case(use_case)
        hint = _use_case_hint(uc)
        annotated = []
        for idx, model in enumerate(models):
            model_id = getattr(model, "model_id", f"model_{idx}")
            stats = self._stats_for(uc, model_id)
            if stats.attempts >= self.min_learn_attempts:
                rank = (0, -stats.success_rate, -stats.ema_score, -stats.last_score, idx)
            else:
                if hint == "browser":
                    prefer = 0 if model_id in {"openai-computer-use", "gemini-computer-use", "anthropic-computer-use"} else 1
                elif hint == "grounding":
                    prefer = 0 if model_id in {"os-atlas"} else 1
                else:
                    prefer = 0 if model_id in {"ui-tars", "showui"} else 1
                rank = (1, prefer, idx)
            annotated.append((rank, model))
        annotated.sort(key=lambda item: item[0])
        return [model for _, model in annotated]

    def choose(self, models: Sequence[Any], *, use_case: str = "") -> Optional[Any]:
        ranked = self.rank(list(models), use_case=use_case)
        return ranked[0] if ranked else None

    def record(self, use_case: str, run: ActionModelRun) -> None:
        self._stats_for(use_case, run.model_id).record(run)

    def best_score(self, use_case: str, model_id: str) -> float:
        return self._stats_for(use_case, model_id).ema_score

    def success_rate(self, use_case: str, model_id: str) -> float:
        return self._stats_for(use_case, model_id).success_rate


_GLOBAL_SELECTOR = ActionModelSelector()


def get_action_model_selector() -> ActionModelSelector:
    return _GLOBAL_SELECTOR
