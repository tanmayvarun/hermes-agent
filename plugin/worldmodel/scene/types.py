"""Typed scene-graph contracts (dict round-trip only; no reconstruction)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Type

Bounds = Tuple[float, float, float, float]


class RegionKind(str, Enum):
    HEADER = "header"
    SIDEBAR = "sidebar"
    CONVERSATION = "conversation"
    TIMELINE = "timeline"
    COMPOSER = "composer"
    MODAL = "modal"
    TOOLBAR = "toolbar"
    FLOATING_MENU = "floating_menu"
    NAVIGATION = "navigation"
    STATUS_BAR = "status_bar"
    UNKNOWN = "unknown"


class EdgeKind(str, Enum):
    CONTAINS = "contains"
    OCCLUDES = "occludes"
    ADJACENT = "adjacent"
    CONTROLS = "controls"
    PARENT_OF = "parent_of"
    MEMBER_OF = "member_of"
    OWNS = "owns"
    LABELS = "labels"
    TRIGGERS = "triggers"
    RESULT_OF = "result_of"
    REPLACES = "replaces"


class SideEffectClass(str, Enum):
    EXPLORE = "explore"
    REVERSIBLE = "reversible"
    EXTERNAL = "external"
    IRREVERSIBLE = "irreversible"


def _bounds_tuple(raw: Any) -> Bounds:
    if raw is None:
        return (0.0, 0.0, 0.0, 0.0)
    if isinstance(raw, (list, tuple)) and len(raw) >= 4:
        return (float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3]))
    return (0.0, 0.0, 0.0, 0.0)


def _enum_value(enum_cls: Type[Enum], raw: Any, default: Enum) -> Enum:
    if isinstance(raw, enum_cls):
        return raw
    if raw is None:
        return default
    try:
        return enum_cls(str(raw))
    except ValueError:
        return default


@dataclass
class SemanticRegion:
    id: str
    kind: RegionKind
    bounds: Bounds = (0.0, 0.0, 0.0, 0.0)
    confidence: float = 0.0
    entity_ids: List[int] = field(default_factory=list)
    parent_region_id: Optional[str] = None
    label: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind.value,
            "bounds": list(self.bounds),
            "confidence": float(self.confidence),
            "entity_ids": list(self.entity_ids),
            "parent_region_id": self.parent_region_id,
            "label": self.label,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SemanticRegion":
        return cls(
            id=str(d.get("id") or ""),
            kind=_enum_value(RegionKind, d.get("kind"), RegionKind.UNKNOWN),  # type: ignore[arg-type]
            bounds=_bounds_tuple(d.get("bounds")),
            confidence=float(d.get("confidence") or 0.0),
            entity_ids=[int(x) for x in (d.get("entity_ids") or [])],
            parent_region_id=d.get("parent_region_id"),
            label=str(d.get("label") or ""),
        )


@dataclass
class SceneNodeRef:
    """Reference to a region or entity node in the context graph."""

    kind: str  # "region" | "entity"
    id: str  # region id or str(entity_id)

    def to_dict(self) -> Dict[str, Any]:
        return {"kind": self.kind, "id": self.id}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SceneNodeRef":
        return cls(kind=str(d.get("kind") or "entity"), id=str(d.get("id") or ""))


@dataclass
class SceneEdge:
    kind: EdgeKind
    source: SceneNodeRef
    target: SceneNodeRef
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind.value,
            "source": self.source.to_dict(),
            "target": self.target.to_dict(),
            "confidence": float(self.confidence),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SceneEdge":
        return cls(
            kind=_enum_value(EdgeKind, d.get("kind"), EdgeKind.CONTAINS),  # type: ignore[arg-type]
            source=SceneNodeRef.from_dict(d.get("source") or {}),
            target=SceneNodeRef.from_dict(d.get("target") or {}),
            confidence=float(d.get("confidence") if d.get("confidence") is not None else 1.0),
        )


@dataclass
class RegionMembership:
    """Evidence that an entity participates in a region or surface."""

    entity_id: int
    region_id: str
    relation: str = "member_of"
    confidence: float = 0.0
    evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": int(self.entity_id),
            "region_id": self.region_id,
            "relation": self.relation,
            "confidence": float(self.confidence),
            "evidence": dict(self.evidence),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "RegionMembership":
        return cls(
            entity_id=int(d.get("entity_id") or 0),
            region_id=str(d.get("region_id") or ""),
            relation=str(d.get("relation") or "member_of"),
            confidence=float(d.get("confidence") if d.get("confidence") is not None else 0.0),
            evidence=dict(d.get("evidence") or {}),
        )


@dataclass
class ContextGraph:
    nodes: List[SceneNodeRef] = field(default_factory=list)
    edges: List[SceneEdge] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ContextGraph":
        return cls(
            nodes=[SceneNodeRef.from_dict(x) for x in (d.get("nodes") or [])],
            edges=[SceneEdge.from_dict(x) for x in (d.get("edges") or [])],
        )


@dataclass
class AffordanceHypothesis:
    """One hypothesized capability for an entity in a region."""

    id: str
    p: float
    region_id: Optional[str] = None
    entity_id: Optional[int] = None
    evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "p": float(self.p),
            "region_id": self.region_id,
            "entity_id": self.entity_id,
            "evidence": dict(self.evidence),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AffordanceHypothesis":
        eid = d.get("entity_id")
        return cls(
            id=str(d.get("id") or ""),
            p=float(d.get("p") or 0.0),
            region_id=d.get("region_id"),
            entity_id=None if eid is None else int(eid),
            evidence=dict(d.get("evidence") or {}),
        )


@dataclass
class AffordanceDistribution:
    """Per-entity affordance hypotheses. Probabilities need not sum to 1."""

    by_entity: Dict[int, List[AffordanceHypothesis]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "by_entity": {
                str(eid): [h.to_dict() for h in hyps] for eid, hyps in self.by_entity.items()
            }
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AffordanceDistribution":
        raw = d.get("by_entity") or {}
        by_entity: Dict[int, List[AffordanceHypothesis]] = {}
        for k, hyps in raw.items():
            by_entity[int(k)] = [AffordanceHypothesis.from_dict(h) for h in (hyps or [])]
        return cls(by_entity=by_entity)

    def hypotheses_for(self, entity_id: int) -> List[AffordanceHypothesis]:
        return list(self.by_entity.get(entity_id) or [])


@dataclass
class ActionRisk:
    affordance_id: str
    side_effect_class: SideEffectClass
    risk: float
    expected_state_delta: str = ""
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "affordance_id": self.affordance_id,
            "side_effect_class": self.side_effect_class.value,
            "risk": float(self.risk),
            "expected_state_delta": self.expected_state_delta,
            "confidence": float(self.confidence),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ActionRisk":
        return cls(
            affordance_id=str(d.get("affordance_id") or ""),
            side_effect_class=_enum_value(  # type: ignore[arg-type]
                SideEffectClass, d.get("side_effect_class"), SideEffectClass.EXPLORE
            ),
            risk=float(d.get("risk") or 0.0),
            expected_state_delta=str(d.get("expected_state_delta") or ""),
            confidence=float(d.get("confidence") if d.get("confidence") is not None else 1.0),
        )


@dataclass
class AttentionSubgraph:
    region_ids: List[str] = field(default_factory=list)
    entity_ids: List[int] = field(default_factory=list)
    goal_kind: str = ""
    residual_mass: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "region_ids": list(self.region_ids),
            "entity_ids": list(self.entity_ids),
            "goal_kind": self.goal_kind,
            "residual_mass": float(self.residual_mass),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AttentionSubgraph":
        return cls(
            region_ids=[str(x) for x in (d.get("region_ids") or [])],
            entity_ids=[int(x) for x in (d.get("entity_ids") or [])],
            goal_kind=str(d.get("goal_kind") or ""),
            residual_mass=float(d.get("residual_mass") or 0.0),
        )


@dataclass
class SceneUnderstandingReport:
    """Worldview-style components for layout / affordance uncertainty."""

    layout_confidence: float = 0.0
    region_coverage: float = 0.0
    affordance_entropy: float = 0.0
    unassigned_entity_fraction: float = 0.0
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "layout_confidence": float(self.layout_confidence),
            "region_coverage": float(self.region_coverage),
            "affordance_entropy": float(self.affordance_entropy),
            "unassigned_entity_fraction": float(self.unassigned_entity_fraction),
            "notes": list(self.notes),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SceneUnderstandingReport":
        return cls(
            layout_confidence=float(d.get("layout_confidence") or 0.0),
            region_coverage=float(d.get("region_coverage") or 0.0),
            affordance_entropy=float(d.get("affordance_entropy") or 0.0),
            unassigned_entity_fraction=float(d.get("unassigned_entity_fraction") or 0.0),
            notes=[str(x) for x in (d.get("notes") or [])],
        )


@dataclass
class CounterfactualRollout:
    """Stage 9 stub — predicted outcome of an affordance without acting."""

    affordance_id: str
    predicted_delta: str = ""
    advances_goal: Optional[bool] = None
    confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "affordance_id": self.affordance_id,
            "predicted_delta": self.predicted_delta,
            "advances_goal": self.advances_goal,
            "confidence": float(self.confidence),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CounterfactualRollout":
        return cls(
            affordance_id=str(d.get("affordance_id") or ""),
            predicted_delta=str(d.get("predicted_delta") or ""),
            advances_goal=d.get("advances_goal"),
            confidence=float(d.get("confidence") or 0.0),
        )


@dataclass
class WorldGraph:
    """Controller-facing hierarchical scene product (Stages 3–8)."""

    regions: List[SemanticRegion] = field(default_factory=list)
    context_graph: ContextGraph = field(default_factory=ContextGraph)
    memberships: List[RegionMembership] = field(default_factory=list)
    affordances: AffordanceDistribution = field(default_factory=AffordanceDistribution)
    risks: List[ActionRisk] = field(default_factory=list)
    attention: Optional[AttentionSubgraph] = None
    report: SceneUnderstandingReport = field(default_factory=SceneUnderstandingReport)
    source_patch_id: Optional[str] = None
    app: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "regions": [r.to_dict() for r in self.regions],
            "context_graph": self.context_graph.to_dict(),
            "memberships": [m.to_dict() for m in self.memberships],
            "affordances": self.affordances.to_dict(),
            "risks": [r.to_dict() for r in self.risks],
            "attention": None if self.attention is None else self.attention.to_dict(),
            "report": self.report.to_dict(),
            "source_patch_id": self.source_patch_id,
            "app": self.app,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "WorldGraph":
        attn_raw = d.get("attention")
        return cls(
            regions=[SemanticRegion.from_dict(x) for x in (d.get("regions") or [])],
            context_graph=ContextGraph.from_dict(d.get("context_graph") or {}),
            memberships=[RegionMembership.from_dict(x) for x in (d.get("memberships") or [])],
            affordances=AffordanceDistribution.from_dict(d.get("affordances") or {}),
            risks=[ActionRisk.from_dict(x) for x in (d.get("risks") or [])],
            attention=None if attn_raw is None else AttentionSubgraph.from_dict(attn_raw),
            report=SceneUnderstandingReport.from_dict(d.get("report") or {}),
            source_patch_id=d.get("source_patch_id"),
            app=str(d.get("app") or ""),
        )
