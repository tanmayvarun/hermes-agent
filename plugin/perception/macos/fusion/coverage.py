"""Layer 4 — vision recovery gate over the Accessibility primary path."""

from __future__ import annotations

import logging
import os
from typing import Optional

from plugin.perception.observation import Observation

logger = logging.getLogger(__name__)


def _ocr_enabled() -> bool:
    return str(os.getenv("HERMES_PERCEPTION_OCR", "1")).strip().lower() not in {"0", "false", "no", "off"}

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
    """Augment an observation with content recovered from its screenshot via OCR.

    Accessibility can be blind on some surfaces — a chrome-only AX tree exposes
    only the app/window and no content (WhatsApp is the canonical case). OCR over
    the screenshot recovers the visible text so the perceptor still sees content;
    with AX + pixels + OCR feeding one observation, a single blind channel no
    longer blinds the perceptor. Best-effort: without a screenshot or an OCR
    engine the observation is returned unchanged. Set HERMES_PERCEPTION_OCR=0 to
    disable.
    """
    if not _ocr_enabled():
        return obs
    from plugin.perception.ocr.recovery import recover_observation_with_ocr

    return recover_observation_with_ocr(obs, use_case=use_case, force=force)


def maybe_recover_with_screen2ax(obs: Observation) -> Observation:
    """Adaptive OCR recovery: only when accessibility coverage looks thin."""
    if not needs_screen2ax(obs):
        return obs
    return maybe_recover_with_ocr(obs, force=False)
