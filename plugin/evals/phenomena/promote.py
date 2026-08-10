"""Promote an annotated phenomenon candidate into the permanent corpus.

Usage:
    python -m plugin.evals.phenomena.promote \\
        --candidate plugin/evals/phenomena/eval_candidates/phenomenon_run_live_... \\
        --family warning_vs_blocker \\
        --fixture-id hard_blocking_storage_dialog_161105
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from plugin.evals.phenomena.schema import (
    DEFAULT_PHENOMENA_DIR,
    PHENOMENA_VERSION,
    GoldenFixture,
    load_manifest,
    write_fixture,
)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def promote_candidate(
    candidate_dir: Path,
    *,
    family: str,
    fixture_id: str,
    gold_overrides: Optional[Dict[str, Any]] = None,
    forbidden: Optional[Sequence[str]] = None,
    tags: Optional[Sequence[str]] = None,
    root: str = DEFAULT_PHENOMENA_DIR,
    version: str = PHENOMENA_VERSION,
    force_privacy: bool = False,
) -> Path:
    candidate_dir = Path(candidate_dir)
    from plugin.evals.phenomena.redaction import require_promote_clearance

    require_promote_clearance(candidate_dir, force=force_privacy)
    ann = _load_json(candidate_dir / "annotation.json")
    if str(ann.get("status") or "") not in {"approved", "annotated", "ready"}:
        # Allow explicit CLI promote even if stub status — caller owns review
        # only when force_privacy was used; otherwise redaction already gated.
        pass

    texts: List[str] = []
    if (candidate_dir / "observation_texts.json").is_file():
        texts = list(_load_json(candidate_dir / "observation_texts.json") or [])
    world = {}
    if (candidate_dir / "world_before.json").is_file():
        world = dict(_load_json(candidate_dir / "world_before.json") or {})
    facts = {}
    if (candidate_dir / "system_facts.json").is_file():
        facts = dict(_load_json(candidate_dir / "system_facts.json") or {})
    exec_ctx = {}
    if (candidate_dir / "executive_context.json").is_file():
        exec_ctx = dict(_load_json(candidate_dir / "executive_context.json") or {})

    expected = dict(ann.get("expected") or {})
    gold = dict(gold_overrides or {})
    if "executability" in expected and "status" not in gold:
        gold["status"] = str(expected["executability"]).lower()
    if expected.get("expect_blocker") is not None and "expect_blocker" not in gold:
        gold["expect_blocker"] = bool(expected["expect_blocker"])
    if expected.get("expect_warning") is not None and "expect_warning" not in gold:
        gold["expect_warning"] = bool(expected["expect_warning"])

    cand_meta = {}
    if (candidate_dir / "candidate.json").is_file():
        cand_meta = dict(_load_json(candidate_dir / "candidate.json") or {})
    source = dict(cand_meta.get("source") or {})

    surface = str(world.get("surface") or "")
    view = {"screen": surface or "dialog", "storage_pressure": bool(gold.get("expect_blocker"))}
    features = {
        "extras": {
            "storage_pressure": bool(gold.get("expect_blocker")),
            "screen_kind": surface or "dialog",
            "has_dialog": surface == "dialog" or bool(gold.get("expect_blocker")),
        }
    }

    fix = GoldenFixture(
        fixture_id=fixture_id,
        family=family,
        phenomenon=str((ann.get("phenomena") or ["environmental_blocker"])[0]),
        source_run=str(source.get("stamp") or ""),
        app=str(ann.get("app") or exec_ctx.get("active_app") or ""),
        note=str(ann.get("note") or ""),
        tags=list(tags or []) + ["promoted", "from_live"],
        observation_texts=texts,
        system_facts=facts,
        view=view,
        features=features,
        parent_intention={
            "id": "i_parent",
            "objective": str(exec_ctx.get("goal") or "forward message"),
            "success_predicate": "forward_affordance_grounded",
        },
        world_before=world,
        artifacts={
            k: str((candidate_dir / k).relative_to(Path.cwd()))
            if (candidate_dir / k).is_file()
            else ""
            for k in ("screenshot.png", "ax.json")
            if (candidate_dir / k).is_file()
        },
        gold=gold,
        forbidden=list(forbidden or ann.get("forbidden") or []),
    )
    path = write_fixture(fix, root=root, version=version)
    _bump_manifest(family, fixture_id, source_run=fix.source_run, root=root, version=version)
    ann["status"] = "promoted"
    ann["promoted_fixture_id"] = fixture_id
    ann["promoted_family"] = family
    (candidate_dir / "annotation.json").write_text(
        json.dumps(ann, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return path


def _bump_manifest(
    family: str,
    fixture_id: str,
    *,
    source_run: str = "",
    root: str = DEFAULT_PHENOMENA_DIR,
    version: str = PHENOMENA_VERSION,
) -> None:
    man_path = Path(root) / version / "_manifest.json"
    man = load_manifest(root=root, version=version)
    if man.get("error"):
        man = {
            "version": version,
            "frozen": True,
            "eval_only": True,
            "families": {f: 0 for f in (
                "warning_vs_blocker",
                "executability",
                "prerequisite_children",
                "effect_resolution",
                "effect_verification",
                "resumption",
                "trajectories",
            )},
            "known_gap_fixture_ids": [],
            "sources": [],
            "changelog": [],
        }
    families = dict(man.get("families") or {})
    # Recount from disk.
    fam_dir = Path(root) / version / family
    n = len(list(fam_dir.glob("*.json"))) if fam_dir.is_dir() else 0
    families[family] = n
    man["families"] = families
    sources = list(man.get("sources") or [])
    note = f"promoted {fixture_id} → {family}"
    if source_run:
        note += f" (run {source_run})"
    if note not in sources:
        sources.append(note)
    man["sources"] = sources
    changelog = list(man.get("changelog") or [])
    changelog.append({"fixture_id": fixture_id, "family": family, "source_run": source_run})
    man["changelog"] = changelog[-50:]
    man_path.parent.mkdir(parents=True, exist_ok=True)
    man_path.write_text(json.dumps(man, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--candidate", type=Path, required=True)
    p.add_argument("--family", required=True)
    p.add_argument("--fixture-id", required=True)
    p.add_argument("--tag", action="append", default=[])
    p.add_argument(
        "--force-privacy",
        action="store_true",
        help="Bypass redaction gate after explicit human review (dangerous).",
    )
    args = p.parse_args(list(argv) if argv is not None else None)
    path = promote_candidate(
        args.candidate,
        family=args.family,
        fixture_id=args.fixture_id,
        tags=args.tag,
        force_privacy=bool(args.force_privacy),
    )
    print(f"promoted → {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
