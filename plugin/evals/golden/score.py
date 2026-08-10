"""Score current code against the frozen module golden corpus.

Usage:
    python -m plugin.evals.golden.score
    python -m plugin.evals.run   # includes [golden_v1] block
"""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from plugin.evals.annotations import annotate, load_overrides
from plugin.evals.corpus import DEFAULT_CORPUS_DIR, load_fixtures
from plugin.evals.fusion import _proposal_from_response, score_fusion_reading
from plugin.evals.golden.schema import (
    DEFAULT_GOLDEN_DIR,
    GOLDEN_MODULES,
    GOLDEN_VERSION,
    GoldenCase,
    load_all_cases,
    load_manifest,
)
from plugin.evals.metrics import MetricResult

LAYER = "golden"


def _norm(text: Any) -> str:
    return str(text or "").strip().lower()


def _rate(hits: float, total: float) -> Optional[float]:
    return None if total <= 0 else hits / total


def _is_search_chrome(text: Any) -> bool:
    raw = str(text or "").strip()
    if not raw:
        return False
    low = raw.lower()
    if re.match(r"^(q\s+)?search\|?$", low):
        return True
    return low.startswith("q ") and "search" in low


@dataclass
class CaseScore:
    case_id: str
    module: str
    passed: bool
    checks: List[Dict[str, Any]] = field(default_factory=list)
    detail: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "module": self.module,
            "passed": self.passed,
            "checks": self.checks,
            "detail": self.detail,
            "failures": [c["name"] for c in self.checks if not c.get("passed")],
        }


def _check(name: str, passed: bool, detail: str = "") -> Dict[str, Any]:
    return {"name": name, "passed": bool(passed), "detail": detail}


# ---------------------------------------------------------------------------
# Perceive
# ---------------------------------------------------------------------------


def score_perceive_case(
    case: GoldenCase,
    fixtures_by_id: Dict[str, Any],
) -> CaseScore:
    result = CaseScore(case_id=case.id, module="perceive", passed=False)
    fixture_id = str((case.input or {}).get("fixture_id") or "")
    fixture = fixtures_by_id.get(fixture_id)
    gold = case.gold or {}
    if fixture is None or not fixture.response:
        result.checks = [_check("fixture_available", False, f"missing {fixture_id}")]
        return result

    reading = _proposal_from_response(fixture.response)
    fusion = score_fusion_reading(fixture, reading)
    surface_ok = any(c.name == "surface_matches_gold" and c.passed for c in fusion.checks)
    # Prefer golden surface over fixture annotation when both exist.
    got_surface = _norm(
        (reading.get("world_model") or {}).get("surface")
        or (reading.get("observed_state") or {}).get("surface")
    )
    expect_surface = _norm(gold.get("surface"))
    if expect_surface:
        surface_ok = got_surface == expect_surface

    got_open = str(
        (reading.get("world_model") or {}).get("open_conversation")
        or (reading.get("observed_state") or {}).get("open_conversation")
        or ""
    ).strip()
    expect_open = str(gold.get("open_conversation") or "").strip()
    open_ok = True
    if "open_conversation" in gold:
        if expect_open:
            open_ok = _norm(expect_open) in _norm(got_open)
        else:
            open_ok = not got_open or _is_search_chrome(got_open) is False and got_open == ""

    chrome_ok = True
    for echo in gold.get("forbidden_open_echo") or []:
        if _norm(echo) and _norm(echo) in _norm(got_open):
            chrome_ok = False
            break
    if _is_search_chrome(got_open):
        chrome_ok = False

    mentions_ok = True
    objects = (reading.get("world_model") or {}).get("objects") or []
    blob = " ".join(
        str(o.get("text") or o.get("label") or "") for o in objects if isinstance(o, dict)
    ).lower()
    for token in gold.get("objects_must_mention") or []:
        if _norm(token) and _norm(token) not in blob and _norm(token) not in _norm(got_open):
            mentions_ok = False

    target_ok = True
    if "target_visible" in gold:
        state = reading.get("observed_state") if isinstance(reading.get("observed_state"), dict) else {}
        got_vis = state.get("target_object_visible")
        expect_vis = gold.get("target_visible")
        if expect_vis is False:
            target_ok = got_vis is False or got_vis is None
        elif expect_vis is True:
            target_ok = got_vis is True

    result.checks = [
        _check("surface", surface_ok, f"expect={expect_surface!r} got={got_surface!r}"),
        _check("open_conversation", open_ok, f"expect={expect_open!r} got={got_open!r}"),
        _check("no_search_chrome_open", chrome_ok, f"open={got_open!r}"),
        _check("objects_mention", mentions_ok, f"required={gold.get('objects_must_mention')}"),
        _check("target_visibility", target_ok, f"expect={gold.get('target_visible')}"),
    ]
    result.passed = all(c["passed"] for c in result.checks)
    return result


# ---------------------------------------------------------------------------
# Critic
# ---------------------------------------------------------------------------


def score_critic_case(case: GoldenCase) -> CaseScore:
    from plugin.agent.world_critic import critique_world_proposal, is_search_field_echo

    result = CaseScore(case_id=case.id, module="critic", passed=False)
    inp = case.input or {}
    gold = case.gold or {}
    prior = dict(inp.get("prior") or {})
    proposal = dict(inp.get("proposal") or {})
    last_action = str(inp.get("last_action") or "")
    observed_surface = str(inp.get("observed_surface") or "")
    prediction_error = inp.get("prediction_error")
    verdict = critique_world_proposal(
        prior,
        proposal,
        last_action=last_action,
        observed_surface=observed_surface,
        prediction_error=prediction_error if isinstance(prediction_error, dict) else None,
    )
    accepted = dict(verdict.accepted_document or {})
    got_surface = _norm(accepted.get("surface"))
    got_open = str(accepted.get("open_conversation") or "").strip()
    expect_surface = _norm(gold.get("accepted_surface"))
    expect_open = str(gold.get("accepted_open") or "").strip()

    result.checks = [
        _check(
            "accepted_surface",
            got_surface == expect_surface if expect_surface else True,
            f"expect={expect_surface!r} got={got_surface!r}",
        ),
        _check(
            "accepted_open",
            (not expect_open) or _norm(expect_open) in _norm(got_open),
            f"expect={expect_open!r} got={got_open!r}",
        ),
    ]
    if gold.get("must_reject_search_chrome_open"):
        result.checks.append(
            _check(
                "rejected_search_chrome_open",
                not is_search_field_echo(got_open) and not _is_search_chrome(got_open),
                f"accepted_open={got_open!r}",
            )
        )
    if gold.get("youtube_not_binding_eligible"):
        from plugin.agent.source_query_binding import scrub_matches_goal_flags

        query = str(
            gold.get("source_query")
            or inp.get("source_query")
            or "zarooratwala"
        ).strip()
        scrubbed = scrub_matches_goal_flags(
            accepted,
            query=query,
            expected_container=str(accepted.get("open_conversation") or ""),
        )
        yt_still = False
        for obj in scrubbed.get("objects") or []:
            if not isinstance(obj, dict):
                continue
            text = str(obj.get("text") or "").lower()
            if ("youtu.be" in text or "youtube.com" in text) and bool(
                obj.get("matches_goal")
            ):
                yt_still = True
                break
        result.checks.append(
            _check(
                "youtube_not_binding_eligible",
                not yt_still,
                "YouTube object still matches_goal after source_query scrub",
            )
        )
    result.passed = all(c["passed"] for c in result.checks)
    return result


# ---------------------------------------------------------------------------
# Meta-action
# ---------------------------------------------------------------------------


def score_meta_action_case(case: GoldenCase) -> CaseScore:
    from plugin.agent.executive.hierarchy import decision_ladder
    from plugin.agent.executive.meta_action import (
        MetaAction,
        MetaChoice,
        MetaContext,
        select_meta_action,
    )
    from plugin.agent.executive.meta_consultation import meta_context_packet
    from plugin.agent.executive.meta_situation import (
        META_PACKET_REQUIRED_SECTIONS,
        situation_from_mapping,
    )
    from plugin.agent.executive.sufficiency import DecisionSufficiency

    result = CaseScore(case_id=case.id, module="meta_action", passed=False)
    inp = case.input or {}
    gold = case.gold or {}
    suff_raw = inp.get("sufficiency") if isinstance(inp.get("sufficiency"), dict) else {}
    sufficiency = None
    if suff_raw:
        blocking = [str(b) for b in (suff_raw.get("blocking_uncertainties") or []) if str(b).strip()]
        sufficiency = DecisionSufficiency(
            sufficient_to_act=bool(suff_raw.get("sufficient_to_act")),
            observe_has_value=bool(suff_raw.get("observe_has_value")),
            suppress_observe=bool(suff_raw.get("suppress_observe")),
            needs_exploration=bool(suff_raw.get("needs_exploration")),
            blocking_uncertainties=blocking,
            useful_information_actions=[
                str(x) for x in (suff_raw.get("useful_information_actions") or [])[:4]
            ],
            sufficient_for_which_actions=[
                str(x) for x in (suff_raw.get("sufficient_for_which_actions") or [])[:4]
            ],
            confidence=float(suff_raw.get("confidence") or 0.0),
            reason=str(suff_raw.get("reason") or "golden")[:160],
        )
    elif bool(inp.get("has_grounded_action")) and not inp.get("awaiting_verification"):
        # Legacy contract cases that only set has_grounded_action.
        sufficiency = DecisionSufficiency(
            sufficient_to_act=True,
            observe_has_value=False,
            suppress_observe=True,
            needs_exploration=False,
            blocking_uncertainties=[],
            useful_information_actions=[],
            sufficient_for_which_actions=["act"],
            confidence=0.8,
            reason="golden: sufficient to act",
        )

    fitness = (
        inp.get("branch_fitness")
        if isinstance(inp.get("branch_fitness"), dict)
        else None
    )
    branch_unfit = bool(inp.get("branch_unfit"))
    if fitness is not None and fitness.get("admissible") is False:
        branch_unfit = True
    ctx = MetaContext(
        awaiting_verification=bool(inp.get("awaiting_verification")),
        last_action_surprised=bool(inp.get("last_action_surprised")),
        post_action_look_owed=bool(inp.get("post_action_look_owed")),
        has_grounded_action=bool(inp.get("has_grounded_action")),
        reperception_exhausted=bool(inp.get("reperception_exhausted")),
        branch_stale=bool(inp.get("branch_stale")),
        hard_block=bool(inp.get("hard_block")),
        probe_available=bool(inp.get("probe_available")),
        ambiguous=bool(inp.get("ambiguous")),
        question_settled=bool(inp.get("question_settled")),
        backtrack_exhausted=bool(inp.get("backtrack_exhausted")),
        information_gathering_exhausted=bool(inp.get("information_gathering_exhausted")),
        think_exhausted=bool(inp.get("think_exhausted")),
        probe_exhausted=bool(inp.get("probe_exhausted")),
        perceive_streak_exhausted=bool(inp.get("perceive_streak_exhausted")),
        steps_remaining=int(inp.get("steps_remaining") or 99),
        sufficiency=sufficiency,
        branch_unfit=branch_unfit,
        branch_fitness=fitness,
        destination_search_needed=bool(inp.get("destination_search_needed")),
        act_clear=bool(inp.get("act_clear")),
        search_exhausted=bool(inp.get("search_exhausted")),
        search_has_criteria=bool(inp.get("search_has_criteria", True)),
        referent_repair_owed=bool(inp.get("referent_repair_owed")),
        route_discovery_owed=bool(inp.get("route_discovery_owed")),
        intention_explore_active=bool(inp.get("intention_explore_active")),
        intention_locally_exhausted=bool(inp.get("intention_locally_exhausted")),
        address_known=bool(inp.get("address_known")),
        referent_search_needed=bool(inp.get("referent_search_needed")),
        retrieve_ready=bool(inp.get("retrieve_ready")),
        search_episode_incomplete=bool(inp.get("search_episode_incomplete")),
        search_episode_complete=bool(inp.get("search_episode_complete")),
        search_retreat_owed=bool(inp.get("search_retreat_owed")),
        role_identity_search_owed=bool(inp.get("role_identity_search_owed")),
    )
    situation = situation_from_mapping(
        inp.get("situation") if isinstance(inp.get("situation"), dict) else {}
    )
    goal_complete = bool(inp.get("goal_complete"))
    score_via = _norm(gold.get("score_via") or "ladder")
    packet = meta_context_packet(ctx, goal_complete=goal_complete, situation=situation)
    got_capability = ""
    if score_via == "sanitize":
        from plugin.agent.executive.meta_consultation import sanitize_meta_choice

        stub = inp.get("stub_choice") if isinstance(inp.get("stub_choice"), dict) else {}
        if not stub:
            stub = {
                "meta_action": gold.get("meta_action") or "act",
                "capability": gold.get("capability") or "",
                "why": "golden stub",
                "confidence": 0.9,
            }
        choice = sanitize_meta_choice(
            stub, ctx, goal_complete=goal_complete, situation=situation
        )
        if choice is None:
            choice = MetaChoice(MetaAction.ASK, "sanitize rejected", {})
        got_capability = str(getattr(choice, "capability", "") or "")
    elif score_via == "scorer":
        choice = select_meta_action(ctx)
    else:
        choice = decision_ladder(ctx, goal_complete=goal_complete)
    got = choice.action.value if isinstance(choice.action, MetaAction) else str(choice.action)
    expect = _norm(gold.get("meta_action"))
    forbidden = {_norm(x) for x in (gold.get("forbidden_meta") or [])}

    missing_sections = [s for s in META_PACKET_REQUIRED_SECTIONS if s not in packet]
    # Mined cases also require look_debt / evidence discriminators to be populated.
    look = packet.get("look_debt") if isinstance(packet.get("look_debt"), dict) else {}
    evidence = packet.get("evidence") if isinstance(packet.get("evidence"), dict) else {}
    packet_shaped = (
        "post_action_look_owed" in look
        and "has_grounded_action" in evidence
        and "allowed_meta_actions" in packet
    )
    hk = packet.get("options") if isinstance(packet.get("options"), dict) else {}
    blockers = packet.get("blockers") if isinstance(packet.get("blockers"), dict) else {}
    expect_cap = _norm(gold.get("capability"))
    capability_any = {_norm(x) for x in (gold.get("capability_any_of") or []) if str(x).strip()}
    cap_ok = True
    if expect_cap or capability_any:
        cap_ok = (got_capability == expect_cap) if expect_cap else (got_capability in capability_any)
    packet_hk_ok = True
    if gold.get("packet_has_housekeeping"):
        packet_hk_ok = bool(hk.get("housekeeping_capabilities")) and bool(
            blockers.get("storage_pressure") or blockers.get("system_warnings")
        )

    result.checks = [
        _check("meta_action", _norm(got) == expect if expect else True, f"expect={expect!r} got={got!r}"),
        _check(
            "forbidden_meta",
            _norm(got) not in forbidden,
            f"got={got!r} forbidden={sorted(forbidden)}",
        ),
        _check(
            "packet_sections",
            not missing_sections,
            f"missing={missing_sections}",
        ),
        _check("packet_shaped", packet_shaped, "look_debt/evidence incomplete"),
        _check(
            "capability",
            cap_ok,
            f"expect={expect_cap or sorted(capability_any)!r} got={got_capability!r}",
        ),
        _check("packet_housekeeping", packet_hk_ok, "blockers/housekeeping missing from packet"),
    ]
    result.passed = all(c["passed"] for c in result.checks)
    return result


# ---------------------------------------------------------------------------
# Brain
# ---------------------------------------------------------------------------


def score_brain_case(case: GoldenCase) -> CaseScore:
    """Score brain goldens via a stub chooser + sanitizer (LLM-off offline).

    Live choice is LLM-only. Offline gold asserts the *admissible* capability on
    this accepted world: a stub proposes ``gold.capability`` and sanitize /
    apply_decision_consultation must keep it (not rewrite to observe or a
    forbidden family).
    """
    from plugin.agent.brain import choose_next_capability
    from plugin.agent.goal import Goal
    from plugin.agent.unified_cognition import UnifiedProposal

    result = CaseScore(case_id=case.id, module="brain", passed=False)
    inp = case.input or {}
    gold = case.gold or {}
    g = dict(inp.get("goal") or {})
    goal = Goal(
        kind=str(g.get("kind") or "whatsapp_forward_message"),
        app="WhatsApp",
        contact=str(g.get("contact") or g.get("source_conversation") or ""),
        link_query=str(g.get("link_query") or g.get("source_query") or ""),
        target_contact=str(g.get("target_contact") or g.get("destination") or ""),
    )
    world = dict(inp.get("accepted_world") or {})
    expect = _norm(gold.get("capability"))
    any_of = {_norm(x) for x in (gold.get("capability_any_of") or []) if str(x).strip()}
    forbidden = {_norm(x) for x in (gold.get("forbidden_families") or [])}
    stub_cap = expect or (sorted(any_of)[0] if any_of else "observe")
    stub_target = str(
        gold.get("target")
        or g.get("link_query")
        or g.get("source_query")
        or g.get("contact")
        or ""
    )

    class _StubChooser:
        def choose(self, system: str, packet: Dict[str, Any]) -> Dict[str, Any]:
            return {
                "capability": stub_cap,
                "target": stub_target,
                "why": "golden_stub_chooser",
                "confidence": 0.9,
            }

    from plugin.agent.decision_consultation import (
        build_decision_brief,
        sanitize_decision,
    )

    prev = os.environ.get("HERMES_DECISION_LLM")
    os.environ["HERMES_DECISION_LLM"] = "0"
    realization = ""
    try:
        proposal = UnifiedProposal(
            world_model=dict(world),
            observed_state={
                "surface": world.get("surface"),
                "open_conversation": world.get("open_conversation"),
                "target_object_visible": bool(inp.get("target_visible")),
            },
            next_action={},
        )

        class _Features:
            conversation_open = _norm(world.get("surface")) == "conversation"
            extras: Dict[str, Any] = {
                "open_conversation": str(world.get("open_conversation") or ""),
                "wa_screen": str(world.get("surface") or ""),
            }

        class _State:
            unified_world_document = dict(world)
            search_attempt_log: List[Any] = []
            last_plan_step = None

        features = _Features()
        state = _State()
        brief = build_decision_brief(
            goal,
            world_document=world,
            features=features,
            execution_state=state,
            perceptor_suggestions=[],
            affordance_qc={},
        )
        admitted = sanitize_decision(
            {
                "capability": stub_cap,
                "target": stub_target,
                "why": "golden_stub_chooser",
                "confidence": 0.9,
            },
            brief,
        )
        trace = choose_next_capability(
            proposal,
            goal,
            features=features,
            execution_state=state,
            chooser=_StubChooser(),
        )
        family = _norm((proposal.next_action or {}).get("family"))
        if isinstance(trace, dict):
            realization = str(trace.get("realization") or "")
    finally:
        if prev is None:
            os.environ.pop("HERMES_DECISION_LLM", None)
        else:
            os.environ["HERMES_DECISION_LLM"] = prev

    # Admissible at sanitize, then either applied or demoted only for missing
    # GroundedUiTarget geometry (hunt often has no Find site offline).
    geometry_demote = family == "observe" and "geometry_required_missing" in realization
    if expect:
        cap_ok = family == expect or (geometry_demote and admitted.ok and _norm(admitted.capability) == expect)
        detail = f"expect={expect!r} got={family!r} realization={realization!r}"
    elif any_of:
        cap_ok = family in any_of or (
            geometry_demote and admitted.ok and _norm(admitted.capability) in any_of
        )
        detail = f"expect_any={sorted(any_of)} got={family!r}"
    else:
        cap_ok = bool(family)
        detail = f"got={family!r}"

    result.checks = [
        _check(
            "admissible",
            bool(admitted.ok),
            f"sanitize={admitted.why!r} cap={admitted.capability!r}",
        ),
        _check("capability", cap_ok, detail),
        _check(
            "forbidden_families",
            family not in forbidden,
            f"got={family!r} forbidden={sorted(forbidden)}",
        ),
    ]
    result.passed = all(c["passed"] for c in result.checks)
    result.detail = f"phase_hint={gold.get('phase_hint')!r}"
    return result


# ---------------------------------------------------------------------------
# Actor
# ---------------------------------------------------------------------------


def _brief_from_gold_input(raw: Dict[str, Any]):
    from plugin.agent.actor import ActorBrief

    point = raw.get("point")
    pt = None
    if isinstance(point, (list, tuple)) and len(point) >= 2:
        pt = (float(point[0]), float(point[1]))
    bounds = raw.get("bounds")
    bd = None
    if isinstance(bounds, (list, tuple)) and len(bounds) >= 4:
        bd = (float(bounds[0]), float(bounds[1]), float(bounds[2]), float(bounds[3]))
    return ActorBrief(
        gesture=str(raw.get("gesture") or ""),
        app=str(raw.get("app") or "WhatsApp"),
        point=pt,
        bounds=bd,
        label=str(raw.get("label") or ""),
        text=str(raw.get("text") or ""),
        field_role=str(raw.get("field_role") or "none"),
        open_search_ui=bool(raw.get("open_search_ui")),
        capability=str(raw.get("capability") or ""),
        target_id=str(raw.get("target_id") or ""),
        target_kind=str(raw.get("target_kind") or ""),
    )


def _apply_perception_confirm_fixture(inp: Dict[str, Any]):
    """If the case freezes a confirm verdict, patch confirm_perception for the score.

    Live zarooratwala refusals are replayed by feeding the observed confirm
    state/reason — the scorer never touches the real screen.
    Returns ``(restore_fn, environ_prev)``.
    """
    fixture = inp.get("perception_confirm")
    if not isinstance(fixture, dict) or not fixture:
        return None, None

    import os
    from unittest.mock import patch

    from plugin.perception.confirm import PerceptionConfirmResult

    prev_guard = os.environ.get("HERMES_ACTION_GUARD")
    os.environ["HERMES_ACTION_GUARD"] = "1"
    result = PerceptionConfirmResult(
        valid=bool(fixture.get("valid", False)),
        state=str(fixture.get("state") or "focus_disturbed"),
        reason=str(fixture.get("reason") or ""),
        evidence=dict(fixture.get("evidence") or {}),
    )

    def _fake_confirm(*_a, **_k):
        return result

    patcher = patch(
        "plugin.perception.confirm.confirm_perception",
        side_effect=_fake_confirm,
    )
    patcher.start()

    def restore():
        patcher.stop()
        if prev_guard is None:
            os.environ.pop("HERMES_ACTION_GUARD", None)
        else:
            os.environ["HERMES_ACTION_GUARD"] = prev_guard

    return restore, prev_guard


def score_actor_case(case: GoldenCase) -> CaseScore:
    from plugin.agent.actor import (
        RecordingMotor,
        exec_backend_for_actor_result,
        execute_actor,
    )

    result = CaseScore(case_id=case.id, module="actor", passed=False)
    inp = case.input or {}
    gold = case.gold or {}
    brief = _brief_from_gold_input(dict(inp.get("brief") or {}))
    motor = RecordingMotor(succeed=True)
    restore_confirm, _ = _apply_perception_confirm_fixture(inp)
    try:
        outcome = execute_actor(brief, motor=motor)
    finally:
        if restore_confirm is not None:
            restore_confirm()

    status_ok = _norm(outcome.status) == _norm(gold.get("status")) if gold.get("status") else True
    ok_flag = True
    if "ok" in gold:
        ok_flag = bool(outcome.ok) is bool(gold.get("ok"))
    validation = str((outcome.evidence or {}).get("validation") or outcome.message or "")
    val_ok = True
    needle = str(gold.get("validation_contains") or "")
    if needle:
        val_ok = needle.lower() in validation.lower()

    msg = str(outcome.message or "")
    msg_ok = True
    msg_needle = str(gold.get("message_contains") or "")
    if msg_needle:
        msg_ok = msg_needle.lower() in msg.lower()

    msg_all_ok = True
    msg_all = [str(x) for x in (gold.get("message_contains_all") or []) if str(x).strip()]
    if msg_all:
        low = msg.lower()
        msg_all_ok = all(n.lower() in low for n in msg_all)

    confirm_payload = (outcome.evidence or {}).get("perception_confirm")
    confirm_reason = ""
    if isinstance(confirm_payload, dict):
        confirm_reason = str(confirm_payload.get("reason") or "")
    reason_blob = f"{msg} {confirm_reason}".lower()
    reason_ok = True
    reason_needles = [str(x) for x in (gold.get("reason_contains_all") or []) if str(x).strip()]
    if reason_needles:
        reason_ok = all(n.lower() in reason_blob for n in reason_needles)

    motor_ops = [str(c.get("op") or "") for c in motor.calls]
    forbidden = {str(x) for x in (gold.get("forbidden_motor_ops") or [])}
    forbid_ok = not any(op in forbidden for op in motor_ops)

    empty_motor_ok = True
    if gold.get("motor_must_be_empty"):
        empty_motor_ok = len(motor.calls) == 0

    motor_ok = True
    expect_op = str(gold.get("motor_op") or "")
    if expect_op:
        motor_ok = expect_op in motor_ops

    open_ok = True
    if "open_search_ui" in gold and motor.calls:
        type_calls = [c for c in motor.calls if c.get("op") == "type"]
        if type_calls:
            open_ok = bool(type_calls[0].get("open_search_ui")) is bool(gold.get("open_search_ui"))

    into_ok = True
    expect_into = gold.get("into")
    if expect_into is not None:
        type_calls = [c for c in motor.calls if c.get("op") == "type"]
        if not type_calls:
            into_ok = False
        else:
            into_ok = _norm(type_calls[0].get("into")) == _norm(expect_into)

    bounds_ok = True
    type_or_click = [c for c in motor.calls if c.get("op") in {"type", "click", "context_click", "hover"}]
    if gold.get("must_have_bounds"):
        bounds_ok = bool(type_or_click) and type_or_click[0].get("bounds") is not None

    point_ok = True
    near = gold.get("bounds_center_near")
    if isinstance(near, (list, tuple)) and len(near) >= 2 and type_or_click:
        b = type_or_click[0].get("bounds")
        if not (isinstance(b, (list, tuple)) and len(b) >= 4):
            point_ok = False
        else:
            cx = float(b[0]) + float(b[2]) / 2.0
            cy = float(b[1]) + float(b[3]) / 2.0
            point_ok = abs(cx - float(near[0])) < 3.0 and abs(cy - float(near[1])) < 3.0

    confirm_state_ok = True
    expect_confirm_state = str(gold.get("confirm_state") or "")
    got_confirm = (outcome.evidence or {}).get("perception_confirm")
    got_state = ""
    if isinstance(got_confirm, dict):
        got_state = str(got_confirm.get("state") or "")
    elif expect_confirm_state:
        got_state = str((outcome.evidence or {}).get("continuity_state") or "")
    if expect_confirm_state:
        confirm_state_ok = _norm(got_state) == _norm(expect_confirm_state)

    backend_ok = True
    expect_backend = str(gold.get("exec_backend") or "")
    got_backend = exec_backend_for_actor_result(outcome)
    if expect_backend:
        backend_ok = _norm(got_backend) == _norm(expect_backend)

    result.checks = [
        _check("status", status_ok, f"expect={gold.get('status')!r} got={outcome.status!r}"),
        _check("ok", ok_flag, f"expect={gold.get('ok')} got={outcome.ok}"),
        _check("validation", val_ok, f"needle={needle!r} got={validation!r}"),
        _check("message_contains", msg_ok, f"needle={msg_needle!r} got={msg!r}"),
        _check(
            "message_contains_all",
            msg_all_ok,
            f"needles={msg_all!r} got={msg!r}",
        ),
        _check(
            "reason_contains_all",
            reason_ok,
            f"needles={reason_needles!r} blob={reason_blob[:240]!r}",
        ),
        _check("forbidden_motor", forbid_ok, f"ops={motor_ops} forbidden={sorted(forbidden)}"),
        _check(
            "motor_must_be_empty",
            empty_motor_ok,
            f"calls={motor.calls}",
        ),
        _check("motor_op", motor_ok, f"expect={expect_op!r} ops={motor_ops}"),
        _check("open_search_ui", open_ok, f"expect={gold.get('open_search_ui')}"),
        _check("into", into_ok, f"expect={expect_into!r} calls={motor.calls}"),
        _check("bounds", bounds_ok, f"calls={motor.calls}"),
        _check("bounds_center_near", point_ok, f"expect={near} calls={motor.calls}"),
        _check(
            "confirm_state",
            confirm_state_ok,
            f"expect={expect_confirm_state!r} got={got_state!r}",
        ),
        _check(
            "exec_backend",
            backend_ok,
            f"expect={expect_backend!r} got={got_backend!r}",
        ),
    ]
    result.passed = all(c["passed"] for c in result.checks)
    return result


# ---------------------------------------------------------------------------
# Brain → actor handoff
# ---------------------------------------------------------------------------


def _point_near(got: Any, expect: Any, tol: float = 2.0) -> bool:
    if not isinstance(expect, (list, tuple)) or len(expect) < 2:
        return True
    if not isinstance(got, (list, tuple)) or len(got) < 2:
        return False
    return (
        abs(float(got[0]) - float(expect[0])) < tol
        and abs(float(got[1]) - float(expect[1])) < tol
    )


def _point_forbidden(got: Any, forbidden: Any, tol: float = 5.0) -> bool:
    """True when got is acceptably far from every forbidden point."""
    if not isinstance(got, (list, tuple)) or len(got) < 2:
        return True
    points = forbidden if isinstance(forbidden, list) else []
    for bad in points:
        if not isinstance(bad, (list, tuple)) or len(bad) < 2:
            continue
        if (
            abs(float(got[0]) - float(bad[0])) < tol
            and abs(float(got[1]) - float(bad[1])) < tol
        ):
            return False
    return True


def score_brain_actor_handoff_case(case: GoldenCase) -> CaseScore:
    from plugin.agent.actor import brief_from_brain_choice, validate_brief

    result = CaseScore(case_id=case.id, module="brain_actor_handoff", passed=False)
    inp = case.input or {}
    gold = case.gold or {}
    scenario = str(inp.get("scenario") or "brief")

    # Full pipeline: perceptor objects+CTA → brain consultation → actor brief.
    # Scores the handoff contract that live 011358 broke (stale accepted world
    # overwrote the perceptor's chat-row point and opened a neighbor group).
    if scenario == "perceptor_brain_actor":
        from plugin.agent.decision_consultation import apply_decision_consultation
        from plugin.agent.goal import Goal
        from plugin.agent.unified_cognition import UnifiedProposal

        perc = dict(inp.get("perceptor") or {})
        wm = dict(perc.get("world_model") or {})
        perc_na = dict(perc.get("next_action") or {})
        accepted = dict(inp.get("accepted_world") or {})
        choice = dict(inp.get("brain_choice") or {})
        g_in = dict(inp.get("goal") or {})

        features_in = dict(inp.get("features") or {})
        search_q = str(features_in.get("search_query") or "").strip()
        attempts = [
            a for a in (inp.get("search_attempts") or []) if isinstance(a, dict)
        ]
        if search_q and not attempts:
            # Post-search chat_list goldens (011358): search already typed.
            attempts = [{"q": search_q, "outcome": "ok"}]

        class _State:
            def __init__(self) -> None:
                self.unified_world_document = accepted
                self.focused_field_role = str(accepted.get("focused_field_role") or "")
                self.last_plan_step = None
                self.search_attempt_log: List[Dict[str, Any]] = list(attempts)
                self.perception_mode = ""
                self.last_meta_action = ""
                self.last_surprise_explanation = None
                self.reflect_corrected_point = None

        class _Chooser:
            def choose(self, system: str, packet: Dict[str, Any]) -> Dict[str, Any]:
                return {
                    "capability": str(choice.get("capability") or ""),
                    "target": str(choice.get("target") or ""),
                    "why": str(choice.get("why") or "golden"),
                    "confidence": float(choice.get("confidence") or 0.9),
                }

        proposal = UnifiedProposal(
            observed_state={"surface": wm.get("surface")},
            world_model=wm,
            next_action=perc_na,
            confidence=float(perc.get("confidence") or 0.9),
        )
        goal = Goal(
            kind=str(g_in.get("kind") or "whatsapp_forward_message"),
            contact=str(g_in.get("contact") or "Pallavi"),
            target_contact=str(g_in.get("target_contact") or "Tanmay"),
            link_query=str(g_in.get("link_query") or "zarooratwala"),
        )
        from plugin.agent.features import StateFeatures

        feat_extras = {"app_content_node_count": 0, **features_in}
        features = StateFeatures(extras=feat_extras)
        apply_decision_consultation(
            proposal,
            goal,
            features=features,
            execution_state=_State(),
            chooser=_Chooser(),
        )
        brain_na = dict(proposal.next_action or {})
        # Actor binds against the perceptor object inventory (fresh look), which
        # is what execute paths should prefer once brain has chosen.
        brief = brief_from_brain_choice(brain_na, wm, app="WhatsApp")
        brief_ok, why = validate_brief(brief)

        brain_pt = brain_na.get("target_point")
        brain_pt_ok = _point_near(brain_pt, gold.get("brain_point_near"))
        brain_tid_ok = True
        if gold.get("brain_target_id"):
            brain_tid_ok = _norm(brain_na.get("target_id")) == _norm(gold.get("brain_target_id"))
        src_ok = True
        if gold.get("geometry_source"):
            src_ok = _norm(brain_na.get("geometry_source")) == _norm(gold.get("geometry_source"))
        fam_ok = True
        if gold.get("capability"):
            fam_ok = _norm(brain_na.get("family")) == _norm(gold.get("capability"))
        gesture_ok = True
        if gold.get("gesture"):
            gesture_ok = _norm(brief.gesture) == _norm(gold.get("gesture"))
        ok_flag = True
        if "brief_ok" in gold:
            ok_flag = bool(brief_ok) is bool(gold.get("brief_ok"))
        geom_ok = True
        if gold.get("must_have_geometry"):
            geom_ok = brief.point is not None or brief.bounds is not None
        tid_ok = True
        if gold.get("target_id"):
            tid_ok = _norm(brief.target_id) == _norm(gold.get("target_id"))
        point_ok = _point_near(brief.point, gold.get("point_near"))
        forbid_ok = _point_forbidden(brief.point, gold.get("must_not_point_near") or [])
        forbid_brain_ok = _point_forbidden(brain_pt, gold.get("must_not_point_near") or [])

        result.checks = [
            _check("capability", fam_ok, f"got={brain_na.get('family')!r}"),
            _check("geometry_source", src_ok, f"got={brain_na.get('geometry_source')!r}"),
            _check("brain_point", brain_pt_ok, f"expect={gold.get('brain_point_near')} got={brain_pt}"),
            _check("brain_target_id", brain_tid_ok, f"got={brain_na.get('target_id')!r}"),
            _check("brain_forbid_point", forbid_brain_ok, f"forbidden={gold.get('must_not_point_near')} got={brain_pt}"),
            _check("gesture", gesture_ok, f"got={brief.gesture!r}"),
            _check("brief_ok", ok_flag, f"ok={brief_ok} why={why}"),
            _check("geometry", geom_ok, f"point={brief.point}"),
            _check("target_id", tid_ok, f"expect={gold.get('target_id')!r} got={brief.target_id!r}"),
            _check("actor_point", point_ok, f"expect={gold.get('point_near')} got={brief.point}"),
            _check("actor_forbid_point", forbid_ok, f"forbidden={gold.get('must_not_point_near')} got={brief.point}"),
        ]
        result.passed = all(c["passed"] for c in result.checks)
        return result

    brief = brief_from_brain_choice(
        dict(inp.get("next_action") or {}),
        dict(inp.get("accepted_world") or {}),
        app="WhatsApp",
    )
    brief_ok, why = validate_brief(brief)

    gesture_ok = True
    if gold.get("gesture"):
        gesture_ok = _norm(brief.gesture) == _norm(gold.get("gesture"))
    role_ok = True
    if gold.get("field_role"):
        role_ok = _norm(brief.field_role) == _norm(gold.get("field_role"))
    open_ok = True
    if "open_search_ui" in gold:
        open_ok = bool(brief.open_search_ui) is bool(gold.get("open_search_ui"))
    ok_flag = True
    if "brief_ok" in gold:
        ok_flag = bool(brief_ok) is bool(gold.get("brief_ok"))
    text_ok = True
    if gold.get("text"):
        text_ok = _norm(brief.text) == _norm(gold.get("text"))
    geom_ok = True
    if gold.get("must_have_geometry"):
        geom_ok = brief.point is not None or brief.bounds is not None
    tid_ok = True
    if gold.get("target_id"):
        tid_ok = _norm(brief.target_id) == _norm(gold.get("target_id"))
    point_ok = _point_near(brief.point, gold.get("point_near"))
    forbid_ok = _point_forbidden(brief.point, gold.get("must_not_point_near") or [])
    kind_ok = True
    if gold.get("target_kind"):
        kind_ok = _norm(brief.target_kind) == _norm(gold.get("target_kind"))
    val_ok = True
    needle = str(gold.get("validation_contains") or "")
    if needle:
        val_ok = needle.lower() in why.lower()

    result.checks = [
        _check("gesture", gesture_ok, f"expect={gold.get('gesture')!r} got={brief.gesture!r}"),
        _check("field_role", role_ok, f"expect={gold.get('field_role')!r} got={brief.field_role!r}"),
        _check("open_search_ui", open_ok, f"expect={gold.get('open_search_ui')} got={brief.open_search_ui}"),
        _check("brief_ok", ok_flag, f"expect={gold.get('brief_ok')} got={brief_ok} why={why}"),
        _check("text", text_ok, f"expect={gold.get('text')!r} got={brief.text!r}"),
        _check("geometry", geom_ok, f"point={brief.point} bounds={brief.bounds}"),
        _check("target_id", tid_ok, f"expect={gold.get('target_id')!r} got={brief.target_id!r}"),
        _check("target_kind", kind_ok, f"expect={gold.get('target_kind')!r} got={brief.target_kind!r}"),
        _check("point_near", point_ok, f"expect={gold.get('point_near')} got={brief.point}"),
        _check("forbid_point", forbid_ok, f"forbidden={gold.get('must_not_point_near')} got={brief.point}"),
        _check("validation", val_ok, f"needle={needle!r} why={why!r}"),
    ]
    result.passed = all(c["passed"] for c in result.checks)
    return result


# ---------------------------------------------------------------------------
# Reflect (surprise explanation → brain recovery)
# ---------------------------------------------------------------------------


def score_reflect_case(case: GoldenCase) -> CaseScore:
    """Score reflect-module goldens: meta / packet / brain detection & recovery."""
    from plugin.agent.brain import apply_surprise_explanation
    from plugin.agent.decision_consultation import DecisionOutcome, apply_decision_consultation
    from plugin.agent.executive.meta_action import MetaAction, MetaContext, select_meta_action
    from plugin.agent.goal import Goal
    from plugin.agent.runtime.state import ExecutionState
    from plugin.agent.unified_cognition import (
        UnifiedProposal,
        _reflect_packet,
        normalize_surprise_explanation,
    )

    result = CaseScore(case_id=case.id, module="reflect", passed=False)
    inp = case.input or {}
    gold = case.gold or {}
    scenario = str(inp.get("scenario") or "brain")

    if scenario == "meta":
        choice = select_meta_action(
            MetaContext(
                awaiting_verification=bool(inp.get("awaiting_verification")),
                last_action_surprised=bool(inp.get("last_action_surprised")),
                has_grounded_action=bool(inp.get("has_grounded_action")),
                reperception_exhausted=bool(inp.get("reperception_exhausted")),
            )
        )
        got = choice.action.value if isinstance(choice.action, MetaAction) else str(choice.action)
        expect = _norm(gold.get("meta_action"))
        forbidden = {_norm(x) for x in (gold.get("forbidden_meta") or [])}
        result.checks = [
            _check("meta_action", _norm(got) == expect, f"expect={expect!r} got={got!r}"),
            _check("forbidden_meta", _norm(got) not in forbidden, f"got={got!r}"),
        ]
        result.passed = all(c["passed"] for c in result.checks)
        return result

    if scenario == "diagnosis_seed":
        from plugin.agent.reflect_diagnosis import (
            enrich_reflect_packet,
            seed_reflect_diagnosis_from_measured,
        )
        from plugin.agent.unified_cognition import finalize_surprise_explanation

        packet = enrich_reflect_packet(dict(inp.get("reflect_packet") or {}))
        seed = seed_reflect_diagnosis_from_measured(packet)
        model_raw = inp.get("model_explanation")
        if isinstance(model_raw, dict):
            expl = finalize_surprise_explanation(model_raw, reflect_packet=packet)
        else:
            expl = seed.to_surprise_explanation()
        repair = expl.get("repair") if isinstance(expl.get("repair"), dict) else {}
        result.checks = [
            _check(
                "cause",
                (not gold.get("cause")) or _norm(expl.get("cause")) == _norm(gold.get("cause")),
                f"expect={gold.get('cause')!r} got={expl.get('cause')!r}",
            ),
            _check(
                "locus",
                (not gold.get("locus")) or _norm(expl.get("locus")) == _norm(gold.get("locus")),
                f"expect={gold.get('locus')!r} got={expl.get('locus')!r}",
            ),
            _check(
                "transition_class",
                (not gold.get("transition_class"))
                or _norm(expl.get("transition_class")) == _norm(gold.get("transition_class")),
                f"expect={gold.get('transition_class')!r} got={expl.get('transition_class')!r}",
            ),
            _check(
                "repair_kind",
                (not gold.get("repair_kind"))
                or _norm(repair.get("kind")) == _norm(gold.get("repair_kind")),
                f"expect={gold.get('repair_kind')!r} got={repair.get('kind')!r}",
            ),
            _check(
                "repair_capability",
                (not gold.get("repair_capability"))
                or _norm(repair.get("capability")) == _norm(gold.get("repair_capability")),
                f"expect={gold.get('repair_capability')!r} got={repair.get('capability')!r}",
            ),
            _check(
                "repair_target",
                (not gold.get("repair_target"))
                or _norm(repair.get("target")) == _norm(gold.get("repair_target")),
                f"expect={gold.get('repair_target')!r} got={repair.get('target')!r}",
            ),
            _check(
                "motor_constraint",
                (not gold.get("motor_constraint"))
                or _norm(repair.get("motor_constraint")) == _norm(gold.get("motor_constraint")),
                f"expect={gold.get('motor_constraint')!r} got={repair.get('motor_constraint')!r}",
            ),
            _check(
                "recommended_next",
                (not gold.get("recommended_next"))
                or _norm(expl.get("recommended_next")) == _norm(gold.get("recommended_next")),
                f"expect={gold.get('recommended_next')!r} got={expl.get('recommended_next')!r}",
            ),
            _check(
                "forbid_repair",
                _norm(repair.get("kind"))
                not in {_norm(x) for x in (gold.get("forbid_repair_kinds") or [])},
                f"got={repair.get('kind')!r}",
            ),
        ]
        result.passed = all(c["passed"] for c in result.checks)
        return result

    if scenario in {"packet", "discovery"}:
        from plugin.agent.unified_cognition import discover_surprise_hypotheses

        state = ExecutionState()
        state.perception_mode = str(inp.get("perception_mode") or "reflect")
        state.last_meta_action = str(inp.get("last_meta_action") or "reflect")
        state.last_action = str(inp.get("last_action") or "")
        step = dict(inp.get("last_plan_step") or {})
        state.last_plan_step = type("S", (), step)()
        state.unified_last_expectation = dict(inp.get("unified_last_expectation") or {})
        state.last_prediction_error = dict(inp.get("last_prediction_error") or {})
        if isinstance(inp.get("last_result"), dict):
            state.last_result = dict(inp.get("last_result") or {})
        if isinstance(inp.get("last_attribution"), dict):
            state.last_attribution = dict(inp.get("last_attribution") or {})
        if isinstance(inp.get("unified_world_document"), dict):
            state.unified_world_document = dict(inp.get("unified_world_document") or {})
        for prior in inp.get("prior_perceptions") or []:
            if isinstance(prior, dict):
                state.note_perception(
                    {
                        "surface": prior.get("surface"),
                        "open_conversation": prior.get("open_conversation"),
                        "objects": prior.get("objects") or [],
                        "focused_field_role": prior.get("focused_field_role") or "",
                    },
                    iteration=int(prior.get("iteration") or 0),
                )
        packet = _reflect_packet(state)
        action = packet.get("action") if isinstance(packet.get("action"), dict) else {}
        measured = packet.get("measured") if isinstance(packet.get("measured"), dict) else {}
        hyps = list(packet.get("discovery_hypotheses") or [])
        if not hyps:
            hyps = discover_surprise_hypotheses(packet)
        hyp_causes = {_norm(h.get("cause")) for h in hyps if isinstance(h, dict)}

        def _pt_near(got: Any, expect: Any, tol: float = 2.0) -> bool:
            if not isinstance(expect, (list, tuple)) or len(expect) < 2:
                return True
            if not isinstance(got, (list, tuple)) or len(got) < 2:
                return False
            return (
                abs(float(got[0]) - float(expect[0])) < tol
                and abs(float(got[1]) - float(expect[1])) < tol
            )

        has_ok = bool(packet) if gold.get("has_reflect_block") else True
        fam_ok = True
        if gold.get("action_family"):
            fam_ok = _norm(action.get("family")) == _norm(gold.get("action_family"))
        intended = action.get("intended_point") or action.get("point")
        pt_ok = _pt_near(intended, gold.get("action_point_near") or gold.get("intended_point_near"))
        landed_ok = _pt_near(
            action.get("motor_landed_point") or measured.get("motor_landed_point"),
            gold.get("motor_landed_near"),
            tol=3.0,
        )
        geom_ok = True
        if "geometry_mismatch" in gold:
            geom_ok = bool(measured.get("geometry_mismatch")) is bool(gold.get("geometry_mismatch"))
        exp_ok = True
        if gold.get("expected_surface"):
            exp_ok = _norm((packet.get("expected") or {}).get("surface")) == _norm(
                gold.get("expected_surface")
            )
        match_ok = True
        if "actual_matched" in gold:
            match_ok = bool((packet.get("actual") or {}).get("matched")) is bool(
                gold.get("actual_matched")
            )
        prior_ok = True
        blob = json.dumps(packet.get("prior_perceptions") or [])
        for token in gold.get("prior_mentions") or []:
            if str(token) not in blob:
                prior_ok = False
        q_ok = True
        if gold.get("has_discovery_questions"):
            q_ok = bool(packet.get("discovery_questions"))
        disc_ok = True
        need_causes = {_norm(x) for x in (gold.get("discovery_causes_include") or [])}
        if need_causes:
            disc_ok = need_causes.issubset(hyp_causes)
        forbid_causes = {_norm(x) for x in (gold.get("discovery_causes_exclude") or [])}
        forbid_ok = True
        if forbid_causes:
            forbid_ok = hyp_causes.isdisjoint(forbid_causes)
        result.checks = [
            _check("has_reflect_block", has_ok, f"keys={list(packet.keys())}"),
            _check("action_family", fam_ok, f"got={action.get('family')!r}"),
            _check("intended_point", pt_ok, f"expect={gold.get('action_point_near') or gold.get('intended_point_near')} got={intended}"),
            _check("motor_landed", landed_ok, f"expect={gold.get('motor_landed_near')} got={action.get('motor_landed_point')}"),
            _check("geometry_mismatch", geom_ok, f"got={measured.get('geometry_mismatch')} measured={measured}"),
            _check("expected_surface", exp_ok, f"got={(packet.get('expected') or {}).get('surface')!r}"),
            _check("actual_matched", match_ok, f"got={(packet.get('actual') or {}).get('matched')}"),
            _check("prior_mentions", prior_ok, f"need={gold.get('prior_mentions')}"),
            _check("discovery_questions", q_ok, f"got={packet.get('discovery_questions')}"),
            _check("discovery_causes", disc_ok, f"need={sorted(need_causes)} got={sorted(hyp_causes)}"),
            _check("discovery_forbid", forbid_ok, f"forbid={sorted(forbid_causes)} got={sorted(hyp_causes)}"),
        ]
        result.passed = all(c["passed"] for c in result.checks)
        return result

    # brain / brain_reground
    state = ExecutionState()
    state.perception_mode = str(inp.get("perception_mode") or "reflect")
    state.last_meta_action = str(inp.get("last_meta_action") or "reflect")
    state.last_action = str(inp.get("last_action") or "")
    step = dict(inp.get("last_plan_step") or {})
    state.last_plan_step = type("S", (), step)()
    expl = normalize_surprise_explanation(inp.get("surprise_explanation") or {})
    state.last_surprise_explanation = expl
    chooser_raw = dict(inp.get("chooser_outcome") or {})
    provisional = DecisionOutcome(
        ok=True,
        capability=str(chooser_raw.get("capability") or ""),
        target=str(chooser_raw.get("target") or ""),
        why=str(chooser_raw.get("why") or ""),
        confidence=float(chooser_raw.get("confidence") or 0.0),
        realization="golden_chooser",
    )
    steered = apply_surprise_explanation(provisional, state)

    if scenario == "brain_reground":
        world = dict(inp.get("accepted_world") or {})
        proposal = UnifiedProposal(world_model=dict(world), next_action={})
        state.unified_world_document = dict(world)
        state.last_surprise_explanation = expl
        state.perception_mode = "reflect"
        state.last_meta_action = "reflect"

        class _Chooser:
            def choose(self, system: str, packet: Dict[str, Any]) -> Dict[str, Any]:
                return {
                    "capability": str(chooser_raw.get("capability") or ""),
                    "target": str(chooser_raw.get("target") or ""),
                    "why": str(chooser_raw.get("why") or ""),
                    "confidence": float(chooser_raw.get("confidence") or 0.0),
                }

        goal = Goal(
            kind="whatsapp_forward_message",
            contact="Pallavi",
            target_contact="Tanmay",
            link_query="zarooratwala",
        )
        import os

        prev = os.environ.get("HERMES_DECISION_LLM")
        os.environ["HERMES_DECISION_LLM"] = "0"
        try:
            apply_decision_consultation(
                proposal,
                goal,
                features=None,
                execution_state=state,
                chooser=_Chooser(),
            )
        finally:
            if prev is None:
                os.environ.pop("HERMES_DECISION_LLM", None)
            else:
                os.environ["HERMES_DECISION_LLM"] = prev

        na = dict(proposal.next_action or {})
        fam = _norm(na.get("family") or "")
        realization = (
            "reflect_corrected_geometry"
            if na.get("reflect_reground")
            else _norm(str((na.get("realization") or "")))
        )
        # Trace may stash realization only on consultation extras; prefer flag.
        if not na.get("reflect_reground") and state.last_failed_motor_key:
            # Fall back: if corrected geometry applied via outcome path
            if isinstance(na.get("target_point"), (list, tuple)):
                near_tmp = gold.get("target_point_near")
                if isinstance(near_tmp, (list, tuple)) and abs(
                    float(na["target_point"][0]) - float(near_tmp[0])
                ) < 2.0:
                    realization = "reflect_corrected_geometry"
        pt = na.get("target_point")
        pt_ok = True
        near = gold.get("target_point_near")
        if isinstance(near, (list, tuple)) and len(near) >= 2:
            pt_ok = (
                isinstance(pt, (list, tuple))
                and abs(float(pt[0]) - float(near[0])) < 2.0
                and abs(float(pt[1]) - float(near[1])) < 2.0
            )
        bad_ok = True
        bad = gold.get("must_not_point_near")
        if isinstance(bad, (list, tuple)) and len(bad) >= 2 and isinstance(pt, (list, tuple)):
            bad_ok = not (
                abs(float(pt[0]) - float(bad[0])) < 5.0
                and abs(float(pt[1]) - float(bad[1])) < 5.0
            )
        cap_ok = fam == _norm(gold.get("capability")) if gold.get("capability") else True
        real_ok = realization == _norm(gold.get("realization")) if gold.get("realization") else True
        cause_ok = _norm(expl.get("cause")) == _norm(gold.get("cause")) if gold.get("cause") else True
        result.checks = [
            _check("capability", cap_ok, f"expect={gold.get('capability')!r} got={fam!r} na={na}"),
            _check("realization", real_ok, f"expect={gold.get('realization')!r} got={realization!r}"),
            _check("cause", cause_ok, f"got={expl.get('cause')!r}"),
            _check("target_point", pt_ok, f"expect={near} got={pt}"),
            _check("must_not_point", bad_ok, f"forbidden={bad} got={pt}"),
        ]
        result.passed = all(c["passed"] for c in result.checks)
        return result

    # brain: block-repeat / repair override path
    fam = _norm(steered.capability)
    realization = str(getattr(steered, "realization", "") or "")
    cap_ok = fam == _norm(gold.get("capability")) if gold.get("capability") else True
    expect_real = str(gold.get("realization") or "")
    if expect_real.endswith("*"):
        real_ok = realization.startswith(expect_real[:-1])
    else:
        real_ok = (not expect_real) or _norm(realization) == _norm(expect_real)
    cause_ok = _norm(expl.get("cause")) == _norm(gold.get("cause")) if gold.get("cause") else True
    forbidden = {_norm(x) for x in (gold.get("must_not_capability") or [])}
    forbid_ok = fam not in forbidden
    target_ok = True
    if gold.get("target"):
        target_ok = _norm(getattr(steered, "target", "")) == _norm(gold.get("target"))
    constraint_ok = True
    if gold.get("motor_constraint"):
        constraint_ok = _norm(getattr(state, "reflect_motor_constraint", "")) == _norm(
            gold.get("motor_constraint")
        )
    result.checks = [
        _check("capability", cap_ok, f"expect={gold.get('capability')!r} got={fam!r}"),
        _check("realization", real_ok, f"expect={expect_real!r} got={realization!r}"),
        _check("cause", cause_ok, f"got={expl.get('cause')!r}"),
        _check("target", target_ok, f"expect={gold.get('target')!r} got={getattr(steered, 'target', '')!r}"),
        _check(
            "motor_constraint",
            constraint_ok,
            f"expect={gold.get('motor_constraint')!r} got={getattr(state, 'reflect_motor_constraint', '')!r}",
        ),
        _check("must_not_capability", forbid_ok, f"got={fam!r} forbidden={sorted(forbidden)}"),
    ]
    result.passed = all(c["passed"] for c in result.checks)
    return result


def score_flow_case(case: GoldenCase) -> CaseScore:
    """Cross-module flow goldens (e.g. surprise → reflect diagnosis → brain repair)."""
    from plugin.agent.brain import apply_surprise_explanation
    from plugin.agent.controller import _last_action_surprised
    from plugin.agent.decision_consultation import DecisionOutcome
    from plugin.agent.executive.meta_action import MetaAction, MetaContext, select_meta_action
    from plugin.agent.reflect_diagnosis import enrich_reflect_packet
    from plugin.agent.runtime.state import ExecutionState
    from plugin.agent.unified_cognition import (
        UnifiedProposal,
        finalize_surprise_explanation,
        note_prediction_error,
        stamp_act_intention,
    )
    from plugin.agent.action import Action

    result = CaseScore(case_id=case.id, module="flow", passed=False)
    inp = case.input or {}
    gold = case.gold or {}
    flow = str(inp.get("flow") or "reflect_repair")

    if flow == "ax_filter_geometry_bind":
        # 123746: exclusive filter compose binds AX Search when VLM omitted it.
        from plugin.agent.decision_consultation import apply_decision_consultation
        from plugin.agent.features import StateFeatures
        from plugin.agent.goal import Goal
        from plugin.agent.unified_cognition import UnifiedProposal

        goal_raw = dict(inp.get("goal") or {})
        goal = Goal(
            kind=str(goal_raw.get("kind") or "whatsapp_forward_message"),
            contact=str(goal_raw.get("contact") or "Pallavi"),
            target_contact=str(goal_raw.get("target_contact") or "Tanmay"),
            link_query=str(goal_raw.get("link_query") or "zarooratwala"),
        )
        doc = dict(inp.get("accepted_document") or inp.get("world_document") or {})
        state = ExecutionState()
        state.unified_world_document = doc
        frontier = inp.get("affordance_frontier")
        if isinstance(frontier, dict):
            state.last_affordance_frontier = dict(frontier)
        stashed = inp.get("last_filter_geometry")
        if isinstance(stashed, dict):
            state.last_filter_geometry = dict(stashed)
        proposal = UnifiedProposal(
            observed_state={"surface": str(doc.get("surface") or "")},
            world_model=doc,
            next_action={},
            confidence=0.9,
        )
        want_cap = str(gold.get("capability") or "compose_search_query")
        # Compose/resolve are SEARCH-stage verbs — default ACT meta would reject them.
        if want_cap in {"compose_search_query", "resolve_entity", "type_query"}:
            state.last_meta_action = "search"

        class _FixedChooser:
            def choose(self, system: str, packet: dict) -> dict:
                return {
                    "capability": want_cap,
                    "target": str(gold.get("chooser_target") or ""),
                    "why": "golden",
                    "confidence": 0.9,
                }

        trace = apply_decision_consultation(
            proposal,
            goal,
            features=StateFeatures(extras=dict(inp.get("features_extras") or {})),
            execution_state=state,
            chooser=_FixedChooser(),
        )
        na = proposal.next_action or {}
        checks = [
            _check(
                "capability",
                _norm(na.get("family")) == _norm(gold.get("family") or want_cap),
                f"got={na.get('family')}",
            )
        ]
        if gold.get("must_have_geometry"):
            checks.append(
                _check(
                    "geometry",
                    na.get("target_point") is not None or bool(na.get("bounds")),
                    f"point={na.get('target_point')} bounds={na.get('bounds')}",
                )
            )
        want_point = gold.get("target_point")
        if isinstance(want_point, (list, tuple)) and len(want_point) >= 2:
            got = na.get("target_point") or []
            checks.append(
                _check(
                    "target_point",
                    isinstance(got, (list, tuple))
                    and len(got) >= 2
                    and abs(float(got[0]) - float(want_point[0])) < 1.0
                    and abs(float(got[1]) - float(want_point[1])) < 1.0,
                    f"got={got}",
                )
            )
        forbid_id = gold.get("forbid_target_id")
        if forbid_id is not None:
            checks.append(
                _check(
                    "forbid_chat_row",
                    na.get("target_id") != forbid_id,
                    f"got target_id={na.get('target_id')}",
                )
            )
        if gold.get("geometry_source"):
            checks.append(
                _check(
                    "geometry_source",
                    _norm(na.get("geometry_source"))
                    == _norm(gold.get("geometry_source")),
                    f"got={na.get('geometry_source')}",
                )
            )
        if gold.get("expect_geometry_missing_demote"):
            checks.append(
                _check(
                    "demote_observe",
                    _norm(na.get("family")) == "observe",
                    f"got={na.get('family')}",
                )
            )
            checks.append(
                _check(
                    "geometry_required_missing",
                    "geometry_required_missing" in _norm(trace.get("realization")),
                    f"realization={trace.get('realization')}",
                )
            )
        result.checks = checks
        result.passed = all(c["passed"] for c in result.checks) if checks else False
        return result

    if flow == "post_accept_affordance_promote":
        # 235701: menu in accepted post-look doc must promote after accept;
        # incomplete handoff schedules bounded relooks (no OCR invent).
        from plugin.agent.affordance_explore import close_current_node_frontier
        from plugin.agent.world_critic import promote_frontier_after_accept

        state = ExecutionState()
        handoff = inp.get("reveal_handoff")
        if isinstance(handoff, dict):
            state.reveal_handoff = dict(handoff)
        doc = dict(inp.get("accepted_document") or {})
        state.unified_world_document = doc
        variant = str(inp.get("variant") or "success").strip().lower()
        checks = []
        if variant == "success":
            status = promote_frontier_after_accept(
                state,
                accepted_document=doc,
                last_action_family=str(
                    inp.get("last_action_family") or "reveal_actions"
                ),
            )
            labels = {
                str(a.get("target_label") or "")
                for a in (state.last_grounded_affordance_set or [])
            }
            want = {_norm(x) for x in (gold.get("promoted_labels") or ["Forward"])}
            checks.extend(
                [
                    _check("promoted", bool(status.get("promoted")), f"status={status}"),
                    _check(
                        "menu_grounded",
                        want.issubset({_norm(x) for x in labels}),
                        f"got={sorted(labels)}",
                    ),
                ]
            )
            if gold.get("handoff_cleared"):
                checks.append(
                    _check(
                        "handoff_cleared",
                        not isinstance(state.reveal_handoff, dict)
                        or not str(
                            (state.reveal_handoff or {}).get("surface") or ""
                        ).strip(),
                        f"handoff={state.reveal_handoff!r}",
                    )
                )
        elif variant == "ocr_enrich":
            # 125715: OCR menu verbs enrich document under handoff, then promote.
            ocr_lines = list(inp.get("ocr_lines") or [])
            if ocr_lines:
                state.last_overlay_ocr_menu = [dict(x) for x in ocr_lines if isinstance(x, dict)]
            status = promote_frontier_after_accept(
                state,
                accepted_document=doc,
                last_action_family=str(
                    inp.get("last_action_family") or "reveal_actions"
                ),
                ocr_lines=ocr_lines or None,
            )
            labels = {
                str(a.get("target_label") or "")
                for a in (state.last_grounded_affordance_set or [])
            }
            if "ocr_enriched" in gold:
                checks.append(
                    _check(
                        "ocr_enriched",
                        bool(status.get("ocr_enriched"))
                        is bool(gold.get("ocr_enriched")),
                        f"status={status}",
                    )
                )
            if gold.get("forbid_invented_forward"):
                checks.append(
                    _check(
                        "no_forward_from_forwarded",
                        "Forward" not in labels
                        and not any(_norm(x) == "forward" for x in labels),
                        f"got={sorted(labels)}",
                    )
                )
            else:
                want = {_norm(x) for x in (gold.get("promoted_labels") or ["Forward"])}
                checks.extend(
                    [
                        _check(
                            "promoted", bool(status.get("promoted")), f"status={status}"
                        ),
                        _check(
                            "menu_grounded",
                            want.issubset({_norm(x) for x in labels}),
                            f"got={sorted(labels)}",
                        ),
                    ]
                )
                if gold.get("handoff_cleared"):
                    checks.append(
                        _check(
                            "handoff_cleared",
                            not isinstance(state.reveal_handoff, dict)
                            or not str(
                                (state.reveal_handoff or {}).get("surface") or ""
                            ).strip(),
                            f"handoff={state.reveal_handoff!r}",
                        )
                    )
        elif variant == "multipass_relook":
            report = close_current_node_frontier(
                accepted_world=doc,
                passive_frontier={"surface": "conversation"},
                execution_state=state,
            )
            checks.append(
                _check(
                    "needs_relook",
                    bool(report.get("needs_relook"))
                    is bool(gold.get("needs_relook", True)),
                    f"got={report.get('needs_relook')}",
                )
            )
            checks.append(
                _check(
                    "must_executive_reperceive",
                    bool(getattr(state, "must_executive_reperceive", False))
                    is bool(gold.get("must_executive_reperceive", True)),
                    f"got={getattr(state, 'must_executive_reperceive', False)}",
                )
            )
            if gold.get("forbid_invented_forward"):
                labels = {
                    str(a.get("target_label") or "")
                    for a in (state.last_grounded_affordance_set or [])
                }
                checks.append(
                    _check(
                        "no_ocr_invent_forward",
                        "Forward" not in labels
                        and not any(_norm(x) == "forward" for x in labels),
                        f"got={sorted(labels)}",
                    )
                )
        result.checks = checks
        result.passed = all(c["passed"] for c in result.checks) if checks else False
        return result

    if flow == "overlay_capture_contract":
        # 150708: window-scoped capture omits context-menu layers; overlay
        # expectancy must force overlay_display, and menu objects then promote.
        from plugin.agent.affordance_frontier import Affordance, AffordanceFrontier, STATUS_LATENT
        from plugin.agent.unified_cognition import expects_overlay_perception
        from plugin.agent.world_critic import reconcile_frontier
        from plugin.perception.macos.accessibility.observer import (
            resolve_screenshot_capture_mode,
        )

        state = ExecutionState()
        handoff = inp.get("reveal_handoff")
        if isinstance(handoff, dict):
            state.reveal_handoff = dict(handoff)
        expects = bool(expects_overlay_perception(state))
        mode = resolve_screenshot_capture_mode(include_overlays=expects)
        forbidden = _norm(gold.get("forbidden_capture_mode") or inp.get("forbidden_capture_mode"))
        checks = [
            _check(
                "expects_overlay",
                expects is bool(gold.get("expects_overlay", True)),
                f"got={expects}",
            ),
            _check(
                "capture_mode",
                _norm(mode) == _norm(gold.get("capture_mode") or "overlay_display"),
                f"got={mode!r}",
            ),
            _check(
                "forbidden_capture_mode",
                (not forbidden) or _norm(mode) != forbidden,
                f"mode={mode!r} forbidden={forbidden!r}",
            ),
        ]
        variant = str(inp.get("variant") or "").strip().lower()
        if variant == "success" or bool(gold.get("menu_grounded")):
            frontier = AffordanceFrontier(
                surface="conversation",
                latent_actions=[
                    Affordance(
                        id="fwd",
                        family="invoke_affordance",
                        status=STATUS_LATENT,
                        target_label="Forward",
                    )
                ],
            )
            doc = dict(inp.get("document_with_menu") or {})
            reconcile_frontier(
                frontier,
                document=doc,
                execution_state=state,
                last_action_family=str(inp.get("last_action_family") or "reveal_actions"),
            )
            labels = {a.target_label for a in frontier.observed_actions}
            want = {_norm(x) for x in (gold.get("promoted_labels") or ["Forward"])}
            checks.append(
                _check(
                    "menu_grounded",
                    want.issubset({_norm(x) for x in labels}),
                    f"got={sorted(labels)}",
                )
            )
            if gold.get("handoff_cleared"):
                checks.append(
                    _check(
                        "handoff_cleared",
                        not isinstance(state.reveal_handoff, dict)
                        or not str((state.reveal_handoff or {}).get("surface") or "").strip(),
                        f"handoff={state.reveal_handoff!r}",
                    )
                )
            checks.append(
                _check(
                    "affordance_set_published",
                    bool(getattr(state, "last_grounded_affordance_set", None)),
                    f"set={getattr(state, 'last_grounded_affordance_set', None)!r}",
                )
            )
        elif variant == "failure":
            # Window-pixel document has no menu items → promote must not invent Forward.
            frontier = AffordanceFrontier(surface="conversation", latent_actions=[])
            doc = dict(inp.get("observed_document_without_menu") or {})
            reconcile_frontier(
                frontier,
                document=doc,
                execution_state=state,
                last_action_family="reveal_actions",
            )
            labels = {a.target_label for a in frontier.observed_actions}
            checks.append(
                _check(
                    "menu_absent_under_window_pixels",
                    "Forward" not in labels
                    and not any(_norm(x) == "forward" for x in labels)
                    and not any(str(x).lower().startswith("forwarded") for x in labels),
                    f"got={sorted(labels)}",
                )
            )
        result.checks = checks
        result.passed = all(c["passed"] for c in result.checks)
        return result

    if flow == "act_intention_reperceive":
        # Act stamps intention → post-act AX settle is diagnostic → look scores
        # intention vs world → multimodal surprise → meta REFLECT.
        decision = Action(
            action=str(inp.get("action") or "ContextClick"),
            action_family=str(inp.get("action_family") or "reveal_actions"),
            semantic_target=str(inp.get("semantic_target") or ""),
            prediction=dict(inp.get("prediction") or {}),
        )
        state = ExecutionState()
        stamped = stamp_act_intention(state, decision)
        state.last_attribution = dict(inp.get("last_attribution") or {})
        pre_surprised = _last_action_surprised(state)
        pre_meta = select_meta_action(
            MetaContext(
                awaiting_verification=True,
                last_action_surprised=pre_surprised,
                has_grounded_action=bool(inp.get("has_grounded_action", True)),
            )
        )
        proposal = UnifiedProposal()
        proposal.world_model = dict(inp.get("observed_world") or {})
        proposal.observed_state = dict(inp.get("observed_world") or {})
        proposal.expected_transition = dict(inp.get("proposal_expected_transition") or {})
        error = note_prediction_error(state, proposal)
        post_surprised = _last_action_surprised(state)
        post_meta = select_meta_action(
            MetaContext(
                awaiting_verification=True,
                last_action_surprised=post_surprised,
                has_grounded_action=bool(inp.get("has_grounded_action", True)),
            )
        )
        pre_got = (
            pre_meta.action.value
            if isinstance(pre_meta.action, MetaAction)
            else str(pre_meta.action)
        )
        post_got = (
            post_meta.action.value
            if isinstance(post_meta.action, MetaAction)
            else str(post_meta.action)
        )
        result.checks = [
            _check(
                "intention_surface",
                (not gold.get("intention_surface"))
                or _norm(stamped.get("surface")) == _norm(gold.get("intention_surface")),
                f"got={stamped.get('surface')!r}",
            ),
            _check(
                "pre_look_not_surprised",
                pre_surprised is False,
                f"pre_surprised={pre_surprised}",
            ),
            _check(
                "pre_look_meta",
                (not gold.get("pre_look_meta")) or _norm(pre_got) == _norm(gold.get("pre_look_meta")),
                f"got={pre_got!r}",
            ),
            _check(
                "prediction_mismatched",
                error.get("matched") is False,
                f"error={error}",
            ),
            _check(
                "post_look_surprised",
                post_surprised is True,
                f"post_surprised={post_surprised}",
            ),
            _check(
                "post_look_meta",
                (not gold.get("post_look_meta"))
                or _norm(post_got) == _norm(gold.get("post_look_meta")),
                f"got={post_got!r}",
            ),
            _check(
                "forbidden_post_meta",
                _norm(post_got)
                not in {_norm(x) for x in (gold.get("forbidden_post_meta") or [])},
                f"got={post_got!r}",
            ),
        ]
        result.passed = all(c["passed"] for c in result.checks)
        return result

    if flow != "reflect_repair":
        result.checks = [_check("flow", False, f"unknown flow={flow!r}")]
        return result

    packet = enrich_reflect_packet(dict(inp.get("reflect_packet") or {}))
    expl = finalize_surprise_explanation(
        inp.get("model_explanation") or {"cause": "unknown", "confidence": 0.2},
        reflect_packet=packet,
    )
    state = ExecutionState()
    state.perception_mode = "reflect"
    state.last_meta_action = "reflect"
    state.last_surprise_explanation = expl
    step = dict(inp.get("last_plan_step") or {})
    state.last_plan_step = type("S", (), step)()
    chooser = dict(inp.get("chooser_outcome") or {})
    steered = apply_surprise_explanation(
        DecisionOutcome(
            ok=True,
            capability=str(chooser.get("capability") or "observe"),
            target=str(chooser.get("target") or ""),
            why=str(chooser.get("why") or "golden"),
            confidence=float(chooser.get("confidence") or 0.0),
            realization="golden_chooser",
        ),
        state,
    )
    repair = expl.get("repair") if isinstance(expl.get("repair"), dict) else {}
    pt = getattr(state, "reflect_corrected_point", None)
    near = gold.get("target_point_near")
    pt_ok = True
    if isinstance(near, (list, tuple)) and len(near) >= 2:
        pt_ok = (
            isinstance(pt, (list, tuple))
            and abs(float(pt[0]) - float(near[0])) < 2.0
            and abs(float(pt[1]) - float(near[1])) < 2.0
        )
    result.checks = [
        _check(
            "diagnosis_cause",
            (not gold.get("cause")) or _norm(expl.get("cause")) == _norm(gold.get("cause")),
            f"got={expl.get('cause')!r}",
        ),
        _check(
            "repair_kind",
            (not gold.get("repair_kind"))
            or _norm(repair.get("kind")) == _norm(gold.get("repair_kind")),
            f"got={repair.get('kind')!r}",
        ),
        _check(
            "brain_capability",
            (not gold.get("capability"))
            or _norm(steered.capability) == _norm(gold.get("capability")),
            f"expect={gold.get('capability')!r} got={steered.capability!r}",
        ),
        _check(
            "brain_target",
            (not gold.get("target")) or _norm(steered.target) == _norm(gold.get("target")),
            f"got={steered.target!r}",
        ),
        _check(
            "realization_prefix",
            (not gold.get("realization_prefix"))
            or str(steered.realization or "").startswith(str(gold.get("realization_prefix"))),
            f"got={steered.realization!r}",
        ),
        _check(
            "realization",
            (not gold.get("realization"))
            or _norm(steered.realization) == _norm(gold.get("realization")),
            f"expect={gold.get('realization')!r} got={steered.realization!r}",
        ),
        _check("target_point", pt_ok, f"expect={near} got={pt}"),
        _check(
            "motor_constraint",
            (not gold.get("motor_constraint"))
            or _norm(getattr(state, "reflect_motor_constraint", ""))
            == _norm(gold.get("motor_constraint")),
            f"got={getattr(state, 'reflect_motor_constraint', '')!r}",
        ),
        _check(
            "must_not_capability",
            _norm(steered.capability)
            not in {_norm(x) for x in (gold.get("must_not_capability") or [])},
            f"got={steered.capability!r}",
        ),
    ]
    forbid_pt = gold.get("forbid_corrected_point")
    if isinstance(forbid_pt, (list, tuple)) and len(forbid_pt) >= 2:
        forbid_ok = not (
            isinstance(pt, (list, tuple))
            and abs(float(pt[0]) - float(forbid_pt[0])) < 2.0
            and abs(float(pt[1]) - float(forbid_pt[1])) < 2.0
        )
        result.checks.append(
            _check(
                "forbid_intended_latch",
                forbid_ok,
                f"forbid={forbid_pt} got={pt}",
            )
        )
    bad = gold.get("must_not_point_near")
    if isinstance(bad, (list, tuple)) and len(bad) >= 2:
        bad_ok = not (
            isinstance(pt, (list, tuple))
            and abs(float(pt[0]) - float(bad[0])) < 5.0
            and abs(float(pt[1]) - float(bad[1])) < 5.0
        )
        result.checks.append(
            _check("must_not_point", bad_ok, f"forbidden={bad} got={pt}")
        )
    result.passed = all(c["passed"] for c in result.checks)
    return result


# ---------------------------------------------------------------------------
# Suite
# ---------------------------------------------------------------------------


def score_ui_case(case: GoldenCase) -> CaseScore:
    """UI recoverability goldens: selection consistency + revert_effects path."""
    from plugin.agent.brain import apply_surprise_explanation
    from plugin.agent.capabilities.revert_effects import (
        analyze_revert_plan,
        approve_revert_plan,
        revert_effects,
        selection_consistency_error,
    )
    from plugin.agent.decision_consultation import DecisionOutcome
    from plugin.agent.reflect_diagnosis import (
        enrich_reflect_packet,
        seed_reflect_diagnosis_from_measured,
    )
    from plugin.agent.runtime.state import ExecutionState
    from plugin.agent.unified_cognition import finalize_surprise_explanation

    result = CaseScore(case_id=case.id, module="ui", passed=False)
    inp = case.input or {}
    gold = case.gold or {}
    flow = str(inp.get("flow") or "selection_consistency")

    if flow == "selection_consistency":
        doc = dict(inp.get("world_document") or {})
        sel = selection_consistency_error(
            doc,
            goal_referents=list(inp.get("goal_referents") or []),
            semantic_target=str(inp.get("semantic_target") or ""),
        )
        checks = [
            _check(
                "consistent",
                bool(sel.get("consistent")) is bool(gold.get("consistent")),
                f"expect={gold.get('consistent')} got={sel.get('consistent')} verdict={sel.get('verdict')}",
            )
        ]
        if "selection_count" in gold:
            checks.append(
                _check(
                    "selection_count",
                    sel.get("selection_count") == gold.get("selection_count"),
                    f"got={sel.get('selection_count')}",
                )
            )
        result.checks = checks
        result.passed = all(c["passed"] for c in checks)
        return result

    if flow == "reflect_seed":
        packet = enrich_reflect_packet(dict(inp.get("reflect_packet") or {}))
        seed = seed_reflect_diagnosis_from_measured(packet)
        forbid = {_norm(x) for x in (gold.get("must_not_repair_kind") or [])}
        checks = [
            _check(
                "repair_kind",
                (not gold.get("repair_kind"))
                or _norm(seed.repair.kind) == _norm(gold.get("repair_kind")),
                f"expect={gold.get('repair_kind')!r} got={seed.repair.kind!r}",
            ),
            _check(
                "capability",
                (not gold.get("capability"))
                or _norm(seed.repair.capability) == _norm(gold.get("capability")),
                f"expect={gold.get('capability')!r} got={seed.repair.capability!r}",
            ),
            _check(
                "cause",
                (not gold.get("cause")) or _norm(seed.cause) == _norm(gold.get("cause")),
                f"got={seed.cause!r}",
            ),
            _check(
                "must_not_repair_kind",
                _norm(seed.repair.kind) not in forbid,
                f"got={seed.repair.kind!r} forbid={sorted(forbid)}",
            ),
        ]
        if gold.get("recommended_next"):
            checks.append(
                _check(
                    "recommended_next",
                    _norm(seed.recommended_next) == _norm(gold.get("recommended_next")),
                    f"expect={gold.get('recommended_next')!r} got={seed.recommended_next!r}",
                )
            )
        if gold.get("target"):
            checks.append(
                _check(
                    "target",
                    _norm(seed.repair.target) == _norm(gold.get("target")),
                    f"got={seed.repair.target!r}",
                )
            )
        result.checks = checks
        result.passed = all(c["passed"] for c in checks)
        return result

    if flow == "revert_plan":
        doc = dict(inp.get("world_document") or {})
        plan = analyze_revert_plan(
            document=doc,
            effect_trace=list(inp.get("effect_trace") or []),
            goal_referents=list(inp.get("goal_referents") or []),
        )
        plan = approve_revert_plan(plan, auto=True)
        outcome = revert_effects(
            app="WhatsApp",
            document=doc,
            effect_trace=list(inp.get("effect_trace") or []),
            goal_referents=list(inp.get("goal_referents") or []),
            dry_run=True,
            force_approve=bool(gold.get("approved", True)),
        )
        first = plan.steps[0].realization if plan.steps else ""
        checks = [
            _check(
                "first_realization",
                (not gold.get("first_realization"))
                or _norm(first) == _norm(gold.get("first_realization")),
                f"got={first!r} steps={[s.realization for s in plan.steps]}",
            ),
            _check(
                "approved",
                (gold.get("approved") is None) or bool(plan.approved) is bool(gold.get("approved")),
                f"approved={plan.approved} reason={plan.approval_reason}",
            ),
            _check(
                "execute_ok",
                (gold.get("execute_ok") is None) or bool(outcome.ok) is bool(gold.get("execute_ok")),
                f"ok={outcome.ok} msg={outcome.message}",
            ),
            _check(
                "capability",
                (not gold.get("capability"))
                or _norm(outcome.capability) == _norm(gold.get("capability")),
                f"got={outcome.capability!r}",
            ),
        ]
        result.checks = checks
        result.passed = all(c["passed"] for c in checks)
        return result

    if flow == "brain_repair":
        packet = enrich_reflect_packet(dict(inp.get("reflect_packet") or {}))
        expl = finalize_surprise_explanation(
            inp.get("model_explanation") or {"cause": "unknown", "confidence": 0.2},
            reflect_packet=packet,
        )
        state = ExecutionState()
        state.perception_mode = "reflect"
        state.last_meta_action = "reflect"
        state.last_surprise_explanation = expl
        step = dict(inp.get("last_plan_step") or {})
        state.last_plan_step = type("S", (), step)()
        chooser = dict(inp.get("chooser_outcome") or {})
        steered = apply_surprise_explanation(
            DecisionOutcome(
                ok=True,
                capability=str(chooser.get("capability") or "observe"),
                target=str(chooser.get("target") or ""),
                why=str(chooser.get("why") or "golden"),
                confidence=float(chooser.get("confidence") or 0.0),
                realization="golden_chooser",
            ),
            state,
        )
        repair = expl.get("repair") if isinstance(expl.get("repair"), dict) else {}
        forbid = {_norm(x) for x in (gold.get("must_not_capability") or [])}
        checks = [
            _check(
                "capability",
                _norm(steered.capability) == _norm(gold.get("capability")),
                f"got={steered.capability!r}",
            ),
            _check(
                "repair_kind",
                (not gold.get("repair_kind"))
                or _norm(repair.get("kind")) == _norm(gold.get("repair_kind")),
                f"got={repair.get('kind')!r}",
            ),
            _check(
                "must_not_capability",
                _norm(steered.capability) not in forbid,
                f"got={steered.capability!r}",
            ),
        ]
        if gold.get("realization_prefix"):
            checks.append(
                _check(
                    "realization_prefix",
                    str(steered.realization or "").startswith(str(gold.get("realization_prefix"))),
                    f"got={steered.realization!r}",
                )
            )
        result.checks = checks
        result.passed = all(c["passed"] for c in checks)
        return result

    result.checks = [_check("flow", False, f"unknown ui flow={flow!r}")]
    return result


def score_all(
    *,
    golden_root: str = DEFAULT_GOLDEN_DIR,
    version: str = GOLDEN_VERSION,
    fixture_corpus: str = DEFAULT_CORPUS_DIR,
) -> Dict[str, Any]:
    fixtures = annotate(load_fixtures(fixture_corpus), overrides=load_overrides())
    by_id = {f.id: f for f in fixtures}
    cases = load_all_cases(root=golden_root, version=version)
    module_scores: Dict[str, List[CaseScore]] = {}

    for module, module_cases in cases.items():
        scored: List[CaseScore] = []
        for case in module_cases:
            if module == "perceive":
                scored.append(score_perceive_case(case, by_id))
            elif module == "critic":
                scored.append(score_critic_case(case))
            elif module == "meta_action":
                scored.append(score_meta_action_case(case))
            elif module == "brain":
                scored.append(score_brain_case(case))
            elif module == "actor":
                scored.append(score_actor_case(case))
            elif module == "brain_actor_handoff":
                scored.append(score_brain_actor_handoff_case(case))
            elif module == "reflect":
                scored.append(score_reflect_case(case))
            elif module == "flow":
                scored.append(score_flow_case(case))
            elif module == "ui":
                scored.append(score_ui_case(case))
            else:
                scored.append(
                    CaseScore(
                        case_id=case.id,
                        module=module,
                        passed=False,
                        checks=[_check("unknown_module", False, module)],
                    )
                )
        module_scores[module] = scored

    metrics: List[MetricResult] = []
    per_module: Dict[str, Any] = {}
    for module in GOLDEN_MODULES:
        scored = module_scores.get(module) or []
        hits = sum(1 for s in scored if s.passed)
        total = len(scored)
        rate = _rate(hits, total)
        per_module[module] = {
            "cases": total,
            "passed": hits,
            "accuracy": rate,
            "failures": [s.to_dict() for s in scored if not s.passed],
        }
        metrics.append(
            MetricResult(
                name=f"golden_{module}_accuracy",
                layer=LAYER,
                value=rate,
                scored=total,
                skipped=0,
                question=f"Does {module} match frozen golden_v1 decision structure?",
                examples=[
                    f"{s.case_id}:{[c['name'] for c in s.checks if not c.get('passed')]}"
                    for s in scored
                    if not s.passed
                ][:8],
            )
        )

    accuracies = [m["accuracy"] for m in per_module.values() if isinstance(m.get("accuracy"), float)]
    mean = round(sum(accuracies) / len(accuracies), 4) if accuracies else None
    return {
        "version": version,
        "layer": LAYER,
        "manifest": load_manifest(golden_root, version),
        "mean_accuracy": mean,
        "modules": per_module,
        "metrics": [m.to_dict() for m in metrics],
        "cases_total": sum(len(v) for v in module_scores.values()),
    }


def summarize_golden(
    *,
    golden_root: str = DEFAULT_GOLDEN_DIR,
    version: str = GOLDEN_VERSION,
    fixture_corpus: str = DEFAULT_CORPUS_DIR,
) -> Dict[str, Any]:
    """Report block for ``plugin.evals.run``."""
    return score_all(
        golden_root=golden_root,
        version=version,
        fixture_corpus=fixture_corpus,
    )


def render(report: Dict[str, Any]) -> str:
    lines = [
        f"golden_{report.get('version')} — mean={report.get('mean_accuracy')}  "
        f"cases={report.get('cases_total')}",
    ]
    for module, block in (report.get("modules") or {}).items():
        acc = block.get("accuracy")
        rendered = f"{acc:.0%}" if isinstance(acc, float) else "n/a"
        lines.append(
            f"  {module:<14} {rendered:>8}  "
            f"{block.get('passed', 0)}/{block.get('cases', 0)}"
        )
        for fail in (block.get("failures") or [])[:3]:
            lines.append(f"      FAIL {fail.get('case_id')} {fail.get('failures')}")
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Score module golden corpus")
    parser.add_argument("--golden-root", default=DEFAULT_GOLDEN_DIR)
    parser.add_argument("--version", default=GOLDEN_VERSION)
    parser.add_argument("--fixtures", default=DEFAULT_CORPUS_DIR)
    parser.add_argument("--json", default="")
    args = parser.parse_args(argv)
    report = score_all(
        golden_root=args.golden_root,
        version=args.version,
        fixture_corpus=args.fixtures,
    )
    print(render(report))
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(report, indent=2) + "\n")
    # Exit on blocking failures (known_gap_case_ids allowed), not mean alone.
    from plugin.evals.gates import _golden_known_gap_ids

    gaps = _golden_known_gap_ids()
    blocking = []
    for block in (report.get("modules") or {}).values():
        for f in block.get("failures") or []:
            cid = str(f.get("case_id") or "")
            if cid and cid not in gaps:
                blocking.append(cid)
    if blocking:
        print(f"BLOCKING: {blocking[:8]}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
