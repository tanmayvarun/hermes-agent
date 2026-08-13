"""Live-run health: stall / slowness / thrash signals for monitors.

UI capture alone cannot see that the agent is spinning. This module reads the
JSONL + console + process liveness and produces a compact health snapshot the
UI monitor, supervise attach-mode, and a human watcher can all share.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from plugin.experiments.runs.live_paths import (
    forward_console_path,
    forward_log_path,
    forward_status_path,
    live_run_dir,
    resolve_forward_log,
    resolve_forward_status,
)


def _pids_for(stamp: str) -> List[int]:
    out = subprocess.run(
        ["pgrep", "-f", stamp], capture_output=True, text=True, check=False
    )
    pids: List[int] = []
    for tok in (out.stdout or "").split():
        try:
            pids.append(int(tok))
        except ValueError:
            continue
    return pids


def _agent_alive(stamp: str) -> bool:
    """True when the forward runner (not just monitor) is still up."""
    out = subprocess.run(
        ["pgrep", "-fl", "run_forward_message"],
        capture_output=True,
        text=True,
        check=False,
    )
    text = out.stdout or ""
    if stamp in text:
        return True
    # Fallback: any run_forward_message while this stamp's log is hot.
    return bool(text.strip()) and bool(_pids_for(stamp))


def _tail_events(log: Path, *, max_bytes: int = 2_000_000) -> List[Dict[str, Any]]:
    if not log.is_file():
        return []
    try:
        raw = log.read_bytes()
        if len(raw) > max_bytes:
            raw = raw[-max_bytes:]
        text = raw.decode("utf-8", errors="replace")
    except Exception:
        return []
    events: List[Dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except Exception:
            continue
    return events


def _last(events: Sequence[Dict[str, Any]], kind: str) -> Optional[Dict[str, Any]]:
    for ev in reversed(events):
        if str(ev.get("kind") or "") == kind:
            return ev
    return None


def _meta_trail(events: Sequence[Dict[str, Any]], *, n: int = 12) -> List[str]:
    trail: List[str] = []
    for ev in events:
        if str(ev.get("kind") or "") != "executive_judgement":
            continue
        ma = ev.get("meta_action") or {}
        trail.append(f"{ma.get('action') or '-'}/{ma.get('capability') or '-'}")
    return trail[-n:]


def _thrash_score(trail: Sequence[str]) -> Tuple[float, str]:
    """Detect meta ping-pong without progress (act/search/explore ↔ perceive/think)."""
    if len(trail) < 6:
        return 0.0, ""
    recent = list(trail[-8:])
    actions = [t.split("/", 1)[0].lower() for t in recent]
    info = {"perceive", "explore", "think"}
    commit = {"act", "search"}
    pairs = 0
    for a, b in zip(actions, actions[1:]):
        if a == b:
            continue
        if (a in commit and b in info) or (a in info and b in commit) or (
            a in info and b in info and {a, b} != {"think"}
        ):
            pairs += 1
    uniq = len(set(actions))
    # Pure observe/explore/think churn with no ACT/SEARCH (live 210526).
    if uniq and not (set(actions) & commit) and len(actions) >= 6:
        return (
            0.85,
            f"meta_info_only_churn actions={uniq} trail={'→'.join(recent[-6:])}",
        )
    if pairs >= 5 and uniq <= 3:
        return 1.0, f"meta_pingpong pairs={pairs} actions={uniq} trail={'→'.join(recent[-6:])}"
    if pairs >= 3 and uniq <= 3:
        return 0.6, f"meta_oscillation pairs={pairs} trail={'→'.join(recent[-6:])}"
    return 0.0, ""


def _surface_contradiction_score(
    events: Sequence[Dict[str, Any]],
) -> Tuple[float, str, int]:
    """Repeated prediction_error: predicted conversation, observed search.

    Live 210526: world_patch stayed conversation while looks reported search —
    health must surface that, not only goal-clock stall.
    """
    n = 0
    last_why = ""
    for ev in events:
        if str(ev.get("kind") or "") != "prediction_error":
            continue
        pred = str(ev.get("predicted_surface") or "").strip().lower()
        obs = str(ev.get("observed_surface") or "").strip().lower()
        matched = ev.get("matched")
        if matched is False and pred == "conversation" and obs in {
            "search",
            "search_results",
        }:
            n += 1
            last_why = f"pred={pred} obs={obs}"
    if n >= 6:
        return 1.0, f"surface_contradiction_x{n} ({last_why})", n
    if n >= 3:
        return 0.7, f"surface_contradiction_x{n} ({last_why})", n
    return 0.0, "", n


def _events_show_grounding_recovery(events: Sequence[Dict[str, Any]]) -> bool:
    """True when the runtime armed grounding / wrong-locus recovery (not ignore)."""
    for ev in events:
        blob = json.dumps(ev, default=str).lower()
        if any(
            tok in blob
            for tok in (
                "grounding_repair",
                "grounding_wrong_locus",
                "inconclusive_grounding",
                "composer_point",
                "wrong_locus:patient:composer",
                "arm_wrong_point",
                "commitment_reground",
                "preserve_semantic_method",
                "wrong_locus_recovery_owed",
            )
        ):
            return True
    return False


def _composer_mistype_score(
    events: Sequence[Dict[str, Any]], console_tail: str
) -> Tuple[float, str, int]:
    """Detect typing/context-click on chat composer while hunting content.

    Live 181132: source chat open, agent typed zarooratwala into "Type a message"
    then context-clicked the draft → spellcheck menu thrash.

    Live 134636: a single context-click in the composer band is a *recoverable*
    grounding failure when the executive invalidates that point. Health watch
    must not hard-kill until recovery is ignored / exhausted.
    """
    n = 0
    last_why = ""
    for ev in events:
        kind = str(ev.get("kind") or "")
        blob = json.dumps(ev, default=str).lower()
        if kind == "execution":
            msg = str(ev.get("message") or "").lower()
            # Context-click near composer band / draft query echo.
            if "context click" in msg and any(
                tok in msg for tok in ("zarooratwala", "type a message", "composer")
            ):
                # Bottom-of-window Y is a weak watchdog hint only (+1, not +2).
                if "center=(" in msg:
                    try:
                        y = float(msg.split("center=(")[1].split(",")[1].split(")")[0])
                        if y >= 900:
                            n += 1
                            last_why = "context_click_composer_band"
                            continue
                    except (IndexError, ValueError, TypeError):
                        pass
                n += 1
                last_why = "context_click_query_echo"
            if "type" in msg and "type a message" in blob:
                n += 2
                last_why = "type_into_message_composer"
        # Pre-motor refusal counts as a detected wrong-locus event (not a kill).
        if "composer_point" in blob or "wrong_locus:patient:composer" in blob:
            n += 1
            last_why = last_why or "composer_point_rejected"
        if "no guesses found" in blob or "ignore spelling" in blob or "learn spelling" in blob:
            n += 2
            last_why = "spellcheck_menu_on_composer"
        if "reveal_actions on message composer" in blob or "composer draft" in blob:
            n += 1
            last_why = last_why or "composer_reveal_gate"
    console_l = console_tail.lower()
    if "no guesses found" in console_l or "ignore spelling" in console_l:
        n = max(n, 3)
        last_why = "spellcheck_menu_console"
    recovered = _events_show_grounding_recovery(events)
    # Hard kill only when mistypes accumulate *and* recovery is absent/exhausted.
    if n >= 4 or (n >= 3 and not recovered):
        return 1.0, f"composer_mistype_hard ({last_why}) x{n}", n
    if n >= 2 and not recovered:
        return (
            0.85,
            f"composer_mistype ({last_why}) x{n}",
            n,
        )
    if n >= 1:
        # Recoverable wrong-locus repetition — executive should reground.
        return (
            0.55,
            f"wrong_locus_repetition ({last_why}) x{n}"
            + ("; recovery_armed" if recovered else ""),
            n,
        )
    return 0.0, "", n


def _observe_decline_score(
    events: Sequence[Dict[str, Any]], console_tail: str
) -> Tuple[float, str, int]:
    """unified_declined → Observe loops with no open_entity after resolve."""
    n = 0
    for ev in events:
        if str(ev.get("kind") or "") != "decision_engine":
            continue
        blob = json.dumps(ev, default=str).lower()
        if "unified_declined_no_legacy_fallthrough" in blob:
            n += 1
    console_n = console_tail.lower().count("unified_declined_no_legacy_fallthrough")
    n = max(n, console_n)
    # Did we ever open after a successful resolve?
    resolved = any(
        str(e.get("kind") or "") == "execution"
        and "resolved source" in str(e.get("message") or "").lower()
        for e in events
    )
    opened = any(
        str(e.get("kind") or "") == "execution"
        and (
            str(e.get("action_family") or "").lower() == "open_entity"
            or "open_entity" in str(e.get("message") or "").lower()
        )
        for e in events
    )
    if resolved and not opened and n >= 3:
        return (
            0.9,
            f"resolve_without_open + observe_decline_x{n}",
            n,
        )
    if n >= 6:
        return 0.75, f"observe_decline_x{n}", n
    if n >= 3:
        return 0.5, f"observe_decline_x{n}", n
    return 0.0, "", n


def snapshot_health(
    stamp: str,
    *,
    stall_warn_s: float = 90.0,
    stall_hard_s: float = 180.0,
    slow_log_s: float = 45.0,
    slow_aux_s: float = 60.0,
) -> Dict[str, Any]:
    """Return a health dict: level ∈ ok|slow|stall_warn|stall_hard|dead|done."""
    now = time.time()
    log = resolve_forward_log(stamp)
    status = resolve_forward_status(stamp)
    console = forward_console_path(stamp)
    run_dir = live_run_dir(stamp)

    events = _tail_events(log)
    clock = _last(events, "progress_clock") or {}
    goal = _last(events, "goal_status") or {}
    forward = _last(events, "forward_task") or {}
    last_exec = _last(events, "execution") or {}
    last_meta = _last(events, "executive_judgement") or {}

    log_age = (now - log.stat().st_mtime) if log.is_file() else None
    console_age = (now - console.stat().st_mtime) if console.is_file() else None
    since_prog = float(clock.get("elapsed_since_progress_s") or 0.0)
    elapsed = float(clock.get("elapsed_s") or 0.0)
    step = clock.get("step")
    no_progress_n = sum(1 for e in events if str(e.get("kind") or "") == "no_progress_replan")
    semantic_repeat_n = sum(
        1 for e in events if str(e.get("kind") or "") == "semantic_repeat_replan"
    )
    trail = _meta_trail(events)
    thrash, thrash_why = _thrash_score(trail)

    console_tail = ""
    if console.is_file():
        try:
            console_tail = console.read_bytes()[-8000:].decode("utf-8", errors="replace")
        except Exception:
            console_tail = ""
    aux_hang = "Auxiliary request payload" in console_tail and (
        console_age is not None and console_age > slow_aux_s
    )
    surf_score, surf_why, surf_n = _surface_contradiction_score(events)
    decline_score, decline_why, decline_n = _observe_decline_score(events, console_tail)
    composer_score, composer_why, composer_n = _composer_mistype_score(events, console_tail)
    outcome = ""
    if "OK=True" in console_tail:
        outcome = "converged"
    elif "OK=False" in console_tail:
        outcome = "failed"

    status_text = ""
    if status.is_file():
        try:
            status_text = status.read_text(errors="replace")
        except Exception:
            status_text = ""
    for marker in (
        "status=done",
        "status=ok",
        "status=fail",
        "status=stalled",
        "status=timeout",
        "status=exited",
    ):
        if marker in status_text:
            outcome = outcome or marker.split("=", 1)[1]
            break

    alive = _agent_alive(stamp)
    ma = last_meta.get("meta_action") or {}
    phase = str((forward.get("forward_task") or forward).get("derived_phase") or "")
    if not phase and isinstance(forward.get("derived_phase"), str):
        phase = str(forward.get("derived_phase") or "")

    alerts: List[str] = []
    level = "ok"

    # Structural signals always computed for the snapshot; applied as alerts
    # even on terminal/dead so postmortems still show why the run rotted.
    structural: List[str] = []
    if surf_why:
        structural.append(surf_why)
    if decline_why:
        structural.append(decline_why)
    if composer_why:
        structural.append(composer_why)
    if thrash_why:
        structural.append(thrash_why)
    if no_progress_n >= 8:
        structural.append(f"no_progress_replan_count={no_progress_n}")
    if semantic_repeat_n >= 8:
        structural.append(f"semantic_repeat_replan_count={semantic_repeat_n}")

    if outcome in {"converged", "ok", "done"}:
        level = "done"
    elif outcome in {"failed", "fail", "stalled", "timeout", "exited"}:
        level = "dead" if not alive else outcome
        alerts.append(f"terminal_outcome={outcome}")
        alerts.extend(structural)
    elif not alive and events:
        level = "dead"
        alerts.append("agent_process_gone")
        alerts.extend(structural)
    else:
        if since_prog >= stall_hard_s:
            level = "stall_hard"
            alerts.append(f"no_goal_progress_for={since_prog:.0f}s (hard≥{stall_hard_s:.0f})")
        elif since_prog >= stall_warn_s:
            level = "stall_warn"
            alerts.append(f"no_goal_progress_for={since_prog:.0f}s (warn≥{stall_warn_s:.0f})")
        if log_age is not None and log_age >= slow_log_s:
            if level == "ok":
                level = "slow"
            alerts.append(f"log_silent={log_age:.0f}s (likely LLM/aux hang)")
        if aux_hang:
            if level == "ok":
                level = "slow"
            alerts.append(f"aux_request_hang console_age={console_age:.0f}s")
        if thrash >= 0.6:
            if level == "ok":
                level = "slow"
            alerts.append(thrash_why)
        if surf_score >= 0.7:
            if level in {"ok", "slow"}:
                level = "stall_warn" if surf_score < 1.0 else "stall_hard"
            alerts.append(surf_why)
        elif surf_score >= 0.5 and level == "ok":
            level = "slow"
            alerts.append(surf_why)
        if decline_score >= 0.75:
            if level in {"ok", "slow"}:
                level = "stall_warn"
            alerts.append(decline_why)
        elif decline_score >= 0.5 and level == "ok":
            level = "slow"
            alerts.append(decline_why)
        # Composer / input wrong-locus: recoverable by default (live 134636).
        # Hard kill only when score says recovery ignored / exhausted (≥0.85).
        if composer_score >= 0.85:
            level = "stall_hard"
            alerts.append(composer_why)
        elif composer_score >= 0.55:
            if level in {"ok", "slow"}:
                level = "stall_warn"
            alerts.append(composer_why)
        if no_progress_n >= 8 and level == "ok":
            level = "slow"
            alerts.append(f"no_progress_replan_count={no_progress_n}")
        if semantic_repeat_n >= 8 and level == "ok":
            level = "slow"
            alerts.append(f"semantic_repeat_replan_count={semantic_repeat_n}")

    # Responsiveness milestones from JSONL (epistemic / affordance / commit).
    milestones = _milestone_timings(events)
    snap: Dict[str, Any] = {
        "ts": now,
        "stamp": stamp,
        "level": level,
        "alerts": alerts,
        "alive": alive,
        "outcome": outcome,
        "elapsed_s": elapsed,
        "since_progress_s": since_prog,
        "log_age_s": round(log_age, 1) if log_age is not None else None,
        "console_age_s": round(console_age, 1) if console_age is not None else None,
        "step": step,
        "phase": phase,
        "goal_reason": str(goal.get("reason") or "")[:160],
        "last_exec": str(last_exec.get("message") or "")[:160],
        "last_meta": f"{ma.get('action') or '-'}/{ma.get('capability') or '-'}",
        "meta_trail": trail,
        "no_progress_replan": no_progress_n,
        "semantic_repeat_replan": semantic_repeat_n,
        "surface_contradiction_n": surf_n,
        "observe_decline_n": decline_n,
        "composer_mistype_n": composer_n,
        "composer_mistype_score": composer_score,
        "thrash": thrash,
        "event_tail_n": len(events),
        "kinds": dict(Counter(str(e.get("kind") or "") for e in events).most_common(8)),
        "milestones": milestones,
        "paths": {
            "log": str(log),
            "console": str(console),
            "status": str(status),
            "run_dir": str(run_dir),
        },
    }
    return snap


def _milestone_timings(events: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """time-to-epistemic / affordance / instrumental from event stream."""
    t0 = None
    for e in events:
        if e.get("ts") is not None:
            try:
                t0 = float(e["ts"])
                break
            except (TypeError, ValueError):
                pass
    out: Dict[str, Any] = {
        "time_to_epistemic_s": None,
        "time_to_affordance_grounded_s": None,
        "time_to_referent_selected_s": None,
        "time_to_instrumental_commit_s": None,
        "reveal_gesture_attempts": 0,
    }
    if t0 is None:
        return out

    def _age(ev: Dict[str, Any]) -> Optional[float]:
        try:
            return max(0.0, float(ev.get("ts")) - t0)
        except (TypeError, ValueError):
            return None

    reveal_n = 0
    for e in events:
        k = str(e.get("kind") or "")
        if k == "execution":
            msg = str(e.get("message") or "").lower()
            fam = str(e.get("action_family") or e.get("family") or "").lower()
            if "typed" in msg and out["time_to_epistemic_s"] is None:
                # Weak: first successful compose often precedes chosen.
                pass
            if fam in {"reveal_actions", "context_click", "right_click"} or "context click" in msg:
                reveal_n += 1
            if "forward" in msg and "picker" in msg and out["time_to_instrumental_commit_s"] is None:
                out["time_to_instrumental_commit_s"] = _age(e)
        if k == "reveal_handoff":
            reveal_n += 1
        if k == "executive_judgement" and out["time_to_epistemic_s"] is None:
            search = (e.get("search") or {}) if isinstance(e.get("search"), dict) else {}
            ref = search.get("referent_search") if isinstance(search.get("referent_search"), dict) else {}
            chosen = str(ref.get("chosen_label") or "").strip()
            if chosen:
                out["time_to_epistemic_s"] = _age(e)
        if k in {"perception_settled", "affordance_frontier"}:
            blob = json.dumps(e, default=str).lower()
            if "grounded_affordance" in blob or (
                "affordance_set" in blob and "empty" not in blob
            ):
                if out["time_to_affordance_grounded_s"] is None:
                    out["time_to_affordance_grounded_s"] = _age(e)
        if k == "forward_task" and out["time_to_referent_selected_s"] is None:
            ft = e.get("forward_task") if isinstance(e.get("forward_task"), dict) else {}
            preds = ft.get("predicates") if isinstance(ft.get("predicates"), dict) else {}
            if preds.get("source_object_selected"):
                out["time_to_referent_selected_s"] = _age(e)
        if k == "execution" and out["time_to_epistemic_s"] is None:
            msg = str(e.get("message") or "")
            if msg.startswith("resolved source") or "resolved source referent" in msg.lower():
                out["time_to_epistemic_s"] = _age(e)
    out["reveal_gesture_attempts"] = reveal_n
    return out


def write_health(stamp: str, snap: Optional[Dict[str, Any]] = None, *, out_dir: Optional[Path] = None) -> Dict[str, Any]:
    snap = snap or snapshot_health(stamp)
    root = out_dir or live_run_dir(stamp)
    root.mkdir(parents=True, exist_ok=True)
    (root / "health.json").write_text(
        json.dumps(snap, indent=2, default=str) + "\n", encoding="utf-8"
    )
    alerts = snap.get("alerts") or []
    lines = [
        f"level={snap.get('level')} stamp={stamp} ts={int(snap.get('ts') or time.time())}",
        f"alive={snap.get('alive')} elapsed_s={snap.get('elapsed_s')} "
        f"since_progress_s={snap.get('since_progress_s')} "
        f"log_age_s={snap.get('log_age_s')} step={snap.get('step')}",
        f"phase={snap.get('phase')!r} meta={snap.get('last_meta')} "
        f"thrash={snap.get('thrash')} no_progress_replan={snap.get('no_progress_replan')} "
        f"semantic_repeat={snap.get('semantic_repeat_replan')} "
        f"surface_contra={snap.get('surface_contradiction_n')} "
        f"observe_decline={snap.get('observe_decline_n')}",
        f"goal={snap.get('goal_reason')}",
        f"exec={snap.get('last_exec')}",
        f"trail={' → '.join(snap.get('meta_trail') or [])}",
    ]
    if alerts:
        lines.append("ALERTS: " + " | ".join(str(a) for a in alerts))
    text = "\n".join(lines) + "\n"
    (root / "health.txt").write_text(text, encoding="utf-8")
    # Also mirror under ui_monitor for the frame watcher.
    try:
        ui = root / "ui_monitor"
        ui.mkdir(parents=True, exist_ok=True)
        (ui / "health.txt").write_text(text, encoding="utf-8")
        (ui / "health.json").write_text(
            json.dumps(snap, indent=2, default=str) + "\n", encoding="utf-8"
        )
    except Exception:
        pass
    return snap


def format_alert_line(snap: Dict[str, Any]) -> str:
    level = str(snap.get("level") or "ok")
    alerts = snap.get("alerts") or []
    base = (
        f"health level={level} since_prog={snap.get('since_progress_s')}s "
        f"log_age={snap.get('log_age_s')}s meta={snap.get('last_meta')} "
        f"phase={snap.get('phase')!r}"
    )
    if alerts:
        return base + " :: " + " | ".join(str(a) for a in alerts)
    return base
