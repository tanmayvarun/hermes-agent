"""Wrong-locus method forbid: field | container | patient.

General failure class: a wrong locus is focused/clickable while the correct
locus is ungrounded, so a locally executable wrong method outranks recovery.
This module is the thin authority that marks those methods non-executable.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, FrozenSet, Optional, Tuple

from plugin.agent.capabilities.action_area import (
    COMPOSER_KINDS,
    FILTER_KINDS,
    contract_for,
    is_high_cost,
    label_looks_like_composer,
    label_looks_like_filter,
    validate_actuation_grounding,
)

FILTER_FIELD_ROLES: FrozenSet[str] = frozenset(
    {"in_chat_find", "sidebar_search", "destination_filter"}
)
COMPOSER_FIELD_ROLES: FrozenSet[str] = frozenset(
    {"composer", "message_composer", "chat_composer", "message_input"}
)

# Capabilities that write into / actuate a filter field.
_FILTER_WRITE_CAPS: FrozenSet[str] = frozenset(
    {
        "compose_search_query",
        "type_query",
        "locate_content",
        "open_search",
    }
)
# Capabilities that act on a content patient (message / link).
_PATIENT_CAPS: FrozenSet[str] = frozenset(
    {
        "reveal_actions",
        "select_content",
        "invoke_affordance",
        "right_click",
        "context_click",
    }
)
# Capabilities that compose into an open conversation container.
_CONTAINER_COMPOSE_CAPS: FrozenSet[str] = frozenset(
    {"compose_search_query", "type_query"}
)


class LocusKind(str, Enum):
    FIELD = "field"
    CONTAINER = "container"
    PATIENT = "patient"


@dataclass(frozen=True)
class LocusRequirement:
    """Required / forbidden loci for a desired effect."""

    desired_effect: str = ""
    required_locus: str = ""
    forbidden_loci: Tuple[str, ...] = ()
    kind: LocusKind = LocusKind.FIELD

    def to_dict(self) -> Dict[str, Any]:
        return {
            "desired_effect": self.desired_effect,
            "required_locus": self.required_locus,
            "forbidden_loci": list(self.forbidden_loci),
            "kind": self.kind.value,
        }


def _norm(s: Any) -> str:
    return str(s or "").strip().lower()


def requirement_for_capability(
    capability: str,
    *,
    brief: Any = None,
    desired_effect: str = "",
) -> Optional[LocusRequirement]:
    """Derive the locus contract implied by a capability + task brief."""
    cap = _norm(capability).replace("-", "_")
    effect = _norm(desired_effect)
    if not effect and brief is not None:
        ts = getattr(brief, "task_state", None)
        if ts is not None and not bool(getattr(ts, "content_located", False)):
            if cap in {"locate_content", "type_query"}:
                effect = "content_located"
        if ts is not None and not bool(getattr(ts, "source_chat_open", False)):
            if cap in {"compose_search_query", "open_entity"}:
                effect = "source_container_open"

    if cap in _FILTER_WRITE_CAPS or effect == "content_located":
        return LocusRequirement(
            desired_effect=effect or "content_located",
            required_locus="filter_field",
            forbidden_loci=("composer", "foreign_container"),
            kind=LocusKind.FIELD,
        )
    if cap in _CONTAINER_COMPOSE_CAPS or effect == "source_container_open":
        return LocusRequirement(
            desired_effect=effect or "source_container_open",
            required_locus="open_matches_referent(source)",
            forbidden_loci=("foreign_container", "composer"),
            kind=LocusKind.CONTAINER,
        )
    if cap in _PATIENT_CAPS or effect == "affordance_invoked":
        return LocusRequirement(
            desired_effect=effect or "affordance_invoked",
            required_locus="commitment.patient_ref",
            forbidden_loci=("non_committed_patient", "composer"),
            kind=LocusKind.PATIENT,
        )
    return None


def focused_field_role(brief: Any = None, world: Optional[Dict[str, Any]] = None) -> str:
    doc = world if isinstance(world, dict) else {}
    if brief is not None:
        w = getattr(brief, "world", None) or {}
        if isinstance(w, dict) and not doc:
            doc = w
        nav = getattr(brief, "navigation", None)
        role = _norm(doc.get("focused_field_role"))
        if not role and nav is not None:
            role = _norm(getattr(nav, "focused_field_role", ""))
        return role
    return _norm(doc.get("focused_field_role"))


def filter_field_evidence(
    *,
    field_role: str = "",
    label: str = "",
    target_kind: str = "",
) -> bool:
    """True when grounded evidence shows a filter/find field — not a composer."""
    role = _norm(field_role)
    if role in FILTER_FIELD_ROLES:
        return True
    if role in COMPOSER_FIELD_ROLES:
        return False
    kind = _norm(target_kind)
    if kind in FILTER_KINDS:
        return True
    if kind in COMPOSER_KINDS:
        return False
    lab = str(label or "").strip()
    if label_looks_like_composer(lab):
        return False
    if label_looks_like_filter(lab):
        return True
    return False


def _foreign_container(brief: Any) -> Tuple[bool, str, str]:
    """Return (is_foreign, open_conversation, source)."""
    if brief is None:
        return False, "", ""
    ts = getattr(brief, "task_state", None)
    if ts is None:
        return False, "", ""
    open_c = str(getattr(ts, "open_conversation", "") or "").strip()
    goal = getattr(brief, "goal", None) or {}
    if not isinstance(goal, dict):
        goal = {}
    source = str(
        goal.get("source_conversation") or goal.get("contact") or ""
    ).strip()
    if not open_c or not source:
        return False, open_c, source
    if bool(getattr(ts, "source_chat_open", False)):
        return False, open_c, source
    try:
        from plugin.agent.capabilities.resolve_entity import open_matches_referent

        if open_matches_referent(open_c, source):
            return False, open_c, source
    except Exception:
        pass
    return True, open_c, source


def wrong_locus_forbidden(
    capability: str,
    *,
    brief: Any = None,
    field_role: str = "",
    label: str = "",
    target_kind: str = "",
    desired_effect: str = "",
    state: Any = None,
    require_field_evidence: bool = False,
) -> Tuple[bool, str, Optional[LocusRequirement]]:
    """Return ``(forbidden, why, requirement)``.

    ``why`` is stable for goldens: ``wrong_locus:<kind>:<detail>``.

    Sanitize uses the default (forbid only on *positive* wrong-locus evidence).
    Motor / actor passes ``require_field_evidence=True`` so HIGH-cost filter
    writes fail closed when role/kind/label do not prove a filter field.
    """
    cap = _norm(capability).replace("-", "_")
    req = requirement_for_capability(cap, brief=brief, desired_effect=desired_effect)
    role = _norm(field_role) or focused_field_role(brief)
    if role in {"none", "unknown"}:
        role = ""
    lab = str(label or "").strip()
    kind = _norm(target_kind)

    # --- field locus -------------------------------------------------------
    if cap in _FILTER_WRITE_CAPS:
        if role in COMPOSER_FIELD_ROLES or label_looks_like_composer(lab) or kind in COMPOSER_KINDS:
            r = req or LocusRequirement(
                desired_effect="content_located",
                required_locus="filter_field",
                forbidden_loci=("composer",),
                kind=LocusKind.FIELD,
            )
            return True, f"wrong_locus:field:composer_focused:{cap}", r
        if require_field_evidence and is_high_cost(cap):
            if not filter_field_evidence(
                field_role=role, label=lab, target_kind=kind
            ):
                r = req or LocusRequirement(
                    desired_effect="content_located",
                    required_locus="filter_field",
                    forbidden_loci=("empty_kind",),
                    kind=LocusKind.FIELD,
                )
                return True, f"wrong_locus:field:empty_kind:{cap}", r
        # Positive wrong-area latch (composer label / entity kind on filter act).
        if role or kind or lab:
            area_ok, area_why = validate_actuation_grounding(
                capability=cap,
                field_role=role,
                label=lab,
                target_kind=kind,
            )
            if not area_ok and "empty_kind" not in area_why:
                r = req or LocusRequirement(
                    desired_effect="content_located",
                    required_locus="filter_field",
                    forbidden_loci=("composer",),
                    kind=LocusKind.FIELD,
                )
                return True, f"wrong_locus:field:{area_why}", r

    # --- container locus ---------------------------------------------------
    if cap in _CONTAINER_COMPOSE_CAPS and brief is not None:
        foreign, open_c, source = _foreign_container(brief)
        phase = _norm(getattr(getattr(brief, "task_state", None), "phase", ""))
        if foreign and phase in {"", "reach_source"}:
            r = LocusRequirement(
                desired_effect="source_container_open",
                required_locus="open_matches_referent(source)",
                forbidden_loci=("foreign_container",),
                kind=LocusKind.CONTAINER,
            )
            return (
                True,
                f"wrong_locus:container:foreign_open:{open_c!r}!={source!r}",
                r,
            )

    # --- patient locus (commitment) ----------------------------------------
    if cap in _PATIENT_CAPS:
        if role in COMPOSER_FIELD_ROLES or label_looks_like_composer(lab):
            r = LocusRequirement(
                desired_effect="affordance_invoked",
                required_locus="commitment.patient_ref",
                forbidden_loci=("composer",),
                kind=LocusKind.PATIENT,
            )
            return True, f"wrong_locus:patient:composer:{cap}", r
        if state is not None:
            try:
                from plugin.agent.executive.affordance_commitment import (
                    forbids_patient_substitute,
                )

                if forbids_patient_substitute(
                    state, family=cap, semantic_target=lab
                ):
                    r = LocusRequirement(
                        desired_effect="affordance_invoked",
                        required_locus="commitment.patient_ref",
                        forbidden_loci=("non_committed_patient",),
                        kind=LocusKind.PATIENT,
                    )
                    return True, "wrong_locus:patient:substitute_forbidden", r
            except Exception:
                pass

    return False, "ok", req


def recovery_capability_for(
    why: str,
    *,
    prefer_open_entity: bool = False,
) -> str:
    """Prefer a recovery capability when wrong-locus fires (allowlisted)."""
    w = _norm(why)
    if "foreign" in w or "container" in w:
        return "open_entity" if prefer_open_entity else "dismiss_transient"
    if "composer" in w or "field" in w:
        return "locate_content"
    if "patient" in w or "substitute" in w:
        return "observe"
    return ""


def stamp_wrong_locus_debt(
    state: Any,
    *,
    kind: str,
    forbidden: str,
    required: str,
    why: str = "",
) -> None:
    """Arm ExecutionState recovery debt for meta (parallel to leave-wrong)."""
    if state is None:
        return
    state.wrong_locus_recovery_owed = True
    state.wrong_locus_kind = str(kind or "")
    state.wrong_locus_forbidden = str(forbidden or "")
    state.wrong_locus_required = str(required or "")
    state.wrong_locus_why = str(why or "")[:240]
    # Keep leave-wrong in sync for container foreign-open (existing meta path).
    if _norm(kind) == LocusKind.CONTAINER.value or "foreign" in _norm(forbidden):
        state.leave_wrong_conversation_owed = True


def clear_wrong_locus_debt(state: Any) -> None:
    if state is None:
        return
    state.wrong_locus_recovery_owed = False
    state.wrong_locus_kind = ""
    state.wrong_locus_forbidden = ""
    state.wrong_locus_required = ""
    state.wrong_locus_why = ""


def method_locus_ineligible(
    capability: str,
    *,
    brief: Any = None,
    state: Any = None,
    field_role: str = "",
    label: str = "",
    target_kind: str = "",
) -> bool:
    """Intention / ranking helper: True → treat method as score-0 / ineligible."""
    forbidden, _, _ = wrong_locus_forbidden(
        capability,
        brief=brief,
        state=state,
        field_role=field_role,
        label=label,
        target_kind=target_kind,
    )
    return forbidden
