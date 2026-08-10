"""Hard preflight: goldens + regression gates + focused pytest (mvn-test equivalent).

Run before every live forward / after every agent change. Exit non-zero on any
blocking failure. Known-gap case ids in the golden manifest are reported but
do not fail the check.

Usage:
    python -m plugin.evals.check              # full package check
    python -m plugin.evals.check --quick      # goldens + gates only (no pytest)

There is no skip env — a failing check always blocks live agent startup.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Sequence


REPO = Path(__file__).resolve().parents[2]

# Process-wide: live agent startup runs the check once, then serves the prompt.
_EVAL_CHECK_PASSED_THIS_PROCESS = False


def _live_goal_requested() -> bool:
    raw = str(os.getenv("HERMES_LIVE_GOAL", "") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def mark_live_goal_process() -> None:
    """Tag this process as a live goal run (agent startup).

    Live experiment entrypoints call this before ``run_goal_closed_loop``.
    The closed loop then refuses to start unless ``require_eval_check_or_exit``
    has already succeeded (same process).
    """
    os.environ["HERMES_LIVE_GOAL"] = "1"


def require_eval_check_or_exit(
    *,
    quick: bool = False,
    force: bool = False,
    reason: str = "live agent startup",
) -> None:
    """Block agent startup when any golden/gate/pytest fails.

    Analogy: API handler must not run until the server finished a green boot.
    Every live prompt re-run goes through agent startup; agent startup goes
    through this check. No skip env — red evals always refuse startup.

    Launchers may run ``python -m plugin.evals.check`` then export
    ``HERMES_EVAL_PREFLIGHT_DONE=1`` so the in-process startup check is a no-op
    after a green launcher preflight.
    """
    global _EVAL_CHECK_PASSED_THIS_PROCESS
    if _EVAL_CHECK_PASSED_THIS_PROCESS and not force:
        return
    preflight_done = str(os.getenv("HERMES_EVAL_PREFLIGHT_DONE", "") or "").strip().lower()
    if preflight_done in {"1", "true", "yes", "on"} and not force:
        print(f"== eval preflight already green (launcher); starting {reason}", flush=True)
        _EVAL_CHECK_PASSED_THIS_PROCESS = True
        return
    print(f"== eval preflight before {reason}", flush=True)
    rc = run_check(quick=quick)
    if rc != 0:
        print(
            f"\nREFUSING {reason}: package eval check failed (exit={rc}). "
            "Fix goldens/gates/tests, then relaunch.",
            flush=True,
        )
        raise SystemExit(rc)
    _EVAL_CHECK_PASSED_THIS_PROCESS = True
    os.environ["HERMES_EVAL_PREFLIGHT_DONE"] = "1"


def require_live_eval_preflight() -> None:
    """Called from ``run_goal_closed_loop`` when ``HERMES_LIVE_GOAL`` is set."""
    if not _live_goal_requested():
        return
    require_eval_check_or_exit(reason="live closed-loop agent startup")


def _blocking_golden_failures() -> List[str]:
    from plugin.evals.gates import _golden_known_gap_ids
    from plugin.evals.golden.score import score_all

    report = score_all()
    gaps = _golden_known_gap_ids()
    fails: List[str] = []
    for module, block in (report.get("modules") or {}).items():
        for f in block.get("failures") or []:
            cid = str(f.get("case_id") or "")
            if cid in gaps:
                continue
            checks = [
                c.get("name")
                for c in (f.get("checks") or [])
                if isinstance(c, dict) and not c.get("passed")
            ][:4]
            fails.append(f"{module}:{cid}:{checks}")
    return fails


def _blocking_gate_failures() -> List[str]:
    from plugin.evals.gates import blocking_failures, run_gates

    return [f"{g.name}: {g.detail}" for g in blocking_failures(run_gates())]


def _run_pytest(quick: bool) -> int:
    if quick:
        return 0
    py = REPO / ".venv" / "bin" / "pytest"
    if not py.is_file():
        py = Path(sys.executable)
        cmd = [str(py), "-m", "pytest"]
    else:
        cmd = [str(py)]
    targets = [
        "tests/plugin/test_golden_corpus.py",
        "tests/plugin/test_act_intention_surprise.py",
        "tests/plugin/test_one_executive_loop.py",
        "tests/plugin/test_decision_consultation.py",
        "tests/plugin/test_model_choice_is_honoured.py::test_prefer_url_ignores_plain_text_matches_goal",
        "tests/plugin/test_compose_search_query.py::test_goal_evidence_tokens_are_a_bag_not_a_joined_query",
        "tests/plugin/test_consultation_routing.py",
        "tests/plugin/test_action_area.py",
        "tests/plugin/test_live_eval_preflight.py",
        "tests/plugin/test_evals.py::test_every_known_failure_is_still_fixed",
        "tests/plugin/test_overlay_capture.py",
        "tests/plugin/test_reveal_affordance_thoroughness.py",
        "tests/plugin/test_post_accept_affordance_promote.py",
        "tests/plugin/test_critic_layer_push_pop.py",
        "tests/plugin/test_affordance_explore.py",
        "tests/plugin/test_layered_perception.py",
        "tests/plugin/test_revert_effects.py",
        "tests/plugin/test_reflect_diagnosis.py",
        "tests/plugin/test_recoverability_substrate.py",
        "tests/plugin/test_effect_judgment_and_referent.py",
        "tests/plugin/test_search_episode.py",
        "tests/plugin/test_meta_search.py",
        "tests/plugin/test_design_flaw_fixes.py::test_prediction_error_does_not_rearm_after_reflect_consume",
    ]
    cmd.extend(["-q", "--tb=line", *targets])
    print(f"\n== pytest {' '.join(targets)}", flush=True)
    return int(subprocess.call(cmd, cwd=str(REPO)))


def run_check(*, quick: bool = False) -> int:
    global _EVAL_CHECK_PASSED_THIS_PROCESS
    print("== plugin.evals.check (package preflight)", flush=True)
    from plugin.evals.golden.score import render, score_all

    report = score_all()
    print(render(report), flush=True)

    golden_fails = _blocking_golden_failures()
    gate_fails = _blocking_gate_failures()

    if golden_fails:
        print("\nBLOCKING golden failures:", flush=True)
        for line in golden_fails:
            print(f"  FAIL {line}", flush=True)
    else:
        print("\ngoldens: all non-gap cases pass", flush=True)

    if gate_fails:
        print("\nBLOCKING regression gates:", flush=True)
        for line in gate_fails:
            print(f"  FAIL {line}", flush=True)
    else:
        print("regression gates: all pass", flush=True)

    pytest_rc = _run_pytest(quick)
    if pytest_rc != 0:
        print(f"\nBLOCKING pytest exit={pytest_rc}", flush=True)

    if golden_fails or gate_fails or pytest_rc != 0:
        print(
            "\npackage check FAILED — fix goldens/gates before live run",
            flush=True,
        )
        _EVAL_CHECK_PASSED_THIS_PROCESS = False
        return 1
    print("\npackage check OK", flush=True)
    _EVAL_CHECK_PASSED_THIS_PROCESS = True
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--quick",
        action="store_true",
        help="Goldens + gates only (skip focused pytest)",
    )
    args = ap.parse_args(argv)
    return run_check(quick=bool(args.quick))


if __name__ == "__main__":
    raise SystemExit(main())
