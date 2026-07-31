"""Collect action-prior hints from model adapters."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from plugin.agent.action import Action
from plugin.agent.features import StateFeatures
from plugin.agent.goal import Goal
from plugin.worldmodel.model import WorldModel

from .base import ActionModelRun, ActionProposal
from .engines import ActionPriorAdapter
from .registry import list_action_models
from .selector import get_action_model_selector


def _candidate_signature(action: Action) -> tuple[str, str, str]:
    return (
        str(action.action_family or action.action).strip().lower(),
        str(action.semantic_target or "").strip().lower(),
        str(action.capability_type or "").strip().lower(),
    )


def action_prior_bonus(candidate: Action, runs: Sequence[ActionModelRun]) -> float:
    """Return a small reusable evidence bonus from action-prior proposals."""
    if not runs:
        return 0.0
    fam, target, cap_type = _candidate_signature(candidate)
    bonus = 0.0
    for run in runs:
        for proposal in run.proposals[:4]:
            p_fam = str(proposal.action_family or "").strip().lower()
            p_target = str(proposal.semantic_target or "").strip().lower()
            if p_fam and p_fam == fam:
                bonus += min(0.15, float(proposal.confidence or 0.0) * 0.08)
            if p_target and target and p_target == target:
                bonus += min(0.15, float(proposal.confidence or 0.0) * 0.10)
            if cap_type and proposal.meta.get("capability_type") and str(proposal.meta.get("capability_type") or "").strip().lower() == cap_type:
                bonus += min(0.12, float(proposal.confidence or 0.0) * 0.06)
            if proposal.reversible is False and candidate.reversible is False:
                bonus += min(0.05, float(proposal.confidence or 0.0) * 0.02)
    return round(min(0.35, bonus), 4)


def collect_action_prior_runs(
    goal: Goal,
    world: WorldModel,
    features: StateFeatures,
    candidates: Sequence[Action],
    *,
    models: Optional[Sequence[Any]] = None,
    selector=None,
) -> List[ActionModelRun]:
    """Run the registered action-prior models in ranked order."""
    sel = selector or get_action_model_selector()
    available = list(models or [])
    if not available:
        available = list_action_models()
    if not available:
        return []
    case = f"{goal.app or world.active_app or ''} {goal.kind or ''}".strip()
    ranked = sel.rank(available, use_case=case)
    runs: List[ActionModelRun] = []
    for model in ranked[:2]:
        try:
            run = model.propose(goal=goal, world=world, features=features, candidates=candidates, use_case=case)
        except Exception as e:
            run = ActionModelRun(
                model_id=getattr(model, "model_id", "action_model"),
                use_case=case,
                proposals=[],
                meta={"error": str(e)},
                degraded=True,
            )
        sel.record(case, run)
        runs.append(run)
        if run.success() and run.score() >= sel.min_accept_score:
            break
    return runs


def maybe_collect_action_prior_runs(
    goal: Goal,
    world: WorldModel,
    features: StateFeatures,
    candidates: Sequence[Action],
    *,
    models: Optional[Sequence[Any]] = None,
    selector=None,
) -> List[ActionModelRun]:
    """Compatibility alias for the decision engine."""
    return collect_action_prior_runs(goal, world, features, candidates, models=models, selector=selector)
