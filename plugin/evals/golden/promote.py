"""Promote a human-checked golden candidate into the frozen corpus.

Candidates from ``harvest_run`` are NOT gold. This tool appends a checked case
to ``corpus/vN/<module>.jsonl``, bumps the manifest count + changelog, and
optionally runs the scorer so a bad promotion fails immediately.

Usage:
    python -m plugin.evals.golden.promote \\
        --case path/to/case.json --module flow --stamp 014321

    # From a harvest candidate line (fills module/id defaults; still needs gold):
    python -m plugin.evals.golden.promote \\
        --from-candidate plugin/evals/golden/candidates/20260807_021051.jsonl \\
        --index 0 --dry-run
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

from plugin.evals.golden.schema import (
    DEFAULT_GOLDEN_DIR,
    GOLDEN_MODULES,
    GOLDEN_VERSION,
    version_dir,
)


def _load_json(path: Path) -> Dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SystemExit(f"case must be a JSON object: {path}")
    return raw


def _load_candidate_line(path: Path, index: int) -> Dict[str, Any]:
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if index < 0 or index >= len(lines):
        raise SystemExit(f"candidate index {index} out of range (n={len(lines)})")
    obj = json.loads(lines[index])
    if not isinstance(obj, dict):
        raise SystemExit("candidate line is not an object")
    module = str(obj.get("module") or "meta_action")
    stamp = str(obj.get("run") or path.stem)
    stamp = stamp.replace("forward_zarooratwala_live_", "").replace(".jsonl", "")[:12]
    case_id = str(obj.get("id") or f"{module}/live_{stamp}_candidate_{index}")
    return {
        "id": case_id,
        "module": module,
        "source": "failure",
        "tags": ["harvest", stamp, module],
        "note": (
            "PROMOTE DRAFT from harvest — replace input/gold with human-checked "
            "decision structure before committing."
        ),
        "input": {
            "harvest": {
                k: obj.get(k)
                for k in (
                    "meta_action",
                    "meta_reason",
                    "last_action_surprised",
                    "awaiting_verification",
                    "family",
                    "outcome",
                    "predicted_surface",
                    "act_intention",
                    "prediction_error",
                )
                if obj.get(k) is not None
            }
        },
        "gold": {},
    }


def _append_case(
    case: Dict[str, Any],
    *,
    root: str = DEFAULT_GOLDEN_DIR,
    version: str = GOLDEN_VERSION,
    dry_run: bool = False,
) -> Path:
    module = str(case.get("module") or "").strip()
    case_id = str(case.get("id") or "").strip()
    if module not in GOLDEN_MODULES:
        raise SystemExit(f"unknown module {module!r}; choose from {GOLDEN_MODULES}")
    if not case_id:
        raise SystemExit("case needs id")
    if not isinstance(case.get("gold"), dict):
        raise SystemExit("case needs gold object (human decision structure)")
    if module != "flow" and not case.get("gold") and case.get("source") != "draft":
        # Allow empty gold only for dry-run drafts.
        pass

    vdir = version_dir(root, version)
    target = vdir / f"{module}.jsonl"
    existing = target.read_text(encoding="utf-8") if target.is_file() else ""
    if case_id in existing:
        raise SystemExit(f"case id already present: {case_id}")

    line = json.dumps(case, ensure_ascii=False)
    if dry_run:
        print(f"DRY-RUN would append to {target}:\n{line}")
        return target

    with target.open("a", encoding="utf-8") as fh:
        if existing and not existing.endswith("\n"):
            fh.write("\n")
        fh.write(line + "\n")
    _bump_manifest(
        root=root,
        version=version,
        module=module,
        case_id=case_id,
        note=str(case.get("note") or "")[:160],
    )
    print(f"promoted {case_id} → {target}")
    return target


def _bump_manifest(
    *,
    root: str,
    version: str,
    module: str,
    case_id: str,
    note: str,
) -> None:
    path = version_dir(root, version) / "_manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    modules = dict(manifest.get("modules") or {})
    modules[module] = int(modules.get(module) or 0) + 1
    manifest["modules"] = modules
    sources = list(manifest.get("sources") or [])
    if case_id not in sources:
        sources.append(case_id)
    manifest["sources"] = sources
    changelog = list(manifest.get("changelog") or [])
    changelog.append(
        {
            "date": date.today().isoformat(),
            "note": note or f"Promote {case_id}",
        }
    )
    manifest["changelog"] = changelog
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"manifest {module} count → {modules[module]}")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", help="Path to a complete golden case JSON object")
    ap.add_argument("--from-candidate", help="Harvest candidates JSONL")
    ap.add_argument("--index", type=int, default=0, help="Line index in --from-candidate")
    ap.add_argument("--module", help="Override module")
    ap.add_argument("--stamp", help="Tag stamp into id/tags when missing")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--score", action="store_true", help="Run golden.score after promote")
    ap.add_argument("--root", default=DEFAULT_GOLDEN_DIR)
    ap.add_argument("--version", default=GOLDEN_VERSION)
    args = ap.parse_args(argv)

    if args.case:
        case = _load_json(Path(args.case))
    elif args.from_candidate:
        case = _load_candidate_line(Path(args.from_candidate), args.index)
        case["source"] = "draft"
    else:
        raise SystemExit("provide --case or --from-candidate")

    if args.module:
        case["module"] = args.module
    if args.stamp:
        tags = list(case.get("tags") or [])
        if args.stamp not in tags:
            tags.append(args.stamp)
        case["tags"] = tags
        if "live_" not in str(case.get("id") or ""):
            case["id"] = f"{case['module']}/live_{args.stamp}_{Path(str(case.get('id'))).name}"

    _append_case(case, root=args.root, version=args.version, dry_run=args.dry_run)

    if args.score and not args.dry_run:
        from plugin.evals.golden.score import summarize_golden

        print(summarize_golden(golden_root=args.root, version=args.version))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
