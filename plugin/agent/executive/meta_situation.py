"""Situation brief that shapes the meta-action LLM packet.

Mined from ``executive_judgement`` events across zarooratwala live runs: the
fields that discriminate unique meta decisions. Keep this compact — no pixels,
no full world documents.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class MetaSituation:
    """Frame-level context the meta chooser should see beyond MetaContext flags."""

    cognitive_mode: str = ""
    mode_triggers: List[str] = field(default_factory=list)
    static_streak: int = 0
    coverage: Optional[float] = None
    evidence_gaps: List[str] = field(default_factory=list)
    blocking_uncertainties: List[str] = field(default_factory=list)
    perception_query: Dict[str, Any] = field(default_factory=dict)
    goal_contract: Dict[str, Any] = field(default_factory=dict)
    phase: str = ""
    last_meta_action: str = ""
    last_action: str = ""
    consecutive_surprise_relooks: int = 0
    consecutive_perceives: int = 0
    consecutive_thinks: int = 0
    consecutive_probes: int = 0
    consecutive_backtracks: int = 0
    consecutive_information_gathering: int = 0
    consecutive_searches: int = 0
    # Blockers + housekeeping shortlist for the meta consultant (no pixels).
    blockers: Dict[str, Any] = field(default_factory=dict)
    housekeeping_capabilities: List[Dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        gaps = [str(g) for g in self.evidence_gaps if str(g).strip()][:6]
        blocking = [str(b) for b in self.blocking_uncertainties if str(b).strip()][:6]
        pending = [
            str(p)
            for p in (self.goal_contract.get("pending") or [])
            if str(p).strip()
        ][:6]
        satisfied = [
            str(s)
            for s in (self.goal_contract.get("satisfied") or [])
            if str(s).strip()
        ][:6]
        pq = dict(self.perception_query or {})
        # Keep only the query skeleton — not prose dumps.
        pq_view = {
            k: pq.get(k)
            for k in (
                "needed",
                "focus",
                "question",
                "why",
                "mode",
            )
            if k in pq and pq.get(k) not in (None, "", [])
        }
        return {
            "cognitive_mode": str(self.cognitive_mode or ""),
            "mode_triggers": [str(t) for t in self.mode_triggers if str(t).strip()][:8],
            "static_streak": int(self.static_streak or 0),
            "coverage": None if self.coverage is None else round(float(self.coverage), 3),
            "evidence_gaps": gaps,
            "blocking_uncertainties": blocking,
            "perception_query": pq_view,
            "goal": {
                "phase": str(self.phase or ""),
                "all_satisfied": bool(self.goal_contract.get("all_satisfied")),
                "pending": pending,
                "satisfied": satisfied,
            },
            "recent": {
                "last_meta_action": str(self.last_meta_action or ""),
                "last_action": str(self.last_action or "")[:80],
            },
            "streaks": {
                "surprise_relooks": int(self.consecutive_surprise_relooks or 0),
                "perceives": int(self.consecutive_perceives or 0),
                "thinks": int(self.consecutive_thinks or 0),
                "probes": int(self.consecutive_probes or 0),
                "backtracks": int(self.consecutive_backtracks or 0),
                "information_gathering": int(self.consecutive_information_gathering or 0),
                "searches": int(self.consecutive_searches or 0),
            },
            "blockers": dict(self.blockers or {}),
            "housekeeping_capabilities": [
                dict(c) for c in (self.housekeeping_capabilities or [])[:6] if isinstance(c, dict)
            ],
        }


# Top-level packet sections the LLM call must always carry (eval contract).
META_PACKET_REQUIRED_SECTIONS = (
    "goal_complete",
    "allowed_meta_actions",
    "look_debt",
    "evidence",
    "search",
    "budgets",
    "options",
    "situation",
    "blockers",
)


def situation_from_mapping(raw: Optional[Dict[str, Any]]) -> MetaSituation:
    data = dict(raw or {})
    goal = data.get("goal") if isinstance(data.get("goal"), dict) else {}
    streaks = data.get("streaks") if isinstance(data.get("streaks"), dict) else {}
    recent = data.get("recent") if isinstance(data.get("recent"), dict) else {}
    contract = data.get("goal_contract") if isinstance(data.get("goal_contract"), dict) else {}
    if not contract and goal:
        contract = {
            "all_satisfied": bool(goal.get("all_satisfied")),
            "pending": list(goal.get("pending") or []),
            "satisfied": list(goal.get("satisfied") or []),
        }
    return MetaSituation(
        cognitive_mode=str(data.get("cognitive_mode") or ""),
        mode_triggers=[str(t) for t in (data.get("mode_triggers") or []) if str(t).strip()],
        static_streak=int(data.get("static_streak") or 0),
        coverage=(
            None
            if data.get("coverage") is None
            else float(data.get("coverage"))
        ),
        evidence_gaps=[str(g) for g in (data.get("evidence_gaps") or []) if str(g).strip()],
        blocking_uncertainties=[
            str(b) for b in (data.get("blocking_uncertainties") or []) if str(b).strip()
        ],
        perception_query=dict(data.get("perception_query") or {}),
        goal_contract=contract,
        phase=str(data.get("phase") or goal.get("phase") or ""),
        last_meta_action=str(
            data.get("last_meta_action") or recent.get("last_meta_action") or ""
        ),
        last_action=str(data.get("last_action") or recent.get("last_action") or ""),
        consecutive_surprise_relooks=int(
            data.get("consecutive_surprise_relooks")
            or streaks.get("surprise_relooks")
            or 0
        ),
        consecutive_perceives=int(
            data.get("consecutive_perceives") or streaks.get("perceives") or 0
        ),
        consecutive_thinks=int(
            data.get("consecutive_thinks") or streaks.get("thinks") or 0
        ),
        consecutive_probes=int(
            data.get("consecutive_probes") or streaks.get("probes") or 0
        ),
        consecutive_backtracks=int(
            data.get("consecutive_backtracks") or streaks.get("backtracks") or 0
        ),
        consecutive_information_gathering=int(
            data.get("consecutive_information_gathering")
            or streaks.get("information_gathering")
            or 0
        ),
        consecutive_searches=int(
            data.get("consecutive_searches") or streaks.get("searches") or 0
        ),
        blockers=dict(data.get("blockers") or {}),
        housekeeping_capabilities=[
            dict(c)
            for c in (data.get("housekeeping_capabilities") or [])
            if isinstance(c, dict)
        ],
    )
