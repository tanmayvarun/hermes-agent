"""Generic SEARCH applicability — belief → epistemic meta-action.

Rule (domain-neutral):

    known target criteria
    + target unresolved (not visible / not selected)
    + searchable scope available in the relevant surface
    → SEARCH

Do not special-case WhatsApp Forward. Destination pickers, Finder, Gmail,
Settings, and find-in-page all share this shape.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence


PICKER_SURFACES = frozenset({"forward_picker", "destination_picker"})
_SEARCH_KINDS = frozenset(
    {
        "search_field",
        "search_input",
        "search_bar",
        "text_field",
        "textfield",
        "field",
    }
)


@dataclass
class EntityResolutionGap:
    """Blocking uncertainty: where is the sought entity inside the current scope?"""

    entity_type: str = "entity"
    desired_identity: str = ""
    current_scope: str = ""
    visible_match: bool = False
    selected: bool = False
    search_capability_available: bool = False
    criteria_sufficient: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @property
    def entity_not_currently_resolved(self) -> bool:
        return bool(self.desired_identity) and not self.selected and not self.visible_match

    @property
    def search_is_applicable(self) -> bool:
        return (
            bool(self.desired_identity)
            and bool(self.criteria_sufficient)
            and self.entity_not_currently_resolved
            and bool(self.search_capability_available)
            and bool(self.current_scope)
        )


@dataclass
class SearchOpportunity:
    scope: str = ""
    search_field: str = ""
    searchable_entity_type: str = "entity"
    query_supported: bool = True
    grounding_confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SearchApplicability:
    """Result of evaluating the generic SEARCH rule against world evidence."""

    applicable: bool = False
    gap: Optional[EntityResolutionGap] = None
    opportunities: List[SearchOpportunity] = field(default_factory=list)
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "applicable": self.applicable,
            "gap": self.gap.to_dict() if self.gap else None,
            "opportunities": [o.to_dict() for o in self.opportunities[:6]],
            "reason": self.reason,
        }


def search_is_applicable(gap: Optional[EntityResolutionGap]) -> bool:
    return bool(gap is not None and gap.search_is_applicable)


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _surface_candidates(execution_state: Any, doc: Dict[str, Any]) -> List[str]:
    """Prefer lagging-doc-independent surface evidence (live 203259 lag)."""
    out: List[str] = []
    for raw in (
        doc.get("surface"),
        getattr(execution_state, "last_accepted_surface", None) if execution_state else None,
        getattr(execution_state, "accepted_surface", None) if execution_state else None,
    ):
        s = _norm(raw)
        if s and s not in out:
            out.append(s)
    for layer in doc.get("layers") or []:
        if not isinstance(layer, dict):
            continue
        s = _norm(layer.get("surface") or layer.get("name") or layer.get("kind"))
        if s and s not in out:
            out.append(s)
    hints = getattr(execution_state, "overlay_hints", None) if execution_state else None
    if isinstance(hints, dict):
        s = _norm(hints.get("active_interaction_surface") or hints.get("surface"))
        if s and s not in out:
            out.append(s)
    uni = getattr(execution_state, "last_unified_proposal", None) if execution_state else None
    if isinstance(uni, dict):
        s = _norm(uni.get("surface"))
        if s and s not in out:
            out.append(s)
    return out


def _foreground_picker_surface(surfaces: Sequence[str]) -> str:
    for s in surfaces:
        if s in PICKER_SURFACES:
            return s
    return ""


def collect_search_opportunities(
    doc: Dict[str, Any],
    *,
    scope: str = "",
    entity_type: str = "contact",
    execution_state: Any = None,
) -> List[SearchOpportunity]:
    """Surface scoped search facilities from inventory / chrome / AX stash."""
    if isinstance(doc.get("search_opportunities"), list):
        parsed: List[SearchOpportunity] = []
        for raw in doc.get("search_opportunities") or []:
            if not isinstance(raw, dict):
                continue
            parsed.append(
                SearchOpportunity(
                    scope=str(raw.get("scope") or scope or "")[:64],
                    search_field=str(raw.get("search_field") or "")[:80],
                    searchable_entity_type=str(
                        raw.get("searchable_entity_type") or entity_type
                    )[:40],
                    query_supported=bool(raw.get("query_supported", True)),
                    grounding_confidence=float(raw.get("grounding_confidence") or 0.0),
                )
            )
        if parsed:
            return parsed[:6]

    ops: List[SearchOpportunity] = []
    surf = scope or _norm(doc.get("surface"))
    for obj in doc.get("objects") or []:
        if not isinstance(obj, dict):
            continue
        text = _norm(obj.get("text") or obj.get("label"))
        kind = _norm(obj.get("kind") or obj.get("semantic_role") or obj.get("role"))
        role = _norm(obj.get("field_role") or obj.get("focused_field_role"))
        is_search = (
            kind in _SEARCH_KINDS
            or "search" in kind
            or "search" in text
            or role in {"destination_filter", "sidebar_search", "in_chat_find", "filter"}
        )
        if not is_search:
            continue
        conf = 0.9
        if obj.get("point") or obj.get("target_point") or obj.get("bounds"):
            conf = 0.98
        ops.append(
            SearchOpportunity(
                scope=surf or "application_ui",
                search_field=str(obj.get("id") or obj.get("label") or text or "search")[:80],
                searchable_entity_type=entity_type,
                query_supported=True,
                grounding_confidence=conf,
            )
        )
    # AX/OCR may have grounded a filter site even when VLM omitted the row.
    if not ops and execution_state is not None:
        stashed = getattr(execution_state, "last_filter_geometry", None)
        if isinstance(stashed, dict) and (
            stashed.get("target_point") is not None or stashed.get("bounds")
        ):
            ops.append(
                SearchOpportunity(
                    scope=surf or "application_ui",
                    search_field=str(stashed.get("target_label") or "search")[:80],
                    searchable_entity_type=entity_type,
                    query_supported=True,
                    grounding_confidence=0.95,
                )
            )
    role = _norm(
        (
            getattr(execution_state, "focused_field_role", None)
            if execution_state is not None
            else None
        )
        or doc.get("focused_field_role")
    )
    if not ops and role in {"destination_filter", "sidebar_search", "in_chat_find"}:
        ops.append(
            SearchOpportunity(
                scope=surf or "application_ui",
                search_field=role,
                searchable_entity_type=entity_type,
                query_supported=True,
                grounding_confidence=0.9,
            )
        )
    return ops[:6]


def _destination_identity(execution_state: Any, doc: Dict[str, Any]) -> str:
    goal = getattr(execution_state, "goal", None) if execution_state else None
    dest = str(getattr(goal, "target_contact", "") or "").strip()
    if dest:
        return dest
    ft = None
    hints = getattr(execution_state, "overlay_hints", None) if execution_state else None
    if isinstance(hints, dict):
        ft = hints.get("forward_task")
    if not isinstance(ft, dict) and isinstance(doc.get("forward_task"), dict):
        ft = doc.get("forward_task")
    if isinstance(ft, dict):
        return str(ft.get("destination") or ft.get("target_contact") or "").strip()
    return ""


def _selection_flags(
    doc: Dict[str, Any],
    identity: str,
    *,
    execution_state: Any = None,
) -> tuple[bool, bool]:
    """Return (visible_match, selected) for the sought identity in scope."""
    dest_l = _norm(identity)
    if not dest_l:
        return False, False
    visible = False
    selected = False
    ft = None
    hints = getattr(execution_state, "overlay_hints", None) if execution_state else None
    if isinstance(hints, dict):
        ft = hints.get("forward_task")
    if not isinstance(ft, dict) and isinstance(doc.get("forward_task"), dict):
        ft = doc.get("forward_task")
    preds = ft.get("predicates") if isinstance(ft, dict) and isinstance(ft.get("predicates"), dict) else {}
    if preds.get("destination_selected"):
        return True, True
    if preds.get("destination_visible") is True:
        visible = True
    for obj in doc.get("objects") or []:
        if not isinstance(obj, dict):
            continue
        text = _norm(obj.get("text") or obj.get("label"))
        if not text:
            continue
        if dest_l in text or text in dest_l:
            visible = True
            if bool(obj.get("selected")) or bool(obj.get("matches_goal")):
                selected = True
                break
    return visible, selected


def evaluate_entity_resolution_search(
    execution_state: Any,
    *,
    entity_type: str = "contact",
    identity: str = "",
    require_picker_scope: bool = True,
) -> SearchApplicability:
    """Evaluate whether SEARCH is the correct meta-action for an entity gap."""
    if execution_state is None:
        return SearchApplicability(reason="no_execution_state")
    doc = getattr(execution_state, "unified_world_document", None)
    if not isinstance(doc, dict):
        doc = {}
    sought = (identity or _destination_identity(execution_state, doc)).strip()
    if not sought:
        return SearchApplicability(reason="criteria_unknown")

    surfaces = _surface_candidates(execution_state, doc)
    scope = _foreground_picker_surface(surfaces)
    if require_picker_scope and not scope:
        # Still allow when document itself claims a picker via forward_task.
        ft = doc.get("forward_task") if isinstance(doc.get("forward_task"), dict) else None
        if isinstance(ft, dict) and ft.get("predicates", {}).get("destination_picker_visible"):
            scope = "forward_picker"
        else:
            return SearchApplicability(reason="scope_not_searchable_picker")

    if not scope:
        scope = surfaces[0] if surfaces else _norm(doc.get("surface")) or "application_ui"

    visible, selected = _selection_flags(doc, sought, execution_state=execution_state)
    opportunities = collect_search_opportunities(
        doc, scope=scope, entity_type=entity_type, execution_state=execution_state
    )
    searchable = any(o.query_supported for o in opportunities)
    gap = EntityResolutionGap(
        entity_type=entity_type,
        desired_identity=sought,
        current_scope=scope,
        visible_match=visible,
        selected=selected,
        search_capability_available=searchable,
        criteria_sufficient=True,
    )
    if selected:
        return SearchApplicability(
            applicable=False,
            gap=gap,
            opportunities=opportunities,
            reason="entity_already_selected",
        )
    if visible:
        return SearchApplicability(
            applicable=False,
            gap=gap,
            opportunities=opportunities,
            reason="entity_visible_act_select",
        )
    if not searchable:
        return SearchApplicability(
            applicable=False,
            gap=gap,
            opportunities=opportunities,
            reason="no_search_facility",
        )
    return SearchApplicability(
        applicable=True,
        gap=gap,
        opportunities=opportunities,
        reason="unresolved_entity_with_searchable_scope",
    )


def entity_resolution_search_needed(execution_state: Any) -> bool:
    """True when the generic SEARCH rule applies for the goal destination."""
    try:
        return bool(evaluate_entity_resolution_search(execution_state).applicable)
    except Exception:
        return False


def attach_search_opportunities(execution_state: Any) -> List[Dict[str, Any]]:
    """Write ``search_opportunities`` onto the world document when missing."""
    if execution_state is None:
        return []
    doc = getattr(execution_state, "unified_world_document", None)
    if not isinstance(doc, dict):
        return []
    eval_result = evaluate_entity_resolution_search(execution_state)
    ops = [o.to_dict() for o in eval_result.opportunities]
    if ops and not doc.get("search_opportunities"):
        try:
            doc = dict(doc)
            doc["search_opportunities"] = ops
            execution_state.unified_world_document = doc
        except Exception:
            pass
    if eval_result.gap is not None:
        try:
            execution_state.last_entity_resolution_gap = eval_result.gap.to_dict()
        except Exception:
            pass
    return ops


def type_query_for_gap(gap: Optional[EntityResolutionGap]) -> str:
    """Concrete query text realizing SEARCH for an entity-resolution gap."""
    if gap is None:
        return ""
    return str(gap.desired_identity or "").strip()
