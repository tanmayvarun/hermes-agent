"""Instrumented Call Pallavi benchmark.

Modes
-----
* fixture (default): offline JSON fixtures + Ghost dry-run
* live (``--live``): launch WhatsApp, macapptree AX observe, real Ghost clicks,
  re-observe after each action, verify call is ringing
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from plugin.agent.action import Action
from plugin.agent.controller import resolve_step_budget, run_goal_closed_loop
from plugin.agent.decision import DecisionEngine
from plugin.agent.goal import Goal
from plugin.agent.runtime.recovery import recover_after_unexpected
from plugin.agent.runtime.state import RuntimeState
from hermes_cli.config import load_config_readonly
from plugin.executor.ghost import ExecResult, ghost_available, get_executor
from plugin.experiments.harness import FIXTURES
from plugin.experiments.logger import EventLogger
from plugin.experiments.live_observe import (
    _accessibility_trusted,
    _live_observe,
    _prompt_accessibility_if_needed,
    _wait,
    entity_snapshot,
    format_raw_observation_trace,
)
from plugin.perception.macos.accessibility.observer import (
    FixtureObserver,
    MacAppTreeObserver,
    get_observer,
    macapptree_available,
)
from plugin.perception.macos.launch import launch_app
from plugin.perception.observation import Observation
from plugin.worldmodel.model import WorldModel

APP = "WhatsApp"
PlanStep = Action

# AX text that indicates an outbound call is ringing / in progress.
# Avoid bare "end" — it false-positives on "end-to-end encrypted".
_RINGING_PATTERNS = (
    r"\bcalling\b",
    r"\bringing\b",
    r"\bend call\b",
    r"\bcall in progress\b",
    r"\bconnecting\b",
    r"\bincoming call\b",
    r"\bongoing call\b",
)


def _joined_labels(wm: WorldModel) -> str:
    parts = []
    for e in wm.entities.values():
        if not e.visible:
            continue
        parts.append(e.semantic_role or "")
        parts.append(e.label or "")
    return " ".join(parts).lower()


def detect_call_ringing(wm: WorldModel, obs: Optional[Observation] = None) -> Dict[str, Any]:
    """Verify outbound call UI from WorldModel (+ optional raw observation)."""
    from plugin.agent.whatsapp_view import WhatsAppWorldView
    from plugin.agent.apps.whatsapp_targets import end_call_clickable, end_call_visible, voice_call_chrome_visible

    view = WhatsAppWorldView.from_world_model(wm)
    joined = _joined_labels(wm)
    screen = (wm.summary().get("current_screen") or {}).get("label") or view.screen.lower()
    matched: List[str] = []
    for pat in _RINGING_PATTERNS:
        if re.search(pat, joined):
            matched.append(pat)
    if obs is not None:
        raw = " ".join(
            f"{n.name or ''} {n.description or ''} {n.value or ''}" for n in obs.nodes
        ).lower()
        raw = re.sub(r"[\u200e\u200f\u202a-\u202e\u2066-\u2069]", "", raw)
        for pat in _RINGING_PATTERNS:
            if re.search(pat, raw) and pat not in matched:
                matched.append(pat)

    # Ringing is only trusted when the semantic view agrees with real hangup/call chrome.
    has_hangup = end_call_clickable(wm) or end_call_visible(wm)
    has_call_chrome = voice_call_chrome_visible(wm) or view.call_state == "ringing"
    ringing = bool(matched) and (has_hangup or has_call_chrome)
    if view.screen == "CALLING" and has_hangup:
        ringing = True
    return {
        "ringing": ringing,
        "screen": screen,
        "matched_patterns": matched,
        "end_call": has_hangup,
        "evidence": joined[:500],
        "semantic_view": view.to_dict(),
    }


def find_action_target(wm: WorldModel, semantic: str, action: str, *, action_family: str = ""):
    """Resolve click/type targets with WhatsApp-overfitted rules (exact labels, bans)."""
    from plugin.agent.apps.whatsapp_targets import resolve_whatsapp_target

    return resolve_whatsapp_target(
        wm,
        semantic,
        action=action,
        action_family=action_family,
    )


def _action_label_for_step(step: PlanStep) -> str:
    sem = (step.semantic_target or "").lower()
    action = step.action.lower()
    if action == "type" or (action == "click" and sem == "search"):
        return "open_search"
    if action == "click" and sem in {"call", "voice call", "audio call"}:
        return "call"
    if action == "click" and sem and sem not in {"search", "end call", "end"}:
        return "open_chat"
    return action or "act"


def _resolve_plan_action_to_fixture(
    step: PlanStep,
    screen_label: str,
) -> Tuple[Optional[Path], Optional[str]]:
    sem = (step.semantic_target or "").lower()
    action = step.action.lower()
    if action == "type" or (action == "click" and sem == "search"):
        return FIXTURES / "whatsapp_search.json", "open_search"
    if action == "click" and sem in {"call", "voice call", "audio call"}:
        return FIXTURES / "whatsapp_call.json", "call"
    if action == "click" and sem and sem not in {"search", "end call", "end"}:
        return FIXTURES / "whatsapp_chat.json", "open_chat"
    if action == "observe":
        return None, None
    order = {
        "conversation": (FIXTURES / "whatsapp_search.json", "open_search"),
        "search": (FIXTURES / "whatsapp_chat.json", "open_chat"),
        "chat": (FIXTURES / "whatsapp_call.json", "call"),
    }
    return order.get(screen_label, (None, None))

def _verify_ringing_poll(
    log: EventLogger,
    runtime: RuntimeState,
    *,
    app: str,
    step: int,
    with_screenshot: bool,
    timeout_s: float = 12.0,
    interval_s: float = 1.5,
) -> Dict[str, Any]:
    """Poll live AX until ringing evidence appears or timeout."""
    deadline = time.time() + timeout_s
    last: Dict[str, Any] = {"ringing": False}
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        try:
            obs = _live_observe(log, app=app, step=step, with_screenshot=with_screenshot)
        except Exception as e:
            log.step("ringing_poll_observe_fail", status="fail", step=step, message=str(e), detail=f"attempt={attempt}")
            _wait(log, interval_s, reason="retry after observe failure", step=step)
            continue
        patch = runtime.world_model.ingest(obs, action="verify_ringing")
        log.world_patch(
            {
                "screen": patch.screen_label,
                "retention": patch.retention,
                "entities": entity_snapshot(runtime.world_model),
                "phase": "ringing_poll",
                "attempt": attempt,
            },
            step=step,
        )
        last = detect_call_ringing(runtime.world_model, obs)
        log.check(
            "call_ringing_poll",
            ok=bool(last["ringing"]),
            expected="ringing/calling/end-call UI",
            actual=last,
            step=step,
        )
        if last["ringing"]:
            return last
        _wait(log, interval_s, reason="waiting for ringing UI", step=step)
    return last


def _call_mentions_relaxed(view: Any, contact: str) -> bool:
    """True if open conversation / evidence mentions contact or its reference stem."""
    from plugin.agent.reference import interpret_reference

    blob = " ".join(
        [
            str(getattr(view, "open_conversation", None) or (view.get("open_conversation") if isinstance(view, dict) else "") or ""),
            " ".join(getattr(view, "visible_contacts", None) or (view.get("visible_contacts") if isinstance(view, dict) else []) or []),
        ]
    ).lower()
    ref = interpret_reference(contact or "")
    needles = [contact or "", ref.name or ""] + list(ref.search_hypotheses or [])
    for n in needles:
        n = (n or "").strip().lower()
        if not n:
            continue
        if n in blob:
            return True
        stem = n.rstrip("….").split()[0]
        if len(stem) >= 2 and stem in blob:
            return True
    return bool(re.search(r"\bend call\b|\bcalling\b|\bringing\b", blob))


def run_call_pallavi_live(
    *,
    log: EventLogger,
    contact: str = "Pallavi",
    goal: str = "Call Pallavi on WhatsApp",
    with_screenshot: bool = False,
    settle_s: float = 1.2,
    hangup: bool = False,
    target_name: str = "",
    target_kind: str = "",
    max_stepcount: Optional[int] = None,
) -> bool:
    """Real WhatsApp Desktop path: launch → AX → Ghost/AX click → verify ringing.

    Must be launched from Terminal.app / iTerm with Accessibility enabled for
    that host — not from Cursor's agent shell.
    """
    runtime = RuntimeState(active_task=goal)
    step_i = 0

    # Prerequisites
    log.step("prereq_check", step=step_i, message="checking Terminal Accessibility + macapptree/ax")
    trusted = _accessibility_trusted()
    if not trusted:
        log.step(
            "accessibility_prompt",
            step=step_i,
            status="warn",
            message="process not AX-trusted — requesting prompt (enable Terminal/iTerm, not Cursor)",
        )
        trusted = _prompt_accessibility_if_needed()
    log.check(
        "accessibility_trusted",
        ok=trusted,
        expected=True,
        actual=trusted,
        step=step_i,
    )
    if not trusted:
        log.result(
            False,
            detail=(
                "Accessibility not granted to this process. "
                "Run from Terminal.app or iTerm (not Cursor), then: "
                "System Settings → Privacy & Security → Accessibility → enable Terminal/iTerm. "
                "See plugin/PERMISSIONS.md"
            ),
        )
        log.write_summary_md()
        print(
            "\n*** LIVE BLOCKED: grant Accessibility to Terminal.app / iTerm, "
            "then re-run this command in that terminal (not Cursor). ***\n"
            "  cd hermes-agent && source .venv/bin/activate && export PYTHONPATH=.\n"
            "  python -m plugin call-pallavi --live --hangup --contact Pallavi\n",
            flush=True,
        )
        return False

    has_tree = macapptree_available()
    has_ghost = ghost_available()
    from plugin.executor.ax_action import ax_available

    has_ax = ax_available()
    log.check("macapptree_installed", ok=has_tree, expected=True, actual=has_tree, step=step_i)
    log.check("ghost_cli_installed", ok=has_ghost, expected=True, actual=has_ghost, step=step_i)
    log.check("ax_pyobjc_available", ok=has_ax, expected=True, actual=has_ax, step=step_i)
    if not has_tree and not has_ax:
        log.result(False, detail="need macapptree or PyObjC AX")
        log.write_summary_md()
        return False
    if not has_ghost and not has_ax:
        log.result(False, detail="need Ghost CLI or PyObjC AX for clicks")
        log.write_summary_md()
        return False
    if not has_ghost and has_ax:
        log.step(
            "executor_backend",
            step=step_i,
            status="warn",
            message="Ghost not found — using PyObjC AX Press/type",
        )

    executor = get_executor(dry_run=False, app=APP)

    # Launch
    launched = launch_app(APP)
    log.step(
        "launch_whatsapp",
        step=step_i,
        status="ok" if launched.ok else "fail",
        message=launched.message,
        detail=" ".join(launched.command),
    )
    if not launched.ok:
        log.result(False, detail=f"failed to launch WhatsApp: {launched.message}")
        log.write_summary_md()
        return False
    _wait(log, 2.5, reason="WhatsApp startup settle", step=step_i)

    # Initial live observe
    try:
        obs = _live_observe(log, app=APP, step=step_i, with_screenshot=with_screenshot)
    except Exception as e:
        log.step("observe_initial", status="fail", step=step_i, message=str(e))
        log.result(False, detail=f"initial live observe failed (Accessibility?): {e}")
        log.write_summary_md()
        return False

    if len(obs.nodes) == 0:
        log.result(False, detail="AX tree empty — grant Accessibility to Terminal and retry")
        log.write_summary_md()
        return False

    patch = runtime.world_model.ingest(obs)
    log.world_patch(
        {
            "screen": patch.screen_label,
            "screen_id": patch.screen_id,
            "retention": patch.retention,
            "entities": entity_snapshot(runtime.world_model),
            "controller": "closed_loop",
        },
        step=step_i,
    )

    # Leave leftover calls so the controller does not false-succeed on End Call chrome.
    from plugin.agent.apps.whatsapp_targets import end_call_clickable, end_call_visible, resolve_whatsapp_target
    from plugin.agent.whatsapp_view import WhatsAppWorldView
    from plugin.executor.ax_action import ax_click, ax_hangup_call, ax_press_escape

    for attempt in range(1, 4):
        view0 = WhatsAppWorldView.from_world_model(runtime.world_model)
        has_hangup = end_call_clickable(runtime.world_model) or end_call_visible(runtime.world_model)
        calling = view0.call_state == "ringing" or view0.screen == "CALLING"
        if not calling and not has_hangup:
            break
        log.step(
            "preclear_hangup",
            step=step_i,
            message=f"ending leftover call before closed-loop (attempt {attempt}) hangup_visible={has_hangup}",
        )
        end_btn = resolve_whatsapp_target(
            runtime.world_model, "End Call", action="click", action_family="end_call"
        ) or resolve_whatsapp_target(
            runtime.world_model, "Decline", action="click", action_family="end_call"
        )
        if end_btn is not None:
            hr = ax_hangup_call(APP, bounds=end_btn.bounds, label=end_btn.label or "End Call")
        elif calling:
            hr = ax_press_escape(APP)
        else:
            break
        log.execution({**hr.__dict__, "planned_action": "preclear_hangup"}, step=step_i)
        _wait(log, 1.8, reason="after preclear hangup", step=step_i)
        obs = _live_observe(log, app=APP, step=step_i, with_screenshot=with_screenshot)
        patch = runtime.world_model.ingest(obs, action="preclear_hangup")
        log.world_patch(
            {
                "screen": patch.screen_label,
                "action": "preclear_hangup",
                "retention": patch.retention,
                "whatsapp_view": WhatsAppWorldView.from_world_model(runtime.world_model).to_dict(),
                "entities": entity_snapshot(runtime.world_model),
            },
            step=step_i,
        )

    view_ready = WhatsAppWorldView.from_world_model(runtime.world_model)
    if view_ready.call_state == "ringing" or view_ready.screen == "CALLING":
        ax_press_escape(APP)
        time.sleep(0.4)
        obs = _live_observe(log, app=APP, step=step_i, with_screenshot=with_screenshot)
        runtime.world_model.ingest(obs, action="preclear_escape")
        view_ready = WhatsAppWorldView.from_world_model(runtime.world_model)

    if view_ready.call_state == "ringing" or end_call_clickable(runtime.world_model):
        log.step(
            "preclear_incomplete",
            step=step_i,
            status="warn",
            message="call UI still present after preclear — will require agent start_call (no stale success)",
        )
    else:
        try:
            ax_press_escape(APP)
            time.sleep(0.35)
        except Exception:
            pass

    from plugin.executor.ax_action import ax_click, ax_press_escape, ax_type

    class _LiveExecutor:
        """Maps PlanStep → Ghost/AX. Executor OK is necessary but not sufficient."""

        def execute(self, step: PlanStep) -> ExecResult:
            from plugin.agent.apps.whatsapp_targets import resolve_whatsapp_target

            act = step.action.lower()
            fam = getattr(step, "action_family", "") or ""
            if act == "type":
                query = step.text or contact
                return ax_type(APP, query, into="Search", submit=False, search_bounds=None)
            if fam == "end_call" or (step.semantic_target or "").lower() in {
                "end call",
                "decline",
            }:
                ent = resolve_whatsapp_target(
                    runtime.world_model,
                    step.semantic_target or "End Call",
                    action="click",
                    action_family="end_call",
                    target_entity_id=getattr(step, "target_entity_id", None),
                )
                return ax_hangup_call(
                    APP,
                    bounds=ent.bounds if ent else None,
                    label=(ent.label if ent else None) or step.semantic_target or "End Call",
                )
            if act == "dismiss":
                target = step.semantic_target or "Clear Menu"
                ent = resolve_whatsapp_target(
                    runtime.world_model,
                    target,
                    action="click",
                    action_family="dismiss",
                    target_entity_id=getattr(step, "target_entity_id", None),
                )
                if ent is not None:
                    return ax_click(APP, ent.label or target, bounds=ent.bounds)
                return ax_press_escape(APP)
            if act == "click":
                target = step.semantic_target or step.text
                tid = getattr(step, "target_entity_id", None)
                if target.lower() == "search":
                    return ax_click(APP, "Search")
                # Prefer Voice / dropdown over Call when starting a call
                if fam == "start_call" or target.lower() in {"call", "voice", "voice call", "audio call"}:
                    ent = resolve_whatsapp_target(
                        runtime.world_model,
                        "Voice",
                        action="click",
                        action_family="start_call",
                        target_entity_id=tid,
                    )
                    if ent is None:
                        for needle in (
                            "Open call dropdown menu",
                            "Open call dropdown",
                            "call dropdown",
                        ):
                            drop = resolve_whatsapp_target(
                                runtime.world_model, needle, action="click", action_family="explore_chrome"
                            )
                            if drop is not None:
                                ent = drop
                                target = drop.label or needle
                                break
                    if ent is None:
                        ent = resolve_whatsapp_target(
                            runtime.world_model, target, action="click", action_family="start_call"
                        )
                else:
                    ent = resolve_whatsapp_target(
                        runtime.world_model,
                        target,
                        action="click",
                        action_family=fam,
                        target_entity_id=tid,
                    )
                if ent is None:
                    return ax_click(APP, target)
                runtime.execution_state.last_target_id = ent.id
                desc = str(ent.attributes.get("description") or "")
                log.log(
                    "click_target",
                    {
                        "semantic": target,
                        "entity_id": ent.id,
                        "label": ent.label,
                        "description": desc,
                        "bounds": ent.bounds,
                        "entity_type": ent.entity_type,
                    },
                    status="ok",
                    step=runtime.execution_state.iteration or 0,
                )
                return ax_click(APP, ent.label or target, bounds=ent.bounds)
            if act == "dismiss":
                ent = resolve_whatsapp_target(
                    runtime.world_model,
                    step.semantic_target or "Not Now",
                    action="click",
                    action_family="dismiss",
                    target_entity_id=getattr(step, "target_entity_id", None),
                )
                if ent is None:
                    return ExecResult(ok=False, backend="ax", message="dismiss target not found")
                return ax_click(APP, ent.label or step.semantic_target or "Not Now", bounds=ent.bounds)
            return ExecResult(ok=False, backend="ax", message=f"unsupported action {step.action}")

    goal_obj = Goal(
        kind="whatsapp_voice_call",
        contact=contact,
        hangup_after=hangup,
        require_agent_initiated_call=True,
    )
    if target_kind or target_name:
        from plugin.agent.reference import interpret_reference

        goal_obj.reference = interpret_reference(
            contact,
            kind=target_kind or None,
            name=target_name or None,
        )
    log.step(
        "closed_loop_start",
        step=step_i,
        message=f"closed-loop goal={goal_obj.description}",
        detail="transition-aware DecisionEngine (observe→act→evaluate progress)",
    )

    def _observe() -> Observation:
        # Avoid double-logging inside _live_observe's log.observation by using a quiet path
        return _live_observe(log, app=APP, step=runtime.execution_state.iteration or 0, with_screenshot=with_screenshot)

    def _observe_with_screenshot() -> Observation:
        return _live_observe(log, app=APP, step=runtime.execution_state.iteration or 0, with_screenshot=True)

    def _wait_cb(seconds: float, reason: str) -> None:
        _wait(log, seconds, reason=reason, step=runtime.execution_state.iteration or 0)

    result = run_goal_closed_loop(
        runtime,
        goal_obj,
        observe=_observe,
        execute=_LiveExecutor(),
        log=log,
        max_iterations=15,
        max_stepcount=resolve_step_budget(
            max_iterations=15,
            max_stepcount=max_stepcount,
            config=load_config_readonly(),
        ),
        settle_s=max(settle_s, 1.0),
        wait_fn=_wait_cb,
        engine=DecisionEngine(selector_enabled=True),
    )

    summary = runtime.world_model.summary()
    view = WhatsAppWorldView.from_world_model(runtime.world_model)
    ring_final = detect_call_ringing(runtime.world_model)
    log.log(
        "world_summary",
        {
            "active_app": summary.get("active_app"),
            "current_screen": summary.get("current_screen"),
            "whatsapp_view": view.to_dict(),
            "entity_count": len(summary.get("entities") or []),
            "transition_count": summary.get("transition_count"),
            "nav_mermaid": summary.get("nav_mermaid"),
            "entities": summary.get("entities"),
            "ringing": ring_final,
            "closed_loop": result.__dict__,
            "planner_invocations": runtime.execution_state.planner_invocations,
        },
        status="ok",
    )

    success = bool(result.ok)
    # Authoritative: freshly observed world via goal evaluator (not post-hoc ring alone)
    if not success:
        from plugin.agent.goal import evaluate_goal as _eval_goal

        final_gs = _eval_goal(goal_obj, runtime.world_model)
        if final_gs.succeeded:
            success = True
            result.ok = True
            result.reason = "goal satisfied on final world observation"
            if final_gs.evidence:
                result.evidence = final_gs.evidence

    if success and hangup:
        end_btn = resolve_whatsapp_target(
            runtime.world_model, "End Call", action="click", action_family="end_call"
        ) or resolve_whatsapp_target(
            runtime.world_model, "Decline", action="click", action_family="end_call"
        )
        hr = ax_hangup_call(
            APP,
            bounds=end_btn.bounds if end_btn else None,
            label=(end_btn.label if end_btn else None) or "End Call",
        )
        log.execution({**hr.__dict__, "planned_action": "hangup"}, step=runtime.execution_state.iteration)

    log.check(
        "goal_call_pallavi_ringing",
        ok=success,
        expected=f"closed-loop call ringing for {contact!r}",
        actual={
            **ring_final,
            "controller_ok": result.ok,
            "controller_reason": result.reason,
            "planner_invocations": result.planner_invocations,
            "iterations": result.iterations,
            "whatsapp_view": view.to_dict(),
        },
    )
    log.check(
        "planner_reentry",
        ok=result.planner_invocations >= max(1, result.iterations - 1) if result.iterations else result.planner_invocations >= 1,
        expected=">=1 planner call per decision cycle",
        actual={"planner_invocations": result.planner_invocations, "iterations": result.iterations},
    )
    log.result(
        success,
        detail=(
            f"closed_loop ok={result.ok} reason={result.reason!r} "
            f"iterations={result.iterations} planner_invocations={result.planner_invocations} "
            f"ringing={ring_final.get('ringing')}"
        ),
    )
    log.write_summary_md()
    return success


def run_call_pallavi_fixture(
    *,
    log: EventLogger,
    inject_fault: bool = False,
    goal: str = "Call Pallavi on WhatsApp",
) -> bool:
    """Offline fixture path (unchanged semantics, detailed logs)."""
    runtime = RuntimeState(active_task=goal)
    executor = get_executor(dry_run=True, app=APP)
    step_i = 0
    conv = FIXTURES / "whatsapp_conversation.json"
    log.step("observe_initial", step=step_i, message="load conversation fixture", fixture=str(conv))
    obs = FixtureObserver(conv).observe()
    log.observation(
        {
            "fixture": str(conv),
            "app": obs.app_name,
            "nodes": len(obs.nodes),
            "source": obs.source,
        },
        step=step_i,
    )
    patch = runtime.world_model.ingest(obs)
    log.world_patch(
        {
            "screen": patch.screen_label,
            "retention": patch.retention,
            "entities": entity_snapshot(runtime.world_model),
        },
        step=step_i,
        status="ok" if patch.screen_label == "conversation" else "fail",
    )
    goal_obj = Goal(kind="whatsapp_voice_call" if "call" in goal.lower() else "unknown", contact=goal)
    decision = DecisionEngine(selector_enabled=True).decide(goal_obj, runtime.world_model, runtime.execution_state)
    log.planner_decision(
        {"goal": goal_obj.description, "action": None if decision is None else decision.__dict__, "mode": "fixture"},
        step=step_i,
    )

    overall_ok = True
    if decision is not None:
        pstep = decision
        screen = (runtime.world_model.summary().get("current_screen") or {}).get("label") or ""
        log.step(
            "plan_step_begin",
            step=step_i,
            message=f"{pstep.action} → {pstep.semantic_target or pstep.text}",
            action=pstep.action,
            semantic=pstep.semantic_target,
        )
        target_sem = pstep.semantic_target or pstep.text
        ent = find_action_target(runtime.world_model, target_sem, pstep.action)
        if pstep.action.lower() == "type":
            er = executor.type_text(pstep.text or "Pallavi", into=target_sem or "Search", app=APP)
            log.execution({**er.__dict__, "planned_action": "Type"}, step=step_i)
        elif pstep.action.lower() == "click" and ent is not None:
            er = executor.click(ent, app=APP)
            log.execution({**er.__dict__, "planned_action": "Click", "entity_id": ent.id}, step=step_i)
        elif pstep.action.lower() == "observe":
            pass
        else:
            fixture, action_label = _resolve_plan_action_to_fixture(pstep, screen)
            if fixture is None:
                pass
            if inject_fault and action_label == "call":
                recovery = recover_after_unexpected(
                    runtime, FixtureObserver(fixture).observe(), goal=goal
                )
                log.log("recovery", {"message": recovery.message}, status="ok", step=step_i)
                pass
            step_obs = FixtureObserver(fixture).observe()
            log.observation({"fixture": str(fixture), "nodes": len(step_obs.nodes), "after_action": action_label}, step=step_i)
            patch = runtime.world_model.ingest(step_obs, action=action_label, target_entity_id=ent.id if ent else None)
            log.world_patch({"screen": patch.screen_label, "action": action_label, "retention": patch.retention}, step=step_i)
            if action_label == "call":
                ring = detect_call_ringing(runtime.world_model, step_obs)
                log.check("call_is_ringing", ok=ring["ringing"], expected="ringing UI", actual=ring, step=step_i)
                overall_ok = overall_ok and ring["ringing"]
            log.step("plan_step_end", step=step_i, screen=patch.screen_label)

    ring_final = detect_call_ringing(runtime.world_model)
    success = overall_ok and ring_final["ringing"]
    log.log("world_summary", {"ringing": ring_final, **runtime.world_model.summary()}, status="ok")
    log.check("goal_call_pallavi_reached", ok=success, expected="call ringing (fixture)", actual=ring_final)
    log.result(success, detail=f"fixture ringing={ring_final.get('ringing')}")
    log.write_summary_md()
    return success


def run_call_pallavi(
    *,
    log_path: Path,
    live: bool = False,
    inject_fault: bool = False,
    goal: str = "Call Pallavi on WhatsApp",
    contact: str = "Pallavi",
    with_screenshot: bool = False,
    hangup: bool = False,
    target_name: str = "",
    target_kind: str = "",
    max_stepcount: Optional[int] = None,
) -> Tuple[bool, EventLogger]:
    run_id = f"call-pallavi-{'live' if live else 'fixture'}-{int(time.time())}"
    log_path = Path(log_path)
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("", encoding="utf-8")
    except OSError:
        pass
    log = EventLogger(log_path, also_console=True, run_id=run_id)
    log.begin_run(
        goal,
        meta={
            "mode": "live" if live else "fixture_dry_run",
            "inject_fault": inject_fault,
            "live": live,
            "contact": contact,
            "target_name": target_name,
            "target_kind": target_kind,
            "hangup": hangup,
            "with_screenshot": with_screenshot,
        },
    )
    if live:
        ok = run_call_pallavi_live(
            log=log,
            contact=contact,
            goal=goal,
            with_screenshot=with_screenshot,
            hangup=hangup,
            target_name=target_name,
            target_kind=target_kind,
            max_stepcount=max_stepcount,
        )
    else:
        ok = run_call_pallavi_fixture(log=log, inject_fault=inject_fault, goal=goal)
    return ok, log
