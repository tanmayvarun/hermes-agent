"""Empirical policy prior — counts as P(action_family | goal, state bucket)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

from plugin.agent.features import StateFeatures
from plugin.agent.goal import Goal

DEFAULT_SEED = Path(__file__).resolve().parent / "seeds" / "whatsapp_voice_call.json"
DEFAULT_STORE = Path(__file__).resolve().parents[2] / "experiments" / "runs" / "policy_prior.json"

PSEUDO = 0.5


@dataclass
class PolicyPrior:
    """P(action_family | goal_kind, feature_bucket) from seed + fitted counts."""

    counts: Dict[str, Dict[str, float]] = field(default_factory=dict)
    alpha: float = 0.35

    @classmethod
    def load(cls, path: Optional[Path] = None, seed: Optional[Path] = None) -> "PolicyPrior":
        prior = cls()
        seed_path = seed or DEFAULT_SEED
        if seed_path.is_file():
            prior._merge_file(seed_path)
        store = path or DEFAULT_STORE
        if store.is_file():
            prior._merge_file(store)
        return prior

    def _merge_file(self, path: Path) -> None:
        data = json.loads(path.read_text(encoding="utf-8"))
        buckets = data.get("buckets") or data
        if isinstance(buckets, dict):
            for bkey, fams in buckets.items():
                if not isinstance(fams, dict):
                    continue
                slot = self.counts.setdefault(str(bkey), {})
                for fam, c in fams.items():
                    try:
                        slot[str(fam)] = slot.get(str(fam), 0.0) + float(c)
                    except (TypeError, ValueError):
                        continue

    def save(self, path: Optional[Path] = None) -> Path:
        out = path or DEFAULT_STORE
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"buckets": self.counts}, indent=2), encoding="utf-8")
        return out

    def score(self, action_family: str, features: StateFeatures, goal: Goal) -> float:
        bkey = features.bucket_key(goal.kind)
        fams = dict(self.counts.get(bkey) or {})
        if not fams:
            for k, v in self.counts.items():
                if k.startswith(goal.kind + "|") or k == goal.kind:
                    for fam, c in v.items():
                        fams[fam] = fams.get(fam, 0.0) + 0.15 * float(c)
        if not fams:
            fams = {
                "type_query": 2.0,
                "open_contact": 2.0,
                "start_call": 2.0,
                "open_search": 1.0,
                "observe": 1.0,
                "dismiss": 1.0,
                "end_call": 1.0,
            }
        total = sum(float(c) for c in fams.values()) + PSEUDO * max(1, len(fams))
        c = float(fams.get(action_family, 0.0)) + PSEUDO
        return c / total if total > 0 else 0.0

    def observe(self, bucket_key: str, action_family: str, weight: float = 1.0) -> None:
        slot = self.counts.setdefault(bucket_key, {})
        slot[action_family] = slot.get(action_family, 0.0) + weight
