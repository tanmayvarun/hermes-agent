"""Generic next-step frontier labeling for semantic ranking and backtracking."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List

from plugin.agent.action import Action
from plugin.agent.features import StateFeatures
from plugin.agent.goal import Goal
from plugin.agent.transition.types import FrontierAction


def action_hypothesis_label(goal: Goal, features: StateFeatures, action: Action) -> str:
    """Return a coarse semantic hypothesis label for a grounded action.

    The label is intentionally generic: it describes the *kind of next step*
    rather than the UI control itself, so the selector can rank plausible
    branches instead of memorizing app-specific buttons.
    """
    fam = (action.action_family or action.action or "").strip().lower()
    target = (action.semantic_target or "").strip().lower()
    surface = str(features.extras.get("active_surface") or "").strip().lower()

    if fam == "observe":
        return "re-perceive current state"
    if fam in {"dismiss", "end_call"}:
        return "clear blocking overlay"
    if fam in {"type_query", "open_search"}:
        return "search or refine reference"
    if fam in {"open_contact", "select_content", "scroll_content"}:
        if goal.kind == "whatsapp_forward_message":
            if fam == "open_contact":
                return "open source conversation"
            if fam == "select_content":
                return "inspect source timeline content"
            if fam == "scroll_content":
                return "search source timeline"
            return "resolve source content"
        return "inspect conversation content"
    if fam in {"probe_hover", "probe_context_menu", "probe_focus"}:
        if fam == "probe_context_menu":
            return "reveal hidden context actions"
        if fam == "probe_hover":
            return "reveal hover actions"
        return "probe latent surface"
    if fam in {"forward_message", "select_forward_target"}:
        return "complete forward workflow"
    if fam == "start_call":
        if target in {"voice", "voice call", "audio call"} or surface == "call_picker":
            return "activate call surface"
        return "start call"
    if fam == "explore_chrome":
        if surface in {"call_picker", "search_results"}:
            return "inspect surfaced affordances"
        return "inspect chrome affordances"
    return fam or "unknown"


def frontier_summary(goal: Goal, features: StateFeatures, actions: Iterable[Action]) -> List[Dict[str, Any]]:
    """Group actions into semantic hypotheses for selector prompts and logs."""
    grouped: Dict[str, Dict[str, Any]] = {}
    for action in actions:
        label = action.frontier_label or action_hypothesis_label(goal, features, action)
        entry = grouped.setdefault(
            label,
            {
                "label": label,
                "best_score": float("-inf"),
                "best_family": "",
                "best_target": "",
                "candidate_count": 0,
                "action_families": [],
                "best_reason": "",
            },
        )
        entry["candidate_count"] += 1
        if action.action_family not in entry["action_families"]:
            entry["action_families"].append(action.action_family)
        if action.score > entry["best_score"]:
            entry["best_score"] = float(action.score)
            entry["best_family"] = action.action_family
            entry["best_target"] = action.semantic_target
            entry["best_reason"] = action.rationale
        if action.frontier_label:
            entry["label"] = action.frontier_label

    summary = list(grouped.values())
    summary.sort(key=lambda item: item["best_score"], reverse=True)
    for item in summary:
        if item["best_score"] == float("-inf"):
            item["best_score"] = 0.0
    return summary[:8]


def annotate_frontier_action(goal: Goal, features: StateFeatures, action: Action) -> FrontierAction:
    """Convert a scored action into a frontier entry with semantic labeling."""
    label = action_hypothesis_label(goal, features, action)
    novelty = 0.9 if not getattr(action, "observed_in_world", "") else 0.25
    semantic_relevance = max(0.0, float(action.value_delta or 0.0)) + max(0.0, float(action.evidence_score or 0.0))
    actionability = max(0.0, float(action.score or 0.0))
    risk = max(0.0, -float(action.value_delta or 0.0))
    return FrontierAction(
        state_signature=str(features.extras.get("state_signature") or ""),
        action_key=str(action.action_family or action.action),
        action_family=str(action.action_family or action.action),
        semantic_target=str(action.semantic_target or ""),
        text=str(action.text or ""),
        tried=bool(getattr(action, "observed_in_world", "")),
        novelty=round(novelty, 4),
        semantic_relevance=round(semantic_relevance, 4),
        actionability=round(actionability, 4),
        information_gain=round(semantic_relevance + novelty * 0.1, 4),
        risk=round(risk, 4),
        score=round(float(action.score or 0.0), 4),
        hypothesis_label=label,
    )
