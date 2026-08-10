"""Semantic world-understanding eval for the multimodal perceptor.

Scores structure, ownership, typed state, cross-surface isolation, affordances,
and decision-relevant beliefs independently — not “did it eventually click?”.
See ``schema.py``, ``score.py``, and ``fixtures/``.
"""

from plugin.evals.perception_semantic.score import (
    score_case,
    score_corpus,
    contamination_rate,
)
from plugin.evals.perception_semantic.schema import (
    ForbiddenInference,
    GoldenPerceptionCase,
    load_cases,
)

__all__ = [
    "ForbiddenInference",
    "GoldenPerceptionCase",
    "contamination_rate",
    "load_cases",
    "score_case",
    "score_corpus",
]
