"""Forward-message procedure policy (not core role-binding).

Supplies RoleBindingSpec and action-family → role maps for forward-style goals.
Other procedures (email, move-file, …) get their own modules.

Action family alone does not determine semantic role. Prefer
``action_open_semantics`` so target role and effect-established roles stay
distinct (content search hit may navigate into a container without *being*
that container).
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Set

from plugin.agent.role_binding import Constraint, RoleBindingSpec

# Resolved *semantic* content kinds — not UI presentation kinds.
_CONTENT_ENTITY_KINDS: Set[str] = {
    "message",
    "message_row",
    "message_bubble",
    "message_with_link",
    "link",
    "content_item",
    "attachment",
    "document",
}
# Presentation/unknown — must not be treated as semantic content by themselves.
_PRESENTATION_KINDS: Set[str] = {
    "search_result",
    "search_result_row",
    "picker_row",
}
_CONTAINER_ENTITY_KINDS: Set[str] = {
    "conversation",
    "conversation_row",
    "chat",
    "chat_row",
    "thread",
    "container",
    "contact",
}
# Phases where opening content may establish source_container via navigation.
_SOURCE_REACHING_PHASES: Set[str] = {
    "",
    "open_source",
    "reach_source",
    # Search-surface commits often still owe the source container.
    "find_link",
}


def forward_role_specs(goal: Any) -> Dict[str, RoleBindingSpec]:
    """Typed roles for a forward-style goal. Values come from the goal object."""
    object_constraints = [
        Constraint(
            relation="same_content_referent",
            referent_source="goal.source_query",
            required=True,
        ),
        Constraint(
            relation="equals_binding",
            referent_source="source_container",
            required=True,
        ),
    ]
    # Originator only when the goal parse expressed authorship ("from X" / "I sent").
    # Unset originator ⇒ container+content only (e.g. "in Pallavi chat").
    originator = ""
    if isinstance(goal, dict):
        originator = str(goal.get("originator") or "").strip()
    else:
        originator = str(getattr(goal, "originator", "") or "").strip()
    if originator:
        object_constraints.append(
            Constraint(
                relation="same_originator",
                referent_source="goal.originator",
                required=True,
            )
        )
    return {
        "source_container": RoleBindingSpec(
            role="source_container",
            expected_entity_kinds={
                "conversation",
                "conversation_row",
                "chat_row",
                "chat",
                "thread",
                "container",
                "contact",
                "contact_row",
            },
            identity_constraints=[
                Constraint(
                    relation="same_identity",
                    referent_source="goal.source_contact",
                    required=True,
                )
            ],
            evidence_threshold=0.85,
        ),
        "source_object": RoleBindingSpec(
            role="source_object",
            expected_entity_kinds={
                "message",
                "content_item",
                "link",
                "attachment",
                "document",
            },
            identity_constraints=object_constraints,
            evidence_threshold=0.85,
        ),
        "destination": RoleBindingSpec(
            role="destination",
            expected_entity_kinds={"conversation", "thread", "container", "contact"},
            identity_constraints=[
                Constraint(
                    relation="same_identity",
                    referent_source="goal.destination",
                    required=True,
                )
            ],
            evidence_threshold=0.85,
        ),
    }


def _norm_kind(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _norm_phase(phase: str) -> str:
    return str(phase or "").strip().lower().replace("-", "_")


def _has_ownership(candidate: Optional[Dict[str, Any]]) -> bool:
    cand = candidate if isinstance(candidate, dict) else {}
    for key in ("belongs_to", "container", "owner_conversation", "owning_conversation"):
        if str(cand.get(key) or "").strip():
            return True
    return False


def _candidate_kind(candidate: Optional[Dict[str, Any]] = None, *, target: str = "") -> str:
    """Return resolved semantic kind; presentation kinds are unknown (\"\")."""
    cand = candidate if isinstance(candidate, dict) else {}
    for key in ("entity_kind", "object_type", "kind", "type"):
        kind = _norm_kind(cand.get(key))
        if not kind:
            continue
        if kind in _PRESENTATION_KINDS:
            continue  # UI row type ≠ semantic entity type
        return kind
    # ui_role alone is presentation — never semantic.
    return ""


def _label_content_heuristic(label: str) -> bool:
    low = str(label or "").strip().lower()
    if not low:
        return False
    if low.startswith("you:"):
        return True
    if "https://" in low or "http://" in low:
        return True
    if " - you:" in low:
        return True
    return False


def looks_like_content_open_target(
    *,
    candidate: Optional[Dict[str, Any]] = None,
    target: str = "",
    target_kind: str = "",
) -> bool:
    """True only for resolved semantic content kinds (message/link/…).

    Presentation rows (``search_result_row``) are unknown — ownership and
    URL/``You:`` label heuristics are evidence only and must **not** authorize
    RoleBinder bypass / navigation typing by themselves.
    """
    cand = candidate if isinstance(candidate, dict) else {}
    kind = _norm_kind(target_kind) or _candidate_kind(cand, target=target)
    # Explicit represents/relation may already resolve to a content kind.
    represents = _norm_kind(cand.get("represents") or cand.get("semantic_kind"))
    if represents in _CONTENT_ENTITY_KINDS:
        return True
    if kind in _CONTENT_ENTITY_KINDS:
        return True
    if kind in _CONTAINER_ENTITY_KINDS or kind in _PRESENTATION_KINDS:
        return False
    ui = _norm_kind(cand.get("ui_role") or cand.get("kind") or cand.get("type"))
    if ui in _PRESENTATION_KINDS:
        return False
    # Empty kind: label/owner heuristics are non-authoritative (do not bypass).
    _ = target
    return False


def looks_like_content_evidence_hit(
    *,
    candidate: Optional[Dict[str, Any]] = None,
    target: str = "",
    target_kind: str = "",
) -> bool:
    """Search/content hit that carries content evidence, not container identity.

    A result like ``You: https://zarooratwala.com/...`` may be a
    ``source_object_candidate`` without being a safe ``source_container`` open.
    Opening it is a *navigation hypothesis* whose settled container must still
    be verified against the required referent.
    """
    if looks_like_content_open_target(
        candidate=candidate, target=target, target_kind=target_kind
    ):
        return True
    if looks_like_container_open_target(
        candidate=candidate, target=target, target_kind=target_kind
    ):
        return False
    cand = candidate if isinstance(candidate, dict) else {}
    kind = _norm_kind(target_kind) or _candidate_kind(cand, target=target)
    blob = " ".join(
        str(x)
        for x in (
            target,
            cand.get("text"),
            cand.get("label"),
            cand.get("title"),
        )
        if str(x or "").strip()
    )
    if not blob.strip():
        return False
    # Presentation / unknown rows with URL or "You:" message preview evidence.
    if kind in _PRESENTATION_KINDS or not kind:
        return _label_content_heuristic(blob)
    return False


def looks_like_container_open_target(
    *,
    candidate: Optional[Dict[str, Any]] = None,
    target: str = "",
    target_kind: str = "",
) -> bool:
    """True only for explicit container/conversation semantic kinds."""
    cand = candidate if isinstance(candidate, dict) else {}
    kind = _norm_kind(target_kind) or _candidate_kind(cand, target=target)
    represents = _norm_kind(cand.get("represents") or cand.get("semantic_kind"))
    if represents in _CONTAINER_ENTITY_KINDS or kind in _CONTAINER_ENTITY_KINDS:
        return True
    return False


def _phase_allows_container_navigation(phase: str) -> bool:
    return _norm_phase(phase) in _SOURCE_REACHING_PHASES


def action_open_semantics(
    family: str,
    *,
    phase: str = "",
    candidate: Optional[Dict[str, Any]] = None,
    target: str = "",
    target_kind: str = "",
) -> Dict[str, Any]:
    """Separate click-target role from roles the settled effect may establish.

    A content search hit may be opened as a navigation address into its owning
    container without claiming ``target_role=source_container``. Settled
    destination identity is verified later via RoleBinder.

    ``establishes_roles=["source_container"]`` only when phase is source-reaching;
    content opens while already in-chat do not re-establish the container.
    Unknown kinds stay unknown — never invent ``conversation`` from “not content”.
    """
    fam = str(family or "").strip().lower().replace("-", "_")
    ph = _norm_phase(phase)
    kind_hint = _norm_kind(target_kind) or _candidate_kind(candidate, target=target)
    if fam not in {"open_entity", "open_contact", "resolve_entity"}:
        return {
            "family": fam,
            "target_role": "",
            "establishes_roles": [],
            "is_navigation": False,
            "target_kind": kind_hint,
        }
    if ph in {"choose_destination", "pick_dest", "invoke_forward"}:
        return {
            "family": fam,
            "target_role": "destination",
            "establishes_roles": ["destination"],
            "is_navigation": False,
            "target_kind": kind_hint if kind_hint in _CONTAINER_ENTITY_KINDS else kind_hint,
        }
    if fam == "resolve_entity":
        # Resolve commits identity of the named target — not navigation-via-content.
        if looks_like_content_open_target(
            candidate=candidate, target=target, target_kind=target_kind
        ):
            return {
                "family": fam,
                "target_role": "source_object",
                "establishes_roles": ["source_object"],
                "is_navigation": False,
                "target_kind": kind_hint or "message",
            }
        if looks_like_container_open_target(
            candidate=candidate, target=target, target_kind=target_kind
        ):
            return {
                "family": fam,
                "target_role": "source_container",
                "establishes_roles": ["source_container"],
                "is_navigation": False,
                "target_kind": kind_hint,
            }
        # Unknown: RoleBinder may still evaluate as container, but kind stays empty.
        return {
            "family": fam,
            "target_role": "source_container",
            "establishes_roles": [],
            "is_navigation": False,
            "target_kind": "",
            "unknown_kind": True,
        }
    if looks_like_content_evidence_hit(
        candidate=candidate, target=target, target_kind=target_kind
    ):
        # Content / search-hit evidence ≠ container identity. During
        # source-reaching, opening it is a navigation hypothesis whose
        # settled open_conversation must still match the required referent.
        content_kind = kind_hint or (
            "message"
            if looks_like_content_open_target(
                candidate=candidate, target=target, target_kind=target_kind
            )
            else "search_result"
        )
        if _phase_allows_container_navigation(ph):
            return {
                "family": fam,
                "target_role": "",  # click target is not a container identity claim
                "establishes_roles": ["source_container"],
                "is_navigation": True,
                "target_kind": content_kind,
                "content_hit_not_container": True,
            }
        # Content-shaped open outside source-reaching: do not establish container.
        return {
            "family": fam,
            "target_role": "",
            "establishes_roles": [],
            "is_navigation": False,
            "target_kind": content_kind,
            "content_hit_not_container": True,
        }
    if looks_like_container_open_target(
        candidate=candidate, target=target, target_kind=target_kind
    ):
        return {
            "family": fam,
            "target_role": "source_container",
            "establishes_roles": ["source_container"],
            "is_navigation": False,
            "target_kind": kind_hint,
        }
    # Unknown semantic kind — not content, not therefore conversation.
    return {
        "family": fam,
        "target_role": "source_container",
        "establishes_roles": [],
        "is_navigation": False,
        "target_kind": "",
        "unknown_kind": True,
    }


def role_for_action_family(
    family: str,
    *,
    phase: str = "",
    target_kind: str = "",
    candidate: Optional[Dict[str, Any]] = None,
    target: str = "",
) -> str:
    """Map a forward-procedure action onto the *target* role (not effect role).

    Prefer ``action_open_semantics`` when callers need establishes/navigation.
    Content-shaped ``open_entity`` returns ``\"\"`` — no container claim on the
    clicked label.
    """
    fam = str(family or "").strip().lower().replace("-", "_")
    if fam in {"open_entity", "open_contact", "resolve_entity"}:
        return str(
            action_open_semantics(
                fam,
                phase=phase,
                candidate=candidate,
                target=target,
                target_kind=target_kind,
            ).get("target_role")
            or ""
        )
    if fam in {"select_content", "reveal_actions", "locate_content"}:
        return "source_object"
    if fam in {"type_query", "compose_search_query"}:
        return ""
    return ""


def role_specs_for_goal(goal: Any) -> Dict[str, RoleBindingSpec]:
    """Procedure dispatch — currently forward-message only."""
    kind = str(getattr(goal, "kind", "") or "").strip().lower()
    if "forward" in kind or getattr(goal, "target_contact", None) is not None:
        return forward_role_specs(goal)
    return forward_role_specs(goal)
