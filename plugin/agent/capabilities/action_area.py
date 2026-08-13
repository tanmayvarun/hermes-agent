"""Action-area contracts: bind each capability to the UI region it may actuate.

App-agnostic. WhatsApp Search vs chat composer is one instance of a general
rule: a capability must land in its *action area*. High error-cost families
(typing a query into the wrong field, irreversible commits) refuse when the
bound object/label is outside that area — even if earlier stages latched a
matches_goal row or a mid-pane CTA point.

Live 095344: compose_search_query latched a contact and typed into a chat
composer. The motor must never write on that grounding.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, FrozenSet, Optional, Tuple


class ActionArea(str, Enum):
    """Logical region a capability is allowed to actuate."""

    FILTER_INPUT = "filter_input"  # search / find / destination filter field
    CONTENT_OBJECT = "content_object"  # message, link, attachment in open surface
    CANDIDATE_ROW = "candidate_row"  # contact / chat / picker row
    AFFORDANCE = "affordance"  # named control on a bound entity
    TRANSIENT = "transient"  # dismiss overlays
    ANY = "any"


class ErrorCost(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"  # wrong write is costly / hard to undo (typed query in chat)
    IRREVERSIBLE = "irreversible"


FILTER_KINDS: FrozenSet[str] = frozenset(
    {"text_field", "search_field", "search_input", "search_bar", "field"}
)
CONTENT_KINDS: FrozenSet[str] = frozenset(
    {
        "message",
        "message_bubble",
        "message_link_preview",
        "link",
        "attachment",
        "media",
        "image",
        "video",
        "audio",
        "document",
    }
)
CANDIDATE_KINDS: FrozenSet[str] = frozenset(
    {"contact_row", "contact", "entity", "chat_row", "row", "search_result_row"}
)
COMPOSER_KINDS: FrozenSet[str] = frozenset(
    {"composer", "message_composer", "chat_composer", "textarea"}
)

_FILTER_LABEL_TOKENS: FrozenSet[str] = frozenset({"search", "find", "filter"})
_COMPOSER_LABEL_TOKENS: FrozenSet[str] = frozenset(
    {"type a message", "write a message", "message", "compose", "write a"}
)


@dataclass(frozen=True)
class ActionAreaContract:
    """Where a capability may land, and how hard we refuse a miss."""

    area: ActionArea
    error_cost: ErrorCost
    # When True, never fall through to matches_goal / name match outside area.
    exclusive: bool = False
    allowed_kinds: FrozenSet[str] = frozenset()
    forbidden_kinds: FrozenSet[str] = frozenset()
    # Default control name for into= / target_label when retargeting.
    canonical_label: str = ""


# Capability / family → action area. Extra motor aliases included.
_CONTRACTS: Dict[str, ActionAreaContract] = {
    "compose_search_query": ActionAreaContract(
        area=ActionArea.FILTER_INPUT,
        error_cost=ErrorCost.HIGH,
        exclusive=True,
        allowed_kinds=FILTER_KINDS,
        forbidden_kinds=CANDIDATE_KINDS | CONTENT_KINDS | COMPOSER_KINDS,
        canonical_label="Search",
    ),
    "type_query": ActionAreaContract(
        area=ActionArea.FILTER_INPUT,
        error_cost=ErrorCost.HIGH,
        exclusive=True,
        allowed_kinds=FILTER_KINDS,
        forbidden_kinds=CANDIDATE_KINDS | CONTENT_KINDS | COMPOSER_KINDS,
        canonical_label="Search",
    ),
    "locate_content": ActionAreaContract(
        area=ActionArea.FILTER_INPUT,
        error_cost=ErrorCost.HIGH,
        exclusive=True,
        allowed_kinds=FILTER_KINDS,
        forbidden_kinds=CANDIDATE_KINDS | CONTENT_KINDS | COMPOSER_KINDS,
        canonical_label="Search",
    ),
    "open_search": ActionAreaContract(
        area=ActionArea.FILTER_INPUT,
        error_cost=ErrorCost.HIGH,
        exclusive=True,
        allowed_kinds=FILTER_KINDS,
        forbidden_kinds=CANDIDATE_KINDS | CONTENT_KINDS | COMPOSER_KINDS,
        canonical_label="Search",
    ),
    "reveal_actions": ActionAreaContract(
        area=ActionArea.CONTENT_OBJECT,
        error_cost=ErrorCost.MEDIUM,
        exclusive=False,
        allowed_kinds=CONTENT_KINDS,
        # Composer / draft text is not a message patient (live 181132 spellcheck).
        forbidden_kinds=frozenset(
            {"search_result_row", "search_panel", "chat_row"}
        )
        | COMPOSER_KINDS,
    ),
    "select_content": ActionAreaContract(
        area=ActionArea.CONTENT_OBJECT,
        error_cost=ErrorCost.MEDIUM,
        exclusive=False,
        allowed_kinds=CONTENT_KINDS,
        forbidden_kinds=frozenset(
            {"search_result_row", "search_panel", "chat_row"}
        )
        | COMPOSER_KINDS,
    ),
    "resolve_entity": ActionAreaContract(
        area=ActionArea.CANDIDATE_ROW,
        error_cost=ErrorCost.MEDIUM,
        exclusive=False,
        allowed_kinds=CANDIDATE_KINDS,
        forbidden_kinds=CONTENT_KINDS | COMPOSER_KINDS,
    ),
    "open_entity": ActionAreaContract(
        area=ActionArea.CANDIDATE_ROW,
        error_cost=ErrorCost.MEDIUM,
        exclusive=False,
        allowed_kinds=CANDIDATE_KINDS,
        forbidden_kinds=CONTENT_KINDS | COMPOSER_KINDS,
    ),
    "open_contact": ActionAreaContract(
        area=ActionArea.CANDIDATE_ROW,
        error_cost=ErrorCost.MEDIUM,
        exclusive=False,
        allowed_kinds=CANDIDATE_KINDS,
        forbidden_kinds=CONTENT_KINDS | COMPOSER_KINDS,
    ),
    "invoke_affordance": ActionAreaContract(
        area=ActionArea.AFFORDANCE,
        error_cost=ErrorCost.MEDIUM,
        exclusive=False,
        allowed_kinds=frozenset({"button", "affordance", "menu_item", "control"}),
        forbidden_kinds=frozenset(),
    ),
    "commit_irreversible": ActionAreaContract(
        area=ActionArea.AFFORDANCE,
        error_cost=ErrorCost.IRREVERSIBLE,
        exclusive=True,
        allowed_kinds=frozenset({"button", "affordance", "menu_item", "control"}),
        forbidden_kinds=FILTER_KINDS | COMPOSER_KINDS | CONTENT_KINDS,
    ),
    "dismiss_transient": ActionAreaContract(
        area=ActionArea.TRANSIENT,
        error_cost=ErrorCost.LOW,
        exclusive=False,
    ),
}


def _norm_cap(capability: str) -> str:
    return str(capability or "").strip().lower().replace("-", "_")


def contract_for(capability: str) -> Optional[ActionAreaContract]:
    return _CONTRACTS.get(_norm_cap(capability))


def is_high_cost(capability: str) -> bool:
    c = contract_for(capability)
    return bool(c and c.error_cost in {ErrorCost.HIGH, ErrorCost.IRREVERSIBLE})


def exclusive_area(capability: str) -> bool:
    c = contract_for(capability)
    return bool(c and c.exclusive)


def _blob(obj: Dict[str, Any]) -> str:
    return " ".join(
        str(obj.get(k) or "") for k in ("text", "label", "id", "kind", "role")
    ).lower()


def label_looks_like_filter(label: str) -> bool:
    low = str(label or "").strip().lower()
    if not low:
        return False
    if any(tok in low for tok in _COMPOSER_LABEL_TOKENS):
        if not any(tok in low for tok in _FILTER_LABEL_TOKENS):
            return False
    return any(tok in low for tok in _FILTER_LABEL_TOKENS)


def label_looks_like_composer(label: str) -> bool:
    low = str(label or "").strip().lower()
    if not low:
        return False
    if any(tok in low for tok in _FILTER_LABEL_TOKENS):
        return False
    return any(tok in low for tok in _COMPOSER_LABEL_TOKENS)


def object_matches_area(obj: Optional[Dict[str, Any]], contract: ActionAreaContract) -> bool:
    """True when a perceived object is a legal landing site for the contract."""
    if obj is None or not isinstance(obj, dict):
        return False
    kind = str(obj.get("kind") or "").strip().lower()
    blob = _blob(obj)
    if kind and kind in contract.forbidden_kinds:
        return False
    if contract.area == ActionArea.FILTER_INPUT:
        if label_looks_like_composer(blob):
            return False
        if kind in contract.allowed_kinds:
            return True
        return any(tok in blob for tok in _FILTER_LABEL_TOKENS)
    if contract.allowed_kinds:
        if kind in contract.allowed_kinds:
            return True
        if contract.area == ActionArea.CONTENT_OBJECT and (
            "message" in kind or "link" in kind
        ):
            return True
        return False
    return True


def kind_matches_area(kind: str, capability: str) -> bool:
    c = contract_for(capability)
    if c is None:
        return True
    return object_matches_area({"kind": kind, "text": ""}, c)


def validate_actuation_grounding(
    *,
    capability: str,
    field_role: str = "",
    label: str = "",
    target_kind: str = "",
) -> Tuple[bool, str]:
    """Pre-motor gate: refuse high-cost acts on the wrong action area.

    Returns ``(ok, why)``. ``why`` is stable for goldens
    (``wrong_action_area:<area>:…``).
    """
    cap = _norm_cap(capability)
    role = str(field_role or "").strip().lower()
    c = contract_for(cap)
    if c is None and role in {"sidebar_search", "destination_filter", "in_chat_find"}:
        c = _CONTRACTS["type_query"]
    if c is None:
        return True, "ok"

    kind = str(target_kind or "").strip().lower()
    lab = str(label or "").strip()

    if kind:
        probe = {"kind": kind, "text": lab, "label": lab}
        if not object_matches_area(probe, c):
            if c.error_cost in {ErrorCost.HIGH, ErrorCost.IRREVERSIBLE}:
                return False, f"wrong_action_area:{c.area.value}:kind={kind}"
            return False, f"wrong_action_area:{c.area.value}:kind={kind}"

    if role in {"composer", "message_composer", "chat_composer", "message_input"}:
        if c.area in {ActionArea.FILTER_INPUT, ActionArea.CONTENT_OBJECT}:
            return False, f"wrong_action_area:{c.area.value}:focused_composer"

    if c.area == ActionArea.FILTER_INPUT:
        # HIGH-cost filter families: empty role+kind with no filter label must
        # not reach the host (fail closed — live composer mistype class).
        if c.error_cost in {ErrorCost.HIGH, ErrorCost.IRREVERSIBLE}:
            filter_roles = {"in_chat_find", "sidebar_search", "destination_filter"}
            role_ok = role in filter_roles
            if (
                not role_ok
                and not kind
                and not label_looks_like_filter(lab)
            ):
                return False, f"wrong_action_area:{c.area.value}:empty_kind"
        if label_looks_like_composer(lab):
            return False, f"wrong_action_area:{c.area.value}:composer_label"
        # Contact / entity name as the field label — not a filter control.
        if lab and not label_looks_like_filter(lab):
            if c.error_cost in {ErrorCost.HIGH, ErrorCost.IRREVERSIBLE}:
                # Empty / rewritten labels are handled upstream; a leftover
                # entity token as into= must not reach the host.
                if kind in CANDIDATE_KINDS or kind in COMPOSER_KINDS:
                    return False, f"wrong_action_area:{c.area.value}:entity_label"
                if kind:
                    return False, f"wrong_action_area:{c.area.value}:label={lab!r}"

    if c.area == ActionArea.CONTENT_OBJECT:
        if label_looks_like_composer(lab) or kind in COMPOSER_KINDS:
            return False, f"wrong_action_area:{c.area.value}:composer"
        # Plain query echo in the message box is not a content patient
        # (live 181132: context-click 'zarooratwala lasawel' → spellcheck).
        if lab and kind in {"", "text", "static", "label", "unknown"}:
            low = lab.lower()
            if any(tok in low for tok in _COMPOSER_LABEL_TOKENS):
                return False, f"wrong_action_area:{c.area.value}:composer_label"

    return True, "ok"


def filter_field_families() -> FrozenSet[str]:
    """Capabilities whose exclusive action area is a filter input."""
    return frozenset(
        name
        for name, c in _CONTRACTS.items()
        if c.area == ActionArea.FILTER_INPUT and c.exclusive
    )
