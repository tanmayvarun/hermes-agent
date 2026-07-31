"""Layer 4 — vision fallback gate. Primary path is Accessibility (none)."""

from __future__ import annotations

import logging
from typing import Optional

from plugin.perception.observation import Observation

logger = logging.getLogger(__name__)

COVERAGE_THRESHOLD = 0.80


def estimate_coverage(obs: Observation, *, visual_node_estimate: Optional[int] = None) -> float:
    """accessible_nodes / visual_nodes. If visual unknown, use 1.0 when nodes>0."""
    accessible = len(obs.nodes)
    if visual_node_estimate and visual_node_estimate > 0:
        return min(1.0, accessible / float(visual_node_estimate))
    if obs.coverage is not None:
        return float(obs.coverage)
    return 1.0 if accessible > 0 else 0.0


def needs_screen2ax(obs: Observation, *, visual_node_estimate: Optional[int] = None) -> bool:
    return estimate_coverage(obs, visual_node_estimate=visual_node_estimate) < COVERAGE_THRESHOLD


def maybe_recover_with_ocr(obs: Observation, *, use_case: str = "", force: bool = False) -> Observation:
    """AX-only rollback: keep the hook, but do not invoke OCR for now.

    We are intentionally disabling OCR at the fusion boundary so the live
    agent runs from Accessibility-only perception while we evaluate AX routing
    and planning.
    """
    return obs


def maybe_recover_with_screen2ax(obs: Observation) -> Observation:
    """Backward-compatible alias for screenshot OCR recovery."""
    if not needs_screen2ax(obs):
        return obs
    return maybe_recover_with_ocr(obs, force=False)
