"""Affordance exploration evals grounded in the Zarooratwala forward task.

Real corpus fixtures (find_link / open_forward / select_destination) carry the
goal ``find zarooratwala … forward to …`` and gold latent labels (Forward on
conversation; Send on forward_picker). These metrics ask:

1. Stage0 / node closure: are same-node hidden & latent affordances present?
2. Stage1 QC: does the reading admit when expected affordances are still missing?
3. Brain resilience: when the frontier is barren, does the chooser ask to
   reperceive instead of forcing a bad transition?

Usage:
    python -m plugin.evals.affordance_exploration
    python -m plugin.evals.run   # includes [affordance_exploration] block
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from plugin.evals.annotations import SURFACE_CONTRACT, annotate, load_overrides
from plugin.evals.corpus import DEFAULT_CORPUS_DIR, Fixture, load_fixtures
from plugin.evals.metrics import MetricResult

LAYER = "affordance_exploration"


def _norm(text: Any) -> str:
    return str(text or "").strip().lower()


def _rate(hits: float, total: float) -> Optional[float]:
    return None if total <= 0 else hits / total


# ---------------------------------------------------------------------------
# Gold scenarios from the zarooratwala forward flow (real corpus phases)
# ---------------------------------------------------------------------------

# Expected same-node latent / hidden labels by surface for this goal.
ZAROORATWALA_NODE_EXPECTATIONS: Dict[str, Dict[str, Any]] = {
    "conversation": {
        "latent": ("Forward", "Reply", "Copy"),
        "critical_probe_family": "reveal_actions",
        "phase_hint": ("find_link", "open_forward"),
        "why": "message actions are hidden until context-click / reveal on the bubble",
    },
    "context_menu": {
        "observed": ("Forward",),
        "latent": (),
        "phase_hint": ("open_forward",),
        "why": "Forward is visible on the open message menu — same node, now observed",
    },
    "forward_picker": {
        "latent": ("Send",),
        "critical_probe_family": "",
        "phase_hint": ("select_destination",),
        "why": "Send is the irreversible control latent on the picker until commit",
    },
}


@dataclass
class ScenarioScore:
    fixture_id: str
    surface: str
    checks: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def score(self) -> float:
        if not self.checks:
            return 0.0
        return round(sum(1 for c in self.checks if c.get("passed")) / len(self.checks), 4)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "surface": self.surface,
            "score": self.score,
            "checks": self.checks,
            "failures": [c["name"] for c in self.checks if not c.get("passed")],
        }


def _gold_surface(fixture: Fixture) -> str:
    return _norm((fixture.annotation or {}).get("surface"))


def _gold_latents(fixture: Fixture) -> List[str]:
    ann = fixture.annotation or {}
    surface = _gold_surface(fixture)
    # Prefer annotation (contract / override), fall back to zarooratwala table.
    labels = list(ann.get("latent_affordances") or [])
    if not labels and surface in ZAROORATWALA_NODE_EXPECTATIONS:
        labels = list(ZAROORATWALA_NODE_EXPECTATIONS[surface].get("latent") or ())
    return [str(x) for x in labels if str(x).strip()]


def _is_zarooratwala(fixture: Fixture) -> bool:
    goal = fixture.goal
    blob = " ".join(
        str(goal.get(k) or "")
        for k in ("source_query", "link_query", "description", "source_conversation", "destination")
    ).lower()
    return "zarooratwala" in blob or "pallavi" in blob and "tanmay" in blob


def _frontier_for(fixture: Fixture):
    from plugin.agent.affordance_frontier import build_affordance_frontier

    surface = _gold_surface(fixture) or _norm(
        (fixture.prior_document or {}).get("surface") or model_surface_safe(fixture)
    )
    objects = list(fixture.objects or fixture.prior_document.get("objects") or [])
    if not objects:
        # Stage0 uses prior world objects; fall back to packet world_model.
        objects = [
            o
            for o in ((fixture.packet or {}).get("world_model") or {}).get("objects") or []
            if isinstance(o, dict)
        ]
    return build_affordance_frontier(
        surface=surface,
        goal_kind=str(fixture.goal.get("operation") or fixture.goal.get("kind") or ""),
        ax_evidence=list(fixture.ax_evidence or []),
        objects=objects,
        overlay=None,
        memory=None,
    )


def model_surface_safe(fixture: Fixture) -> str:
    from plugin.evals.corpus import model_surface

    return model_surface(fixture) or ""


def _latent_labels(frontier) -> set:
    got = {_norm(a.target_label) for a in frontier.latent_actions}
    got |= {_norm(m.label) for p in frontier.probe_actions for m in (p.may_reveal or [])}
    return {g for g in got if g}


def _observed_labels(frontier) -> set:
    return {_norm(a.target_label) for a in frontier.observed_actions if _norm(a.target_label)}


def score_fixture_closure(fixture: Fixture) -> Optional[ScenarioScore]:
    """Did stage0/passive frontier expose zarooratwala same-node latents?"""
    if not _is_zarooratwala(fixture):
        return None
    surface = _gold_surface(fixture)
    if surface not in ZAROORATWALA_NODE_EXPECTATIONS:
        return None
    expect = ZAROORATWALA_NODE_EXPECTATIONS[surface]
    score = ScenarioScore(fixture_id=fixture.id, surface=surface)
    frontier = _frontier_for(fixture)
    latent_got = _latent_labels(frontier)
    observed_got = _observed_labels(frontier)

    wanted_latent = {_norm(x) for x in (expect.get("latent") or ())}
    wanted_observed = {_norm(x) for x in (expect.get("observed") or ())}

    if wanted_latent:
        hit = wanted_latent & latent_got
        score.checks.append(
            {
                "name": "latent_same_node_present",
                "passed": bool(hit == wanted_latent) or bool(hit),
                "detail": f"wanted={sorted(wanted_latent)} got={sorted(latent_got)}",
            }
        )
        # Soft: at least the task-critical Forward/Send
        critical = wanted_latent & {"forward", "send"}
        score.checks.append(
            {
                "name": "task_critical_latent_present",
                "passed": bool(critical <= latent_got) if critical else True,
                "detail": f"critical={sorted(critical)} got={sorted(latent_got)}",
            }
        )

    if wanted_observed:
        score.checks.append(
            {
                "name": "revealed_control_is_observed",
                "passed": bool(wanted_observed <= observed_got),
                "detail": f"wanted={sorted(wanted_observed)} got={sorted(observed_got)}",
            }
        )
        # Must not still list Forward only as latent when menu is open
        score.checks.append(
            {
                "name": "revealed_not_only_latent",
                "passed": not bool(wanted_observed & latent_got - observed_got),
                "detail": "observed menu items must not remain latent-only",
            }
        )

    if surface == "conversation":
        # Forward must not be invented as observed without a menu.
        score.checks.append(
            {
                "name": "forward_not_falsely_observed",
                "passed": "forward" not in observed_got,
                "detail": f"observed={sorted(observed_got)}",
            }
        )
        probe_fam = str(expect.get("critical_probe_family") or "")
        if probe_fam:
            probe_families = {str(p.family or "").lower() for p in frontier.probe_actions}
            probe_families |= {
                str(a.family or "").lower()
                for a in frontier.latent_actions
                if a.trigger_action
            }
            # Also accept reveal_actions / context-style families on objects
            has_reveal = any(
                "reveal" in str(a.family or "").lower()
                or "context" in str(getattr(a, "trigger_action", "") or "").lower()
                or str(a.family or "").lower() == probe_fam
                for a in list(frontier.probe_actions) + list(frontier.latent_actions)
            )
            score.checks.append(
                {
                    "name": "reveal_probe_available",
                    "passed": has_reveal or bool(latent_got & {"forward"}),
                    "detail": f"probe_families≈{sorted(probe_families)[:6]}",
                }
            )

    return score


def score_closure_after_enrich(fixture: Fixture) -> Optional[ScenarioScore]:
    """Run soft node closure and re-check critical latents are still represented."""
    if not _is_zarooratwala(fixture):
        return None
    surface = _gold_surface(fixture)
    if surface not in ZAROORATWALA_NODE_EXPECTATIONS:
        return None
    from plugin.agent.affordance_explore import close_current_node_frontier
    from plugin.agent.unified_cognition import UnifiedProposal

    frontier = _frontier_for(fixture)
    proposal = UnifiedProposal(
        world_model=dict(fixture.document or fixture.prior_document or {}),
        missing_affordance_information=list(
            (fixture.response or {}).get("missing_affordance_information") or []
        ),
        recommended_probe=dict((fixture.response or {}).get("recommended_probe") or {}),
        suggested_actions=list(
            (fixture.response or {}).get("suggested_actions")
            or (fixture.response or {}).get("next_actions")
            or []
        ),
    )
    report = close_current_node_frontier(
        accepted_world=dict(fixture.document or fixture.prior_document or {}),
        passive_frontier=frontier.to_packet(),
        proposal=proposal,
        execution_state=None,
    )
    closed = report.get("frontier") or {}
    labels = set()
    for key in ("latent_actions", "probe_actions", "observed_actions"):
        for a in closed.get(key) or []:
            if not isinstance(a, dict):
                continue
            labels.add(_norm(a.get("target_label") or a.get("label")))
            for m in a.get("may_reveal") or []:
                if isinstance(m, dict):
                    labels.add(_norm(m.get("label")))
                else:
                    labels.add(_norm(m))
    expect = ZAROORATWALA_NODE_EXPECTATIONS[surface]
    wanted = {_norm(x) for x in list(expect.get("latent") or ()) + list(expect.get("observed") or ())}
    critical = wanted & {"forward", "send"}
    score = ScenarioScore(fixture_id=fixture.id, surface=surface)
    score.checks.append(
        {
            "name": "closure_keeps_critical_labels",
            "passed": bool(critical <= labels) if critical else True,
            "detail": f"critical={sorted(critical)} closed_labels≈{sorted(g for g in labels if g)[:8]}",
        }
    )
    score.checks.append(
        {
            "name": "closure_tags_node_scope",
            "passed": any(
                isinstance(a, dict) and a.get("node_scope")
                for key in ("observed_actions", "latent_actions", "probe_actions")
                for a in (closed.get(key) or [])
            ),
            "detail": "node_scope present on closed frontier entries",
        }
    )
    return score


def score_stage1_affordance_qc(fixture: Fixture) -> Optional[ScenarioScore]:
    """When gold latents exist, stage1 should either see them or flag QC miss."""
    if not _is_zarooratwala(fixture) or not fixture.response:
        return None
    surface = _gold_surface(fixture)
    latents = {_norm(x) for x in _gold_latents(fixture)}
    if not latents or surface not in ZAROORATWALA_NODE_EXPECTATIONS:
        return None
    response = fixture.response or {}
    qc = response.get("affordance_qc") if isinstance(response.get("affordance_qc"), dict) else {}
    missing_info = " ".join(
        str(x) for x in (response.get("missing_affordance_information") or [])
    ).lower()
    frontier = _frontier_for(fixture)
    latent_got = _latent_labels(frontier)
    has_critical = bool((latents & {"forward", "send"}) <= latent_got) if (
        latents & {"forward", "send"}
    ) else bool(latents & latent_got)

    score = ScenarioScore(fixture_id=fixture.id, surface=surface)
    # Pass if passive frontier already has them OR stage1 QC admits the gap.
    qc_miss = (
        qc.get("expected_found") is False
        or bool(qc.get("missing"))
        or any(tok in missing_info for tok in ("forward", "send", "latent", "menu", "reveal"))
    )
    score.checks.append(
        {
            "name": "affordance_present_or_qc_flags_gap",
            "passed": has_critical or qc_miss,
            "detail": (
                f"has_critical={has_critical} qc={qc or 'none'} "
                f"missing_info={missing_info[:80]!r}"
            ),
        }
    )
    return score


def score_brain_reperceive_resilience() -> MetricResult:
    """Synthetic zarooratwala briefs: barren frontier → observe/reperceive."""
    from plugin.agent.decision_consultation import (
        DecisionBrief,
        NavigationInfo,
        TaskState,
    )
    from plugin.agent.brain import barren_frontier_reperceive

    cases = [
        # Conversation with target message but no Forward latent — must reperceive.
        DecisionBrief(
            goal={
                "source_conversation": "Pallavi",
                "source_query": "zarooratwala",
                "destination": "Tanmay",
            },
            world={
                "surface": "conversation",
                "open_conversation": "Pallavi",
                "objects": [
                    {
                        "id": "m1",
                        "kind": "link",
                        "text": "zarooratwala.com link",
                        "matches_goal": True,
                    }
                ],
            },
            task_state=TaskState(
                phase="act_on_content",
                open_conversation="Pallavi",
                source_chat_open=True,
                content_visible=True,
            ),
            navigation=NavigationInfo(surface="conversation", forbidden=()),
            capabilities=["reveal_actions", "select_content", "locate_content", "observe"],
            affordance_frontier={
                "surface": "conversation",
                "observed_actions": [{"family": "scroll", "label": "timeline"}],
                "latent_actions": [],
                "probe_actions": [],
            },
        ),
        # Healthy frontier with Forward latent — must NOT force observe.
        DecisionBrief(
            goal={
                "source_conversation": "Pallavi",
                "source_query": "zarooratwala",
                "destination": "Tanmay",
            },
            world={
                "surface": "conversation",
                "open_conversation": "Pallavi",
                "objects": [
                    {
                        "id": "m1",
                        "kind": "link",
                        "text": "zarooratwala.com link",
                        "matches_goal": True,
                    }
                ],
            },
            task_state=TaskState(
                phase="act_on_content",
                open_conversation="Pallavi",
                source_chat_open=True,
                content_visible=True,
            ),
            navigation=NavigationInfo(surface="conversation", forbidden=()),
            capabilities=["reveal_actions", "select_content", "observe"],
            affordance_frontier={
                "surface": "conversation",
                "observed_actions": [{"family": "select_content", "label": "msg"}],
                "latent_actions": [
                    {
                        "family": "invoke_affordance",
                        "label": "Forward",
                        "node_scope": "current",
                    }
                ],
                "probe_actions": [{"family": "reveal_actions", "label": "message"}],
            },
        ),
    ]
    hits = 0
    scored = 0
    examples: List[str] = []
    for i, brief in enumerate(cases):
        scored += 1
        barren, reason = barren_frontier_reperceive(brief)
        # LLM-only consultation: barren detection is the brain signal to look again
        # (apply_decision_consultation forces observe over a barren frontier).
        if i == 0:
            ok = barren
            if not ok:
                examples.append(f"barren case: barren={barren} why={reason!r}")
        else:
            ok = not barren
            if not ok:
                examples.append(f"healthy case: barren={barren} why={reason!r}")
        if ok:
            hits += 1
    return MetricResult(
        name="brain_reperceive_when_frontier_barren",
        layer=LAYER,
        value=_rate(hits, scored),
        scored=scored,
        skipped=0,
        question="When zarooratwala affordances are missing, does the brain ask to reperceive?",
        examples=examples,
    )


def zarooratwala_latent_recall(fixtures: Sequence[Fixture]) -> MetricResult:
    hits = 0
    scored = 0
    skipped = 0
    misses: List[str] = []
    for fixture in fixtures:
        result = score_fixture_closure(fixture)
        if result is None:
            skipped += 1
            continue
        scored += 1
        critical = next(
            (c for c in result.checks if c["name"] == "task_critical_latent_present"),
            None,
        )
        if critical and critical["passed"]:
            hits += 1
        elif len(misses) < 12:
            misses.append(f"{fixture.id}: {critical and critical.get('detail')}")
    return MetricResult(
        name="zarooratwala_critical_latent_recall",
        layer=LAYER,
        value=_rate(hits, scored),
        scored=scored,
        skipped=skipped,
        question="On zarooratwala frames, is Forward/Send present as same-node latent?",
        examples=misses,
    )


def zarooratwala_closure_score(fixtures: Sequence[Fixture]) -> MetricResult:
    scores: List[float] = []
    skipped = 0
    worst: List[str] = []
    for fixture in fixtures:
        result = score_closure_after_enrich(fixture)
        if result is None:
            skipped += 1
            continue
        scores.append(result.score)
        if result.score < 1.0 and len(worst) < 8:
            worst.append(f"{fixture.id}: {result.score} {result.to_dict()['failures']}")
    return MetricResult(
        name="zarooratwala_node_closure_score",
        layer=LAYER,
        value=(sum(scores) / len(scores)) if scores else None,
        scored=len(scores),
        skipped=skipped,
        question="After soft node closure, do critical labels + node_scope survive?",
        examples=worst,
    )


def zarooratwala_stage1_qc(fixtures: Sequence[Fixture]) -> MetricResult:
    hits = 0
    scored = 0
    skipped = 0
    bad: List[str] = []
    for fixture in fixtures:
        result = score_stage1_affordance_qc(fixture)
        if result is None:
            skipped += 1
            continue
        scored += 1
        if result.score >= 1.0:
            hits += 1
        elif len(bad) < 10:
            bad.append(f"{fixture.id}: {result.checks[0].get('detail')}")
    return MetricResult(
        name="zarooratwala_stage1_affordance_qc",
        layer=LAYER,
        value=_rate(hits, scored),
        scored=scored,
        skipped=skipped,
        question="Does stage1 present critical affordances or flag the QC gap?",
        examples=bad,
    )


def summarize_affordance_exploration(fixtures: Sequence[Fixture]) -> Dict[str, Any]:
    metrics = [
        zarooratwala_latent_recall(fixtures),
        zarooratwala_closure_score(fixtures),
        zarooratwala_stage1_qc(fixtures),
        score_brain_reperceive_resilience(),
    ]
    per: List[Dict[str, Any]] = []
    for fixture in fixtures:
        s = score_fixture_closure(fixture)
        if s is not None:
            per.append(s.to_dict())
    mean = (
        round(sum(p["score"] for p in per) / len(per), 4) if per else None
    )
    return {
        "goal": "zarooratwala_forward",
        "fixtures_scored": len(per),
        "mean_closure_score": mean,
        "metrics": [m.to_dict() for m in metrics],
        "expectations": ZAROORATWALA_NODE_EXPECTATIONS,
        "worst": sorted(per, key=lambda p: p["score"])[:8],
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", default=DEFAULT_CORPUS_DIR)
    parser.add_argument("--json", default="")
    args = parser.parse_args(list(argv) if argv is not None else None)
    fixtures = annotate(load_fixtures(args.corpus), overrides=load_overrides())
    report = summarize_affordance_exploration(fixtures)
    print(
        f"Affordance exploration (zarooratwala) — "
        f"{report.get('fixtures_scored', 0)} fixtures  "
        f"mean={report.get('mean_closure_score')}"
    )
    for metric in report.get("metrics") or []:
        value = metric.get("value")
        print(
            f"  {str(metric.get('name') or ''):<42} "
            f"{(f'{value:.2%}' if isinstance(value, float) else 'n/a'):>8}  "
            f"scored={metric.get('scored', 0)}"
        )
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=2) + "\n")
        print(f"\nreport written to {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
