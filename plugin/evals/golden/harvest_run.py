"""Extract annotation *candidates* from zarooratwala run JSONL.

Candidates are NOT gold. A human must promote them into ``corpus/vN/*.jsonl``
with checked labels. Prefer failure streaks (transition regression, VERIFY/THINK
loops, stalled open).

Usage:
    python -m plugin.evals.golden.harvest_run \\
        --runs plugin/experiments/runs --limit 8 --out plugin/evals/golden/candidates
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence


DEFAULT_RUNS_DIR = "plugin/experiments/runs"
DEFAULT_OUT_DIR = "plugin/evals/golden/candidates"

# Event kinds that make useful module-golden candidates.
_INTERESTING = frozenset(
    {
        "executive_judgement",
        "meta_action_phase",
        "transition_eval",
        "verification",
        "planner_decision",
        "perception_summary",
        "ax_settle_regression_diagnostic",
        "executive_reperceive",
        "stalled",
        # Act-intention → post-act score → inferred surprise (014321 class).
        "act_intention",
        "prediction_error",
        "prediction_held",
        "execution_effect_missing",
        "transition_attribution",
    }
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


def _is_zarooratwala_run(path: Path) -> bool:
    name = path.name.lower()
    return "zarooratwala" in name or "forward" in name and "live" in name


def list_run_logs(runs_dir: str, *, limit: int = 0) -> List[Path]:
    root = Path(runs_dir)
    found: List[Path] = []
    if root.is_dir():
        found.extend(p for p in root.glob("*.jsonl") if _is_zarooratwala_run(p))
        # /tmp/hermes-runs/<stamp>/forward_*.jsonl layout
        found.extend(p for p in root.glob("*/*.jsonl") if _is_zarooratwala_run(p))
    # Always also scan the live /tmp root when harvesting the default repo runs dir.
    try:
        from plugin.experiments.runs.live_paths import iter_live_run_logs

        if str(root).endswith("plugin/experiments/runs") or root.name == "runs":
            found.extend(iter_live_run_logs(limit=0))
    except Exception:
        tmp = Path("/tmp/hermes-runs")
        if tmp.is_dir():
            found.extend(p for p in tmp.glob("*/*.jsonl") if _is_zarooratwala_run(p))
    uniq: Dict[str, Path] = {}
    for p in found:
        try:
            uniq[str(p.resolve())] = p
        except OSError:
            uniq[str(p)] = p
    paths = sorted(
        uniq.values(),
        key=lambda p: p.stat().st_mtime if p.exists() else 0,
        reverse=True,
    )
    if limit:
        paths = paths[: max(0, int(limit))]
    return paths


def _meta_from_judgement(event: Dict[str, Any]) -> Dict[str, Any]:
    meta = event.get("meta_action") if isinstance(event.get("meta_action"), dict) else {}
    suff = event.get("sufficiency") if isinstance(event.get("sufficiency"), dict) else {}
    return {
        "module": "meta_action",
        "meta_action": str(meta.get("action") or ""),
        "meta_reason": str(meta.get("reason") or "")[:200],
        "last_action_surprised": bool(event.get("last_action_surprised")),
        "awaiting_verification": bool(event.get("awaiting_verification")),
        "has_grounded_action": bool(event.get("has_grounded_action")),
        "sufficiency_reason": str(suff.get("reason") or "")[:160],
        "sufficient_to_act": suff.get("sufficient_to_act"),
    }


def _transition_candidate(event: Dict[str, Any]) -> Dict[str, Any]:
    summary = event.get("summary") if isinstance(event.get("summary"), dict) else {}
    attempt = event.get("attempt") if isinstance(event.get("attempt"), dict) else {}
    outcome = str(
        summary.get("outcome")
        or attempt.get("outcome")
        or event.get("reason")
        or ""
    ).strip().lower()
    return {
        "module": "critic",  # often AX settle misread; promote to critic/meta gold
        "outcome": outcome,
        "action_family": str(
            attempt.get("action_family")
            or (attempt.get("prediction") or {}).get("action_family")
            or ""
        ),
        "predicted_surface": str(
            ((attempt.get("prediction") or {}) if isinstance(attempt.get("prediction"), dict) else {}).get(
                "expected_surface"
            )
            or ""
        ),
        "tag_hint": "ax_settle_regression" if outcome == "regression" else outcome,
    }


def _planner_candidate(event: Dict[str, Any]) -> Dict[str, Any]:
    decision = event.get("decision") if isinstance(event.get("decision"), dict) else {}
    return {
        "module": "brain",
        "family": str(decision.get("action_family") or decision.get("action") or ""),
        "rationale": str(decision.get("rationale") or "")[:200],
        "semantic_target": str(decision.get("semantic_target") or "")[:80],
    }


def _perception_candidate(event: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "module": "perceive",
        "surface": str(event.get("surface") or ""),
        "message": str(event.get("message") or event.get("text") or "")[:240],
    }


def harvest_run(path: Path) -> Dict[str, Any]:
    """Scan one run log into candidate records (failure-biased)."""
    counts: Counter = Counter()
    candidates: List[Dict[str, Any]] = []
    for event in _iter_jsonl(path):
        kind = str(event.get("kind") or "")
        if kind not in _INTERESTING:
            continue
        counts[kind] += 1
        t = event.get("run_elapsed_s")
        base = {
            "run": path.name,
            "kind": kind,
            "ts": event.get("ts"),
            "run_elapsed_s": t,
            "step": event.get("step"),
            "status": event.get("status"),
        }
        if kind == "executive_judgement":
            rec = {**base, **_meta_from_judgement(event)}
            # Prefer surprising / non-act judgements for annotation.
            if rec.get("last_action_surprised") or rec.get("meta_action") in {
                "verify",
                "think",
                "perceive",
                "backtrack",
                "information_gathering",
            }:
                candidates.append(rec)
        elif kind in {"transition_eval", "verification", "ax_settle_regression_diagnostic"}:
            rec = {**base, **_transition_candidate(event)}
            if rec.get("outcome") in {"regression", "no_effect", "uncertain", "fail"} or kind.endswith(
                "diagnostic"
            ):
                candidates.append(rec)
        elif kind == "planner_decision":
            rec = {**base, **_planner_candidate(event)}
            candidates.append(rec)
        elif kind == "perception_summary":
            rec = {**base, **_perception_candidate(event)}
            candidates.append(rec)
        elif kind in {"meta_action_phase", "executive_reperceive", "stalled"}:
            candidates.append(
                {
                    **base,
                    "module": "meta_action",
                    "handling": event.get("handling"),
                    "in_flight": event.get("in_flight"),
                    "message": str(event.get("message") or "")[:160],
                    "meta_action": (event.get("meta_action") or {}).get("action")
                    if isinstance(event.get("meta_action"), dict)
                    else None,
                }
            )
        elif kind == "act_intention":
            candidates.append(
                {
                    **base,
                    "module": "flow",
                    "act_intention": {
                        "surface": event.get("surface"),
                        "action_family": event.get("action_family"),
                        "likely_controls": event.get("likely_controls"),
                    },
                    "tag_hint": "act_intention",
                }
            )
        elif kind in {"prediction_error", "prediction_held", "execution_effect_missing"}:
            pe = event.get("prediction_error")
            if not isinstance(pe, dict):
                pe = {
                    "matched": event.get("matched"),
                    "predicted_surface": event.get("predicted_surface"),
                    "observed_surface": event.get("observed_surface"),
                    "verdict": event.get("message") or event.get("detail") or event.get("verdict"),
                }
            candidates.append(
                {
                    **base,
                    "module": "flow",
                    "prediction_error": pe,
                    "family": event.get("family"),
                    "tag_hint": "prediction_mismatch"
                    if kind != "prediction_held"
                    else "prediction_held",
                }
            )
        elif kind == "transition_attribution":
            candidates.append(
                {
                    **base,
                    "module": "meta_action",
                    "outcome": event.get("outcome"),
                    "effect_kind": event.get("effect_kind"),
                    "belief_authority": event.get("belief_authority"),
                    "tag_hint": "attribution",
                }
            )

    # Cap per run so a stuck log does not drown the candidate set.
    failures = [
        c
        for c in candidates
        if c.get("outcome") in {"regression", "no_effect", "uncertain", "fail"}
        or c.get("last_action_surprised")
        or c.get("meta_action") in {"verify", "think"}
        or c.get("kind")
        in {
            "stalled",
            "ax_settle_regression_diagnostic",
            "prediction_error",
            "execution_effect_missing",
            "act_intention",
        }
        or c.get("tag_hint") in {"prediction_mismatch", "act_intention"}
    ]
    others = [c for c in candidates if c not in failures]
    selected = (failures + others)[:40]
    return {
        "run": path.name,
        "event_counts": dict(counts),
        "candidates_total": len(candidates),
        "candidates_written": len(selected),
        "candidates": selected,
    }


def harvest_runs(
    runs_dir: str = DEFAULT_RUNS_DIR,
    out_dir: str = DEFAULT_OUT_DIR,
    *,
    limit: int = 8,
) -> Dict[str, Any]:
    paths = list_run_logs(runs_dir, limit=limit)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    reports: List[Dict[str, Any]] = []
    all_candidates: List[Dict[str, Any]] = []
    for path in paths:
        report = harvest_run(path)
        reports.append(
            {
                "run": report["run"],
                "event_counts": report["event_counts"],
                "candidates_written": report["candidates_written"],
            }
        )
        stamp = path.stem.replace("forward_zarooratwala_live_", "")[:32]
        dest = out / f"{stamp}.jsonl"
        with dest.open("w", encoding="utf-8") as fh:
            for cand in report["candidates"]:
                fh.write(json.dumps(cand, ensure_ascii=False) + "\n")
                all_candidates.append(cand)
    index = {
        "runs_scanned": len(paths),
        "runs": reports,
        "candidates_total": len(all_candidates),
        "out_dir": str(out),
        "note": "Candidates are not gold. Promote into corpus/vN after human labeling.",
    }
    (out / "_index.json").write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    return index


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Harvest golden annotation candidates from run JSONL")
    parser.add_argument("--runs", default=DEFAULT_RUNS_DIR)
    parser.add_argument("--out", default=DEFAULT_OUT_DIR)
    parser.add_argument("--limit", type=int, default=8)
    args = parser.parse_args(argv)
    index = harvest_runs(args.runs, args.out, limit=args.limit)
    print(
        f"harvested candidates from {index.get('runs_scanned')} runs → "
        f"{index.get('out_dir')} ({index.get('candidates_total')} lines)"
    )
    for row in index.get("runs") or []:
        print(f"  {row.get('run')}: wrote={row.get('candidates_written')} kinds={row.get('event_counts')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
