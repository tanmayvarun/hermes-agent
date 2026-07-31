"""Generic state features for policy prior / decision scoring."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass
class StateFeatures:
    app: str = ""
    screen_kind: str = "unknown"  # generic screen kind: list | search | detail | call | dialog | menu | input | unknown
    screen_bucket: str = "unknown"  # list | search | conversation | calling | dialog | unknown
    has_dialog: bool = False
    has_text_query: bool = False
    query_matches_goal: bool = False
    has_named_entity: bool = False  # goal contact visible
    conversation_open: bool = False
    call_available: bool = False
    call_ringing: bool = False
    leftover_call: bool = False
    search_focused: bool = False
    goal_progress: float = 0.0  # 0..1
    worldview_score: float = 1.0
    mean_belief: float = 1.0
    needs_reobserve: bool = False
    extras: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d

    def bucket_key(self, goal_kind: str) -> str:
        """Coarse key for empirical prior counts."""
        screen_kind = self.screen_kind or self.screen_bucket or "unknown"
        parts = [
            goal_kind,
            f"sk={screen_kind}",
            f"sb={self.screen_bucket}",
            f"q={int(self.has_text_query)}",
            f"qm={int(self.query_matches_goal)}",
            f"c={int(self.has_named_entity)}",
            f"co={int(self.conversation_open)}",
            f"d={int(self.has_dialog)}",
            f"r={int(self.call_ringing)}",
            f"l={int(self.leftover_call)}",
        ]
        return "|".join(parts)

    def feature_hash(self, goal_kind: str) -> str:
        raw = json.dumps({"k": goal_kind, **{k: v for k, v in self.to_dict().items() if k != "extras"}}, sort_keys=True)
        return hashlib.sha1(raw.encode()).hexdigest()[:12]
