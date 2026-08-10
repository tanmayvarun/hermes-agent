"""Mine unique meta-decision situations from zarooratwala live runs → goldens.

Walks every ``executive_judgement`` in ``plugin/experiments/runs``, clusters by
the signal fingerprint the LLM packet uses, labels each cluster with today's
``decision_ladder`` (current policy), and writes/updates:

- ``corpus/v1/meta_action.jsonl`` — golden cases (keeps hand-authored contracts)
- ``corpus/v1/meta_situations_index.json`` — full inventory for packet design

Usage:
    python -m plugin.evals.golden.mine_meta_situations \\
        --runs plugin/experiments/runs --write
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from plugin.agent.executive.hierarchy import decision_ladder
from plugin.agent.executive.meta_action import MetaContext
from plugin.agent.executive.meta_consultation import meta_context_packet
from plugin.agent.executive.meta_situation import MetaSituation
from plugin.agent.executive.sufficiency import DecisionSufficiency
from plugin.evals.golden.schema import (
    DEFAULT_GOLDEN_DIR,
    GOLDEN_VERSION,
    GoldenCase,
    load_module_cases,
    module_path,
    version_dir,
)

OBSOLETE_REASON_SUBSTR = (
    "re-planning exhausted",
    "define_action to bind",
    "re-planning stopped changing",
    "perceive_exhausted_fall_through",
)

# Historical VERIFY-on-surprise → current REFLECT contract.
POLICY_MIGRATE_VERIFY_SURPRISE = True


def _iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open(encoding="utf-8", errors="replace") as fh:
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


def list_run_logs(runs_dir: str) -> List[Path]:
    root = Path(runs_dir)
    if not root.is_dir():
        return []
    return sorted(
        (
            p
            for p in root.glob("*.jsonl")
            if "zarooratwala" in p.name.lower()
            or ("forward" in p.name.lower() and "live" in p.name.lower())
        ),
        key=lambda p: p.stat().st_mtime,
    )


def _stamp_from_run(name: str) -> str:
    m = re.search(r"(20\d{6}_\d{6})", name)
    return m.group(1) if m else name.replace(".jsonl", "")[-15:]


def _bucket_streak(n: Any) -> int:
    try:
        v = int(n or 0)
    except (TypeError, ValueError):
        v = 0
    if v <= 0:
        return 0
    if v == 1:
        return 1
    if v == 2:
        return 2
    if v <= 4:
        return 4
    return 5


def build_ctx_and_situation(
    ev: Dict[str, Any],
) -> Tuple[MetaContext, MetaSituation, bool, str]:
    meta = ev.get("meta_action") if isinstance(ev.get("meta_action"), dict) else {}
    suff = ev.get("sufficiency") if isinstance(ev.get("sufficiency"), dict) else {}
    scores = meta.get("scores") if isinstance(meta.get("scores"), dict) else {}
    reason = str(meta.get("reason") or "")
    blocking = [
        str(b)
        for b in (
            ev.get("blocking_uncertainties")
            or suff.get("blocking_uncertainties")
            or []
        )
        if str(b).strip()
    ][:6]
    contract = ev.get("goal_contract") if isinstance(ev.get("goal_contract"), dict) else {}
    streaks = ev.get("streaks") if isinstance(ev.get("streaks"), dict) else {}
    triggers = [str(t) for t in (ev.get("mode_triggers") or []) if str(t).strip()]

    post_owed = bool(ev.get("post_action_look_owed")) or bool(
        scores.get("must_reperceive") == 1.0
    ) or ("relook owed" in reason)
    surprised = bool(ev.get("last_action_surprised"))
    awaiting = bool(ev.get("awaiting_verification")) or post_owed
    # Old "fresh look" / "verify first" under surprise → look debt + surprise.
    if "verify first" in reason or scores.get("verify_folded") == 1.0:
        surprised = True
        awaiting = True
    if "prediction error" in reason or "reflect before" in reason:
        surprised = True
        awaiting = True
        post_owed = post_owed or True

    branch_stale = (
        "rung 4" in reason
        or "branch stale" in reason
        or "branch exhausted" in reason
        or "backtracks exhausted" in reason
        or "branch_exhausted" in triggers
    )
    ambiguous = (
        "ambiguous" in triggers
        or "no clear strategy" in reason
        or "no_matching_procedure" in triggers
    )
    hard_block = "rung 6" in reason or (
        str(meta.get("action")) == "ask_user" and "ask user" in reason
    )
    backtrack_exhausted = "backtracks exhausted" in reason
    ig_exhausted = "information gathering exhausted" in reason
    perceive_streak_exhausted = "perceive streak exhausted" in reason

    sufficiency = DecisionSufficiency(
        sufficient_to_act=bool(suff.get("sufficient_to_act")),
        observe_has_value=bool(suff.get("observe_has_value")),
        suppress_observe=bool(suff.get("suppress_observe")),
        needs_exploration=bool(suff.get("needs_exploration")),
        blocking_uncertainties=blocking,
        useful_information_actions=[
            str(x) for x in (suff.get("useful_information_actions") or [])[:4]
        ],
        sufficient_for_which_actions=[
            str(x) for x in (suff.get("sufficient_for_which_actions") or [])[:4]
        ],
        confidence=float(suff.get("confidence") or 0.0),
        reason=str(suff.get("reason") or "")[:160],
    )
    ctx = MetaContext(
        sufficiency=sufficiency,
        has_grounded_action=bool(ev.get("has_grounded_action")),
        awaiting_verification=awaiting,
        last_action_surprised=surprised,
        post_action_look_owed=bool(post_owed),
        branch_stale=branch_stale,
        hard_block=hard_block,
        probe_available=False,
        ambiguous=ambiguous,
        question_settled=False,
        reperception_exhausted=False,
        steps_remaining=99,
        backtrack_exhausted=backtrack_exhausted,
        information_gathering_exhausted=ig_exhausted,
        think_exhausted=False,
        probe_exhausted=False,
        perceive_streak_exhausted=perceive_streak_exhausted,
    )
    pq = ev.get("perception_query") if isinstance(ev.get("perception_query"), dict) else {}
    situation = MetaSituation(
        cognitive_mode=str(ev.get("cognitive_mode") or ""),
        mode_triggers=triggers,
        static_streak=int(ev.get("static_streak") or 0),
        coverage=(
            None if ev.get("coverage") is None else float(ev.get("coverage"))
        ),
        evidence_gaps=[
            str(g) for g in (ev.get("perceptor_evidence_gaps") or []) if str(g).strip()
        ][:6],
        blocking_uncertainties=blocking,
        perception_query=pq,
        goal_contract=contract,
        phase=str(contract.get("phase") or ""),
        last_meta_action="",
        last_action="",
        consecutive_surprise_relooks=int(streaks.get("surprise_relooks") or 0),
        consecutive_perceives=int(streaks.get("perceives") or 0),
        consecutive_thinks=int(streaks.get("thinks") or 0),
        consecutive_probes=int(streaks.get("probes") or 0),
        consecutive_backtracks=int(streaks.get("backtracks") or 0),
        consecutive_information_gathering=int(
            streaks.get("information_gathering") or 0
        ),
    )
    goal_complete = bool(contract.get("all_satisfied"))
    return ctx, situation, goal_complete, reason


def situation_fingerprint(ctx: MetaContext, sit: MetaSituation, goal_complete: bool) -> Tuple:
    """Policy-relevant fingerprint — one golden per unique decision situation."""
    suff = ctx.sufficiency
    return (
        bool(ctx.last_action_surprised),
        bool(ctx.awaiting_verification),
        bool(ctx.post_action_look_owed),
        bool(ctx.has_grounded_action),
        bool(suff and suff.sufficient_to_act),
        bool(suff and suff.observe_has_value),
        bool(suff and suff.blocking_uncertainties),
        bool(sit.evidence_gaps),
        bool(ctx.branch_stale),
        bool(ctx.ambiguous),
        bool(ctx.hard_block),
        bool(ctx.backtrack_exhausted),
        bool(ctx.information_gathering_exhausted),
        bool(ctx.perceive_streak_exhausted),
        bool(goal_complete),
        _bucket_streak(sit.static_streak),
        tuple(sorted(sit.mode_triggers)[:6]),
        str(sit.cognitive_mode or ""),
    )


def _ctx_input(ctx: MetaContext, sit: MetaSituation, goal_complete: bool) -> Dict[str, Any]:
    suff = ctx.sufficiency
    return {
        "awaiting_verification": bool(ctx.awaiting_verification),
        "last_action_surprised": bool(ctx.last_action_surprised),
        "post_action_look_owed": bool(ctx.post_action_look_owed),
        "has_grounded_action": bool(ctx.has_grounded_action),
        "reperception_exhausted": bool(ctx.reperception_exhausted),
        "branch_stale": bool(ctx.branch_stale),
        "hard_block": bool(ctx.hard_block),
        "probe_available": bool(ctx.probe_available),
        "ambiguous": bool(ctx.ambiguous),
        "question_settled": bool(ctx.question_settled),
        "backtrack_exhausted": bool(ctx.backtrack_exhausted),
        "information_gathering_exhausted": bool(ctx.information_gathering_exhausted),
        "think_exhausted": bool(ctx.think_exhausted),
        "probe_exhausted": bool(ctx.probe_exhausted),
        "perceive_streak_exhausted": bool(ctx.perceive_streak_exhausted),
        "steps_remaining": int(ctx.steps_remaining),
        "goal_complete": bool(goal_complete),
        "sufficiency": {
            "sufficient_to_act": bool(suff.sufficient_to_act) if suff else False,
            "observe_has_value": bool(suff.observe_has_value) if suff else False,
            "needs_exploration": bool(suff.needs_exploration) if suff else False,
            "suppress_observe": bool(suff.suppress_observe) if suff else False,
            "blocking_uncertainties": list(suff.blocking_uncertainties) if suff else [],
            "confidence": float(suff.confidence) if suff else 0.0,
            "reason": str(suff.reason) if suff else "",
        },
        "situation": sit.to_dict(),
    }


def mine(
    runs_dir: str,
    *,
    min_count: int = 1,
    purity: float = 0.0,
) -> Dict[str, Any]:
    clusters: Dict[Tuple, Dict[str, Any]] = {}
    skipped_obsolete = 0
    total = 0
    for path in list_run_logs(runs_dir):
        for ev in _iter_jsonl(path):
            if ev.get("kind") != "executive_judgement":
                continue
            meta = ev.get("meta_action") if isinstance(ev.get("meta_action"), dict) else {}
            hist = str(meta.get("action") or "").strip().lower()
            reason = str(meta.get("reason") or "")
            if not hist:
                continue
            if any(s in reason for s in OBSOLETE_REASON_SUBSTR):
                skipped_obsolete += 1
                continue
            total += 1
            ctx, sit, goal_complete, reason = build_ctx_and_situation(ev)
            key = situation_fingerprint(ctx, sit, goal_complete)
            bucket = clusters.get(key)
            if bucket is None:
                bucket = {
                    "count": 0,
                    "actions": Counter(),
                    "reasons": Counter(),
                    "example": None,
                    "ctx": ctx,
                    "situation": sit,
                    "goal_complete": goal_complete,
                    "runs": Counter(),
                }
                clusters[key] = bucket
            bucket["count"] += 1
            bucket["actions"][hist] += 1
            bucket["reasons"][reason[:120]] += 1
            bucket["runs"][path.name] += 1
            if bucket["example"] is None:
                bucket["example"] = {
                    "run": path.name,
                    "step": ev.get("step"),
                    "historical_action": hist,
                    "historical_reason": reason[:160],
                }

    cases: List[GoldenCase] = []
    index_rows: List[Dict[str, Any]] = []
    for i, (key, bucket) in enumerate(
        sorted(clusters.items(), key=lambda kv: (-kv[1]["count"], str(kv[0])))
    ):
        if bucket["count"] < min_count:
            continue
        hist_maj, hist_n = bucket["actions"].most_common(1)[0]
        purity_n = hist_n / max(1, bucket["count"])
        if purity_n < purity:
            continue
        ctx: MetaContext = bucket["ctx"]
        sit: MetaSituation = bucket["situation"]
        goal_complete = bool(bucket["goal_complete"])
        ladder = decision_ladder(ctx, goal_complete=goal_complete)
        gold_action = ladder.action.value
        # Policy migration: historical VERIFY under surprise → REFLECT today.
        if (
            POLICY_MIGRATE_VERIFY_SURPRISE
            and hist_maj == "verify"
            and ctx.last_action_surprised
        ):
            gold_action = "reflect"
        # Prefer ladder; if ladder agrees with historical majority, tag as live.
        agrees = gold_action == hist_maj
        packet = meta_context_packet(ctx, goal_complete=goal_complete, situation=sit)
        ex = bucket["example"] or {}
        stamp = _stamp_from_run(str(ex.get("run") or "live"))
        case_id = f"meta/live_sit_{i:03d}_{gold_action}_{stamp}"
        note = (
            f"Mined unique meta situation n={bucket['count']} hist={hist_maj}"
            f"({purity_n:.0%}) ladder={ladder.action.value}; "
            f"ex={ex.get('run')} step={ex.get('step')}"
        )
        tags = [
            "mined_live",
            f"hist_{hist_maj}",
            f"gold_{gold_action}",
            "agrees_hist" if agrees else "policy_update",
            stamp,
        ]
        forbidden = []
        if gold_action == "reflect":
            forbidden = ["verify", "act"]
        elif gold_action == "perceive" and ctx.post_action_look_owed:
            forbidden = ["act", "verify"]
        elif gold_action == "act" and not ctx.post_action_look_owed:
            forbidden = ["verify"]
        cases.append(
            GoldenCase(
                id=case_id,
                module="meta_action",
                source="outcome",
                note=note[:320],
                tags=tags,
                input=_ctx_input(ctx, sit, goal_complete),
                gold={
                    "meta_action": gold_action,
                    "forbidden_meta": forbidden,
                    "score_via": "ladder",
                    "packet_sections": list(packet.keys()),
                    "historical_majority": hist_maj,
                    "historical_count": bucket["count"],
                    "historical_purity": round(purity_n, 3),
                },
            )
        )
        index_rows.append(
            {
                "id": case_id,
                "count": bucket["count"],
                "historical_majority": hist_maj,
                "historical_actions": dict(bucket["actions"]),
                "gold_meta_action": gold_action,
                "ladder_reason": ladder.reason,
                "agrees_historical": agrees,
                "fingerprint": [str(x) for x in key],
                "example": ex,
                "top_runs": bucket["runs"].most_common(5),
            }
        )

    return {
        "judgements_used": total,
        "skipped_obsolete": skipped_obsolete,
        "unique_situations": len(clusters),
        "cases": cases,
        "index": index_rows,
    }


def _merge_with_hand_authored(mined: List[GoldenCase]) -> List[GoldenCase]:
    """Keep non-mined hand cases; replace prior mined_live set."""
    existing = load_module_cases("meta_action")
    kept = [c for c in existing if "mined_live" not in (c.tags or [])]
    # Preserve hand-authored ids; drop mined duplicates of those ids.
    hand_ids = {c.id for c in kept}
    merged = list(kept)
    for c in mined:
        if c.id in hand_ids:
            continue
        merged.append(c)
    return merged


def write_corpus(
    mined: Dict[str, Any],
    *,
    root: str = DEFAULT_GOLDEN_DIR,
    version: str = GOLDEN_VERSION,
) -> Path:
    cases = _merge_with_hand_authored(list(mined["cases"]))
    path = module_path("meta_action", root=root, version=version)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for case in cases:
            fh.write(json.dumps(case.to_dict(), ensure_ascii=False) + "\n")

    index_path = version_dir(root, version) / "meta_situations_index.json"
    index_path.write_text(
        json.dumps(
            {
                "judgements_used": mined["judgements_used"],
                "skipped_obsolete": mined["skipped_obsolete"],
                "unique_situations": mined["unique_situations"],
                "golden_cases_written": len(cases),
                "mined_cases": len(mined["cases"]),
                "situations": mined["index"],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    manifest_path = version_dir(root, version) / "_manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        modules = dict(manifest.get("modules") or {})
        modules["meta_action"] = len(cases)
        manifest["modules"] = modules
        sources = list(manifest.get("sources") or [])
        note = (
            f"mined unique meta situations from {mined['judgements_used']} "
            f"executive_judgement events ({mined['unique_situations']} unique)"
        )
        if note not in sources:
            sources.append(note)
        manifest["sources"] = sources
        changelog = list(manifest.get("changelog") or [])
        changelog.append(
            {
                "date": "2026-08-07",
                "note": (
                    "Mine every unique live meta-decision situation into "
                    "meta_action goldens; reshape LLM meta packet "
                    "(look_debt/evidence/search/budgets/situation) from discriminators."
                ),
            }
        )
        manifest["changelog"] = changelog
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    return path


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", default="plugin/experiments/runs")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--min-count", type=int, default=1)
    parser.add_argument("--purity", type=float, default=0.0)
    args = parser.parse_args(argv)
    mined = mine(args.runs, min_count=args.min_count, purity=args.purity)
    print(
        f"judgements={mined['judgements_used']} obsolete_skipped={mined['skipped_obsolete']} "
        f"unique={mined['unique_situations']} cases={len(mined['cases'])}"
    )
    by_gold = Counter(c.gold.get("meta_action") for c in mined["cases"])
    print("gold actions:", dict(by_gold))
    agrees = sum(
        1 for c in mined["cases"] if "agrees_hist" in (c.tags or [])
    )
    print(f"agrees_historical={agrees} policy_update={len(mined['cases']) - agrees}")
    if args.write:
        path = write_corpus(mined)
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
