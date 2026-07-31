"""Policy experience logging + offline fit."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

from plugin.agent.policy.prior import DEFAULT_STORE, PolicyPrior

DEFAULT_EVENTS = Path(__file__).resolve().parents[2] / "experiments" / "runs" / "policy_events.jsonl"


def log_policy_event(
    event: Dict[str, Any],
    *,
    path: Optional[Path] = None,
) -> None:
    out = path or DEFAULT_EVENTS
    out.parent.mkdir(parents=True, exist_ok=True)
    rec = {"ts": time.time(), **event}
    with out.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, default=str) + "\n")


def fit_prior_from_events(
    events_path: Optional[Path] = None,
    store_path: Optional[Path] = None,
    *,
    min_weight: float = 0.0,
) -> PolicyPrior:
    """Aggregate policy_events.jsonl into empirical prior counts."""
    path = events_path or DEFAULT_EVENTS
    prior = PolicyPrior.load(path=None)  # seed only first
    # Fresh counts from events (keep seed via load then add events heavily)
    if not path.is_file():
        prior.save(store_path or DEFAULT_STORE)
        return prior
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        bucket = ev.get("bucket_key") or ""
        fam = ev.get("action_family") or ""
        delta = float(ev.get("success_delta") or 0.0)
        if not bucket or not fam:
            continue
        # Weight: successful verified actions count more
        w = 1.0 + max(0.0, delta) * 2.0
        if delta < 0:
            w = 0.25
        if w < min_weight:
            continue
        prior.observe(str(bucket), str(fam), weight=w)
    prior.save(store_path or DEFAULT_STORE)
    return prior
