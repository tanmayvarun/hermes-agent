"""Forward-message procedure policy (not core role-binding).

Supplies RoleBindingSpec and action-family → role maps for forward-style goals.
Other procedures (email, move-file, …) get their own modules.
"""

from __future__ import annotations

from typing import Any, Dict

from plugin.agent.role_binding import Constraint, RoleBindingSpec


def forward_role_specs(goal: Any) -> Dict[str, RoleBindingSpec]:
    """Typed roles for a forward-style goal. Values come from the goal object."""
    return {
        "source_container": RoleBindingSpec(
            role="source_container",
            expected_entity_kinds={"conversation", "thread", "container", "contact"},
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
            identity_constraints=[
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
                # Container ≠ originator: "from Pallavi" requires sender/author,
                # not merely residing inside Pallavi's conversation.
                Constraint(
                    relation="same_originator",
                    referent_source="goal.originator",
                    required=True,
                ),
            ],
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


def role_for_action_family(family: str, *, phase: str = "") -> str:
    """Map a forward-procedure action family onto a typed role."""
    fam = str(family or "").strip().lower().replace("-", "_")
    ph = str(phase or "").strip().lower().replace("-", "_")
    if fam in {"open_entity", "open_contact", "resolve_entity"}:
        if ph in {"choose_destination", "pick_dest", "invoke_forward"}:
            return "destination"
        return "source_container"
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
