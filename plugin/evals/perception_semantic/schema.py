"""Structured golden perception cases — world understanding, not click outcomes."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

DEFAULT_CASES_DIR = Path(__file__).resolve().parent / "fixtures"


@dataclass
class SurfaceGold:
    id: str
    type: str
    foreground: bool = False

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SurfaceGold":
        return cls(
            id=str(d.get("id") or ""),
            type=str(d.get("type") or d.get("id") or ""),
            foreground=bool(d.get("foreground")),
        )


@dataclass
class ClaimGold:
    predicate: str
    value: Any
    owner_surface: str
    subject: str = ""
    semantic_role: str = ""

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ClaimGold":
        return cls(
            predicate=str(d.get("predicate") or ""),
            value=d.get("value"),
            owner_surface=str(d.get("owner_surface") or ""),
            subject=str(d.get("subject") or ""),
            semantic_role=str(d.get("semantic_role") or ""),
        )


@dataclass
class AffordanceGold:
    family: str
    target: str = ""
    surface: str = ""

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AffordanceGold":
        return cls(
            family=str(d.get("family") or ""),
            target=str(d.get("target") or ""),
            surface=str(d.get("surface") or ""),
        )


@dataclass
class ForbiddenInference:
    predicate: str
    value: Any = True
    reason: str = ""

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ForbiddenInference":
        return cls(
            predicate=str(d.get("predicate") or ""),
            value=d.get("value", True),
            reason=str(d.get("reason") or ""),
        )


@dataclass
class ActionSpec:
    family: str
    surface: str = ""
    text: str = ""

    @classmethod
    def from_dict(cls, d: Any) -> "ActionSpec":
        if isinstance(d, (list, tuple)) and len(d) >= 1:
            return cls(
                family=str(d[0]),
                surface=str(d[1]) if len(d) > 1 else "",
                text=str(d[2]) if len(d) > 2 else "",
            )
        if isinstance(d, dict):
            return cls(
                family=str(d.get("family") or ""),
                surface=str(d.get("surface") or ""),
                text=str(d.get("text") or d.get("target") or ""),
            )
        return cls(family=str(d or ""))


@dataclass
class GoldenPerceptionCase:
    """One semantic world-understanding fixture (phenomenon-tagged)."""

    id: str
    phenomena: List[str] = field(default_factory=list)
    app: str = ""
    note: str = ""
    # Production-shaped multimodal packet (goal, observation.ax_evidence, …).
    packet: Dict[str, Any] = field(default_factory=dict)
    # Screenshot relative to record_dir / absolute / empty if contract-only.
    screenshot: str = ""
    record_dir: str = ""
    # Human gold world (not the recorded model reply).
    surfaces: List[SurfaceGold] = field(default_factory=list)
    claims: List[ClaimGold] = field(default_factory=list)
    affordances: List[AffordanceGold] = field(default_factory=list)
    forbidden: List[ForbiddenInference] = field(default_factory=list)
    acceptable_actions: List[ActionSpec] = field(default_factory=list)
    forbidden_actions: List[str] = field(default_factory=list)
    # Optional contaminated / recorded proposal used for negative scoring.
    contaminated_response: Optional[Dict[str, Any]] = None
    # Optional correct annotated response for positive scoring without VLM.
    annotated_response: Optional[Dict[str, Any]] = None
    metamorphic_of: str = ""
    metamorphic_transform: str = ""

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "GoldenPerceptionCase":
        gold = d.get("gold") if isinstance(d.get("gold"), dict) else d
        return cls(
            id=str(d.get("id") or ""),
            phenomena=[str(x) for x in (d.get("phenomena") or [])],
            app=str(d.get("app") or ""),
            note=str(d.get("note") or ""),
            packet=dict(d.get("packet") or {}),
            screenshot=str(d.get("screenshot") or ""),
            record_dir=str(d.get("record_dir") or ""),
            surfaces=[
                SurfaceGold.from_dict(x)
                for x in (gold.get("surfaces") or [])
                if isinstance(x, dict)
            ],
            claims=[
                ClaimGold.from_dict(x)
                for x in (gold.get("claims") or gold.get("observations") or [])
                if isinstance(x, dict)
            ],
            affordances=[
                AffordanceGold.from_dict(x)
                for x in (gold.get("affordances") or [])
                if isinstance(x, dict)
            ],
            forbidden=[
                ForbiddenInference.from_dict(x)
                for x in (gold.get("forbidden") or gold.get("forbidden_inferences") or [])
                if isinstance(x, dict)
            ],
            acceptable_actions=[
                ActionSpec.from_dict(x) for x in (gold.get("acceptable_actions") or [])
            ],
            forbidden_actions=[
                str(x) for x in (gold.get("forbidden_actions") or []) if str(x).strip()
            ],
            contaminated_response=(
                dict(d["contaminated_response"])
                if isinstance(d.get("contaminated_response"), dict)
                else None
            ),
            annotated_response=(
                dict(d["annotated_response"])
                if isinstance(d.get("annotated_response"), dict)
                else None
            ),
            metamorphic_of=str(d.get("metamorphic_of") or ""),
            metamorphic_transform=str(d.get("metamorphic_transform") or ""),
        )


def load_cases(
    root: str | Path = DEFAULT_CASES_DIR,
) -> List[GoldenPerceptionCase]:
    root_path = Path(root)
    cases: List[GoldenPerceptionCase] = []
    if not root_path.exists():
        return cases
    for path in sorted(root_path.rglob("*.json")):
        if path.name.startswith("_"):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and item.get("id"):
                    cases.append(GoldenPerceptionCase.from_dict(item))
        elif isinstance(data, dict) and data.get("id"):
            cases.append(GoldenPerceptionCase.from_dict(data))
    return cases


def case_to_dict(case: GoldenPerceptionCase) -> Dict[str, Any]:
    import copy

    return {
        "id": case.id,
        "phenomena": list(case.phenomena),
        "app": case.app,
        "note": case.note,
        "packet": copy.deepcopy(case.packet),
        "screenshot": case.screenshot,
        "record_dir": case.record_dir,
        "metamorphic_of": case.metamorphic_of,
        "metamorphic_transform": case.metamorphic_transform,
        "gold": {
            "surfaces": [
                {"id": s.id, "type": s.type, "foreground": s.foreground}
                for s in case.surfaces
            ],
            "claims": [
                {
                    "predicate": c.predicate,
                    "value": c.value,
                    "owner_surface": c.owner_surface,
                    "subject": c.subject,
                    "semantic_role": c.semantic_role,
                }
                for c in case.claims
            ],
            "affordances": [
                {"family": a.family, "target": a.target, "surface": a.surface}
                for a in case.affordances
            ],
            "forbidden": [
                {"predicate": f.predicate, "value": f.value, "reason": f.reason}
                for f in case.forbidden
            ],
            "acceptable_actions": [
                {"family": a.family, "surface": a.surface, "text": a.text}
                for a in case.acceptable_actions
            ],
            "forbidden_actions": list(case.forbidden_actions),
        },
        "annotated_response": copy.deepcopy(case.annotated_response),
        "contaminated_response": copy.deepcopy(case.contaminated_response),
    }
