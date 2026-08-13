"""Evidence-driven task bindings — object args before relational ops.

Phase strings for forward are a *view* of predicates, not a driver.
Never advance because an action was attempted; advance only when the world
proves the required predicates.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Literal, Optional, Sequence

BindingStatus = Literal[
    "unresolved",
    "ambiguous",
    "provisional",
    "confirmed",
    "invalidated",
]


@dataclass
class TaskBinding:
    name: str
    constraints: Dict[str, Any] = field(default_factory=dict)
    candidate_entity_ids: List[int] = field(default_factory=list)
    resolved_entity_id: Optional[int] = None
    # Identity label when semantic commit has no persistent entity handle yet.
    resolved_label: str = ""
    confidence: float = 0.0
    status: BindingStatus = "unresolved"
    evidence: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TaskBinding":
        return cls(
            name=str(d.get("name") or ""),
            constraints=dict(d.get("constraints") or {}),
            candidate_entity_ids=[int(x) for x in (d.get("candidate_entity_ids") or [])],
            resolved_entity_id=(
                int(d["resolved_entity_id"]) if d.get("resolved_entity_id") is not None else None
            ),
            resolved_label=str(d.get("resolved_label") or ""),
            confidence=float(d.get("confidence") or 0.0),
            status=str(d.get("status") or "unresolved"),  # type: ignore[arg-type]
            evidence=[str(x) for x in (d.get("evidence") or [])],
        )

    @property
    def is_identity_established(self) -> bool:
        """Semantic identity committed (entity handle and/or authoritative label)."""
        if self.status not in {"provisional", "confirmed"}:
            return False
        return self.resolved_entity_id is not None or bool(
            str(self.resolved_label or "").strip()
        )

    @property
    def is_grounded(self) -> bool:
        """Persistent/usable entity handle exists — required for irreversible acts."""
        return (
            self.status in {"provisional", "confirmed"}
            and self.resolved_entity_id is not None
        )


@dataclass
class ForwardPredicates:
    source_conversation_open: bool = False
    source_conversation_visible: bool = False
    source_object_visible: bool = False
    source_object_selected: bool = False
    forward_surface_open: bool = False
    destination_picker_visible: bool = False
    destination_selected: bool = False
    forward_completed: bool = False

    def to_dict(self) -> Dict[str, bool]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ForwardPredicates":
        return cls(
            source_conversation_open=bool(d.get("source_conversation_open")),
            source_conversation_visible=bool(d.get("source_conversation_visible")),
            source_object_visible=bool(d.get("source_object_visible")),
            source_object_selected=bool(d.get("source_object_selected")),
            forward_surface_open=bool(d.get("forward_surface_open")),
            destination_picker_visible=bool(d.get("destination_picker_visible")),
            destination_selected=bool(d.get("destination_selected")),
            forward_completed=bool(d.get("forward_completed")),
        )


@dataclass
class ForwardTaskState:
    """Bindings + predicates for whatsapp_forward_message."""

    bindings: Dict[str, TaskBinding] = field(default_factory=dict)
    predicates: ForwardPredicates = field(default_factory=ForwardPredicates)
    local_objective: str = ""
    derived_phase: str = "OPEN_SOURCE"
    # Soft flags for controller / value
    suppress_observe: bool = False
    binding_repair: bool = False

    def binding(self, name: str) -> TaskBinding:
        if name not in self.bindings:
            self.bindings[name] = TaskBinding(name=name)
        return self.bindings[name]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "bindings": {k: v.to_dict() for k, v in self.bindings.items()},
            "predicates": self.predicates.to_dict(),
            "local_objective": self.local_objective,
            "derived_phase": self.derived_phase,
            "suppress_observe": self.suppress_observe,
            "binding_repair": self.binding_repair,
        }

    @classmethod
    def from_dict(cls, d: Optional[Dict[str, Any]]) -> "ForwardTaskState":
        if not d:
            return cls()
        bindings = {
            k: TaskBinding.from_dict(v) if isinstance(v, dict) else TaskBinding(name=k)
            for k, v in (d.get("bindings") or {}).items()
        }
        preds = d.get("predicates") or {}
        return cls(
            bindings=bindings,
            predicates=ForwardPredicates.from_dict(preds if isinstance(preds, dict) else {}),
            local_objective=str(d.get("local_objective") or ""),
            derived_phase=str(d.get("derived_phase") or "OPEN_SOURCE"),
            suppress_observe=bool(d.get("suppress_observe")),
            binding_repair=bool(d.get("binding_repair")),
        )

    def invalidate_downstream_of(self, name: str) -> None:
        """When an upstream binding fails, clear dependent provisional state."""
        order = [
            "source_conversation",
            "source_object",
            "destination",
        ]
        if name not in order:
            return
        idx = order.index(name)
        for downstream in order[idx + 1 :]:
            b = self.binding(downstream)
            if b.status in {"provisional", "confirmed", "ambiguous"}:
                b.status = "invalidated"
                b.resolved_entity_id = None
                b.confidence = 0.0
                b.evidence.append(f"invalidated_after:{name}")
        if name in {"source_conversation", "source_object"}:
            self.predicates.source_object_selected = False
            self.predicates.forward_surface_open = False
            self.predicates.destination_picker_visible = False
            self.predicates.destination_selected = False

    def do_not_advance(self, effect: str, detail: str = "") -> None:
        """Explicitly refuse to mark a predicate true after a failed transition."""
        if hasattr(self.predicates, effect):
            setattr(self.predicates, effect, False)
        self.binding_repair = True
        self.local_objective = detail or f"repair after failed {effect}"

    def derive_phase(self, *, leftover: bool) -> str:
        """Phase is a view of predicates — never of attempted actions."""
        p = self.predicates
        if leftover:
            self.derived_phase = "PRECLEAR"
            self.local_objective = "clear leftover call chrome"
            return self.derived_phase
        if p.forward_completed:
            self.derived_phase = "DONE"
            self.local_objective = "forward completed"
            return self.derived_phase
        # PICK_DEST only when the real destination picker is visible.
        if p.destination_picker_visible:
            self.derived_phase = "PICK_DEST"
            self.local_objective = "select forward destination"
            return self.derived_phase
        if not p.source_conversation_open:
            self.derived_phase = "OPEN_SOURCE"
            self.local_objective = (
                "open source conversation"
                if not p.source_conversation_visible
                else "open visible source conversation"
            )
            return self.derived_phase
        src_obj = self.binding("source_object")
        # Once the source object is selected, keep the binding alive across occlusion.
        if src_obj.is_grounded and p.source_object_selected:
            self.derived_phase = "OPEN_FORWARD"
            self.local_objective = "invoke Forward on bound source object"
            return self.derived_phase
        if p.source_object_visible and src_obj.status in {"provisional", "ambiguous", "confirmed"}:
            # Visible match but not selected yet — still find/select
            self.derived_phase = "OPEN_FORWARD" if src_obj.is_grounded else "FIND_LINK"
            self.local_objective = "select source object matching query"
            return self.derived_phase
        self.derived_phase = "FIND_LINK"
        self.local_objective = "resolve source object matching query"
        return self.derived_phase

    def consistency_rollback(self) -> None:
        """If derived phase implies surfaces that are absent, roll back predicates."""
        p = self.predicates
        if self.derived_phase == "PICK_DEST" and not p.destination_picker_visible:
            p.destination_picker_visible = False
            p.forward_surface_open = False
            self.binding_repair = True
            self.derive_phase(leftover=False)


def find_query_entities(
    entities: Sequence[Any],
    query: str,
    *,
    in_sidebar_fn: Any = None,
    allowed_entity_types: Optional[Sequence[str]] = None,
) -> List[Any]:
    """Entities whose label/desc contain query, excluding sidebar when possible."""
    q = (query or "").strip().lower()
    if not q:
        return []
    compact_q = re.sub(r"[^a-z0-9]+", "", q)
    query_tokens = [t for t in re.split(r"[^a-z0-9]+", q) if t]
    allowed = {str(t).strip().lower() for t in (allowed_entity_types or []) if str(t).strip()}
    ents = [e for e in entities if getattr(e, "visible", True)]
    scored: List[tuple[float, Any]] = []
    for e in ents:
        if in_sidebar_fn is not None:
            try:
                if in_sidebar_fn(e, ents):
                    continue
            except Exception:
                pass
        lab = f"{getattr(e, 'label', '') or ''} {getattr(e, 'semantic_role', '') or ''}"
        attrs = getattr(e, "attributes", None) or {}
        desc = str(attrs.get("description") or "")
        blob = f"{lab} {desc}".lower()
        compact_blob = re.sub(r"[^a-z0-9]+", "", blob)
        token_blob = [t for t in re.split(r"[^a-z0-9]+", blob) if t]
        fuzzy_hit = False
        if q in blob or (compact_q and compact_q in compact_blob):
            fuzzy_hit = True
        elif compact_q and len(compact_q) >= 4:
            if any(SequenceMatcher(None, compact_q, tok).ratio() >= 0.84 for tok in token_blob):
                fuzzy_hit = True
            elif query_tokens and all(
                any(SequenceMatcher(None, qt, tok).ratio() >= 0.84 for tok in token_blob)
                for qt in query_tokens
            ):
                fuzzy_hit = True
        if not fuzzy_hit:
            continue
        etype = str(getattr(e, "entity_type", "") or "").lower()
        if allowed and etype and etype not in allowed:
            # Keep a soft escape hatch for rows whose AX type is weakly normalized.
            if not any(token in {"message", "link", "static", "cell"} for token in allowed):
                continue
        score = 0.0
        if etype == "link":
            score += 4.0
        elif etype in {"message", "static", "cell"}:
            score += 2.0
        elif etype in {"button", "textfield"}:
            score += 0.5
        elif etype in {"photo", "image"}:
            score -= 2.5
        elif etype in {"group", "window", "unknown"}:
            score -= 3.0
        if "http://" in blob or "https://" in blob:
            score += 2.5
        if "link" in blob:
            score += 1.5
        if "message" in blob:
            score += 1.0
        if q in lab.lower():
            score += 1.0
        if compact_q and compact_q in re.sub(r"[^a-z0-9]+", "", lab.lower()):
            score += 0.75
        scored.append((score, e))
    scored.sort(key=lambda pair: (-pair[0], len(str(getattr(pair[1], "label", "") or ""))))
    return [e for _, e in scored]


def source_object_latently_selected(state: "ForwardTaskState") -> bool:
    """True when the source object should remain believed selected even if occluded."""
    src_obj = state.binding("source_object")
    return bool(state.predicates.source_object_selected and src_obj.is_grounded)


def picker_chrome_visible(world_entities: Sequence[Any]) -> bool:
    """Destination picker surface — stricter than a lone Forward CTA."""
    picker_labels = {
        "send to",
        "select chats",
        "select chat",
        "forward to",
        "search name or number",
    }
    for e in world_entities:
        if not getattr(e, "visible", True):
            continue
        lab = (getattr(e, "label", None) or getattr(e, "semantic_role", None) or "").strip().lower()
        if lab in picker_labels:
            return True
        desc = str((getattr(e, "attributes", None) or {}).get("description") or "").strip().lower()
        if desc in picker_labels:
            return True
    return False
