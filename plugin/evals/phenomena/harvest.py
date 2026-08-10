"""Freeze live failures into phenomenon ``eval_candidates/`` bundles.

Candidates are NOT gold. Human review adds ``annotation.json``, then promote.

Usage:
    # From a perception_semantic eval_candidate (production packet)
    python -m plugin.evals.phenomena.harvest \\
        --from-perception-candidate \\
        plugin/evals/perception_semantic/eval_candidates/run_live_20260810_161105_step_0001

    # From a live run JSONL (when /tmp stamp still exists)
    python -m plugin.evals.phenomena.harvest \\
        --from-run /tmp/hermes-runs/20260810_161105 --auto-blocker

    # From a perceptor frame record
    python -m plugin.evals.phenomena.harvest \\
        --from-frame plugin/experiments/fixtures/perceptor/live_20260810_161105/frame_0001.json
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

DEFAULT_CANDIDATES = Path(__file__).resolve().parent / "eval_candidates"
PERCEPTION_CANDIDATES = (
    Path(__file__).resolve().parents[1] / "perception_semantic" / "eval_candidates"
)

_ANNOTATION_STUB = {
    "status": "needs_annotation",
    "phenomena": [],
    "app": "",
    "note": "",
    "expected": {
        "executability": "",
        "spawn_child": None,
        "expect_blocker": None,
        "expect_warning": None,
    },
    "forbidden": [],
    "families_to_promote": [],
}


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _stamp_from_name(name: str) -> str:
    m = re.search(r"(20\d{6}_\d{6})", name)
    return m.group(1) if m else re.sub(r"[^a-zA-Z0-9_]+", "_", name)[:32]


def _ax_texts(ax: Any) -> List[str]:
    texts: List[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for k in ("label", "name", "value", "description", "title"):
                v = node.get(k)
                if isinstance(v, str) and v.strip():
                    texts.append(v.strip())
            for c in node.get("children") or node.get("nodes") or []:
                walk(c)
        elif isinstance(node, list):
            for x in node:
                walk(x)

    walk(ax)
    # Prefer storage-relevant first, keep unique order.
    seen = set()
    out: List[str] = []
    for t in texts:
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def _looks_like_storage_blocker(texts: Sequence[str]) -> bool:
    blob = "\n".join(texts).lower()
    return "storage is too full" in blob or "free up at least" in blob


def write_candidate_bundle(
    *,
    candidate_id: str,
    stamp: str,
    step: Optional[int] = None,
    app: str = "",
    observation_texts: Sequence[str] = (),
    ax: Any = None,
    executive_context: Optional[Dict[str, Any]] = None,
    world_before: Optional[Dict[str, Any]] = None,
    intention_stack: Optional[Any] = None,
    meta_decision: Optional[Dict[str, Any]] = None,
    capability_inventory: Optional[Any] = None,
    transition: Optional[Dict[str, Any]] = None,
    screenshot_src: Optional[Path] = None,
    system_facts: Optional[Dict[str, Any]] = None,
    run_excerpt: Optional[List[Dict[str, Any]]] = None,
    out_root: Path = DEFAULT_CANDIDATES,
    source: Optional[Dict[str, Any]] = None,
) -> Path:
    dest = out_root / candidate_id
    dest.mkdir(parents=True, exist_ok=True)

    files: List[str] = []
    if ax is not None:
        _write_json(dest / "ax.json", ax)
        files.append("ax.json")
    if executive_context is not None:
        _write_json(dest / "executive_context.json", executive_context)
        files.append("executive_context.json")
    if world_before is not None:
        _write_json(dest / "world_before.json", world_before)
        files.append("world_before.json")
    if intention_stack is not None:
        _write_json(dest / "intention_stack.json", intention_stack)
        files.append("intention_stack.json")
    if meta_decision is not None:
        _write_json(dest / "meta_decision.json", meta_decision)
        files.append("meta_decision.json")
    if capability_inventory is not None:
        _write_json(dest / "capability_inventory.json", capability_inventory)
        files.append("capability_inventory.json")
    if transition is not None:
        _write_json(dest / "transition.json", transition)
        files.append("transition.json")
    if system_facts is not None:
        _write_json(dest / "system_facts.json", system_facts)
        files.append("system_facts.json")
    if run_excerpt is not None:
        excerpt_path = dest / "run_excerpt.jsonl"
        with excerpt_path.open("w", encoding="utf-8") as fh:
            for row in run_excerpt:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        files.append("run_excerpt.jsonl")

    _write_json(dest / "observation_texts.json", list(observation_texts))
    files.append("observation_texts.json")

    if screenshot_src is not None and screenshot_src.is_file():
        shutil.copy2(screenshot_src, dest / "screenshot.png")
        files.append("screenshot.png")

    ann = dict(_ANNOTATION_STUB)
    ann["app"] = app
    if _looks_like_storage_blocker(observation_texts):
        ann["phenomena"] = [
            "environmental_blocker",
            "prerequisite_child",
            "effect_verification",
        ]
        ann["expected"] = {
            "executability": "blocked_resolvable",
            "spawn_child": True,
            "expect_blocker": True,
            "expect_warning": False,
        }
        ann["forbidden"] = ["continue_parent_search", "duplicate_child"]
        ann["families_to_promote"] = [
            "warning_vs_blocker",
            "executability",
            "prerequisite_children",
            "effect_resolution",
            "effect_verification",
            "resumption",
            "trajectories",
        ]
        ann["note"] = (
            "Auto-hint from storage dialog text; human must confirm before promote."
        )
    _write_json(dest / "annotation.json", ann)
    files.append("annotation.json")

    candidate = {
        "id": candidate_id,
        "status": "needs_annotation",
        "source": source
        or {
            "kind": "live_failure",
            "stamp": stamp,
            "step": step,
        },
        "phenomena": list(ann.get("phenomena") or []),
        "files": files,
    }
    _write_json(dest / "candidate.json", candidate)
    files.append("candidate.json")

    _update_index(out_root, candidate)
    return dest


def _update_index(out_root: Path, candidate: Dict[str, Any]) -> None:
    idx_path = out_root / "_index.json"
    rows: List[Dict[str, Any]] = []
    if idx_path.is_file():
        try:
            raw = json.loads(idx_path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                rows = raw
            elif isinstance(raw, dict):
                rows = list(raw.get("candidates") or [])
        except json.JSONDecodeError:
            rows = []
    rows = [r for r in rows if r.get("id") != candidate.get("id")]
    rows.append(
        {
            "id": candidate.get("id"),
            "status": candidate.get("status"),
            "stamp": (candidate.get("source") or {}).get("stamp"),
            "phenomena": list(candidate.get("phenomena") or []),
        }
    )
    _write_json(idx_path, {"candidates": rows})


def harvest_perception_candidate(
    src: Path,
    *,
    out_root: Path = DEFAULT_CANDIDATES,
) -> Path:
    src = Path(src)
    if not src.is_dir():
        raise FileNotFoundError(src)
    ax = None
    if (src / "ax.json").is_file():
        ax = json.loads((src / "ax.json").read_text(encoding="utf-8"))
    texts = _ax_texts(ax) if ax is not None else []
    if (src / "observation_texts.json").is_file():
        texts = json.loads((src / "observation_texts.json").read_text(encoding="utf-8"))
    exec_ctx = None
    if (src / "executive_context.json").is_file():
        exec_ctx = json.loads((src / "executive_context.json").read_text(encoding="utf-8"))
    world = None
    if (src / "model_output.json").is_file():
        mo = json.loads((src / "model_output.json").read_text(encoding="utf-8"))
        world = mo.get("world_model") or mo
    transition = None
    if (src / "transition.json").is_file():
        transition = json.loads((src / "transition.json").read_text(encoding="utf-8"))
    stamp = _stamp_from_name(src.name)
    step_m = re.search(r"step_(\d+)", src.name)
    step = int(step_m.group(1)) if step_m else None
    app = ""
    if isinstance(exec_ctx, dict):
        app = str(exec_ctx.get("active_app") or "")
    cand_id = f"phenomenon_{src.name}"
    shot = src / "screenshot.png"
    return write_candidate_bundle(
        candidate_id=cand_id,
        stamp=stamp,
        step=step,
        app=app,
        observation_texts=texts,
        ax=ax,
        executive_context=exec_ctx,
        world_before=world if isinstance(world, dict) else None,
        transition=transition if isinstance(transition, dict) else None,
        screenshot_src=shot if shot.is_file() else None,
        out_root=out_root,
        source={
            "kind": "perception_eval_candidate",
            "stamp": stamp,
            "step": step,
            "src": str(src),
            "harvest_quality": "production_packet",
        },
    )


def harvest_frame(
    frame_path: Path,
    *,
    out_root: Path = DEFAULT_CANDIDATES,
) -> Path:
    frame_path = Path(frame_path)
    raw = json.loads(frame_path.read_text(encoding="utf-8"))
    packet = raw.get("packet") or {}
    ax = packet.get("ax") or raw.get("ax")
    texts = _ax_texts(ax) if ax else []
    # Also pull OCR / dialog strings from packet if present.
    for key in ("dialogs", "system_warnings", "ocr_texts"):
        for t in packet.get(key) or []:
            if str(t).strip():
                texts.append(str(t).strip())
    stamp = _stamp_from_name(str(raw.get("stamp") or frame_path.parent.name))
    frame_n = raw.get("frame") or 0
    shot = None
    shot_name = raw.get("screenshot") or ""
    if shot_name:
        cand = frame_path.parent / Path(shot_name).name
        if cand.is_file():
            shot = cand
    return write_candidate_bundle(
        candidate_id=f"phenomenon_frame_{stamp}_{int(frame_n):04d}",
        stamp=stamp,
        step=int(frame_n) if frame_n else None,
        app=str(packet.get("app") or ""),
        observation_texts=texts,
        ax=ax,
        executive_context=packet.get("executive_context"),
        world_before=raw.get("response") if isinstance(raw.get("response"), dict) else None,
        screenshot_src=shot,
        out_root=out_root,
        source={
            "kind": "perceptor_frame",
            "stamp": stamp,
            "frame": frame_n,
            "src": str(frame_path),
        },
    )


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


def harvest_run_auto_blocker(
    run_dir: Path,
    *,
    out_root: Path = DEFAULT_CANDIDATES,
) -> List[Path]:
    """Scan a live run JSONL for storage/blocker evidence and freeze bundles."""
    run_dir = Path(run_dir)
    jsonl = None
    if run_dir.is_file() and run_dir.suffix == ".jsonl":
        jsonl = run_dir
        run_dir = run_dir.parent
    else:
        cands = sorted(run_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        jsonl = cands[0] if cands else None
    if jsonl is None or not jsonl.is_file():
        raise FileNotFoundError(f"no jsonl in {run_dir}")

    stamp = _stamp_from_name(run_dir.name)
    written: List[Path] = []
    for row in _iter_jsonl(jsonl):
        phase = str(row.get("phase") or row.get("kind") or "")
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else row
        blob_parts: List[str] = []
        for key in ("observation_texts", "dialogs", "system_warnings", "evidence"):
            for t in payload.get(key) or []:
                blob_parts.append(str(t))
        # Nested housekeeping / executability
        for key in ("blockers", "last_warnings", "last_blocking_conditions"):
            val = payload.get(key)
            if val:
                blob_parts.append(json.dumps(val)[:500])
        blob = "\n".join(blob_parts).lower()
        interesting = (
            "storage is too full" in blob
            or "storage_pressure" in blob
            or phase in {"executability", "prerequisite_child", "housekeeping_act"}
        )
        if not interesting:
            continue
        step = row.get("iteration") or row.get("step") or len(written) + 1
        written.append(
            write_candidate_bundle(
                candidate_id=f"phenomenon_run_{stamp}_step_{int(step):04d}",
                stamp=stamp,
                step=int(step),
                observation_texts=blob_parts[:12],
                world_before=payload if isinstance(payload, dict) else None,
                meta_decision=payload.get("meta_action")
                if isinstance(payload, dict)
                else None,
                run_excerpt=[row],
                out_root=out_root,
                source={
                    "kind": "run_jsonl",
                    "stamp": stamp,
                    "step": int(step),
                    "phase": phase,
                    "src": str(jsonl),
                },
            )
        )
    return written


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--from-perception-candidate", type=Path, default=None)
    p.add_argument("--from-frame", type=Path, default=None)
    p.add_argument("--from-run", type=Path, default=None)
    p.add_argument("--auto-blocker", action="store_true")
    p.add_argument("--out", type=Path, default=DEFAULT_CANDIDATES)
    args = p.parse_args(list(argv) if argv is not None else None)

    if args.from_perception_candidate:
        dest = harvest_perception_candidate(args.from_perception_candidate, out_root=args.out)
        print(f"wrote {dest}")
        return 0
    if args.from_frame:
        dest = harvest_frame(args.from_frame, out_root=args.out)
        print(f"wrote {dest}")
        return 0
    if args.from_run:
        if not args.auto_blocker:
            print("pass --auto-blocker with --from-run", flush=True)
            return 2
        paths = harvest_run_auto_blocker(args.from_run, out_root=args.out)
        for path in paths:
            print(f"wrote {path}")
        print(f"{len(paths)} candidate(s)")
        return 0 if paths else 1
    p.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
