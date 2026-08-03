"""Live WhatsApp find-and-forward goal runner (Terminal + Accessibility)."""

from __future__ import annotations

import os
import json
import time
import subprocess
import hashlib
from pathlib import Path
from typing import Any, Optional, Tuple

from plugin.agent.controller import resolve_step_budget, run_goal_closed_loop
from plugin.agent.capabilities.open_entity import _POINT_TARGET_SIZE
from plugin.agent.decision import DecisionEngine
from plugin.agent.goal import Goal
from plugin.agent.perception_cycle import build_view_features
from plugin.agent.runtime.state import RuntimeState
from plugin.agent.whatsapp_view import WhatsAppWorldView
from hermes_cli.config import load_config_readonly
from hermes_cli.fallback_config import get_ordered_model_chain
from plugin.experiments.logger import EventLogger
from plugin.experiments.live_observe import _accessibility_trusted, _live_observe, _prompt_accessibility_if_needed, _wait, entity_snapshot
from plugin.executor.ax_action import ax_available, ax_click, ax_type
from plugin.executor.ghost import ExecResult, get_executor, ghost_available
from plugin.perception.macos.launch import launch_app
from plugin.perception.macos.accessibility.observer import macapptree_available
from plugin.perception.observation import Observation
from utils import base_url_host_matches

APP = "WhatsApp"

_FORWARD_RUNTIME_PROVIDER = "ollama-cloud"
_FORWARD_RUNTIME_MODEL = "gpt-oss:120b"
_PRECLEAR_STALL_SIGNATURE_LIMIT = 2


def _bind_forward_runtime_main() -> None:
    """Pin this live forward run to the primary Ollama Cloud runtime."""
    try:
        from hermes_cli.config import get_env_value_prefer_dotenv

        ollama_base = (
            os.getenv("OLLAMA_BASE_URL", "")
            or get_env_value_prefer_dotenv("OLLAMA_BASE_URL")
            or ""
        ).strip()
        ollama_key = (
            os.getenv("OLLAMA_API_KEY", "")
            or get_env_value_prefer_dotenv("OLLAMA_API_KEY")
            or ""
        ).strip()
    except Exception:
        ollama_base = os.getenv("OLLAMA_BASE_URL", "").strip()
        ollama_key = os.getenv("OLLAMA_API_KEY", "").strip()
    if not ollama_base:
        ollama_base = "https://ollama.com/v1"
    from agent.auxiliary_client import set_runtime_main

    set_runtime_main(
        _FORWARD_RUNTIME_PROVIDER,
        _FORWARD_RUNTIME_MODEL,
        base_url=ollama_base,
        api_key=ollama_key,
    )
    # Keep nested auxiliary tasks on the same runtime so task-local config
    # cannot drift back to a stale alternate provider during this live
    # forward run.
    os.environ["HERMES_CONTENT_OBJECT_RESOLUTION_PROVIDER"] = _FORWARD_RUNTIME_PROVIDER
    os.environ["HERMES_CONTENT_OBJECT_RESOLUTION_MODEL"] = _FORWARD_RUNTIME_MODEL
    os.environ["HERMES_CONTENT_OBJECT_RESOLUTION_BASE_URL"] = ollama_base
    os.environ["HERMES_AUXILIARY_PROVIDER_POLICY"] = "ollama-only"
    # Content-object resolution is the critical "what next?" perception step.
    # Use the same high-capability runtime rather than a stale auxiliary chain.
    os.environ["HERMES_CONTENT_OBJECT_RESOLUTION_TIMEOUT"] = "15"
    try:
        fallback_chain = get_ordered_model_chain(load_config_readonly())
    except Exception:
        fallback_chain = []
    os.environ["HERMES_CONTENT_OBJECT_RESOLUTION_FALLBACK_CHAIN"] = json.dumps(fallback_chain)

    # Leave a clear breadcrumb in the run log so auth/routing mismatches are
    # obvious when the live loop stalls or falls through to another provider.
    try:
        from agent.auxiliary_client import get_runtime_main_snapshot

        runtime = get_runtime_main_snapshot()
        print(
            "[runtime_bind] "
            f"provider={runtime.get('provider') or _FORWARD_RUNTIME_PROVIDER} "
            f"model={runtime.get('model') or _FORWARD_RUNTIME_MODEL} "
            f"base_url={runtime.get('base_url') or ollama_base} "
            f"aux_policy={os.getenv('HERMES_AUXILIARY_PROVIDER_POLICY') or ''} "
            f"ollama_api_key_present={bool((os.getenv('OLLAMA_API_KEY') or '').strip())} "
            f"ollama_api_key_len={len((os.getenv('OLLAMA_API_KEY') or '').strip())} "
            f"ollama_api_key_sha1={(hashlib.sha1((os.getenv('OLLAMA_API_KEY') or '').strip().encode('utf-8')).hexdigest()[:10] if (os.getenv('OLLAMA_API_KEY') or '').strip() else '')}",
            flush=True,
        )
    except Exception:
        pass


def _note_preclear_signature(
    previous_signature: str,
    current_signature: str,
    *,
    repeat_count: int,
) -> tuple[int, bool]:
    """Track repeated preclear states and stop re-trying if nothing changes."""
    prev = (previous_signature or "").strip()
    current = (current_signature or "").strip()
    if not current:
        return 0, False
    if current == prev:
        repeat_count += 1
    else:
        repeat_count = 0
    return repeat_count, repeat_count >= _PRECLEAR_STALL_SIGNATURE_LIMIT


def run_forward_message_live(
    *,
    log: EventLogger,
    prompt: str,
    source_contact: str,
    target_contact: str,
    link_query: str,
    settle_s: float = 1.2,
    max_iterations: int = 20,
    max_stepcount: Optional[int] = None,
) -> bool:
    goal_obj = Goal(
        kind="whatsapp_forward_message",
        contact=source_contact,
        app="WhatsApp",
        prompt=prompt,
        target_contact=target_contact,
        link_query=link_query,
        hangup_after=False,
        require_contact_in_call=False,
    )
    runtime = RuntimeState(active_task=goal_obj.description)
    step_i = 0
    _bind_forward_runtime_main()

    log.step("prereq_check", step=step_i, message="checking Terminal Accessibility")
    trusted = _accessibility_trusted()
    if not trusted:
        trusted = _prompt_accessibility_if_needed()
    log.check("accessibility_trusted", ok=trusted, expected=True, actual=trusted, step=step_i)
    if not trusted:
        log.result(ok=False, detail="Accessibility not trusted for this host")
        log.write_summary_md()
        return False

    has_tree = macapptree_available()
    has_ghost = ghost_available()
    has_ax = ax_available()
    log.check("macapptree_installed", ok=has_tree, expected=True, actual=has_tree, step=step_i)
    log.check("ghost_cli_installed", ok=has_ghost, expected=True, actual=has_ghost, step=step_i)
    log.check("ax_pyobjc_available", ok=has_ax, expected=True, actual=has_ax, step=step_i)
    if not has_tree and not has_ax:
        log.result(False, detail="need macapptree or PyObjC AX")
        log.write_summary_md()
        return False

    get_executor(dry_run=False, app=APP)
    # Force a clean app session so we do not inherit a stale storage-warning
    # overlay from an existing WhatsApp process.
    try:
        subprocess.run(["pkill", "-x", APP], capture_output=True, text=True, timeout=5)
    except Exception:
        pass
    launched = launch_app(APP)
    log.step(
        "launch_whatsapp",
        step=step_i,
        status="ok" if launched.ok else "fail",
        message=launched.message,
    )
    if not launched.ok:
        log.result(False, detail=f"failed to launch WhatsApp: {launched.message}")
        log.write_summary_md()
        return False
    _wait(log, 2.0, reason="WhatsApp startup settle", step=step_i)

    try:
        obs = _live_observe(log, app=APP, step=step_i, with_screenshot=True)
    except Exception as e:
        log.result(False, detail=f"initial observe failed: {e}")
        log.write_summary_md()
        return False
    if not obs.nodes:
        log.result(False, detail="AX tree empty")
        log.write_summary_md()
        return False
    patch = runtime.world_model.ingest(obs)
    # Populate the interpreted-perception cache before we branch on call/list
    # state. This keeps the preclear logic aligned with the smart perception
    # layer instead of the raw AX labels alone.
    try:
        build_view_features(runtime, goal_obj)
    except Exception:
        pass
    log.world_patch(
        {
            "screen": patch.screen_label,
            "retention": patch.retention,
            "entities": entity_snapshot(runtime.world_model),
            "controller": "closed_loop_forward",
        },
        step=step_i,
    )

    # Preclear: hang up leftover calls and return to chat list before closed loop
    from plugin.agent.apps.whatsapp_targets import (
        end_call_clickable,
        end_call_visible,
        resolve_whatsapp_target,
    )
    from plugin.executor.ax_action import ax_hangup_call, ax_press_escape

    for attempt in range(1, 4):
        view0 = WhatsAppWorldView.from_world_model(runtime.world_model)
        has_hangup = end_call_clickable(runtime.world_model) or end_call_visible(runtime.world_model)
        # Only preclear when hangup chrome is actually perceived — not ghost CALLING
        if not has_hangup:
            break
        log.step(
            "preclear_hangup",
            step=step_i,
            message=(
                f"preclear attempt {attempt}: "
                f"screen={view0.screen} call_state={view0.call_state} "
                f"hangup_visible={has_hangup}"
            ),
        )
        end_btn = resolve_whatsapp_target(
            runtime.world_model, "End Call", action="click", action_family="end_call"
        ) or resolve_whatsapp_target(
            runtime.world_model, "Decline", action="click", action_family="end_call"
        )
        if end_btn is not None:
            hr = ax_hangup_call(APP, bounds=end_btn.bounds, label=end_btn.label or "End Call")
        else:
            hr = ax_press_escape(APP)
        log.log(
            "execution",
            {**hr.__dict__, "planned_action": "preclear_hangup", "entity_id": getattr(end_btn, "id", None)},
            status="ok" if hr.ok else "fail",
            step=step_i,
        )
        _wait(log, 1.8, reason="after preclear hangup", step=step_i)
        obs = _live_observe(log, app=APP, step=step_i, with_screenshot=True)
        patch = runtime.world_model.ingest(obs, action="preclear_hangup")
        try:
            build_view_features(runtime, goal_obj)
        except Exception:
            pass
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
    # Real leftover call = hangup control or strong calling chrome with geometry.
    # Ghost CALLING (nav list + zero-bound AX) must not abort forward.
    still_calling = end_call_clickable(runtime.world_model) or (
        end_call_visible(runtime.world_model)
        and (view_ready.screen == "CALLING" or view_ready.call_state == "ringing")
    )
    if still_calling:
        # Last-chance Escape only if perception still shows hangup chrome
        ax_press_escape(APP)
        _wait(log, 0.6, reason="preclear last Escape", step=step_i)
        obs = _live_observe(log, app=APP, step=step_i, with_screenshot=True)
        runtime.world_model.ingest(obs, action="preclear_last_escape")
        view_ready = WhatsAppWorldView.from_world_model(runtime.world_model)
        still_calling = end_call_clickable(runtime.world_model) or (
            end_call_visible(runtime.world_model)
            and (view_ready.screen == "CALLING" or view_ready.call_state == "ringing")
        )

    if still_calling:
        log.step(
            "preclear_failed",
            step=step_i,
            status="fail",
            message=(
                f"call UI still present after hangup — aborting forward "
                f"(screen={view_ready.screen} call_state={view_ready.call_state})"
            ),
        )
        log.result(ok=False, detail="preclear_failed: still CALLING after hangup attempts")
        log.write_summary_md()
        return False

    if view_ready.screen == "CALLING" or view_ready.call_state == "ringing":
        log.step(
            "preclear_ghost_call_ignored",
            step=step_i,
            status="warn",
            message=(
                f"ignoring ghost call perception (no hangup control): "
                f"screen={view_ready.screen} call_state={view_ready.call_state}"
            ),
        )

    if view_ready.unexpected_dialogs and view_ready.screen == "DIALOG":
        log.step(
            "preclear_dialog",
            step=step_i,
            message=f"dismissing dialogs={view_ready.unexpected_dialogs[:3]!r}",
        )
        dismissed = False
        for label in list(view_ready.unexpected_dialogs)[:3]:
            dlg = resolve_whatsapp_target(
                runtime.world_model, label, action="click", action_family="dismiss"
            )
            if dlg is None:
                continue
            ax_click(APP, dlg.label or label, bounds=dlg.bounds)
            dismissed = True
        if not dismissed:
            ax_press_escape(APP)
        _wait(log, 0.6, reason="after preclear dialog", step=step_i)
        obs = _live_observe(log, app=APP, step=step_i, with_screenshot=True)
        patch = runtime.world_model.ingest(obs, action="preclear_dialog")
        log.world_patch(
            {
                "screen": patch.screen_label,
                "action": "preclear_dialog",
                "whatsapp_view": WhatsAppWorldView.from_world_model(runtime.world_model).to_dict(),
                "entities": entity_snapshot(runtime.world_model),
            },
            step=step_i,
        )

    source_l = source_contact.strip().lower()
    preclear_signature = view_ready.world_signature or ""
    preclear_repeat_count = 0
    for preclear_attempt in range(1, 3):
        open_c = (view_ready.open_conversation or "").lower()
        on_source = bool(source_l) and (
            source_l in open_c or any(t in open_c for t in source_l.split() if len(t) > 2)
        )
        if view_ready.screen in {"LIST", "SEARCH", "SEARCH_RESULTS"} or on_source:
            break
        preclear_repeat_count, stalled = _note_preclear_signature(
            preclear_signature,
            view_ready.world_signature or "",
            repeat_count=preclear_repeat_count,
        )
        if stalled:
            log.step(
                "preclear_stalled",
                step=step_i,
                status="warn",
                message=(
                    f"preclear state repeated without progress "
                    f"(screen={view_ready.screen} signature={view_ready.world_signature})"
                ),
            )
            break
        log.step(
            "preclear_list",
            step=step_i,
            message=(
                f"attempt {preclear_attempt}: leaving open={view_ready.open_conversation!r} "
                f"toward chat list"
            ),
        )
        chats = resolve_whatsapp_target(
            runtime.world_model, "Chats", action="click", action_family="open_search"
        )
        if chats:
            ax_click(APP, chats.label or "Chats", bounds=chats.bounds)
        else:
            ax_press_escape(APP)
        _wait(log, 0.8, reason="after preclear list", step=step_i)
        obs = _live_observe(log, app=APP, step=step_i, with_screenshot=True)
        patch = runtime.world_model.ingest(obs, action="preclear_list")
        try:
            build_view_features(runtime, goal_obj)
        except Exception:
            pass
        view_ready = WhatsAppWorldView.from_world_model(runtime.world_model)
        log.world_patch(
            {
                "screen": patch.screen_label,
                "action": "preclear_list",
                "attempt": preclear_attempt,
                "whatsapp_view": view_ready.to_dict(),
                "entities": entity_snapshot(runtime.world_model),
            },
            step=step_i,
        )
        preclear_signature = view_ready.world_signature or preclear_signature

    class _Executor:
        @staticmethod
        def _scroll_anchor() -> Optional[tuple[int, int]]:
            scene = runtime.world_model.last_scene_graph or {}
            regions = scene.get("regions") if isinstance(scene, dict) else []
            preferred_kinds = {"timeline", "conversation", "content"}
            for region in regions or []:
                if not isinstance(region, dict):
                    continue
                kind = str(region.get("kind") or "").lower()
                bounds = region.get("bounds") or []
                if kind not in preferred_kinds or len(bounds) < 4:
                    continue
                try:
                    x, y, w, h = (float(bounds[0]), float(bounds[1]), float(bounds[2]), float(bounds[3]))
                except Exception:
                    continue
                if w > 0 and h > 0:
                    return (int(x + w * 0.62), int(y + h * 0.5))
            ents = [e for e in runtime.world_model.entities.values() if e.visible and len(e.bounds or ()) >= 4]
            if not ents:
                return None
            xs = [float(e.bounds[0]) for e in ents]
            ys = [float(e.bounds[1]) for e in ents]
            rights = [float(e.bounds[0]) + float(e.bounds[2]) for e in ents]
            bottoms = [float(e.bounds[1]) + float(e.bounds[3]) for e in ents]
            x0, y0 = min(xs), min(ys)
            W, H = max(rights) - x0, max(bottoms) - y0
            if W <= 0 or H <= 0:
                return None
            return (int(x0 + W * 0.62), int(y0 + H * 0.5))

        def execute(self, step):
            act = (step.action or "").lower()
            target = step.semantic_target or ""
            fam = getattr(step, "action_family", "") or ""
            if act == "observe":
                return ExecResult(ok=True, backend="none", message="observe")
            if fam == "scroll_content" or act == "scroll":
                direction = getattr(step, "scroll_direction", "") or "down"
                amount = int(getattr(step, "scroll_amount", 0) or 3)
                anchor = self._scroll_anchor()
                return get_executor(dry_run=False, app=APP).scroll(direction, amount=amount, anchor=anchor)
            if act == "type":
                return ax_type(APP, step.text or "", into=target or "Search", submit=False)
            if fam == "end_call" or target.lower() in {"end call", "decline"}:
                ent = resolve_whatsapp_target(
                    runtime.world_model,
                    target or "End Call",
                    action="click",
                    action_family="end_call",
                    target_entity_id=getattr(step, "target_entity_id", None),
                )
                return ax_hangup_call(
                    APP,
                    bounds=ent.bounds if ent else None,
                    label=(ent.label if ent else None) or target or "End Call",
                )
            if act == "dismiss" or fam == "dismiss":
                ent = resolve_whatsapp_target(
                    runtime.world_model,
                    target or "Clear Menu",
                    action="click",
                    action_family="dismiss",
                )
                if ent is not None:
                    return ax_click(APP, ent.label or target or "Clear Menu", bounds=ent.bounds)
                return ax_press_escape(APP)
            if act == "click":
                ent = resolve_whatsapp_target(
                    runtime.world_model,
                    target,
                    action="click",
                    action_family=fam,
                    target_entity_id=getattr(step, "target_entity_id", None),
                )
                if ent is None:
                    return ax_click(APP, target)
                runtime.execution_state.last_target_id = ent.id
                log.log(
                    "click_target",
                    {
                        "semantic": target,
                        "action_family": fam,
                        "entity_id": ent.id,
                        "label": ent.label,
                        "description": str(ent.attributes.get("description") or ""),
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
                    target or "Not Now",
                    action="click",
                    action_family="dismiss",
                )
                if ent is not None:
                    return ax_click(APP, ent.label or target or "Not Now", bounds=ent.bounds)
                return ax_click(APP, target or "Not Now")
            return ExecResult(ok=False, backend="ax", message=f"unsupported action {step.action}")

    log.step(
        "closed_loop_start",
        step=step_i,
        message=f"closed-loop goal={goal_obj.description}",
        detail="whatsapp_forward_message",
    )

    def _observe() -> Observation:
        return _live_observe(
            log, app=APP, step=runtime.execution_state.iteration or 0, with_screenshot=True
        )

    def _observe_with_screenshot() -> Observation:
        return _live_observe(
            log, app=APP, step=runtime.execution_state.iteration or 0, with_screenshot=True
        )

    def _wait_cb(seconds: float, reason: str) -> None:
        _wait(log, seconds, reason=reason, step=runtime.execution_state.iteration or 0)

    result = run_goal_closed_loop(
        runtime,
        goal_obj,
        observe=_observe,
        execute=_Executor(),
        log=log,
        max_iterations=max_iterations,
        max_stepcount=resolve_step_budget(
            max_iterations=max_iterations,
            max_stepcount=max_stepcount,
            config=load_config_readonly(),
        ),
        settle_s=max(settle_s, 1.0),
        wait_fn=_wait_cb,
        engine=DecisionEngine(selector_enabled=True),
    )

    view = WhatsAppWorldView.from_world_model(runtime.world_model)
    log.log(
        "world_summary",
        {"whatsapp_view": view.to_dict(), "ok": result.ok, "reason": result.reason},
        status="ok",
    )
    log.check(
        "forward_task",
        ok=bool(result.ok),
        expected=f"forward {link_query!r} from {source_contact!r} to {target_contact!r}",
        actual=result.reason,
    )
    log.result(
        ok=bool(result.ok),
        detail=(
            f"closed_loop ok={result.ok} reason={result.reason!r} "
            f"iterations={runtime.execution_state.iteration}"
        ),
    )
    log.write_summary_md()
    return bool(result.ok)


def run_forward_message(
    *,
    log_path: Path,
    prompt: str,
    source_contact: str = "Kulvinder",
    target_contact: str = "Pallavi",
    link_query: str = "zarooratwala",
    max_iterations: int = 20,
    max_stepcount: Optional[int] = None,
) -> Tuple[bool, EventLogger]:
    run_id = f"wa-forward-live-{int(time.time())}"
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("", encoding="utf-8")
    log = EventLogger(log_path, also_console=True, run_id=run_id)
    log.begin_run(
        prompt,
        meta={
            "mode": "live",
            "kind": "whatsapp_forward_message",
            "source_contact": source_contact,
            "target_contact": target_contact,
            "link_query": link_query,
        },
    )
    ok = run_forward_message_live(
        log=log,
        prompt=prompt,
        source_contact=source_contact,
        target_contact=target_contact,
        link_query=link_query,
        max_iterations=max_iterations,
        max_stepcount=max_stepcount,
    )
    return ok, log
