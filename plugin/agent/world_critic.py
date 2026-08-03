"""World-model critic: propose/review residual updates to the carried document.

The multimodal perceptor does heavy sensor fusion and *proposes* a world
document. This module accepts or rejects structural deltas against the prior
accepted document, last runtime result, and a small navigation graph.

It is intentionally mostly rule/structure based. Soft content hypotheses can
pass through; illegal surface / field-role jumps cannot quietly rewrite the
document that remaps and motors will obey.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set

# Closed surface vocabulary (must stay aligned with unified_cognition).
CANONICAL_SURFACES: Set[str] = {
    "chat_list",
    "conversation",
    "search",
    "context_menu",
    "forward_picker",
    "dialog",
    "blank",
}

# Parent / predecessor surfaces that may legally lead to a child.
# Missing edge ⇒ critic keeps the prior surface unless last action explains it.
SURFACE_PARENTS: Dict[str, Set[str]] = {
    "chat_list": {"blank", "conversation", "search", "dialog", "chat_list"},
    "search": {"chat_list", "conversation", "search", "blank"},
    "conversation": {"chat_list", "search", "conversation", "dialog", "forward_picker"},
    "context_menu": {"conversation"},
    "forward_picker": {"context_menu", "conversation", "dialog", "forward_picker"},
    "dialog": {
        "conversation",
        "chat_list",
        "search",
        "forward_picker",
        "context_menu",
        "dialog",
    },
    "blank": set(CANONICAL_SURFACES),
}

# Actions that justify landing on a surface even without a parent edge.
ACTION_OPENS_SURFACE: Dict[str, Set[str]] = {
    "forward_picker": {
        "invoke_affordance",
        "forward_message",
        "reveal_actions",
        "resolve_entity",
        "open_entity",
        "type_query",
    },
    "context_menu": {"reveal_actions", "context_click"},
    "search": {"type_query", "compose_search_query", "open_search", "open_entity"},
    "conversation": {"open_entity", "open_contact", "locate_content", "select_content"},
    "dialog": {"invoke_affordance", "commit_irreversible", "click"},
}

# Focused editable field role implied by surface when the model omits it.
SURFACE_FIELD_ROLE: Dict[str, str] = {
    "forward_picker": "destination_filter",
    "search": "sidebar_search",
    "chat_list": "sidebar_search",
    "conversation": "in_chat_or_composer",
    "context_menu": "none",
    "dialog": "dialog_field",
    "blank": "none",
}

# Surfaces where sidebar Cmd+F / source compose+type remaps are illegal.
NO_SIDEBAR_SEARCH_SURFACES: Set[str] = {
    "forward_picker",
    "context_menu",
    "dialog",
}

SIDEBAR_SEARCH_ROLES: Set[str] = {"sidebar_search"}


@dataclass
class CriticDecision:
    field: str
    verdict: str  # accept | reject | edit
    reason: str
    prior: Any = None
    proposed: Any = None
    accepted: Any = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field": self.field,
            "verdict": self.verdict,
            "reason": self.reason,
            "prior": self.prior,
            "proposed": self.proposed,
            "accepted": self.accepted,
        }


@dataclass
class CriticVerdict:
    """Residual merge of a perceptor proposal into the accepted world document."""

    accepted_document: Dict[str, Any]
    decisions: List[CriticDecision] = field(default_factory=list)
    focused_field_role: str = "none"
    surface: str = ""
    forbid_sidebar_search_motor: bool = False
    forbid_source_compose_remap: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "surface": self.surface,
            "focused_field_role": self.focused_field_role,
            "forbid_sidebar_search_motor": self.forbid_sidebar_search_motor,
            "forbid_source_compose_remap": self.forbid_source_compose_remap,
            "decisions": [d.to_dict() for d in self.decisions],
            "accepted_document": self.accepted_document,
        }


def _norm_surface(value: Any) -> str:
    text = str(value or "").strip().lower().replace(" ", "_")
    if text in CANONICAL_SURFACES:
        return text
    # Mild aliases the model sometimes emits.
    aliases = {
        "chatlist": "chat_list",
        "list": "chat_list",
        "search_results": "search",
        "picker": "forward_picker",
        "forward": "forward_picker",
        "destination_picker": "forward_picker",
        "menu": "context_menu",
    }
    return aliases.get(text, text if text else "")


def _last_action_family(prior: Dict[str, Any], last_action: str = "") -> str:
    if last_action:
        return str(last_action or "").strip().lower()
    attempts = list(prior.get("attempts") or [])
    if not attempts:
        return ""
    last = attempts[-1]
    if isinstance(last, dict):
        return str(last.get("action") or "").strip().lower()
    return str(last or "").strip().lower()


def infer_field_role(surface: str, proposed: Optional[Dict[str, Any]] = None) -> str:
    if isinstance(proposed, dict):
        role = str(
            proposed.get("focused_field_role")
            or proposed.get("field_role")
            or ""
        ).strip().lower()
        if role:
            return role
    return SURFACE_FIELD_ROLE.get(surface, "none")


def _surface_transition_ok(
    prior_surface: str,
    proposed_surface: str,
    *,
    last_action: str,
) -> tuple[bool, str]:
    if not proposed_surface:
        return False, "empty proposed surface"
    if proposed_surface not in CANONICAL_SURFACES:
        return False, f"non-canonical surface {proposed_surface!r}"
    if not prior_surface or prior_surface == proposed_surface:
        return True, "same or initial surface"
    parents = SURFACE_PARENTS.get(proposed_surface, set())
    if prior_surface in parents:
        # While hunting/acting inside a conversation, do not silently fall into
        # sidebar search — that is the zarooratwala drift class.
        if (
            prior_surface == "conversation"
            and proposed_surface == "search"
            and last_action
            in {"locate_content", "select_content", "reveal_actions", "observe"}
        ):
            return False, (
                f"refuse conversation->search during {last_action!r}; "
                "sidebar search abandons the open-chat hunt"
            )
        return True, f"{prior_surface} is a legal parent of {proposed_surface}"
    openers = ACTION_OPENS_SURFACE.get(proposed_surface, set())
    if last_action and any(tok in last_action for tok in openers):
        # Typing on a picker/dialog must not "explain" a jump into sidebar search.
        if prior_surface in NO_SIDEBAR_SEARCH_SURFACES and proposed_surface in {
            "search",
            "chat_list",
        }:
            return False, (
                f"refuse {prior_surface!r}->{proposed_surface!r}: "
                f"sidebar search is not reachable from picker/dialog via {last_action!r}"
            )
        return True, f"last action {last_action!r} opens {proposed_surface}"
    # Jumping to blank / dialog is usually recovery chrome; allow with note.
    if proposed_surface in {"blank", "dialog"}:
        return True, f"recovery surface {proposed_surface}"
    return False, (
        f"illegal jump {prior_surface!r} -> {proposed_surface!r} "
        f"without justifying action (last={last_action!r})"
    )


def critique_world_proposal(
    prior: Optional[Dict[str, Any]],
    proposal: Dict[str, Any],
    *,
    last_action: str = "",
    observed_surface: str = "",
) -> CriticVerdict:
    """Merge ``proposal`` into ``prior`` with structural accept/reject reasons."""
    prior_doc = dict(prior or {})
    prop = dict(proposal or {})
    decisions: List[CriticDecision] = []

    prior_surface = _norm_surface(prior_doc.get("surface"))
    proposed_surface = _norm_surface(prop.get("surface") or observed_surface)
    action = _last_action_family(prior_doc, last_action)

    ok, reason = _surface_transition_ok(
        prior_surface, proposed_surface, last_action=action
    )
    if ok and proposed_surface:
        surface = proposed_surface
        decisions.append(
            CriticDecision(
                field="surface",
                verdict="accept",
                reason=reason,
                prior=prior_surface,
                proposed=proposed_surface,
                accepted=surface,
            )
        )
    else:
        surface = prior_surface or proposed_surface or "blank"
        decisions.append(
            CriticDecision(
                field="surface",
                verdict="reject" if prior_surface else "edit",
                reason=reason or "kept prior surface",
                prior=prior_surface,
                proposed=proposed_surface,
                accepted=surface,
            )
        )

    # open_conversation: do not wipe a confirmed open without evidence.
    prior_open = str(prior_doc.get("open_conversation") or "").strip()
    prop_open = str(prop.get("open_conversation") or "").strip()
    if prop_open:
        open_conversation = prop_open
        decisions.append(
            CriticDecision(
                field="open_conversation",
                verdict="accept",
                reason="proposal named an open conversation",
                prior=prior_open,
                proposed=prop_open,
                accepted=open_conversation,
            )
        )
    elif prior_open and surface in {"conversation", "context_menu", "forward_picker"}:
        open_conversation = prior_open
        decisions.append(
            CriticDecision(
                field="open_conversation",
                verdict="reject",
                reason=(
                    "proposal cleared open_conversation while still on a "
                    "conversation-descended surface; kept prior"
                ),
                prior=prior_open,
                proposed=prop_open,
                accepted=open_conversation,
            )
        )
    else:
        open_conversation = prop_open or prior_open
        decisions.append(
            CriticDecision(
                field="open_conversation",
                verdict="accept" if prop_open == prior_open else "edit",
                reason="merged open_conversation",
                prior=prior_open,
                proposed=prop_open,
                accepted=open_conversation,
            )
        )

    field_role = infer_field_role(surface, prop)
    # If the surface proposal was rejected, ignore the proposed field role —
    # it belongs to the discarded surface (e.g. sidebar_search on a hunt).
    if surface != proposed_surface:
        field_role = SURFACE_FIELD_ROLE.get(surface, "none")
        decisions.append(
            CriticDecision(
                field="focused_field_role",
                verdict="edit",
                reason="surface rejected; field role taken from accepted surface",
                proposed=str(prop.get("focused_field_role") or ""),
                accepted=field_role,
            )
        )
    # Structural override: picker/menu never imply sidebar search.
    elif surface in NO_SIDEBAR_SEARCH_SURFACES and field_role in SIDEBAR_SEARCH_ROLES:
        decisions.append(
            CriticDecision(
                field="focused_field_role",
                verdict="edit",
                reason=f"{surface} cannot host sidebar_search; coerced to destination_filter/none",
                prior=field_role,
                proposed=field_role,
                accepted=SURFACE_FIELD_ROLE.get(surface, "none"),
            )
        )
        field_role = SURFACE_FIELD_ROLE.get(surface, "none")
    else:
        decisions.append(
            CriticDecision(
                field="focused_field_role",
                verdict="accept",
                reason="field role from surface/proposal",
                proposed=str(prop.get("focused_field_role") or ""),
                accepted=field_role,
            )
        )

    accepted = dict(prop)
    # Carry forward prior keys the proposal omitted.
    for key, value in prior_doc.items():
        if key not in accepted or accepted.get(key) in (None, "", [], {}):
            accepted[key] = value
    accepted["surface"] = surface
    accepted["open_conversation"] = open_conversation
    accepted["focused_field_role"] = field_role

    # Soft bags: prefer proposal when present.
    for key in ("objects", "progress", "attempts", "exhausted"):
        if key in prop and prop.get(key) not in (None, "", [], {}):
            accepted[key] = prop.get(key)
            decisions.append(
                CriticDecision(
                    field=key,
                    verdict="accept",
                    reason="proposal provided soft content",
                    accepted="(set)",
                )
            )

    # Beliefs are special: omission is a valid retraction, so an empty list
    # must clear any carried-forward belief inventory.
    if "beliefs" in prop:
        accepted["beliefs"] = prop.get("beliefs") or []
        decisions.append(
            CriticDecision(
                field="beliefs",
                verdict="accept",
                reason="belief retraction is explicit by omission/empty list",
                accepted="(set)" if accepted["beliefs"] else "[]",
            )
        )

    forbid_sidebar_motor = (
        surface in NO_SIDEBAR_SEARCH_SURFACES or field_role == "destination_filter"
    )

    return CriticVerdict(
        accepted_document=accepted,
        decisions=decisions,
        focused_field_role=field_role,
        surface=surface,
        forbid_sidebar_search_motor=forbid_sidebar_motor,
        forbid_source_compose_remap=forbid_sidebar_motor,
    )


def accepted_surface(execution_state: Any) -> str:
    doc = getattr(execution_state, "unified_world_document", None) or {}
    if isinstance(doc, dict):
        return _norm_surface(doc.get("surface"))
    return ""


def accepted_field_role(execution_state: Any) -> str:
    role = str(getattr(execution_state, "focused_field_role", "") or "").strip().lower()
    if role:
        return role
    doc = getattr(execution_state, "unified_world_document", None) or {}
    if isinstance(doc, dict):
        return infer_field_role(_norm_surface(doc.get("surface")), doc)
    return "none"


def sidebar_search_forbidden(execution_state: Any = None, *, surface: str = "", role: str = "") -> bool:
    surf = surface or (accepted_surface(execution_state) if execution_state is not None else "")
    field = role or (accepted_field_role(execution_state) if execution_state is not None else "")
    return surf in NO_SIDEBAR_SEARCH_SURFACES or field == "destination_filter"
