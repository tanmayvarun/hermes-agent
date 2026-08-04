"""Strategic search: which branch to try next, and in what order.

Information gathering is not only looking harder at the current screen. Once a
branch stops converging the useful question stops being "what is on this
surface" and becomes "which part of the action space should I be in at all" --
a question about branches, not pixels. This module is that arm of the
INFORMATION_GATHERING meta-action.

It consults the reasoning model for an ordered plan over the branches still
worth trying, so a retreat has a direction the agent reasoned its way to rather
than whichever untried family happened to sit nearest on the frontier. When the
model declines or is unreachable the frontier ordering still stands, so the
executive always gets a plan -- just a less considered one.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

# Families that are never a *branch*: looking again is the move the executive is
# retreating from, so proposing it as a new direction is a no-op.
_NON_BRANCH_FAMILIES = {"", "observe"}

MAX_PLAN_FAMILIES = 4


@dataclass
class BranchPlan:
    """An ordered plan over the branches worth trying next."""

    ordered_families: List[str] = field(default_factory=list)
    avoid_families: List[str] = field(default_factory=list)
    hypothesis: str = ""
    reason: str = ""
    confidence: float = 0.0
    # Where the ordering came from: the reasoning model, or the live frontier.
    source: str = "none"

    @property
    def head(self) -> str:
        """The branch to take now."""
        return self.ordered_families[0] if self.ordered_families else ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ordered_families": list(self.ordered_families),
            "avoid_families": list(self.avoid_families),
            "hypothesis": self.hypothesis,
            "reason": self.reason,
            "confidence": round(float(self.confidence), 3),
            "source": self.source,
        }


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _frontier_families(branch: Any) -> List[str]:
    """Branch families the live frontier still offers, untried first."""
    entries = list(getattr(branch, "frontier", None) or [])
    untried: List[str] = []
    tried: List[str] = []
    for entry in entries:
        family = _norm(getattr(entry, "action_family", ""))
        if family in _NON_BRANCH_FAMILIES:
            continue
        bucket = tried if bool(getattr(entry, "tried", False)) else untried
        if family not in bucket:
            bucket.append(family)
    return untried + [f for f in tried if f not in untried]


def _candidate_pool(branch: Any) -> List[Any]:
    """The frontier as Action candidates, which is what the selector reasons over."""
    from plugin.agent.action import Action

    pool: List[Any] = []
    seen = set()
    for entry in list(getattr(branch, "frontier", None) or []):
        family = _norm(getattr(entry, "action_family", ""))
        if family in _NON_BRANCH_FAMILIES:
            continue
        target = str(getattr(entry, "semantic_target", "") or "")
        key = (family, target)
        if key in seen:
            continue
        seen.add(key)
        pool.append(
            Action(
                action=family,
                action_family=family,
                semantic_target=target,
                text=str(getattr(entry, "text", "") or ""),
                rationale=str(getattr(entry, "hypothesis_label", "") or ""),
            )
        )
    return pool


def _order_from_strategy(strategy: Any, frontier: Sequence[str]) -> tuple[List[str], List[str]]:
    """Turn the model's strategy into an ordered, de-duplicated branch list."""
    avoid = [_norm(f) for f in (getattr(strategy, "avoid_families", None) or [])]
    avoid = [f for f in avoid if f]
    ordered: List[str] = []
    for family in (
        _norm(getattr(strategy, "preferred_family", "")),
        _norm(getattr(strategy, "backtrack_family", "")),
        *frontier,
    ):
        if family in _NON_BRANCH_FAMILIES or family in avoid or family in ordered:
            continue
        ordered.append(family)
    return ordered[:MAX_PLAN_FAMILIES], avoid


def plan_branches(
    goal: Any,
    world: Any,
    features: Any,
    execution_state: Any,
    *,
    caller: Optional[Callable[..., Any]] = None,
) -> BranchPlan:
    """Ask which branches are still worth trying, and in what order.

    The frontier ordering is the floor: it is always a usable plan. The model is
    asked to improve on it, because "the current direction has stopped paying,
    where else could the target be reached from" is a judgement about the task,
    not something the nearest-untried-family heuristic can make.
    """
    branch = getattr(execution_state, "exploration_branch", None)
    frontier = _frontier_families(branch)
    plan = BranchPlan(
        ordered_families=frontier[:MAX_PLAN_FAMILIES],
        reason="frontier ordering (untried branches first)",
        source="frontier" if frontier else "none",
    )

    pool = _candidate_pool(branch)
    if len(pool) < 2:
        # Nothing to choose between: an ordering question needs alternatives.
        return plan

    try:
        from plugin.agent.decision_selector import select_branch_strategy_with_llm

        strategy, trace = select_branch_strategy_with_llm(
            goal,
            world,
            features,
            pool,
            branch=branch.to_dict() if hasattr(branch, "to_dict") else None,
            caller=caller,
            task="branch_strategy",
        )
    except Exception as exc:
        logger.debug("strategic search unavailable: %s", exc)
        return plan

    if strategy is None:
        return plan

    ordered, avoid = _order_from_strategy(strategy, frontier)
    if not ordered:
        return plan

    plan.ordered_families = ordered
    plan.avoid_families = avoid
    plan.hypothesis = str(getattr(strategy, "branch_hypothesis", "") or "")
    plan.reason = str(getattr(strategy, "reason", "") or "") or "model-ordered branch plan"
    plan.confidence = float(getattr(strategy, "confidence", 0.0) or 0.0)
    plan.source = "llm"
    logger.info(
        "Strategic search plan: %s (avoid=%s, why=%s)",
        " -> ".join(plan.ordered_families),
        ",".join(plan.avoid_families) or "-",
        plan.reason[:120],
    )
    return plan
