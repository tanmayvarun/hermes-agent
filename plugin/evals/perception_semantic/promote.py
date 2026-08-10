"""Promote a reviewed eval candidate into ``fixtures/<phenomenon>/``.

Candidates from ``harvest_failure`` are NOT gold until a human fills
``annotation.json`` (surfaces, typed claims, ownership, affordances, actions).

Usage:
    python -m plugin.evals.perception_semantic.promote \\
        --candidate eval_candidates/run_20260809_184742_step_0015 \\
        --phenomenon cross_surface \\
        --id whatsapp_forward_picker_live_184742_step15

    # Dry-run
    python -m plugin.evals.perception_semantic.promote \\
        --candidate eval_candidates/golden_whatsapp_forward_picker_source_1_dest_0 \\
        --dry-run
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from plugin.evals.perception_semantic.schema import (
    DEFAULT_CASES_DIR,
    GoldenPerceptionCase,
    case_to_dict,
)

DEFAULT_CANDIDATES_DIR = Path(__file__).resolve().parent / "eval_candidates"
DEFAULT_PERCEPTOR_ROOT = (
    Path(__file__).resolve().parents[2] / "experiments" / "fixtures" / "perceptor"
)


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _require_annotation(ann: Dict[str, Any]) -> None:
    gold = ann.get("gold") if isinstance(ann.get("gold"), dict) else {}
    surfaces = gold.get("surfaces") or []
    claims = gold.get("claims") or gold.get("observations") or []
    if not surfaces:
        raise SystemExit("annotation.json gold.surfaces is required before promote")
    if not claims:
        raise SystemExit("annotation.json gold.claims is required before promote")
    if not ann.get("phenomena"):
        raise SystemExit("annotation.json phenomena tags are required before promote")


def promote_candidate(
    candidate_dir: Path,
    *,
    fixtures_root: Path = DEFAULT_CASES_DIR,
    phenomenon: str = "",
    case_id: str = "",
    dry_run: bool = False,
    copy_screenshot: bool = True,
) -> Path:
    raw = Path(candidate_dir)
    if raw.is_dir():
        cand = raw
    else:
        # Accept id, relative path under package, or bare folder name.
        text = str(candidate_dir).strip().rstrip("/")
        for cand in (
            Path(text),
            DEFAULT_CANDIDATES_DIR / text,
            DEFAULT_CANDIDATES_DIR / Path(text).name,
            Path(__file__).resolve().parent / text,
        ):
            if cand.is_dir():
                break
        else:
            raise SystemExit(f"candidate dir not found: {candidate_dir}")
    if not cand.is_dir():
        raise SystemExit(f"candidate dir not found: {cand}")

    meta = _load(cand / "candidate.json") if (cand / "candidate.json").is_file() else {}
    ann = _load(cand / "annotation.json")
    packet = _load(cand / "model_input.json")
    model_out = (
        _load(cand / "model_output.json")
        if (cand / "model_output.json").is_file()
        else {}
    )
    _require_annotation(ann)

    phenoms = [str(x) for x in (ann.get("phenomena") or [])]
    primary = phenomenon or (phenoms[0] if phenoms else "unclassified")
    # Map phenomenon → directory bucket (architect taxonomy).
    bucket = {
        "nested_surfaces": "surface_composition",
        "cross_surface_selection": "cross_surface",
        "foreground_authority": "cross_surface",
        "selection_state_typing": "selection_state",
        "object_binding": "object_binding",
        "latent_affordances": "latent_affordances",
        "partial_observation": "partial_observation",
        "sensor_conflict": "sensor_conflict",
        "task_conditioning": "task_conditioning",
    }.get(primary, primary if primary.endswith("s") or "_" in primary else "cross_surface")

    cid = case_id or str(ann.get("id") or meta.get("id") or cand.name)
    cid = cid.replace("golden_", "").replace("run_", "")
    if not cid.startswith("whatsapp_") and "whatsapp" in str(ann.get("app") or "").lower():
        pass

    record_dir = f"semantic_{cid}"
    screenshot_name = "frame_0001.png"
    shot_src = cand / "screenshot.png"
    if copy_screenshot and shot_src.is_file() and not dry_run:
        dest_dir = DEFAULT_PERCEPTOR_ROOT / record_dir
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(shot_src, dest_dir / screenshot_name)

    case = GoldenPerceptionCase.from_dict(
        {
            "id": cid,
            "phenomena": phenoms,
            "app": ann.get("app") or "WhatsApp",
            "note": ann.get("note")
            or f"Promoted from candidate {meta.get('id') or cand.name}",
            "record_dir": record_dir if shot_src.is_file() else "",
            "screenshot": screenshot_name if shot_src.is_file() else "",
            "packet": packet,
            "gold": ann.get("gold") or {},
            "annotated_response": ann.get("annotated_response"),
            "contaminated_response": ann.get("contaminated_response")
            or (
                model_out
                if (model_out.get("world_model") or {}).get("beliefs")
                else None
            ),
        }
    )
    payload = case_to_dict(case)
    # Preserve optional contaminated/annotated if present on annotation.
    if ann.get("contaminated_response"):
        payload["contaminated_response"] = ann["contaminated_response"]
    if ann.get("annotated_response"):
        payload["annotated_response"] = ann["annotated_response"]

    out_path = fixtures_root / bucket / f"{cid}.json"
    if dry_run:
        print(f"DRY-RUN would write {out_path}")
        print(json.dumps({k: payload[k] for k in ("id", "phenomena", "app", "note")}, indent=2))
        return out_path

    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        raise SystemExit(f"fixture already exists: {out_path}")
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # Mark candidate promoted.
    ann["status"] = "promoted"
    ann["promoted_fixture"] = str(out_path)
    (cand / "annotation.json").write_text(
        json.dumps(ann, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    if (cand / "candidate.json").is_file():
        meta["status"] = "promoted"
        meta["promoted_fixture"] = str(out_path)
        (cand / "candidate.json").write_text(
            json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    print(f"promoted {cid} → {out_path}")
    return out_path


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--candidate", required=True, help="Candidate directory or id")
    ap.add_argument("--phenomenon", default="", help="Primary taxonomy bucket override")
    ap.add_argument("--id", default="", help="Fixture id override")
    ap.add_argument("--fixtures", default=str(DEFAULT_CASES_DIR))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-screenshot-copy", action="store_true")
    args = ap.parse_args(argv)

    promote_candidate(
        Path(args.candidate),
        fixtures_root=Path(args.fixtures),
        phenomenon=args.phenomenon,
        case_id=args.id,
        dry_run=args.dry_run,
        copy_screenshot=not args.no_screenshot_copy,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
