"""Domain/environment blocker detectors.

Generic substrate lives in ``executive.blocking``; detectors here interpret
environment evidence into Warning / BlockingCondition. Keep regexes and
app-specific wording out of the core substrate.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from plugin.agent.executive.blocking import BlockingCondition, Warning
from plugin.agent.executive.blocker_detectors.storage import detect_storage_signals


def run_detectors(
    *,
    observation_texts: Sequence[str] = (),
    view: Optional[Dict[str, Any]] = None,
    features: Optional[Dict[str, Any]] = None,
    intention_id: str = "",
    app: str = "",
) -> Tuple[List[Warning], List[BlockingCondition]]:
    """Aggregate domain detectors. Storage is the first implemented adapter."""
    warnings: List[Warning] = []
    blockers: List[BlockingCondition] = []
    w, b = detect_storage_signals(
        observation_texts=observation_texts,
        view=view,
        features=features,
        intention_id=intention_id,
        app=app,
    )
    warnings.extend(w)
    blockers.extend(b)
    return warnings, blockers
