"""Evaluate whether the world critic keeps a correct high-level world document.

The perceptor proposes; the critic accepts/rejects. These checks score the
*accepted* document as a thin navigation-graph representation — not pixels,
not motor scripts.

Defect-first: each scenario names a real way the high-level model drifts
(picker→search jump, wiped open conversation, wrong field role, …).

Usage:
    python -m plugin.experiments.world_critic_eval
    # or via perceptor_eval --world-critic-scenarios
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from plugin.agent.world_critic import (
    CANONICAL_SURFACES,
    NO_SIDEBAR_SEARCH_SURFACES,
    SURFACE_FIELD_ROLE,
    critique_world_proposal,
    infer_field_role,
)
from plugin.experiments.perceptor_eval import Check, canonical_surface


@dataclass(frozen=True)
class WorldCriticScenario:
    """One prior → proposal → expected accepted high-level document."""

    name: str
    prior: Dict[str, Any]
    proposal: Dict[str, Any]
    last_action: str = ""
    observed_surface: str = ""
    # Expected accepted high-level fields.
    expect_surface: str = ""
    expect_open: Optional[str] = None
    expect_field_role: str = ""
    expect_forbid_sidebar: Optional[bool] = None
    require_pass: Sequence[str] = ()
    require_fail: Sequence[str] = ()


@dataclass
class TrajectoryStep:
    proposal: Dict[str, Any]
    last_action: str = ""
    expect_surface: str = ""
    expect_open: Optional[str] = None
    expect_field_role: str = ""


@dataclass(frozen=True)
class WorldCriticTrajectory:
    """A multi-step residual update path through the navigation graph."""

    name: str
    initial: Dict[str, Any]
    steps: Sequence[TrajectoryStep]
    require_pass: Sequence[str] = ()


def score_accepted_representation(
    *,
    prior: Dict[str, Any],
    proposal: Dict[str, Any],
    accepted: Dict[str, Any],
    verdict: Any,
    expect_surface: str = "",
    expect_open: Optional[str] = None,
    expect_field_role: str = "",
    expect_forbid_sidebar: Optional[bool] = None,
) -> List[Check]:
    """Is the accepted document a coherent high-level world representation?"""
    checks: List[Check] = []
    surface = canonical_surface(str(accepted.get("surface") or "")) or str(
        accepted.get("surface") or ""
    ).strip().lower()
    prior_surface = canonical_surface(str(prior.get("surface") or "")) or str(
        prior.get("surface") or ""
    ).strip().lower()
    proposed_surface = canonical_surface(str(proposal.get("surface") or "")) or str(
        proposal.get("surface") or ""
    ).strip().lower()
    open_conv = str(accepted.get("open_conversation") or "").strip()
    role = str(
        accepted.get("focused_field_role") or getattr(verdict, "focused_field_role", "") or ""
    ).strip().lower()
    if not role:
        role = infer_field_role(surface, accepted)

    checks.append(
        Check(
            "accepted_surface_canonical",
            surface in CANONICAL_SURFACES or not surface,
            f"surface={surface!r}",
        )
    )
    if expect_surface:
        expect = canonical_surface(expect_surface) or expect_surface
        checks.append(
            Check(
                "accepted_surface_matches_expected",
                surface == expect,
                f"got={surface!r} expect={expect!r} proposed={proposed_surface!r}",
            )
        )
    else:
        checks.append(Check("accepted_surface_matches_expected", True, "n/a"))

    if expect_open is not None:
        checks.append(
            Check(
                "open_conversation_matches_expected",
                open_conv == expect_open,
                f"got={open_conv!r} expect={expect_open!r}",
            )
        )
    else:
        checks.append(Check("open_conversation_matches_expected", True, "n/a"))

    # Structural: conversation-descended surfaces keep a named open chat when
    # the prior had one and the proposal wiped it.
    prior_open = str(prior.get("open_conversation") or "").strip()
    prop_open = str(proposal.get("open_conversation") or "").strip()
    must_keep = (
        bool(prior_open)
        and not prop_open
        and surface in {"conversation", "context_menu", "forward_picker"}
    )
    checks.append(
        Check(
            "open_conversation_not_wiped_on_descended_surface",
            (not must_keep) or open_conv == prior_open,
            f"prior={prior_open!r} accepted={open_conv!r} surface={surface}",
        )
    )

    expected_role = expect_field_role or SURFACE_FIELD_ROLE.get(surface, "")
    if expected_role:
        checks.append(
            Check(
                "field_role_consistent_with_surface",
                role == expected_role or role == expect_field_role,
                f"role={role!r} expect={expected_role!r} surface={surface}",
            )
        )
    else:
        checks.append(Check("field_role_consistent_with_surface", True, "n/a"))

    # Picker/menu never host sidebar search role.
    checks.append(
        Check(
            "picker_field_role_not_sidebar_search",
            surface not in NO_SIDEBAR_SEARCH_SURFACES or role != "sidebar_search",
            f"surface={surface} role={role}",
        )
    )

    forbid = bool(getattr(verdict, "forbid_sidebar_search_motor", False))
    if expect_forbid_sidebar is not None:
        checks.append(
            Check(
                "sidebar_motor_gate_matches_expected",
                forbid is expect_forbid_sidebar,
                f"forbid={forbid} expect={expect_forbid_sidebar}",
            )
        )
    else:
        checks.append(
            Check(
                "sidebar_motor_gate_matches_expected",
                True,
                "n/a",
            )
        )
    checks.append(
        Check(
            "picker_forbids_sidebar_motor",
            surface not in NO_SIDEBAR_SEARCH_SURFACES or forbid,
            f"surface={surface} forbid={forbid}",
        )
    )

    # Illegal jump: if proposal asked for a non-parent search from picker,
    # accepted must not follow it.
    illegal_picker_to_search = (
        prior_surface in NO_SIDEBAR_SEARCH_SURFACES
        and proposed_surface in {"search", "chat_list"}
        and proposed_surface != prior_surface
    )
    checks.append(
        Check(
            "illegal_picker_to_search_rejected",
            (not illegal_picker_to_search) or surface == prior_surface,
            f"prior={prior_surface} proposed={proposed_surface} accepted={surface}",
        )
    )

    # Soft content: objects from a structurally-accepted proposal should land.
    prop_objects = proposal.get("objects") if isinstance(proposal.get("objects"), list) else []
    acc_objects = accepted.get("objects") if isinstance(accepted.get("objects"), list) else []
    structural_ok = (not expect_surface) or surface == (
        canonical_surface(expect_surface) or expect_surface
    )
    if prop_objects and structural_ok and surface == proposed_surface:
        checks.append(
            Check(
                "soft_objects_accepted_when_structure_ok",
                len(acc_objects) >= 1,
                f"proposed_objects={len(prop_objects)} accepted={len(acc_objects)}",
            )
        )
    else:
        checks.append(Check("soft_objects_accepted_when_structure_ok", True, "n/a"))

    # High-level representation: no motor scripts / click recipes in the doc.
    blob = json.dumps(accepted, ensure_ascii=False, default=str).lower()
    motorish = any(
        token in blob
        for token in (
            "cmd+f",
            "keydown",
            "ax_type",
            "click center",
            "osascript",
            "cgEvent",
        )
    )
    checks.append(
        Check(
            "representation_has_no_motor_scripts",
            not motorish,
            "document contains motor/mechanism strings",
        )
    )

    # Thinness: required high-level keys present.
    required = {"surface", "open_conversation", "objects", "beliefs", "progress"}
    checks.append(
        Check(
            "representation_has_core_keys",
            required.issubset(set(accepted.keys())) or {"surface", "open_conversation"}.issubset(
                set(accepted.keys())
            ),
            f"keys={sorted(accepted.keys())}",
        )
    )

    # Critic must leave a reason trail for structural fields.
    decisions = list(getattr(verdict, "decisions", None) or [])
    checks.append(
        Check(
            "critic_emits_decisions_with_reasons",
            bool(decisions) and all(str(getattr(d, "reason", "") or "").strip() for d in decisions),
            f"n_decisions={len(decisions)}",
        )
    )

    # Residual: prior keys survive when proposal omits them.
    if prior.get("progress") and not proposal.get("progress"):
        checks.append(
            Check(
                "residual_keeps_prior_progress_when_omitted",
                bool(accepted.get("progress")),
                str(accepted.get("progress"))[:80],
            )
        )
    else:
        checks.append(Check("residual_keeps_prior_progress_when_omitted", True, "n/a"))

    return checks


def run_scenario(scenario: WorldCriticScenario) -> Dict[str, Any]:
    verdict = critique_world_proposal(
        scenario.prior,
        scenario.proposal,
        last_action=scenario.last_action,
        observed_surface=scenario.observed_surface,
    )
    checks = score_accepted_representation(
        prior=scenario.prior,
        proposal=scenario.proposal,
        accepted=verdict.accepted_document,
        verdict=verdict,
        expect_surface=scenario.expect_surface,
        expect_open=scenario.expect_open,
        expect_field_role=scenario.expect_field_role,
        expect_forbid_sidebar=scenario.expect_forbid_sidebar,
    )
    by_name = {c.name: c for c in checks}
    failed_required = [
        name for name in scenario.require_pass if name in by_name and not by_name[name].passed
    ]
    unexpectedly_passed = [
        name for name in scenario.require_fail if name in by_name and by_name[name].passed
    ]
    ok = not failed_required and not unexpectedly_passed
    return {
        "name": scenario.name,
        "ok": ok,
        "accepted": {
            "surface": verdict.surface,
            "open_conversation": verdict.accepted_document.get("open_conversation"),
            "focused_field_role": verdict.focused_field_role,
            "forbid_sidebar_search_motor": verdict.forbid_sidebar_search_motor,
        },
        "failed_required": failed_required,
        "unexpectedly_passed": unexpectedly_passed,
        "checks": [c.to_dict() for c in checks],
        "decisions": [d.to_dict() for d in verdict.decisions],
    }


def run_trajectory(traj: WorldCriticTrajectory) -> Dict[str, Any]:
    doc = dict(traj.initial)
    step_results: List[Dict[str, Any]] = []
    all_checks: List[Check] = []
    for index, step in enumerate(traj.steps):
        verdict = critique_world_proposal(
            doc,
            step.proposal,
            last_action=step.last_action,
        )
        checks = score_accepted_representation(
            prior=doc,
            proposal=step.proposal,
            accepted=verdict.accepted_document,
            verdict=verdict,
            expect_surface=step.expect_surface,
            expect_open=step.expect_open,
            expect_field_role=step.expect_field_role,
            expect_forbid_sidebar=True
            if step.expect_surface in NO_SIDEBAR_SEARCH_SURFACES
            else None,
        )
        all_checks.extend(checks)
        step_results.append(
            {
                "step": index,
                "accepted_surface": verdict.surface,
                "accepted_open": verdict.accepted_document.get("open_conversation"),
                "field_role": verdict.focused_field_role,
                "failed": [c.name for c in checks if not c.passed],
            }
        )
        doc = dict(verdict.accepted_document)

    # For trajectories, require_pass means every instance of that check passed.
    failed_required = []
    for name in traj.require_pass:
        instances = [c for c in all_checks if c.name == name]
        if instances and not all(c.passed for c in instances):
            failed_required.append(name)
    ok = not failed_required and all(not s["failed"] for s in step_results)
    return {
        "name": traj.name,
        "ok": ok,
        "final": {
            "surface": doc.get("surface"),
            "open_conversation": doc.get("open_conversation"),
            "focused_field_role": doc.get("focused_field_role"),
        },
        "failed_required": failed_required,
        "steps": step_results,
    }


# ---------------------------------------------------------------------------
# Scenario fixtures — high-level representation updates
# ---------------------------------------------------------------------------


def _doc(
    surface: str,
    open_conversation: str = "",
    *,
    objects: Optional[List[Dict[str, Any]]] = None,
    progress: Optional[Dict[str, Any]] = None,
    field_role: str = "",
    beliefs: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    return {
        "surface": surface,
        "open_conversation": open_conversation,
        "focused_field_role": field_role or SURFACE_FIELD_ROLE.get(surface, ""),
        "objects": objects or [],
        "beliefs": beliefs or [],
        "progress": progress
        or {"phase": "", "objective": "", "notes": ""},
        "attempts": [],
        "exhausted": [],
    }


def _struct_pass(*extra: str) -> tuple:
    base = (
        "accepted_surface_matches_expected",
        "open_conversation_matches_expected",
        "field_role_consistent_with_surface",
        "representation_has_no_motor_scripts",
        "critic_emits_decisions_with_reasons",
        "representation_has_core_keys",
    )
    return base + tuple(extra)


def world_critic_scenarios() -> List[WorldCriticScenario]:
    """Screens along: find zarooratwala from Pallavi → forward to Tanmay."""
    zaroorat_msg = {
        "id": "m_z",
        "kind": "message",
        "text": "zarooratwala.com groceries link",
        "matches_goal": True,
        "point": [420, 540],
    }
    tanmay_row = {
        "id": "d_t",
        "kind": "contact",
        "text": "Tanmay",
        "matches_goal": True,
        "point": [300, 280],
    }
    return [
        # --- OPEN_SOURCE: chat list / search -------------------------------
        WorldCriticScenario(
            name="s00_blank_to_chat_list",
            prior=_doc("blank"),
            proposal=_doc(
                "chat_list",
                progress={"phase": "OPEN_SOURCE", "objective": "open Pallavi", "notes": ""},
            ),
            last_action="observe",
            expect_surface="chat_list",
            expect_open="",
            expect_field_role="sidebar_search",
            expect_forbid_sidebar=False,
            require_pass=_struct_pass(),
        ),
        WorldCriticScenario(
            name="s01_chat_list_to_sidebar_search",
            prior=_doc(
                "chat_list",
                progress={"phase": "OPEN_SOURCE", "objective": "Pallavi", "notes": ""},
            ),
            proposal=_doc("search", field_role="sidebar_search"),
            last_action="type_query",
            expect_surface="search",
            expect_open="",
            expect_field_role="sidebar_search",
            expect_forbid_sidebar=False,
            require_pass=_struct_pass("sidebar_motor_gate_matches_expected"),
        ),
        WorldCriticScenario(
            name="s02_search_holds_source_query",
            prior=_doc("search", field_role="sidebar_search"),
            proposal=_doc(
                "search",
                field_role="sidebar_search",
                objects=[{"id": "c1", "kind": "contact", "text": "Pallavi"}],
                progress={
                    "phase": "OPEN_SOURCE",
                    "objective": "open Pallavi",
                    "notes": "query=Pallavi zarooratwala",
                },
            ),
            last_action="type_query",
            expect_surface="search",
            expect_open="",
            expect_field_role="sidebar_search",
            expect_forbid_sidebar=False,
            require_pass=_struct_pass("soft_objects_accepted_when_structure_ok"),
        ),
        WorldCriticScenario(
            name="s03_search_opens_pallavi_conversation",
            prior=_doc("search", field_role="sidebar_search"),
            proposal=_doc(
                "conversation",
                "Pallavi",
                objects=[{"id": "m0", "kind": "message", "text": "Haa , Bas 2 min"}],
            ),
            last_action="open_entity",
            expect_surface="conversation",
            expect_open="Pallavi",
            expect_field_role="in_chat_or_composer",
            expect_forbid_sidebar=False,
            require_pass=_struct_pass("soft_objects_accepted_when_structure_ok"),
        ),
        WorldCriticScenario(
            name="s04_chat_list_direct_open_pallavi",
            prior=_doc("chat_list", progress={"phase": "OPEN_SOURCE", "objective": "Pallavi", "notes": ""}),
            proposal=_doc(
                "conversation",
                "Pallavi",
                objects=[{"id": "m1", "kind": "message", "text": "hi"}],
            ),
            last_action="open_entity",
            expect_surface="conversation",
            expect_open="Pallavi",
            expect_field_role="in_chat_or_composer",
            require_pass=_struct_pass("soft_objects_accepted_when_structure_ok"),
        ),
        # --- FIND_LINK: in-conversation hunt -------------------------------
        WorldCriticScenario(
            name="s05_conversation_locate_zarooratwala",
            prior=_doc(
                "conversation",
                "Pallavi",
                progress={"phase": "FIND_LINK", "objective": "zarooratwala", "notes": ""},
            ),
            proposal=_doc(
                "conversation",
                "Pallavi",
                objects=[zaroorat_msg],
                progress={
                    "phase": "FIND_LINK",
                    "objective": "zarooratwala",
                    "notes": "native_find queried",
                },
            ),
            last_action="locate_content",
            expect_surface="conversation",
            expect_open="Pallavi",
            expect_field_role="in_chat_or_composer",
            require_pass=_struct_pass("soft_objects_accepted_when_structure_ok"),
        ),
        WorldCriticScenario(
            name="s06_conversation_keeps_open_during_find",
            prior=_doc("conversation", "Pallavi"),
            proposal=_doc("conversation", ""),  # wipe attempt mid-hunt
            last_action="locate_content",
            expect_surface="conversation",
            expect_open="Pallavi",
            require_pass=(
                "open_conversation_not_wiped_on_descended_surface",
                "open_conversation_matches_expected",
                "accepted_surface_matches_expected",
            ),
        ),
        WorldCriticScenario(
            name="s07_select_zarooratwala_message",
            prior=_doc(
                "conversation",
                "Pallavi",
                objects=[zaroorat_msg],
                progress={"phase": "FIND_LINK", "objective": "zarooratwala", "notes": "visible"},
            ),
            proposal=_doc(
                "conversation",
                "Pallavi",
                objects=[zaroorat_msg],
                progress={
                    "phase": "FIND_LINK",
                    "objective": "select zarooratwala message",
                    "notes": "selected",
                },
            ),
            last_action="select_content",
            expect_surface="conversation",
            expect_open="Pallavi",
            require_pass=_struct_pass(),
        ),
        WorldCriticScenario(
            name="s08_reject_sidebar_search_while_hunting",
            prior=_doc(
                "conversation",
                "Pallavi",
                progress={"phase": "FIND_LINK", "objective": "zarooratwala", "notes": ""},
            ),
            proposal=_doc("search", "", field_role="sidebar_search"),
            last_action="locate_content",
            expect_surface="conversation",
            expect_open="Pallavi",
            require_pass=(
                "accepted_surface_matches_expected",
                "open_conversation_not_wiped_on_descended_surface",
            ),
        ),
        # --- OPEN_FORWARD: context menu ------------------------------------
        WorldCriticScenario(
            name="s09_reveal_forward_menu",
            prior=_doc("conversation", "Pallavi", objects=[zaroorat_msg]),
            proposal=_doc(
                "context_menu",
                "Pallavi",
                objects=[
                    {"id": "a1", "kind": "affordance", "text": "Forward"},
                    {"id": "a2", "kind": "affordance", "text": "Copy"},
                ],
            ),
            last_action="reveal_actions",
            expect_surface="context_menu",
            expect_open="Pallavi",
            expect_field_role="none",
            expect_forbid_sidebar=True,
            require_pass=_struct_pass(
                "picker_forbids_sidebar_motor",
                "soft_objects_accepted_when_structure_ok",
            ),
        ),
        WorldCriticScenario(
            name="s10_keep_open_when_menu_clears_open",
            prior=_doc("conversation", "Pallavi"),
            proposal=_doc("context_menu", ""),
            last_action="reveal_actions",
            expect_surface="context_menu",
            expect_open="Pallavi",
            expect_field_role="none",
            expect_forbid_sidebar=True,
            require_pass=(
                "accepted_surface_matches_expected",
                "open_conversation_not_wiped_on_descended_surface",
                "open_conversation_matches_expected",
            ),
        ),
        WorldCriticScenario(
            name="s11_reject_menu_to_sidebar_search",
            prior=_doc("context_menu", "Pallavi"),
            proposal=_doc("search", "", field_role="sidebar_search"),
            last_action="type_query",
            expect_surface="context_menu",
            expect_open="Pallavi",
            expect_forbid_sidebar=True,
            require_pass=(
                "accepted_surface_matches_expected",
                "illegal_picker_to_search_rejected",
                "picker_forbids_sidebar_motor",
            ),
        ),
        # --- PICK_DEST: forward picker -------------------------------------
        WorldCriticScenario(
            name="s12_accept_forward_picker_after_invoke",
            prior=_doc("context_menu", "Pallavi"),
            proposal=_doc(
                "forward_picker",
                "Pallavi",
                objects=[tanmay_row],
                progress={
                    "phase": "PICK_DEST",
                    "objective": "Tanmay",
                    "notes": "",
                },
            ),
            last_action="invoke_affordance",
            expect_surface="forward_picker",
            expect_open="Pallavi",
            expect_field_role="destination_filter",
            expect_forbid_sidebar=True,
            require_pass=_struct_pass(
                "picker_forbids_sidebar_motor",
                "soft_objects_accepted_when_structure_ok",
            ),
        ),
        WorldCriticScenario(
            name="s13_picker_destination_filter_role",
            prior=_doc("forward_picker", "Pallavi", field_role="destination_filter"),
            proposal=_doc(
                "forward_picker",
                "Pallavi",
                field_role="destination_filter",
                objects=[tanmay_row],
                progress={
                    "phase": "PICK_DEST",
                    "objective": "filter Tanmay",
                    "notes": "typed destination",
                },
            ),
            last_action="type_query",
            expect_surface="forward_picker",
            expect_open="Pallavi",
            expect_field_role="destination_filter",
            expect_forbid_sidebar=True,
            require_pass=_struct_pass(
                "picker_field_role_not_sidebar_search",
                "sidebar_motor_gate_matches_expected",
            ),
        ),
        WorldCriticScenario(
            name="s14_coerce_sidebar_role_on_picker",
            prior=_doc("conversation", "Pallavi"),
            proposal=_doc(
                "forward_picker",
                "Pallavi",
                field_role="sidebar_search",
            ),
            last_action="invoke_affordance",
            expect_surface="forward_picker",
            expect_open="Pallavi",
            expect_field_role="destination_filter",
            expect_forbid_sidebar=True,
            require_pass=(
                "field_role_consistent_with_surface",
                "picker_field_role_not_sidebar_search",
            ),
        ),
        WorldCriticScenario(
            name="s15_reject_picker_to_sidebar_search",
            prior=_doc("forward_picker", "Pallavi", field_role="destination_filter"),
            proposal=_doc("search", "", field_role="sidebar_search"),
            last_action="type_query",
            expect_surface="forward_picker",
            expect_open="Pallavi",
            expect_field_role="destination_filter",
            expect_forbid_sidebar=True,
            require_pass=(
                "accepted_surface_matches_expected",
                "illegal_picker_to_search_rejected",
                "open_conversation_not_wiped_on_descended_surface",
                "picker_forbids_sidebar_motor",
                "sidebar_motor_gate_matches_expected",
            ),
        ),
        WorldCriticScenario(
            name="s16_reject_picker_to_chat_list",
            prior=_doc("forward_picker", "Pallavi"),
            proposal=_doc("chat_list", ""),
            last_action="open_entity",
            expect_surface="forward_picker",
            expect_open="Pallavi",
            expect_forbid_sidebar=True,
            require_pass=(
                "accepted_surface_matches_expected",
                "illegal_picker_to_search_rejected",
                "open_conversation_matches_expected",
            ),
        ),
        # --- dialog / cancel recovery --------------------------------------
        WorldCriticScenario(
            name="s17_dialog_over_picker_keeps_open",
            prior=_doc("forward_picker", "Pallavi", field_role="destination_filter"),
            proposal=_doc(
                "dialog",
                "Pallavi",
                objects=[{"id": "b1", "kind": "button", "text": "Cancel"}],
            ),
            last_action="click",
            expect_surface="dialog",
            expect_open="Pallavi",
            expect_forbid_sidebar=True,
            require_pass=_struct_pass("picker_forbids_sidebar_motor"),
        ),
        WorldCriticScenario(
            name="s18_dialog_back_to_conversation",
            prior=_doc("dialog", "Pallavi"),
            proposal=_doc("conversation", "Pallavi", objects=[zaroorat_msg]),
            last_action="dismiss_transient",
            expect_surface="conversation",
            expect_open="Pallavi",
            require_pass=_struct_pass(),
        ),
        # --- residual / negative -------------------------------------------
        WorldCriticScenario(
            name="s19_residual_keeps_find_progress",
            prior=_doc(
                "conversation",
                "Pallavi",
                progress={
                    "phase": "FIND_LINK",
                    "objective": "zarooratwala",
                    "notes": "native find tried",
                },
            ),
            proposal={
                "surface": "conversation",
                "open_conversation": "Pallavi",
            },
            last_action="locate_content",
            expect_surface="conversation",
            expect_open="Pallavi",
            require_pass=(
                "residual_keeps_prior_progress_when_omitted",
                "accepted_surface_matches_expected",
            ),
        ),
        WorldCriticScenario(
            name="s20_negative_illegal_jump_expect_fail_checks",
            prior=_doc("forward_picker", "Pallavi"),
            proposal=_doc("search"),
            last_action="type_query",
            expect_surface="search",  # broken critic would accept this
            expect_open="",
            require_fail=("accepted_surface_matches_expected",),
            require_pass=("illegal_picker_to_search_rejected",),
        ),
    ]


def world_critic_trajectories() -> List[WorldCriticTrajectory]:
    zaroorat_msg = {
        "id": "m_z",
        "kind": "message",
        "text": "zarooratwala.com groceries link",
        "matches_goal": True,
    }
    tanmay_row = {"id": "d_t", "kind": "contact", "text": "Tanmay", "matches_goal": True}
    return [
        WorldCriticTrajectory(
            name="zarooratwala_forward_full_screen_path",
            initial=_doc(
                "chat_list",
                progress={"phase": "OPEN_SOURCE", "objective": "Pallavi", "notes": ""},
            ),
            steps=(
                TrajectoryStep(
                    proposal=_doc("search", field_role="sidebar_search"),
                    last_action="type_query",
                    expect_surface="search",
                    expect_open="",
                    expect_field_role="sidebar_search",
                ),
                TrajectoryStep(
                    proposal=_doc(
                        "conversation",
                        "Pallavi",
                        progress={
                            "phase": "FIND_LINK",
                            "objective": "zarooratwala",
                            "notes": "opened source",
                        },
                    ),
                    last_action="open_entity",
                    expect_surface="conversation",
                    expect_open="Pallavi",
                    expect_field_role="in_chat_or_composer",
                ),
                TrajectoryStep(
                    proposal=_doc(
                        "conversation",
                        "Pallavi",
                        objects=[zaroorat_msg],
                        progress={
                            "phase": "FIND_LINK",
                            "objective": "zarooratwala",
                            "notes": "located",
                        },
                    ),
                    last_action="locate_content",
                    expect_surface="conversation",
                    expect_open="Pallavi",
                    expect_field_role="in_chat_or_composer",
                ),
                TrajectoryStep(
                    proposal=_doc(
                        "conversation",
                        "Pallavi",
                        objects=[zaroorat_msg],
                        progress={
                            "phase": "FIND_LINK",
                            "objective": "select message",
                            "notes": "",
                        },
                    ),
                    last_action="select_content",
                    expect_surface="conversation",
                    expect_open="Pallavi",
                    expect_field_role="in_chat_or_composer",
                ),
                TrajectoryStep(
                    proposal=_doc(
                        "context_menu",
                        "",
                        objects=[{"id": "a1", "kind": "affordance", "text": "Forward"}],
                    ),
                    last_action="reveal_actions",
                    expect_surface="context_menu",
                    expect_open="Pallavi",
                    expect_field_role="none",
                ),
                TrajectoryStep(
                    proposal=_doc(
                        "forward_picker",
                        "Pallavi",
                        objects=[tanmay_row],
                        progress={
                            "phase": "PICK_DEST",
                            "objective": "Tanmay",
                            "notes": "",
                        },
                    ),
                    last_action="invoke_affordance",
                    expect_surface="forward_picker",
                    expect_open="Pallavi",
                    expect_field_role="destination_filter",
                ),
                TrajectoryStep(
                    proposal=_doc(
                        "forward_picker",
                        "Pallavi",
                        field_role="destination_filter",
                        objects=[tanmay_row],
                        progress={
                            "phase": "PICK_DEST",
                            "objective": "Tanmay",
                            "notes": "filtered",
                        },
                    ),
                    last_action="type_query",
                    expect_surface="forward_picker",
                    expect_open="Pallavi",
                    expect_field_role="destination_filter",
                ),
                # Classic drift: Cmd+F / source search while picker open.
                TrajectoryStep(
                    proposal=_doc("search", "", field_role="sidebar_search"),
                    last_action="type_query",
                    expect_surface="forward_picker",
                    expect_open="Pallavi",
                    expect_field_role="destination_filter",
                ),
                TrajectoryStep(
                    proposal=_doc(
                        "dialog",
                        "Pallavi",
                        objects=[{"id": "b1", "kind": "button", "text": "Cancel"}],
                    ),
                    last_action="click",
                    expect_surface="dialog",
                    expect_open="Pallavi",
                    expect_field_role="dialog_field",
                ),
            ),
            require_pass=(
                "accepted_surface_matches_expected",
                "illegal_picker_to_search_rejected",
                "open_conversation_not_wiped_on_descended_surface",
                "picker_forbids_sidebar_motor",
                "representation_has_no_motor_scripts",
            ),
        ),
        WorldCriticTrajectory(
            name="open_source_without_search_bar",
            initial=_doc("chat_list"),
            steps=(
                TrajectoryStep(
                    proposal=_doc("conversation", "Pallavi"),
                    last_action="open_entity",
                    expect_surface="conversation",
                    expect_open="Pallavi",
                    expect_field_role="in_chat_or_composer",
                ),
                TrajectoryStep(
                    proposal=_doc("conversation", "Pallavi", objects=[zaroorat_msg]),
                    last_action="locate_content",
                    expect_surface="conversation",
                    expect_open="Pallavi",
                ),
                TrajectoryStep(
                    proposal=_doc("context_menu", "Pallavi"),
                    last_action="reveal_actions",
                    expect_surface="context_menu",
                    expect_open="Pallavi",
                ),
                TrajectoryStep(
                    proposal=_doc("forward_picker", "Pallavi", objects=[tanmay_row]),
                    last_action="invoke_affordance",
                    expect_surface="forward_picker",
                    expect_open="Pallavi",
                    expect_field_role="destination_filter",
                ),
            ),
            require_pass=(
                "accepted_surface_matches_expected",
                "open_conversation_matches_expected",
                "field_role_consistent_with_surface",
            ),
        ),
    ]


def evaluate_world_critic_scenarios() -> Dict[str, Any]:
    results = [run_scenario(s) for s in world_critic_scenarios()]
    failed = [r["name"] for r in results if not r["ok"]]
    return {
        "scenario_count": len(results),
        "passed": len(results) - len(failed),
        "failed": failed,
        "results": results,
    }


def evaluate_world_critic_trajectories() -> Dict[str, Any]:
    results = [run_trajectory(t) for t in world_critic_trajectories()]
    failed = [r["name"] for r in results if not r["ok"]]
    return {
        "trajectory_count": len(results),
        "passed": len(results) - len(failed),
        "failed": failed,
        "results": results,
    }


def render_report(scenarios: Dict[str, Any], trajectories: Dict[str, Any]) -> str:
    lines = [
        "World-critic representation eval",
        f"  scenarios    {scenarios['passed']}/{scenarios['scenario_count']} passed"
        + (f"  failed: {scenarios['failed']}" if scenarios["failed"] else ""),
        f"  trajectories {trajectories['passed']}/{trajectories['trajectory_count']} passed"
        + (f"  failed: {trajectories['failed']}" if trajectories["failed"] else ""),
        "",
        "Scenarios",
        "---------",
    ]
    for result in scenarios.get("results") or []:
        status = "PASS" if result.get("ok") else "FAIL"
        accepted = result.get("accepted") or {}
        lines.append(f"[{status}] {result['name']}")
        lines.append(
            "      surface={surface!r}  open={open!r}  field_role={role!r}  "
            "forbid_sidebar_motor={forbid}".format(
                surface=accepted.get("surface"),
                open=accepted.get("open_conversation"),
                role=accepted.get("focused_field_role"),
                forbid=accepted.get("forbid_sidebar_search_motor"),
            )
        )
        if not result.get("ok"):
            lines.append(
                f"      failed_required={result.get('failed_required')} "
                f"unexpectedly_passed={result.get('unexpectedly_passed')}"
            )
    lines.extend(["", "Trajectories", "------------"])
    for result in trajectories.get("results") or []:
        status = "PASS" if result.get("ok") else "FAIL"
        lines.append(f"[{status}] {result['name']}")
        lines.append(f"      final={result.get('final')}")
        for step in result.get("steps") or []:
            mark = "ok" if not step.get("failed") else "FAIL"
            line = (
                f"      step {step['step']}: [{mark}] "
                f"surface={step.get('accepted_surface')!r} "
                f"open={step.get('accepted_open')!r} "
                f"role={step.get('field_role')!r}"
            )
            if step.get("failed"):
                line += f"  failed={step['failed']}"
            lines.append(line)
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args()
    scenarios = evaluate_world_critic_scenarios()
    trajectories = evaluate_world_critic_trajectories()
    report = {"scenarios": scenarios, "trajectories": trajectories}
    print(render_report(scenarios, trajectories))
    if args.json:
        args.json.write_text(json.dumps(report, indent=2, ensure_ascii=False))
        print(f"\nfull report: {args.json}")
    failed = bool(scenarios.get("failed") or trajectories.get("failed"))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
