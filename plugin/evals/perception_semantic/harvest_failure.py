"""Freeze a live / recorded perception failure into ``eval_candidates/``.

Candidates are NOT gold. A human annotates surfaces, typed claims, ownership,
affordances, and acceptable/forbidden actions, then promotes into ``fixtures/``.

Sources:

    # From a HERMES_PERCEPTOR_RECORD_DIR frame (preferred — full packet + reply)
    python -m plugin.evals.perception_semantic.harvest_failure \\
        --from-frame plugin/experiments/fixtures/perceptor/live_forward/frame_0284.json

    # From a live run JSONL step (best-effort when frames were not recorded)
    python -m plugin.evals.perception_semantic.harvest_failure \\
        --from-run /tmp/hermes-runs/20260809_184742 --step 15

    # Auto-detect contamination / forbidden-commit steps in a run
    python -m plugin.evals.perception_semantic.harvest_failure \\
        --from-run /tmp/hermes-runs/20260809_184742 --auto-fail

    # Materialize candidate layout from an already-promoted golden (curriculum seed)
    python -m plugin.evals.perception_semantic.harvest_failure \\
        --from-golden fixtures/cross_surface/whatsapp_forward_picker_source_1_dest_0.json
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

DEFAULT_CANDIDATES_DIR = Path(__file__).resolve().parent / "eval_candidates"
DEFAULT_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
DEFAULT_PERCEPTOR_ROOT = (
    Path(__file__).resolve().parents[2] / "experiments" / "fixtures" / "perceptor"
)

_ANNOTATION_STUB = {
    "status": "needs_annotation",
    "phenomena": [],
    "app": "",
    "note": "",
    "gold": {
        "surfaces": [],
        "claims": [],
        "affordances": [],
        "forbidden": [],
        "acceptable_actions": [],
        "forbidden_actions": [],
        "rejected_evidence": [],
    },
}


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            text = line.strip()
            if not text:
                continue
            try:
                obj = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                yield obj


def _find_run_jsonl(run_dir: Path) -> Optional[Path]:
    if run_dir.is_file() and run_dir.suffix == ".jsonl":
        return run_dir
    if not run_dir.is_dir():
        return None
    cands = sorted(run_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    for p in cands:
        if "forward" in p.name.lower() or "zarooratwala" in p.name.lower():
            return p
    return cands[0] if cands else None


def _stamp_from_run(run_dir: Path) -> str:
    name = run_dir.name if run_dir.is_dir() else run_dir.stem
    m = re.search(r"(20\d{6}_\d{6})", name)
    return m.group(1) if m else re.sub(r"[^a-zA-Z0-9_]+", "_", name)[:24]


def _copy_screenshot(src: str, dest: Path) -> str:
    if not src:
        return ""
    path = Path(src)
    if not path.is_file():
        return ""
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path, dest)
    return dest.name


def _ax_from_packet(packet: Dict[str, Any]) -> List[Dict[str, Any]]:
    obs = packet.get("observation") if isinstance(packet.get("observation"), dict) else {}
    ax = obs.get("ax_evidence") if isinstance(obs.get("ax_evidence"), list) else []
    return [n for n in ax if isinstance(n, dict)]


def _executive_context(packet: Dict[str, Any], *, step: Any = None) -> Dict[str, Any]:
    goal = packet.get("goal") if isinstance(packet.get("goal"), dict) else {}
    obj = (
        packet.get("perception_objective")
        if isinstance(packet.get("perception_objective"), dict)
        else {}
    )
    obs = packet.get("observation") if isinstance(packet.get("observation"), dict) else {}
    wm = packet.get("world_model") if isinstance(packet.get("world_model"), dict) else {}
    return {
        "goal": goal.get("description") or goal.get("operation") or "",
        "goal_fields": {
            "source_conversation": goal.get("source_conversation"),
            "destination": goal.get("destination"),
            "source_query": goal.get("source_query"),
        },
        "current_intention": obj.get("question")
        or obj.get("intent")
        or (wm.get("progress") or {}).get("objective")
        or "",
        "perception_objective": obj,
        "active_app": obs.get("app") or goal.get("app") or "",
        "active_interaction_surface": obs.get("active_interaction_surface")
        or wm.get("surface")
        or "",
        "known_bindings": {
            "source_object": goal.get("source_query") or goal.get("source_conversation"),
            "destination": goal.get("destination"),
            "open_conversation": wm.get("open_conversation"),
        },
        "previous_action": packet.get("last_action") or {},
        "step": step,
    }


def write_candidate_bundle(
    out_dir: Path,
    *,
    candidate_id: str,
    packet: Dict[str, Any],
    model_output: Optional[Dict[str, Any]] = None,
    transition: Optional[Dict[str, Any]] = None,
    screenshot_src: str = "",
    source: Dict[str, Any],
    annotation: Optional[Dict[str, Any]] = None,
    phenomena_hint: Optional[Sequence[str]] = None,
    status: str = "needs_annotation",
) -> Path:
    """Write the architect-shaped candidate packet directory."""
    out_dir.mkdir(parents=True, exist_ok=True)
    shot_name = _copy_screenshot(screenshot_src, out_dir / "screenshot.png")
    ax = _ax_from_packet(packet)
    _write_json(out_dir / "ax.json", {"nodes": ax, "count": len(ax)})
    _write_json(
        out_dir / "executive_context.json",
        _executive_context(packet, step=source.get("step")),
    )
    _write_json(out_dir / "model_input.json", packet)
    _write_json(out_dir / "model_output.json", model_output or {})
    _write_json(out_dir / "transition.json", transition or {})
    stub = dict(_ANNOTATION_STUB)
    stub["status"] = status
    if annotation:
        stub.update(annotation)
        stub["status"] = status
    if phenomena_hint and not stub.get("phenomena"):
        stub["phenomena"] = list(phenomena_hint)
    if not stub.get("app"):
        obs = packet.get("observation") if isinstance(packet.get("observation"), dict) else {}
        stub["app"] = str(obs.get("app") or "WhatsApp")
    _write_json(out_dir / "annotation.json", stub)
    index = {
        "id": candidate_id,
        "status": status,
        "screenshot": shot_name,
        "source": source,
        "phenomena": list(stub.get("phenomena") or []),
        "files": [
            "screenshot.png",
            "ax.json",
            "executive_context.json",
            "model_input.json",
            "model_output.json",
            "transition.json",
            "annotation.json",
        ],
    }
    _write_json(out_dir / "candidate.json", index)
    _update_index(out_dir.parent, index)
    return out_dir


def _update_index(root: Path, entry: Dict[str, Any]) -> None:
    path = root / "_index.json"
    data: Dict[str, Any] = {"candidates": []}
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            data = {"candidates": []}
    rows = [r for r in (data.get("candidates") or []) if r.get("id") != entry.get("id")]
    rows.append(
        {
            "id": entry.get("id"),
            "status": entry.get("status"),
            "phenomena": entry.get("phenomena") or [],
            "source": entry.get("source") or {},
        }
    )
    data["candidates"] = sorted(rows, key=lambda r: str(r.get("id") or ""))
    data["count"] = len(data["candidates"])
    _write_json(path, data)


def harvest_from_frame(
    frame_path: Path,
    *,
    out_root: Path = DEFAULT_CANDIDATES_DIR,
    candidate_id: str = "",
    phenomena: Optional[Sequence[str]] = None,
) -> Path:
    raw = json.loads(frame_path.read_text(encoding="utf-8"))
    packet = dict(raw.get("packet") or {})
    response = raw.get("response") if isinstance(raw.get("response"), dict) else {}
    shot = str(raw.get("screenshot") or "")
    shot_path = ""
    if shot:
        cand = frame_path.parent / shot
        if cand.is_file():
            shot_path = str(cand)
    stamp = frame_path.parent.name
    frame_i = raw.get("frame") or frame_path.stem
    cid = candidate_id or f"{stamp}_frame_{frame_i}"
    return write_candidate_bundle(
        out_root / cid,
        candidate_id=cid,
        packet=packet,
        model_output=response,
        transition={"shadow_task_state": raw.get("shadow_task_state") or {}},
        screenshot_src=shot_path,
        source={
            "kind": "recorded_frame",
            "frame_path": str(frame_path),
            "frame": frame_i,
            "stamp": stamp,
        },
        phenomena_hint=phenomena
        or [
            "nested_surfaces",
            "cross_surface_selection",
            "foreground_authority",
        ],
    )


def _events_for_step(jsonl: Path, step: int) -> List[Dict[str, Any]]:
    return [e for e in _iter_jsonl(jsonl) if e.get("step") == step]


def _detect_failure_steps(jsonl: Path) -> List[Tuple[int, str]]:
    """Heuristic: forward_picker + commit / 1 Selected contamination."""
    found: List[Tuple[int, str]] = []
    seen = set()
    for e in _iter_jsonl(jsonl):
        step = e.get("step")
        if step is None:
            continue
        kind = str(e.get("kind") or "")
        reason = ""
        if kind == "perception_summary":
            msg = str(e.get("message") or e.get("detail") or "")
            surface = str(e.get("surface") or "")
            if surface == "forward_picker" and "1 selected" in msg.lower():
                reason = "forward_picker_mentions_source_selected_chrome"
        elif kind in {"planner_decision", "act_intention", "decision_engine"}:
            decision = e.get("decision") if isinstance(e.get("decision"), dict) else {}
            family = str(
                e.get("action_family")
                or decision.get("action_family")
                or decision.get("action")
                or ""
            )
            surface = str(
                e.get("surface")
                or decision.get("surface")
                or ""
            )
            target = str(
                e.get("semantic_target") or decision.get("semantic_target") or ""
            )
            if family == "commit_irreversible" and (
                surface in {"forward_picker", "conversation"}
                or target.lower() == "forward"
            ):
                reason = "commit_forward_while_picker_open"
        elif kind == "transition_attribution":
            layers = e.get("hypothesis_layers") or []
            blob = json.dumps(layers, default=str).lower()
            if "perception_failure" in blob or "cross_surface" in blob:
                reason = "transition_attribution_perception_failure"
        if reason and step not in seen:
            seen.add(step)
            found.append((int(step), reason))
    return found


def _best_screenshot_for_step(run_dir: Path, step: int, events: Sequence[Dict[str, Any]]) -> str:
    for e in events:
        shot = str(e.get("screenshot") or "")
        if shot and Path(shot).is_file():
            return shot
    umon = run_dir / "ui_monitor"
    if umon.is_dir():
        # Prefer agent_shot nearest to step index when present.
        agents = sorted(umon.glob("agent_shot_*.png"))
        if agents:
            idx = max(0, min(len(agents) - 1, step - 1))
            # Heuristic: later steps → later shots; clamp.
            pick = agents[min(len(agents) - 1, max(0, (step // 2) - 1))]
            return str(pick)
        frames = sorted(umon.glob("frame_*.png"))
        if frames:
            return str(frames[min(len(frames) - 1, max(0, step - 1))])
    # Already-harvested screenshot under experiments fixtures.
    for root in (
        DEFAULT_PERCEPTOR_ROOT / f"cross_surface_{_stamp_from_run(run_dir)}",
        DEFAULT_PERCEPTOR_ROOT / "cross_surface_184742",
    ):
        if (root / "frame_0001.png").is_file():
            return str(root / "frame_0001.png")
    return ""


def _packet_from_run_events(
    events: Sequence[Dict[str, Any]],
    *,
    stamp: str,
    step: int,
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """Best-effort reconstruction when HERMES_PERCEPTOR_RECORD_DIR was off."""
    perception = next((e for e in events if e.get("kind") == "perception_summary"), {})
    planner = next((e for e in events if e.get("kind") == "planner_decision"), {})
    act = next((e for e in events if e.get("kind") == "act_intention"), {})
    execj = next((e for e in events if e.get("kind") == "executive_judgement"), {})
    world = next((e for e in events if e.get("kind") == "world_patch"), {})
    decision_engine = next((e for e in events if e.get("kind") == "decision_engine"), {})
    transition = next(
        (
            e
            for e in events
            if e.get("kind")
            in {"transition_eval", "transition_attribution", "post_transition_diagnosis"}
        ),
        {},
    )
    view = planner.get("whatsapp_view") if isinstance(planner.get("whatsapp_view"), dict) else {}
    decision = planner.get("decision") if isinstance(planner.get("decision"), dict) else {}
    surface = str(
        perception.get("surface")
        or act.get("surface")
        or decision.get("surface")
        or ""
    )
    packet: Dict[str, Any] = {
        "goal": {
            "operation": "whatsapp_forward_message",
            "source_conversation": str(
                view.get("open_conversation")
                or world.get("open_conversation")
                or "Pallavi"
            ),
            "source_query": "zarooratwala",
            "destination": "Tanmay",
            "description": (
                "find the zarooratwala link sent to pallavi on whatsapp and forward to tanmay"
            ),
        },
        "world_model": {
            "frame": step,
            "surface": surface or str(world.get("screen") or ""),
            "open_conversation": view.get("open_conversation")
            or world.get("open_conversation")
            or "",
            "objects": [],
            "beliefs": [],
            "progress": {
                "phase": str((world.get("screen") or "")),
                "objective": "select destination",
            },
        },
        "observation": {
            "frame": step,
            "app": "WhatsApp",
            "window_name": str(view.get("window_name") or "WhatsApp"),
            "active_interaction_surface": surface or "unknown",
            "ax_evidence": [],
            "ax_node_count": next(
                (e.get("nodes") for e in events if e.get("kind") == "observation_raw"),
                0,
            ),
            "search_query": view.get("search_query") or "",
            "search_visible": bool(view.get("search_visible")),
        },
        "last_action": {
            "family": act.get("action_family") or decision.get("action_family"),
            "target": act.get("semantic_target") or decision.get("semantic_target"),
        },
        "harvest_quality": "best_effort_from_jsonl",
        "harvest_note": (
            "AX tree and production packet were not recorded; annotate from screenshot "
            "+ perception_summary. Re-run with HERMES_PERCEPTOR_RECORD_DIR or "
            "HERMES_PERCEPTION_EVAL_CANDIDATES_DIR for full packets."
        ),
    }
    if surface in {"forward_picker", "destination_picker"}:
        packet["perception_objective"] = {
            "intent": "resolve_destination",
            "question": "Is destination Tanmay selected in the forward picker? "
            "If not, is the destination search field available?",
        }
    model_output = {
        "perception_summary": {
            "surface": perception.get("surface"),
            "message": perception.get("message"),
            "detail": perception.get("detail"),
            "text": perception.get("text"),
        },
        "planner_decision": decision,
        "act_intention": {
            "action_family": act.get("action_family"),
            "semantic_target": act.get("semantic_target"),
            "surface": act.get("surface"),
        },
        "executive_judgement": {
            "meta_action": execj.get("meta_action"),
            "has_grounded_action": execj.get("has_grounded_action"),
        },
        "decision_engine_trace": (
            (decision_engine.get("trace") or {}).get("chosen")
            if isinstance(decision_engine.get("trace"), dict)
            else None
        ),
    }
    return packet, model_output, transition


def harvest_from_run(
    run_dir: Path,
    *,
    step: int,
    out_root: Path = DEFAULT_CANDIDATES_DIR,
    reason: str = "",
    phenomena: Optional[Sequence[str]] = None,
) -> Path:
    jsonl = _find_run_jsonl(run_dir)
    if jsonl is None:
        raise SystemExit(f"no run jsonl under {run_dir}")
    stamp = _stamp_from_run(run_dir if run_dir.is_dir() else run_dir.parent)
    events = _events_for_step(jsonl, step)
    if not events:
        raise SystemExit(f"no events for step={step} in {jsonl}")
    packet, model_output, transition = _packet_from_run_events(
        events, stamp=stamp, step=step
    )
    shot = _best_screenshot_for_step(
        run_dir if run_dir.is_dir() else run_dir.parent, step, events
    )
    cid = f"run_{stamp}_step_{step:04d}"
    return write_candidate_bundle(
        out_root / cid,
        candidate_id=cid,
        packet=packet,
        model_output=model_output,
        transition=transition,
        screenshot_src=shot,
        source={
            "kind": "live_run",
            "run_dir": str(run_dir),
            "jsonl": str(jsonl),
            "step": step,
            "stamp": stamp,
            "reason": reason or "manual",
            "harvest_quality": packet.get("harvest_quality"),
        },
        phenomena_hint=phenomena
        or [
            "nested_surfaces",
            "cross_surface_selection",
            "foreground_authority",
            "selection_state_typing",
        ],
    )


def harvest_from_golden(
    golden_path: Path,
    *,
    out_root: Path = DEFAULT_CANDIDATES_DIR,
    status: str = "promoted",
) -> Path:
    raw = json.loads(golden_path.read_text(encoding="utf-8"))
    packet = dict(raw.get("packet") or {})
    shot = ""
    record_dir = str(raw.get("record_dir") or "")
    screenshot = str(raw.get("screenshot") or "")
    if screenshot:
        for cand in (
            Path(screenshot),
            DEFAULT_PERCEPTOR_ROOT / record_dir / screenshot,
            DEFAULT_PERCEPTOR_ROOT / "cross_surface_184742" / Path(screenshot).name,
            golden_path.parent / screenshot,
        ):
            if cand.is_file():
                shot = str(cand)
                break
    cid = f"golden_{raw.get('id') or golden_path.stem}"
    annotation = {
        "status": status,
        "phenomena": list(raw.get("phenomena") or []),
        "app": raw.get("app") or "",
        "note": raw.get("note") or "",
        "gold": raw.get("gold") or {},
        "promoted_fixture": str(golden_path),
    }
    return write_candidate_bundle(
        out_root / cid,
        candidate_id=cid,
        packet=packet,
        model_output=raw.get("contaminated_response") or raw.get("annotated_response") or {},
        transition={},
        screenshot_src=shot,
        source={
            "kind": "golden",
            "golden_path": str(golden_path),
            "record_dir": record_dir,
        },
        annotation=annotation,
        phenomena_hint=raw.get("phenomena") or [],
        status=status,
    )


def dump_candidate_from_live_packet(
    packet: Dict[str, Any],
    screenshot_path: str,
    proposal: Optional[Dict[str, Any]],
    *,
    directory: str,
    step: Any = None,
    stamp: str = "",
    shadow: Optional[Dict[str, Any]] = None,
) -> Optional[Path]:
    """Called from production recording path — always full packet quality."""
    if not directory:
        return None
    root = Path(directory)
    stamp = stamp or "live"
    frame = packet.get("observation", {}).get("frame") if isinstance(packet.get("observation"), dict) else None
    frame = frame or step or len(list(root.glob("run_*"))) + 1
    try:
        frame_i = int(frame)
    except (TypeError, ValueError):
        frame_i = 0
    cid = f"run_{stamp}_step_{frame_i:04d}"
    return write_candidate_bundle(
        root / cid,
        candidate_id=cid,
        packet=packet,
        model_output=proposal or {},
        transition={"shadow_task_state": shadow or {}},
        screenshot_src=screenshot_path,
        source={
            "kind": "live_record",
            "stamp": stamp,
            "step": frame_i,
            "harvest_quality": "production_packet",
        },
        status="needs_annotation",
    )


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(DEFAULT_CANDIDATES_DIR))
    ap.add_argument("--from-frame", help="Recorded perceptor frame JSON")
    ap.add_argument("--from-run", help="Live run dir or jsonl")
    ap.add_argument("--step", type=int, help="Step inside --from-run")
    ap.add_argument(
        "--auto-fail",
        action="store_true",
        help="Harvest all heuristically-failed steps from --from-run",
    )
    ap.add_argument("--from-golden", help="Existing semantic golden JSON")
    ap.add_argument("--id", default="", help="Override candidate id")
    ap.add_argument(
        "--phenomena",
        default="",
        help="Comma-separated phenomenon tags",
    )
    args = ap.parse_args(argv)
    out_root = Path(args.out)
    phenomena = [p.strip() for p in args.phenomena.split(",") if p.strip()] or None

    written: List[Path] = []
    if args.from_frame:
        written.append(
            harvest_from_frame(
                Path(args.from_frame),
                out_root=out_root,
                candidate_id=args.id,
                phenomena=phenomena,
            )
        )
    elif args.from_golden:
        written.append(
            harvest_from_golden(Path(args.from_golden), out_root=out_root)
        )
    elif args.from_run:
        run_path = Path(args.from_run)
        if args.auto_fail:
            jsonl = _find_run_jsonl(run_path)
            if jsonl is None:
                raise SystemExit(f"no jsonl under {run_path}")
            fails = _detect_failure_steps(jsonl)
            if not fails:
                print(f"no auto-fail steps in {jsonl}")
                return 1
            for step, reason in fails:
                written.append(
                    harvest_from_run(
                        run_path,
                        step=step,
                        out_root=out_root,
                        reason=reason,
                        phenomena=phenomena,
                    )
                )
        elif args.step is None:
            raise SystemExit("--step is required with --from-run (or pass --auto-fail)")
        else:
            written.append(
                harvest_from_run(
                    run_path,
                    step=args.step,
                    out_root=out_root,
                    phenomena=phenomena,
                )
            )
    else:
        raise SystemExit("provide --from-frame, --from-run, or --from-golden")

    for path in written:
        print(f"candidate → {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
