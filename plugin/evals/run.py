"""Run the eval pyramid and print one report per layer.

    python -m plugin.evals.run                      # gates + corpus metrics
    python -m plugin.evals.run --closed-loop        # also read the run logs
    python -m plugin.evals.run --json out.json      # machine-readable report
    python -m plugin.evals.run --baseline prev.json # fail on drift

Layers stay separate on purpose. A single number would tell you something
broke; these tell you whether the system stopped *seeing*, stopped
*understanding what it could do*, or merely started *choosing badly* -- three
different bugs with three different fixes.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Sequence

from plugin.evals.annotations import annotate, annotation_coverage, load_overrides
from plugin.evals.closed_loop import analyse_runs, recent_runs, summarize
from plugin.evals.executive import analyse_executive_runs, summarize_executive
from plugin.evals.temporal import analyse_temporal_runs, summarize_temporal
from plugin.evals.corpus import DEFAULT_CORPUS_DIR, coverage_report, load_fixtures
from plugin.evals.gates import blocking_failures, compare_to_baseline, run_gates
from plugin.evals.metrics import MetricResult, evaluate_all
from plugin.evals.resolution import summarize_resolution
from plugin.evals.sufficiency import summarize_sufficiency

LAYER_ORDER = (
    "observation",
    "structure",
    "affordance",
    "latent_affordance",
    "relevance",
    "ranking",
    "uncertainty",
    "end_to_end",
    "error",
)

RUNS_DIR = "plugin/experiments/runs"


def build_report(
    corpus_dir: str = DEFAULT_CORPUS_DIR,
    *,
    closed_loop: bool = False,
    temporal: bool = False,
    executive: bool = False,
    runs_dir: str = RUNS_DIR,
    run_limit: int = 12,
) -> Dict[str, Any]:
    fixtures = load_fixtures(corpus_dir)
    # Re-derive annotations at read time so a change to the ground-truth
    # contract takes effect without re-harvesting, and so a stale label in a
    # committed fixture cannot quietly outlive the rule that produced it.
    if fixtures:
        fixtures = annotate(fixtures, overrides=load_overrides())
    metrics: List[MetricResult] = evaluate_all(fixtures) if fixtures else []
    gates = run_gates()
    report: Dict[str, Any] = {
        "corpus": coverage_report(fixtures),
        "annotations": annotation_coverage(fixtures),
        "gates": [g.to_dict() for g in gates],
        "gate_failures": [g.to_dict() for g in blocking_failures(gates)],
        "metrics": [m.to_dict() for m in metrics],
        # Component correctness of the executive brain's core computation. It is
        # deterministic and needs no run logs, so it is always in the report.
        "sufficiency": summarize_sufficiency(),
        # Brain-gated entity resolution, graded across domains (chat/files/tabs)
        # to prove the gate is semantic-general, not WhatsApp string rules.
        "resolution": summarize_resolution(),
    }
    if closed_loop:
        outcomes = analyse_runs(recent_runs(runs_dir, run_limit))
        report["closed_loop"] = summarize(outcomes)
        report["closed_loop"]["runs_detail"] = [o.to_dict() for o in outcomes]
    if temporal:
        traces = analyse_temporal_runs(recent_runs(runs_dir, run_limit))
        report["temporal"] = summarize_temporal(traces)
    if executive:
        traces = analyse_executive_runs(recent_runs(runs_dir, run_limit))
        report["executive"] = summarize_executive(traces)
    return report


def render(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    corpus = report.get("corpus") or {}
    lines.append(
        f"corpus: {corpus.get('count', 0)} fixtures  "
        f"phases={corpus.get('phases')}  with_screenshot={corpus.get('with_screenshot')}"
    )
    if corpus.get("missing_failure_traits"):
        lines.append(f"  gap: no fixture covers {corpus['missing_failure_traits']}")
    rates = (report.get("annotations") or {}).get("rates") or {}
    if rates:
        lines.append(f"  ground truth coverage: {rates}")

    lines.append("")
    failures = report.get("gate_failures") or []
    lines.append(f"regression gates: {len(report.get('gates') or []) - len(failures)}/{len(report.get('gates') or [])} pass")
    for gate in failures:
        lines.append(f"  FAIL {gate['name']}: {gate['detail']}")

    suff = report.get("sufficiency") or {}
    if suff:
        lines.append("")
        lines.append("[decision_sufficiency]")
        lines.append(
            f"  cases={suff.get('cases')} verdict_accuracy={suff.get('verdict_accuracy')} "
            f"false_act_rate={suff.get('false_act_rate')} missed_act_rate={suff.get('missed_act_rate')} "
            f"confidence_separation={suff.get('confidence_separation')}"
        )
        for example in (suff.get("failures") or [])[:3]:
            lines.append(f"      FAIL {example}")

    res = report.get("resolution") or {}
    if res:
        lines.append("")
        lines.append("[entity_resolution]")
        lines.append(
            f"  cases={res.get('cases')} domains={res.get('domains')} accuracy={res.get('accuracy')} "
            f"fast_path_tp_rate={res.get('fast_path_true_positive_rate')} "
            f"escalation_recall={res.get('escalation_recall')} "
            f"false_fast_path_rate={res.get('false_fast_path_rate')}"
        )
        for example in (res.get("failures") or [])[:3]:
            lines.append(f"      FAIL {example}")

    by_layer: Dict[str, List[Dict[str, Any]]] = {}
    for metric in report.get("metrics") or []:
        by_layer.setdefault(metric["layer"], []).append(metric)
    for layer in LAYER_ORDER:
        entries = by_layer.get(layer)
        if not entries:
            continue
        lines.append("")
        lines.append(f"[{layer}]")
        for metric in entries:
            value = metric["value"]
            shown = "n/a" if value is None else f"{value:.3f}"
            arrow = "" if metric["higher_is_better"] else " (lower is better)"
            lines.append(
                f"  {metric['name']:<34} {shown:>6}{arrow}   "
                f"scored={metric['scored']} skipped={metric['skipped']}"
            )
            if metric["examples"]:
                lines.append(f"      e.g. {metric['examples'][0]}")

    closed = report.get("closed_loop")
    if closed:
        lines.append("")
        lines.append("[end_to_end]")
        lines.append(
            f"  runs={closed.get('runs')} completion={closed.get('completion_rate')} "
            f"false_success={closed.get('false_success_rate')} median_steps={closed.get('median_steps')}"
        )
        for stage, rate in (closed.get("stage_reach_rate") or {}).items():
            lines.append(f"    {stage:<30} {rate}")

    temporal = report.get("temporal")
    if temporal and temporal.get("runs"):
        lines.append("")
        lines.append("[temporal_consistency]")
        lines.append(f"  runs={temporal.get('runs')}")
        for name in (
            "belief_flip_rate",
            "surface_stability",
            "object_identity_continuity",
            "unjustified_phase_regression_rate",
        ):
            lines.append(f"    {name:<38} {temporal.get(name)}")

    executive = report.get("executive")
    if executive and executive.get("runs"):
        lines.append("")
        lines.append("[executive_calibration]")
        lines.append(f"  runs={executive.get('runs')} judgements={executive.get('judgements')}")
        for name in (
            "sufficiency_precision",
            "act_success_rate",
            "meta_action_appropriateness",
            "skip_safety",
        ):
            lines.append(f"    {name:<38} {executive.get(name)}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the perception eval pyramid")
    parser.add_argument("--corpus", default=DEFAULT_CORPUS_DIR)
    parser.add_argument("--closed-loop", action="store_true", help="also analyse recent run logs")
    parser.add_argument("--temporal", action="store_true", help="also measure temporal consistency of recent runs")
    parser.add_argument("--executive", action="store_true", help="also measure executive judgement calibration of recent runs")
    parser.add_argument("--runs", default=RUNS_DIR)
    parser.add_argument("--run-limit", type=int, default=12)
    parser.add_argument("--json", default="", help="write the full report here")
    parser.add_argument("--baseline", default="", help="compare against a previous report and fail on drift")
    parser.add_argument("--strict", action="store_true", help="exit non-zero on any gate failure")
    args = parser.parse_args(argv)

    report = build_report(
        args.corpus,
        closed_loop=args.closed_loop,
        temporal=args.temporal,
        executive=args.executive,
        runs_dir=args.runs,
        run_limit=args.run_limit,
    )
    print(render(report))

    breaches: List[Dict[str, Any]] = []
    if args.baseline:
        try:
            baseline = json.loads(Path(args.baseline).read_text())
        except (OSError, ValueError) as exc:
            print(f"\nbaseline unreadable: {exc}")
            baseline = {}
        if baseline:
            breaches = compare_to_baseline(report, baseline)
            report["baseline_breaches"] = breaches
            if breaches:
                print("\nregressions against baseline:")
                for breach in breaches:
                    print(
                        f"  {breach['metric']}: {breach['before']} -> {breach['after']} "
                        f"(delta {breach['delta']}, limit {breach['limit']})"
                    )
            else:
                print("\nno metric moved further than its gate allows")

    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(report, indent=2) + "\n")
        print(f"\nreport written to {args.json}")

    failed = bool(report.get("gate_failures")) or bool(breaches)
    return 1 if (failed and (args.strict or breaches)) else 0


if __name__ == "__main__":
    raise SystemExit(main())
