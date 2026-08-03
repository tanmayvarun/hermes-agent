"""Evaluate whether the agent chose the right *kind* of capability.

Unit tests that only check vocabulary membership and FakePointer smoke paths
cannot catch the failure mode that burned live runs: the model sees the right
scene and still picks scroll / click forever. These checks score the proposal
against the representation substrate the packet already carries.

Defect-first: each check names a real way the composition fails.

Usage (also wired into perceptor_eval):
    from plugin.experiments.capability_eval import score_capability_choice
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Set

from plugin.agent.capabilities.catalog import realized_verbs
from plugin.agent.capabilities.commit_irreversible import is_commit_label
from plugin.agent.capabilities.invoke_affordance import is_irreversible_affordance
from plugin.agent.unified_cognition import ALLOWED_ACTIONS, UnifiedProposal
from plugin.experiments.perceptor_eval import Check, canonical_surface


# Families that hunt by paging. Acceptable only when locate is unavailable or
# already exhausted — never the primary answer to "find X".
_HUNT_BY_SCROLL = frozenset({"scroll", "scroll_content"})

# Opening a container. Wrong once the needed conversation is already open.
_OPEN_CONTAINER = frozenset({"open_entity", "open_contact", "click"})

# Committing side effects.
_COMMIT = frozenset({"commit_irreversible"})


@dataclass(frozen=True)
class CapabilityScenario:
    """A minimal scene + an action, scored for composition fitness."""

    name: str
    packet: Dict[str, Any]
    proposal: Dict[str, Any]
    # Checks that must pass for this scenario to be considered healthy.
    require_pass: Sequence[str]
    # Checks that must fail — used by negative tests that inject a defect.
    require_fail: Sequence[str] = ()


def _goal(packet: Dict[str, Any]) -> Dict[str, Any]:
    goal = packet.get("goal") or {}
    return goal if isinstance(goal, dict) else {}


def _query(packet: Dict[str, Any]) -> str:
    return str(_goal(packet).get("source_query") or "").strip().lower()


def _destination(packet: Dict[str, Any]) -> str:
    return str(_goal(packet).get("destination") or "").strip().lower()


def _source(packet: Dict[str, Any]) -> str:
    return str(_goal(packet).get("source_conversation") or "").strip().lower()


def _state(proposal: UnifiedProposal) -> Dict[str, Any]:
    return proposal.observed_state if isinstance(proposal.observed_state, dict) else {}


def _document(proposal: UnifiedProposal, packet: Dict[str, Any]) -> Dict[str, Any]:
    doc = proposal.world_model if isinstance(proposal.world_model, dict) else {}
    if doc:
        return doc
    prior = packet.get("world_model")
    return prior if isinstance(prior, dict) else {}


def _surface(proposal: UnifiedProposal, packet: Dict[str, Any]) -> str:
    raw = str(_state(proposal).get("surface") or _document(proposal, packet).get("surface") or "")
    return canonical_surface(raw) or raw.strip().lower()


def _open_conversation(proposal: UnifiedProposal, packet: Dict[str, Any]) -> str:
    return str(
        _state(proposal).get("open_conversation")
        or _document(proposal, packet).get("open_conversation")
        or ""
    ).strip()


def _objects(proposal: UnifiedProposal, packet: Dict[str, Any]) -> List[Dict[str, Any]]:
    doc = _document(proposal, packet)
    objects = doc.get("objects") or proposal.visible_objects or []
    return [o for o in objects if isinstance(o, dict)]


def _query_visible(proposal: UnifiedProposal, packet: Dict[str, Any]) -> bool:
    query = _query(packet)
    if not query:
        return bool(_state(proposal).get("target_object_visible"))
    if _state(proposal).get("target_object_visible") is True:
        return True
    for obj in _objects(proposal, packet):
        text = str(obj.get("text") or "").lower()
        if query in text or (obj.get("matches_goal") is True):
            return True
    return False


def _exhausted(proposal: UnifiedProposal, packet: Dict[str, Any]) -> Set[str]:
    doc = _document(proposal, packet)
    return {str(x).strip().lower() for x in (doc.get("exhausted") or []) if str(x).strip()}


def _family(proposal: UnifiedProposal) -> str:
    action = proposal.next_action or {}
    return str(action.get("family") or "").strip().lower().replace("-", "_")


def _action_text(proposal: UnifiedProposal) -> str:
    action = proposal.next_action or {}
    return str(action.get("text") or action.get("target_label") or "").strip()


def score_capability_choice(proposal: UnifiedProposal, packet: Dict[str, Any]) -> List[Check]:
    """Is the proposed family a fit for the substrate the reading describes?

    These are soft composition rules, not a hardcoded plan: several families can
    be right; the checks catch the ones that are *structurally* wrong for the
    scene (scroll-hunting with locate available, Send via invoke, reopening a
    chat that is already open, …).
    """
    checks: List[Check] = []
    family = _family(proposal)
    surface = _surface(proposal, packet)
    open_conv = _open_conversation(proposal, packet)
    query = _query(packet)
    visible = _query_visible(proposal, packet)
    exhausted = _exhausted(proposal, packet)
    text = _action_text(proposal)
    realized = set(realized_verbs())

    checks.append(Check(
        "capability_vocabulary_offered",
        realized <= set(packet.get("allowed_actions") or ALLOWED_ACTIONS),
        f"missing={sorted(realized - set(packet.get('allowed_actions') or []))}",
    ))

    checks.append(Check("action_family_present", bool(family), family))
    checks.append(Check(
        "action_is_known_capability_or_motor",
        family in ALLOWED_ACTIONS or family in realized,
        family,
    ))

    # --- locate vs scroll -------------------------------------------------
    hunting = (
        surface == "conversation"
        and bool(open_conv)
        and bool(query)
        and not visible
        and "locate_content" not in exhausted
    )
    checks.append(Check(
        "hunt_prefers_locate_over_scroll",
        (not hunting) or family == "locate_content" or family in {"observe", "request_more_evidence"},
        f"surface={surface} open={open_conv!r} family={family} visible={visible}",
    ))
    checks.append(Check(
        "scroll_is_not_the_primary_hunt",
        (not hunting) or family not in _HUNT_BY_SCROLL,
        f"family={family}",
    ))
    # While hunting inside an already-open conversation, opening the destination
    # or an unrelated entity abandons the search branch.
    dest = _destination(packet)
    source = _source(packet)
    opening = hunting and family in {"open_entity", "open_contact", "click"} and bool(text)
    opens_dest = opening and dest and dest in text.lower()
    opens_other = opening and source and dest and source not in text.lower() and dest not in text.lower()
    checks.append(Check(
        "hunt_does_not_open_destination_early",
        not opens_dest,
        f"text={text!r}",
    ))
    checks.append(Check(
        "hunt_does_not_abandon_open_conversation",
        not opens_other,
        f"text={text!r} open={open_conv!r}",
    ))

    # --- target visible: advance, don't keep locating ---------------------
    when_visible = surface == "conversation" and visible and bool(query)
    checks.append(Check(
        "visible_target_advances_past_locate",
        (not when_visible) or family != "locate_content",
        f"family={family} visible={visible}",
    ))
    checks.append(Check(
        "visible_target_uses_select_reveal_or_invoke",
        (not when_visible)
        or family in {
            "select_content",
            "reveal_actions",
            "invoke_affordance",
            "right_click",
            "hover",
            "click",
            "observe",
            "request_more_evidence",
        },
        f"family={family}",
    ))

    # --- context menu / forward affordance --------------------------------
    on_menu = surface in {"context_menu", "dialog"}
    checks.append(Check(
        "menu_uses_invoke_not_scroll",
        (not on_menu) or family not in _HUNT_BY_SCROLL,
        f"surface={surface} family={family}",
    ))
    invoke_text = text
    if family == "invoke_affordance" and invoke_text:
        checks.append(Check(
            "invoke_refuses_irreversible_labels",
            not is_irreversible_affordance(invoke_text),
            invoke_text,
        ))
    else:
        checks.append(Check("invoke_refuses_irreversible_labels", True, "n/a"))

    # --- forward picker / destination -------------------------------------
    on_picker = surface == "forward_picker"
    checks.append(Check(
        "picker_opens_destination_or_types_not_scroll_hunt",
        (not on_picker)
        or family in {
            "open_entity",
            "open_contact",
            "click",
            "type",
            "type_query",
            "locate_content",
            "commit_irreversible",
            "dismiss_transient",
            "observe",
            "request_more_evidence",
        },
        f"family={family}",
    ))

    # --- commit gate ------------------------------------------------------
    if family == "commit_irreversible":
        checks.append(Check(
            "commit_label_is_allowlisted",
            is_commit_label(text) if text else False,
            text,
        ))
        checks.append(Check(
            "commit_action_marked_irreversible_in_proposal",
            # Proposal JSON may not carry reversible; scored via proposal_to_action elsewhere.
            True,
            "see actionability",
        ))
    else:
        checks.append(Check("commit_label_is_allowlisted", True, "n/a"))
        checks.append(Check("commit_action_marked_irreversible_in_proposal", True, "n/a"))

    # Sending via a motor click while commit exists is the gate-smuggle.
    sendish = bool(text) and is_commit_label(text)
    checks.append(Check(
        "send_goes_through_commit_not_invoke_or_bare_click",
        (not sendish) or family in _COMMIT,
        f"family={family} text={text!r}",
    ))

    # --- grounding for entity-shaped capabilities -------------------------
    action = proposal.next_action or {}
    entity_shaped = family in {"open_entity", "select_content", "reveal_actions"}
    grounded = bool(
        action.get("target_id") not in (None, "")
        or action.get("target_point")
        or str(action.get("target_label") or action.get("text") or "").strip()
    )
    checks.append(Check(
        "entity_capability_is_grounded",
        (not entity_shaped) or grounded,
        f"family={family}",
    ))

    locate = family == "locate_content"
    checks.append(Check(
        "locate_carries_a_query",
        (not locate) or bool(str(action.get("text") or "").strip()),
        str(action.get("text") or ""),
    ))

    # Chrome-only AX: point-clicking a chat row reports ok and changes nothing.
    # Prefer type_query (search) when the observation explicitly says content=0.
    obs = packet.get("observation") if isinstance(packet.get("observation"), dict) else {}
    ax_content = obs.get("ax_content_node_count") if isinstance(obs, dict) else None
    try:
        starved = ax_content is not None and int(ax_content) <= 0
    except (TypeError, ValueError):
        starved = False
    on_list = surface in {"chat_list", "list", "main_chat_list"} and not open_conv
    pointer_open = family in {"open_entity", "open_contact", "click"}
    checks.append(Check(
        "chrome_only_list_opens_via_search_not_point_click",
        (not starved) or (not on_list) or (not pointer_open),
        f"ax_content={ax_content} surface={surface} family={family}",
    ))

    return checks


def score_capability_gates(proposal: UnifiedProposal, packet: Dict[str, Any]) -> List[Check]:
    """Run the real proposal→action→dispatch refusal path for irreversible labels."""
    from plugin.agent.capabilities.base import CapabilityRequest
    from plugin.agent.capabilities.dispatch import dispatch
    from plugin.agent.goal import Goal
    from plugin.agent.unified_cognition import proposal_to_action
    from plugin.worldmodel.model import WorldModel

    checks: List[Check] = []
    goal_spec = _goal(packet)
    goal = Goal(
        kind=str(goal_spec.get("operation") or "whatsapp_forward_message"),
        contact=str(goal_spec.get("source_conversation") or ""),
        target_contact=str(goal_spec.get("destination") or ""),
        link_query=str(goal_spec.get("source_query") or ""),
    )
    action, reason = proposal_to_action(proposal, goal, WorldModel())
    family = _family(proposal)
    text = _action_text(proposal)

    if family == "invoke_affordance" and text and is_irreversible_affordance(text):
        # Admissibility may still produce an Action; dispatch must refuse.
        class Overlay:
            pass

        outcome = dispatch(
            CapabilityRequest(name="invoke_affordance", app="WhatsApp", arg=text),
            Overlay(),
        )
        checks.append(Check(
            "dispatch_blocks_irreversible_invoke",
            not outcome.ok and outcome.evidence.get("reason") == "irreversible",
            outcome.message,
        ))
    else:
        checks.append(Check("dispatch_blocks_irreversible_invoke", True, "n/a"))

    if family == "commit_irreversible":
        checks.append(Check(
            "commit_proposal_is_admissible",
            action is not None and reason == "admissible",
            reason,
        ))
        checks.append(Check(
            "commit_action_is_not_reversible",
            bool(action) and action.reversible is False,
            repr(getattr(action, "reversible", None)),
        ))
    else:
        checks.append(Check("commit_proposal_is_admissible", True, "n/a"))
        checks.append(Check("commit_action_is_not_reversible", True, "n/a"))

    if family in realized_verbs() and family not in {"commit_irreversible", "invoke_affordance"}:
        checks.append(Check(
            "realized_capability_proposal_admissible",
            action is not None and reason == "admissible",
            f"{family}:{reason}",
        ))
    else:
        checks.append(Check("realized_capability_proposal_admissible", True, "n/a"))

    return checks


def score_outcome_evidence_contract(evidence: Dict[str, Any], *, capability: str) -> List[Check]:
    """Locate/open outcomes report reachability, never relevance."""
    checks: List[Check] = []
    checks.append(Check("evidence_is_dict", isinstance(evidence, dict)))
    forbidden = {"selected", "is_the_one", "relevant", "correct_message", "target_matched"}
    leaked = sorted(forbidden & set(evidence))
    checks.append(Check(
        "evidence_does_not_claim_relevance",
        not leaked,
        f"leaked={leaked}",
    ))
    if capability == "locate_content":
        checks.append(Check(
            "locate_evidence_reports_reachability",
            "text_match_reachable" in evidence or "match_reachable" in evidence
            or "surface_exhausted" in evidence,
            str(sorted(evidence))[:120],
        ))
    else:
        checks.append(Check("locate_evidence_reports_reachability", True, "n/a"))
    if capability == "commit_irreversible":
        checks.append(Check(
            "commit_evidence_marks_irreversible",
            evidence.get("irreversible") is True,
            str(evidence)[:80],
        ))
    else:
        checks.append(Check("commit_evidence_marks_irreversible", True, "n/a"))
    return checks


# ---------------------------------------------------------------------------
# Scenario fixtures — the forward composition, as scenes
# ---------------------------------------------------------------------------


def _base_packet(**overrides) -> Dict[str, Any]:
    packet = {
        "goal": {
            "operation": "whatsapp_forward_message",
            "source_conversation": "Pallavi",
            "source_query": "zarooratwala",
            "destination": "Tanmay",
        },
        "world_model": {
            "surface": "chat_list",
            "open_conversation": "",
            "objects": [],
            "beliefs": [],
            "progress": {"phase": "open_source", "objective": "open Pallavi", "notes": ""},
            "attempts": [],
            "exhausted": [],
        },
        "observation": {"frame": 1, "app": "WhatsApp", "ax_evidence": []},
        "allowed_actions": list(ALLOWED_ACTIONS),
    }
    packet.update(overrides)
    return packet


def _prop(
    *,
    surface: str,
    open_conversation: str = "",
    target_visible: bool = False,
    family: str,
    text: str = "",
    target_point: Optional[List[int]] = None,
    objects: Optional[List[Dict[str, Any]]] = None,
    exhausted: Optional[List[str]] = None,
) -> Dict[str, Any]:
    return {
        "observed_state": {
            "surface": surface,
            "open_conversation": open_conversation,
            "target_object_visible": target_visible,
        },
        "world_model": {
            "surface": surface,
            "open_conversation": open_conversation,
            "objects": objects or [],
            "beliefs": [],
            "progress": {"phase": "", "objective": "", "notes": ""},
            "attempts": [],
            "exhausted": exhausted or [],
        },
        "next_action": {
            "family": family,
            "text": text,
            "target_point": target_point,
            "confidence": 0.9,
        },
        "scene_summary": f"Surface {surface}. Choosing {family}.",
        "confidence": 0.9,
        "visible_objects": objects or [],
    }


def forward_scenarios() -> List[CapabilityScenario]:
    """Healthy and defective compositions for the zarooratwala forward flow."""
    hunting_packet = _base_packet(
        world_model={
            "surface": "conversation",
            "open_conversation": "Pallavi",
            "objects": [{"id": "m1", "kind": "message", "text": "otp warning", "point": [100, 100]}],
            "beliefs": [],
            "progress": {"phase": "find_message", "objective": "zarooratwala", "notes": ""},
            "attempts": [],
            "exhausted": [],
        }
    )
    visible_objects = [
        {
            "id": "m2",
            "kind": "message",
            "text": "zarooratwala.com groceries",
            "point": [400, 500],
            "matches_goal": True,
        }
    ]

    return [
        CapabilityScenario(
            name="chat_list_opens_source",
            packet=_base_packet(),
            proposal=_prop(
                surface="chat_list",
                family="open_entity",
                text="Pallavi",
                target_point=[120, 200],
            ),
            require_pass=(
                "action_family_present",
                "entity_capability_is_grounded",
                "scroll_is_not_the_primary_hunt",
            ),
        ),
        CapabilityScenario(
            name="chrome_only_list_uses_type_query",
            packet=_base_packet(
                observation={
                    "frame": 1,
                    "app": "WhatsApp",
                    "ax_evidence": [],
                    "ax_content_node_count": 0,
                }
            ),
            proposal=_prop(
                surface="chat_list",
                family="type_query",
                text="Pallavi",
            ),
            require_pass=(
                "chrome_only_list_opens_via_search_not_point_click",
                "action_family_present",
            ),
        ),
        CapabilityScenario(
            name="chrome_only_list_point_open_is_caught",
            packet=_base_packet(
                observation={
                    "frame": 1,
                    "app": "WhatsApp",
                    "ax_evidence": [],
                    "ax_content_node_count": 0,
                }
            ),
            proposal=_prop(
                surface="chat_list",
                family="open_entity",
                text="Pallavi",
                target_point=[285, 480],
            ),
            require_pass=(),
            require_fail=("chrome_only_list_opens_via_search_not_point_click",),
        ),
        CapabilityScenario(
            name="hunting_uses_locate",
            packet=hunting_packet,
            proposal=_prop(
                surface="conversation",
                open_conversation="Pallavi",
                family="locate_content",
                text="zarooratwala",
            ),
            require_pass=(
                "hunt_prefers_locate_over_scroll",
                "scroll_is_not_the_primary_hunt",
                "locate_carries_a_query",
                "hunt_does_not_open_destination_early",
            ),
        ),
        CapabilityScenario(
            name="hunting_by_scroll_is_caught",
            packet=hunting_packet,
            proposal=_prop(
                surface="conversation",
                open_conversation="Pallavi",
                family="scroll",
                text="",
            ),
            require_pass=(),
            require_fail=("scroll_is_not_the_primary_hunt", "hunt_prefers_locate_over_scroll"),
        ),
        CapabilityScenario(
            name="hunting_opens_destination_early_is_caught",
            packet=hunting_packet,
            proposal=_prop(
                surface="conversation",
                open_conversation="Pallavi",
                family="open_entity",
                text="Tanmay",
                target_point=[50, 50],
            ),
            require_pass=(),
            require_fail=("hunt_does_not_open_destination_early",),
        ),
        CapabilityScenario(
            name="visible_target_reveals_actions",
            packet=hunting_packet,
            proposal=_prop(
                surface="conversation",
                open_conversation="Pallavi",
                target_visible=True,
                family="reveal_actions",
                text="zarooratwala.com groceries",
                target_point=[400, 500],
                objects=visible_objects,
            ),
            require_pass=(
                "visible_target_advances_past_locate",
                "visible_target_uses_select_reveal_or_invoke",
                "entity_capability_is_grounded",
            ),
        ),
        CapabilityScenario(
            name="visible_target_still_locating_is_caught",
            packet=hunting_packet,
            proposal=_prop(
                surface="conversation",
                open_conversation="Pallavi",
                target_visible=True,
                family="locate_content",
                text="zarooratwala",
                objects=visible_objects,
            ),
            require_pass=(),
            require_fail=("visible_target_advances_past_locate",),
        ),
        CapabilityScenario(
            name="menu_invokes_forward",
            packet=_base_packet(),
            proposal=_prop(
                surface="context_menu",
                open_conversation="Pallavi",
                family="invoke_affordance",
                text="Forward",
            ),
            require_pass=(
                "menu_uses_invoke_not_scroll",
                "invoke_refuses_irreversible_labels",
                "send_goes_through_commit_not_invoke_or_bare_click",
            ),
        ),
        CapabilityScenario(
            name="menu_invoke_send_is_caught",
            packet=_base_packet(),
            proposal=_prop(
                surface="context_menu",
                family="invoke_affordance",
                text="Send",
            ),
            require_pass=(),
            require_fail=(
                "invoke_refuses_irreversible_labels",
                "send_goes_through_commit_not_invoke_or_bare_click",
            ),
        ),
        CapabilityScenario(
            name="picker_opens_destination",
            packet=_base_packet(),
            proposal=_prop(
                surface="forward_picker",
                family="open_entity",
                text="Tanmay",
                target_point=[200, 300],
            ),
            require_pass=("picker_opens_destination_or_types_not_scroll_hunt",),
        ),
        CapabilityScenario(
            name="send_uses_commit",
            packet=_base_packet(),
            proposal=_prop(
                surface="forward_picker",
                family="commit_irreversible",
                text="Send",
            ),
            require_pass=(
                "commit_label_is_allowlisted",
                "send_goes_through_commit_not_invoke_or_bare_click",
            ),
        ),
        CapabilityScenario(
            name="send_via_bare_click_is_caught",
            packet=_base_packet(),
            proposal=_prop(
                surface="forward_picker",
                family="click",
                text="Send",
                target_point=[800, 900],
            ),
            require_pass=(),
            require_fail=("send_goes_through_commit_not_invoke_or_bare_click",),
        ),
    ]


def evaluate_scenario(scenario: CapabilityScenario) -> Dict[str, Any]:
    proposal = UnifiedProposal(
        observed_state=scenario.proposal.get("observed_state") or {},
        world_model=scenario.proposal.get("world_model") or {},
        next_action=scenario.proposal.get("next_action") or {},
        scene_summary=str(scenario.proposal.get("scene_summary") or ""),
        confidence=float(scenario.proposal.get("confidence") or 0.0),
        visible_objects=list(scenario.proposal.get("visible_objects") or []),
    )
    choice = score_capability_choice(proposal, scenario.packet)
    gates = score_capability_gates(proposal, scenario.packet)
    by_name = {c.name: c for c in choice + gates}
    failed_required = [n for n in scenario.require_pass if n in by_name and not by_name[n].passed]
    passed_forbidden = [n for n in scenario.require_fail if n in by_name and by_name[n].passed]
    return {
        "name": scenario.name,
        "ok": not failed_required and not passed_forbidden,
        "failed_required": failed_required,
        "passed_forbidden": passed_forbidden,
        "checks": {n: c.passed for n, c in by_name.items()},
    }


def evaluate_forward_scenarios() -> Dict[str, Any]:
    results = [evaluate_scenario(s) for s in forward_scenarios()]
    return {
        "scenario_count": len(results),
        "passed": sum(1 for r in results if r["ok"]),
        "failed": [r["name"] for r in results if not r["ok"]],
        "results": results,
    }


# ---------------------------------------------------------------------------
# Multi-step trajectories — composition across state transitions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TrajectoryStep:
    """One (state, action) pair in a multi-step composition."""

    surface: str
    family: str
    open_conversation: str = ""
    target_visible: bool = False
    text: str = ""
    target_point: Optional[List[int]] = None
    objects: Optional[List[Dict[str, Any]]] = None
    exhausted: Optional[List[str]] = None
    # Expected next surface after this action succeeds (None = no claim).
    expect_next_surface: Optional[str] = None


@dataclass(frozen=True)
class CapabilityTrajectory:
    name: str
    steps: Sequence[TrajectoryStep]
    # When True, a defective trajectory: at least one step must fail choice checks.
    expect_failure: bool = False


def _packet_for_step(step: TrajectoryStep) -> Dict[str, Any]:
    return _base_packet(
        world_model={
            "surface": step.surface,
            "open_conversation": step.open_conversation,
            "objects": list(step.objects or []),
            "beliefs": [],
            "progress": {"phase": "", "objective": "", "notes": ""},
            "attempts": [],
            "exhausted": list(step.exhausted or []),
        }
    )


def score_trajectory_transitions(steps: Sequence[TrajectoryStep]) -> List[Check]:
    """Cross-step invariants that single-frame scoring cannot see."""
    checks: List[Check] = []
    families = [s.family for s in steps]

    # Once the query is visible, later steps must not return to locate/scroll hunt.
    first_visible = next((i for i, s in enumerate(steps) if s.target_visible), None)
    if first_visible is not None:
        later = steps[first_visible + 1 :]
        relapsed = [s.family for s in later if s.family in {"locate_content", "scroll", "scroll_content"}]
        checks.append(Check(
            "trajectory_does_not_relapse_to_hunt_after_visible",
            not relapsed,
            f"relapsed={relapsed}",
        ))
    else:
        checks.append(Check("trajectory_does_not_relapse_to_hunt_after_visible", True, "n/a"))

    # Commit must be the last irreversible act; nothing after Send in a happy path.
    commit_idxs = [i for i, s in enumerate(steps) if s.family == "commit_irreversible"]
    if commit_idxs:
        last_commit = commit_idxs[-1]
        after = families[last_commit + 1 :]
        checks.append(Check(
            "nothing_follows_commit_in_happy_path",
            not after,
            f"after={after}",
        ))
    else:
        checks.append(Check("nothing_follows_commit_in_happy_path", True, "n/a"))

    # Expected surface transitions, when the trajectory states them.
    for i, step in enumerate(steps[:-1]):
        if not step.expect_next_surface:
            continue
        nxt = steps[i + 1]
        checks.append(Check(
            f"transition_{i}_{step.family}_to_{step.expect_next_surface}",
            nxt.surface == step.expect_next_surface,
            f"got={nxt.surface}",
        ))

    # invoke(Forward) should be followed by picker/destination work, not another reveal.
    for i, step in enumerate(steps[:-1]):
        if step.family == "invoke_affordance" and step.text.lower() == "forward":
            nxt = steps[i + 1]
            checks.append(Check(
                "after_forward_enters_picker_or_destination",
                nxt.surface in {"forward_picker", "search", "dialog"}
                or nxt.family in {"open_entity", "type", "type_query", "locate_content", "commit_irreversible"},
                f"next_surface={nxt.surface} next_family={nxt.family}",
            ))

    # No Send before Forward in this composition.
    forward_seen = False
    send_before_forward = False
    for step in steps:
        if step.family == "invoke_affordance" and step.text.lower() == "forward":
            forward_seen = True
        if step.family == "commit_irreversible" and not forward_seen:
            send_before_forward = True
    checks.append(Check(
        "send_does_not_precede_forward",
        not send_before_forward,
        f"families={families}",
    ))
    return checks


def evaluate_trajectory(traj: CapabilityTrajectory) -> Dict[str, Any]:
    step_results = []
    all_ok = True
    for idx, step in enumerate(traj.steps):
        scenario = CapabilityScenario(
            name=f"{traj.name}:step{idx}",
            packet=_packet_for_step(step),
            proposal=_prop(
                surface=step.surface,
                open_conversation=step.open_conversation,
                target_visible=step.target_visible,
                family=step.family,
                text=step.text,
                target_point=step.target_point,
                objects=step.objects,
                exhausted=step.exhausted,
            ),
            require_pass=(),  # scored via choice checks + transitions
        )
        result = evaluate_scenario(scenario)
        # For a healthy trajectory every step's critical choice checks must pass.
        critical = [
            "scroll_is_not_the_primary_hunt",
            "hunt_prefers_locate_over_scroll",
            "invoke_refuses_irreversible_labels",
            "send_goes_through_commit_not_invoke_or_bare_click",
            "entity_capability_is_grounded",
            "locate_carries_a_query",
        ]
        # Only enforce hunt checks when hunting.
        hunting = (
            step.surface == "conversation"
            and bool(step.open_conversation)
            and not step.target_visible
            and step.family in {"locate_content", "scroll", "scroll_content", "open_entity", "click"}
        )
        failed = []
        for name in critical:
            if name not in result["checks"]:
                continue
            if name.startswith("hunt_") or name == "scroll_is_not_the_primary_hunt":
                if not hunting and step.family != "locate_content":
                    # When not hunting, scroll_is_not_primary is vacuously true;
                    # hunt_prefers is also vacuous.
                    continue
            if name == "locate_carries_a_query" and step.family != "locate_content":
                continue
            if name == "entity_capability_is_grounded" and step.family not in {
                "open_entity",
                "select_content",
                "reveal_actions",
            }:
                continue
            if name == "invoke_refuses_irreversible_labels" and step.family != "invoke_affordance":
                continue
            if not result["checks"][name]:
                failed.append(name)
        step_ok = not failed
        if not step_ok:
            all_ok = False
        step_results.append({"index": idx, "family": step.family, "ok": step_ok, "failed": failed})

    transitions = score_trajectory_transitions(traj.steps)
    transition_fail = [c.name for c in transitions if not c.passed]
    if transition_fail:
        all_ok = False

    ok = (not all_ok) if traj.expect_failure else all_ok
    return {
        "name": traj.name,
        "ok": ok,
        "expect_failure": traj.expect_failure,
        "steps": step_results,
        "transition_failures": transition_fail,
        "transition_checks": {c.name: c.passed for c in transitions},
    }


def forward_trajectories() -> List[CapabilityTrajectory]:
    msg = [{
        "id": "m2",
        "kind": "message",
        "text": "zarooratwala.com groceries",
        "point": [400, 500],
        "matches_goal": True,
    }]
    return [
        CapabilityTrajectory(
            name="happy_path_forward",
            steps=(
                TrajectoryStep(
                    surface="chat_list",
                    family="open_entity",
                    text="Pallavi",
                    target_point=[120, 200],
                    expect_next_surface="conversation",
                ),
                TrajectoryStep(
                    surface="conversation",
                    open_conversation="Pallavi",
                    family="locate_content",
                    text="zarooratwala",
                    expect_next_surface="conversation",
                ),
                TrajectoryStep(
                    surface="conversation",
                    open_conversation="Pallavi",
                    target_visible=True,
                    family="select_content",
                    text="zarooratwala.com groceries",
                    target_point=[400, 500],
                    objects=msg,
                ),
                TrajectoryStep(
                    surface="conversation",
                    open_conversation="Pallavi",
                    target_visible=True,
                    family="reveal_actions",
                    text="zarooratwala.com groceries",
                    target_point=[400, 500],
                    objects=msg,
                    expect_next_surface="context_menu",
                ),
                TrajectoryStep(
                    surface="context_menu",
                    open_conversation="Pallavi",
                    family="invoke_affordance",
                    text="Forward",
                    expect_next_surface="forward_picker",
                ),
                TrajectoryStep(
                    surface="forward_picker",
                    family="open_entity",
                    text="Tanmay",
                    target_point=[200, 300],
                ),
                TrajectoryStep(
                    surface="forward_picker",
                    family="commit_irreversible",
                    text="Send",
                ),
            ),
        ),
        CapabilityTrajectory(
            name="scroll_hunt_then_never_recovers",
            expect_failure=True,
            steps=(
                TrajectoryStep(
                    surface="conversation",
                    open_conversation="Pallavi",
                    family="scroll",
                ),
                TrajectoryStep(
                    surface="conversation",
                    open_conversation="Pallavi",
                    family="scroll",
                ),
                TrajectoryStep(
                    surface="conversation",
                    open_conversation="Pallavi",
                    family="scroll",
                ),
            ),
        ),
        CapabilityTrajectory(
            name="send_before_forward_is_caught",
            expect_failure=True,
            steps=(
                TrajectoryStep(
                    surface="conversation",
                    open_conversation="Pallavi",
                    target_visible=True,
                    family="reveal_actions",
                    text="msg",
                    target_point=[1, 2],
                    objects=msg,
                    expect_next_surface="context_menu",
                ),
                TrajectoryStep(
                    surface="context_menu",
                    family="commit_irreversible",
                    text="Send",
                ),
            ),
        ),
    ]


def evaluate_forward_trajectories() -> Dict[str, Any]:
    results = [evaluate_trajectory(t) for t in forward_trajectories()]
    return {
        "trajectory_count": len(results),
        "passed": sum(1 for r in results if r["ok"]),
        "failed": [r["name"] for r in results if not r["ok"]],
        "results": results,
    }
