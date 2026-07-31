"""Synthetic evals for strategic-search rescue.

The goal is to prove that the agent can abandon a dead local branch and
select a better sibling/backtrack strategy when the current frontier stalls.

These cases are intentionally generic: they use an abstract "chat / list /
detail / search" world so success transfers to computer-use reasoning on any
machine rather than a single screenshot or app-specific surface.
"""

from __future__ import annotations

import argparse
import json
import statistics
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from plugin.agent.decision_selector import select_branch_strategy_with_llm
from plugin.agent.features import StateFeatures
from plugin.agent.goal import Goal
from plugin.agent.transition.types import BranchStrategy
from plugin.worldmodel.entities.entity import Entity
from plugin.worldmodel.model import WorldModel


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    if hasattr(value, "to_dict") and callable(value.to_dict):
        try:
            return _json_safe(value.to_dict())
        except Exception:
            pass
    if hasattr(value, "__dict__"):
        try:
            return _json_safe(vars(value))
        except Exception:
            pass
    return str(value)


def _norm(text: Any) -> str:
    return " ".join(str(text or "").strip().lower().split())


def _token_set(text: Any) -> set[str]:
    return {tok for tok in _norm(text).replace("/", " ").replace("-", " ").split() if len(tok) >= 4}


def _text_overlap(expected: str, actual: str) -> float:
    expected_tokens = _token_set(expected)
    if not expected_tokens:
        return 1.0
    actual_tokens = _token_set(actual)
    if not actual_tokens:
        return 0.0
    return len(expected_tokens & actual_tokens) / max(1, len(expected_tokens))


def _f1(precision: float, recall: float) -> float:
    if precision <= 0.0 or recall <= 0.0:
        return 0.0
    return 2.0 * precision * recall / (precision + recall)


def _entity(
    eid: int,
    *,
    label: str,
    etype: str = "button",
    bounds: Tuple[float, float, float, float] = (0.0, 0.0, 40.0, 40.0),
    role: Optional[str] = None,
    actions: Optional[List[str]] = None,
    description: str = "",
) -> Entity:
    attrs: Dict[str, Any] = {}
    if description:
        attrs["description"] = description
    return Entity(
        id=eid,
        entity_type=etype,
        semantic_role=label,
        label=label,
        role=role or ("AXTextField" if etype == "textfield" else "AXButton"),
        bounds=bounds,
        actions=list(actions if actions is not None else (["click"] if etype != "textfield" else ["click", "type"])),
        visible=True,
        attributes=attrs,
    )


def _world(screen_kind: str, entities: Sequence[Entity]) -> WorldModel:
    world = WorldModel()
    world.active_app = "GenericChat"
    world.entities = {entity.id: entity for entity in entities}
    world.tracker._entities = dict(world.entities)
    world.tracker._next_id = max((entity.id for entity in entities), default=0) + 1
    world.last_scene_graph = {
        "regions": [{"kind": screen_kind, "entity_ids": [entity.id for entity in entities]}],
        "report": {"layout_confidence": 0.78, "region_coverage": 0.84, "affordance_entropy": 0.61},
        "attention": {"region_ids": [screen_kind], "entity_ids": [entity.id for entity in entities]},
    }
    return world


def _goal() -> Goal:
    return Goal(
        kind="generic_forward_message",
        app="GenericChat",
        contact="Source Person",
        target_contact="Destination Person",
        link_query="source link",
        prompt="find the source link in the conversation and forward it to the destination contact",
    )


def _features(
    *,
    screen_kind: str,
    screen_bucket: str,
    active_surface: str,
    branch_active: bool = True,
    branch_depth: int = 2,
    branch_stagnant_steps: int = 1,
    world_explore_observe_count: int = 0,
    perception_cycle_stalled: bool = False,
) -> StateFeatures:
    extras: Dict[str, Any] = {
        "active_surface": active_surface,
        "branch_active": branch_active,
        "branch_depth": branch_depth,
        "branch_affordances": ["source_message_visible", "search_results_visible"],
        "branch_preferred_family": "",
        "world_explore_observe_count": world_explore_observe_count,
        "perception_cycle_stalled": perception_cycle_stalled,
        "world_exploration_needed": False,
        "world_signature": f"{screen_bucket}|{active_surface}",
    }
    return StateFeatures(
        app="GenericChat",
        screen_kind=screen_kind,
        screen_bucket=screen_bucket,
        conversation_open=screen_kind in {"conversation", "detail"},
        search_focused=screen_kind == "search",
        worldview_score=0.83,
        mean_belief=0.9,
        extras=extras,
    )


@dataclass
class StrategicSearchRescueCase:
    case_id: str
    description: str
    goal: Goal
    world: WorldModel
    features: StateFeatures
    candidates: List[Tuple[str, Any]]
    branch: Dict[str, Any] = field(default_factory=dict)
    frontier_summary: List[Dict[str, Any]] = field(default_factory=list)
    expected_preferred_family: str = ""
    expected_backtrack_family: str = ""
    expected_avoid_families: List[str] = field(default_factory=list)
    expected_branch_hypothesis: str = ""
    expected_expected_surface: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "description": self.description,
            "goal": _json_safe(self.goal.to_dict() if hasattr(self.goal, "to_dict") else self.goal),
            "world": _json_safe(self.world.to_dict() if hasattr(self.world, "to_dict") else self.world),
            "features": _json_safe(self.features.to_dict()),
            "candidates": [
                {
                    "candidate_id": cid,
                    "action": _json_safe(action.to_dict() if hasattr(action, "to_dict") else action),
                }
                for cid, action in self.candidates
            ],
            "branch": _json_safe(self.branch),
            "frontier_summary": _json_safe(self.frontier_summary),
            "expected_preferred_family": self.expected_preferred_family,
            "expected_backtrack_family": self.expected_backtrack_family,
            "expected_avoid_families": list(self.expected_avoid_families),
            "expected_branch_hypothesis": self.expected_branch_hypothesis,
            "expected_expected_surface": self.expected_expected_surface,
        }


@dataclass
class StrategicSearchRescueResult:
    case_id: str
    description: str
    preferred_family: str
    backtrack_family: str
    avoid_families: List[str]
    branch_hypothesis: str
    expected_surface: str
    confidence: float
    latency_s: float
    preferred_family_match: bool
    backtrack_family_match: bool
    avoid_precision: float
    avoid_recall: float
    avoid_f1: float
    branch_hypothesis_overlap: float
    expected_surface_match: bool
    overall_score: float
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "description": self.description,
            "preferred_family": self.preferred_family,
            "backtrack_family": self.backtrack_family,
            "avoid_families": list(self.avoid_families),
            "branch_hypothesis": self.branch_hypothesis,
            "expected_surface": self.expected_surface,
            "confidence": round(float(self.confidence or 0.0), 4),
            "latency_s": round(float(self.latency_s or 0.0), 4),
            "preferred_family_match": bool(self.preferred_family_match),
            "backtrack_family_match": bool(self.backtrack_family_match),
            "avoid_precision": round(float(self.avoid_precision or 0.0), 4),
            "avoid_recall": round(float(self.avoid_recall or 0.0), 4),
            "avoid_f1": round(float(self.avoid_f1 or 0.0), 4),
            "branch_hypothesis_overlap": round(float(self.branch_hypothesis_overlap or 0.0), 4),
            "expected_surface_match": bool(self.expected_surface_match),
            "overall_score": round(float(self.overall_score or 0.0), 4),
            "raw": _json_safe(self.raw),
        }


@dataclass
class StrategicSearchRescueSummary:
    case_count: int
    preferred_family_accuracy: float
    backtrack_family_accuracy: float
    avoid_micro_precision: float
    avoid_micro_recall: float
    avoid_micro_f1: float
    avoid_macro_precision: float
    avoid_macro_recall: float
    avoid_macro_f1: float
    branch_hypothesis_match_rate: float
    expected_surface_match_rate: float
    mean_overall_score: float
    median_latency_s: float
    cases: List[StrategicSearchRescueResult] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_count": self.case_count,
            "preferred_family_accuracy": round(float(self.preferred_family_accuracy or 0.0), 4),
            "backtrack_family_accuracy": round(float(self.backtrack_family_accuracy or 0.0), 4),
            "avoid_micro_precision": round(float(self.avoid_micro_precision or 0.0), 4),
            "avoid_micro_recall": round(float(self.avoid_micro_recall or 0.0), 4),
            "avoid_micro_f1": round(float(self.avoid_micro_f1 or 0.0), 4),
            "avoid_macro_precision": round(float(self.avoid_macro_precision or 0.0), 4),
            "avoid_macro_recall": round(float(self.avoid_macro_recall or 0.0), 4),
            "avoid_macro_f1": round(float(self.avoid_macro_f1 or 0.0), 4),
            "branch_hypothesis_match_rate": round(float(self.branch_hypothesis_match_rate or 0.0), 4),
            "expected_surface_match_rate": round(float(self.expected_surface_match_rate or 0.0), 4),
            "mean_overall_score": round(float(self.mean_overall_score or 0.0), 4),
            "median_latency_s": round(float(self.median_latency_s or 0.0), 4),
            "notes": list(self.notes),
            "cases": [case.to_dict() for case in self.cases],
        }


def build_default_cases() -> List[StrategicSearchRescueCase]:
    goal = _goal()
    cases: List[StrategicSearchRescueCase] = []

    cases.append(
        StrategicSearchRescueCase(
            case_id="search_results_stalled_open_row",
            description="Search has stalled and the source row is visible; the strategy should leave observe and open the row.",
            goal=goal,
            world=_world(
                "search_results",
                [
                    _entity(1, label="Search", etype="textfield", role="AXTextField", actions=["click", "type"]),
                    _entity(2, label="Source Person", etype="static", role="AXStaticText", actions=[]),
                    _entity(3, label="Destination Person", etype="static", role="AXStaticText", actions=[]),
                ],
            ),
            features=_features(screen_kind="search", screen_bucket="search", active_surface="search_results"),
            candidates=[
                (
                    "c1",
                    _make_action("Type", "Search", "source link", "type_query", False, "refine search query"),
                ),
                (
                    "c2",
                    _make_action("Click", "Source Person", "", "open_contact", True, "open the source conversation row"),
                ),
                (
                    "c3",
                    _make_action("Observe", "", "", "observe", True, "re-observe without changing the branch"),
                ),
            ],
            branch={
                "active": True,
                "active_surface": "search_results",
                "frontier_hypothesis": "search results are stale and the source row should be opened",
                "depth": 3,
                "no_effect_count": 2,
                "observe_count": 1,
                "stagnant_steps": 2,
            },
            frontier_summary=[
                {"action_family": "type_query", "score": 0.42, "tried": True, "hypothesis_label": "refine search"},
                {"action_family": "open_contact", "score": 0.87, "tried": False, "hypothesis_label": "open source row"},
                {"action_family": "observe", "score": 0.12, "tried": True, "hypothesis_label": "look again"},
            ],
            expected_preferred_family="open_contact",
            expected_backtrack_family="type_query",
            expected_avoid_families=["observe"],
            expected_branch_hypothesis="open the source row",
            expected_expected_surface="conversation",
        )
    )

    cases.append(
        StrategicSearchRescueCase(
            case_id="detail_panel_dead_end_refine_search",
            description="Detail panel chrome is present but the search branch should be refined instead of looping on observe.",
            goal=goal,
            world=_world(
                "detail",
                [
                    _entity(10, label="Info", etype="button", role="AXButton", actions=["click"]),
                    _entity(11, label="Search", etype="textfield", role="AXTextField", actions=["click", "type"]),
                    _entity(12, label="Source Person", etype="static", role="AXStaticText", actions=[]),
                ],
            ),
            features=_features(screen_kind="detail", screen_bucket="conversation", active_surface="detail_panel"),
            candidates=[
                (
                    "c1",
                    _make_action("Click", "Info", "", "open_contact", True, "inspect the info panel"),
                ),
                (
                    "c2",
                    _make_action("Type", "Search", "source link", "type_query", False, "refine the search query"),
                ),
                (
                    "c3",
                    _make_action("Observe", "", "", "observe", True, "watch the same panel again"),
                ),
            ],
            branch={
                "active": True,
                "active_surface": "detail_panel",
                "frontier_hypothesis": "detail panel is not producing the target; search should be refined",
                "depth": 4,
                "no_effect_count": 2,
                "observe_count": 1,
                "stagnant_steps": 2,
            },
            frontier_summary=[
                {"action_family": "open_contact", "score": 0.34, "tried": True, "hypothesis_label": "inspect panel"},
                {"action_family": "type_query", "score": 0.82, "tried": False, "hypothesis_label": "refine query"},
                {"action_family": "observe", "score": 0.15, "tried": True, "hypothesis_label": "repeat observation"},
            ],
            expected_preferred_family="type_query",
            expected_backtrack_family="open_contact",
            expected_avoid_families=["observe"],
            expected_branch_hypothesis="refine the search query",
            expected_expected_surface="search_results",
        )
    )

    cases.append(
        StrategicSearchRescueCase(
            case_id="false_call_chrome_backtrack_to_search",
            description="A false call chrome surface should force a backtrack instead of continuing to observe it.",
            goal=goal,
            world=_world(
                "call_chrome",
                [
                    _entity(20, label="Call", etype="button", role="AXButton", actions=["click"]),
                    _entity(21, label="Source Person", etype="static", role="AXStaticText", actions=[]),
                    _entity(22, label="Search", etype="textfield", role="AXTextField", actions=["click", "type"]),
                ],
            ),
            features=_features(
                screen_kind="dialog",
                screen_bucket="calling",
                active_surface="call_chrome",
                world_explore_observe_count=1,
                perception_cycle_stalled=True,
            ),
            candidates=[
                (
                    "c1",
                    _make_action("Click", "Call", "", "dismiss", True, "dismiss the accidental call chrome"),
                ),
                (
                    "c2",
                    _make_action("Type", "Search", "source link", "type_query", False, "return to search refinement"),
                ),
                (
                    "c3",
                    _make_action("Observe", "", "", "observe", True, "stay on the stalled chrome"),
                ),
            ],
            branch={
                "active": True,
                "active_surface": "call_chrome",
                "frontier_hypothesis": "call chrome is a false positive and the agent should backtrack",
                "depth": 2,
                "no_effect_count": 1,
                "observe_count": 2,
                "stagnant_steps": 3,
            },
            frontier_summary=[
                {"action_family": "dismiss", "score": 0.88, "tried": False, "hypothesis_label": "clear false chrome"},
                {"action_family": "type_query", "score": 0.51, "tried": False, "hypothesis_label": "continue search"},
                {"action_family": "observe", "score": 0.09, "tried": True, "hypothesis_label": "watch the dead end"},
            ],
            expected_preferred_family="dismiss",
            expected_backtrack_family="type_query",
            expected_avoid_families=["observe"],
            expected_branch_hypothesis="false positive",
            expected_expected_surface="search_results",
        )
    )

    cases.append(
        StrategicSearchRescueCase(
            case_id="timeline_visible_open_source_message",
            description="When the source message is already visible, the rescue strategy should stop idling and open the source content.",
            goal=goal,
            world=_world(
                "conversation",
                [
                    _entity(30, label="Source message: source link", etype="link", role="AXLink", actions=["click"]),
                    _entity(31, label="Source Person", etype="static", role="AXStaticText", actions=[]),
                    _entity(32, label="Search", etype="textfield", role="AXTextField", actions=["click", "type"]),
                ],
            ),
            features=_features(screen_kind="conversation", screen_bucket="conversation", active_surface="conversation"),
            candidates=[
                (
                    "c1",
                    _make_action("Click", "Source message: source link", "", "select_content", True, "open the source message evidence"),
                ),
                (
                    "c2",
                    _make_action("Type", "Search", "source link", "type_query", False, "refine query even though evidence is visible"),
                ),
                (
                    "c3",
                    _make_action("Observe", "", "", "observe", True, "re-observe the same conversation"),
                ),
            ],
            branch={
                "active": True,
                "active_surface": "conversation",
                "frontier_hypothesis": "the source message itself should be selected rather than re-searching",
                "depth": 3,
                "no_effect_count": 2,
                "observe_count": 1,
                "stagnant_steps": 2,
            },
            frontier_summary=[
                {"action_family": "select_content", "score": 0.9, "tried": False, "hypothesis_label": "open source content"},
                {"action_family": "type_query", "score": 0.31, "tried": True, "hypothesis_label": "refine search"},
                {"action_family": "observe", "score": 0.05, "tried": True, "hypothesis_label": "repeat observation"},
            ],
            expected_preferred_family="select_content",
            expected_backtrack_family="type_query",
            expected_avoid_families=["observe"],
            expected_branch_hypothesis="source message itself",
            expected_expected_surface="conversation",
        )
    )

    return cases


def _make_action(
    action: str,
    semantic_target: str,
    text: str,
    action_family: str,
    reversible: bool,
    rationale: str,
) -> Any:
    from plugin.agent.action import Action

    expected = ""
    if action_family == "type_query":
        expected = f"SearchQueryEquals({text or semantic_target})"
    elif action_family in {"open_contact", "select_content"}:
        expected = f"Open({semantic_target or text})"
    elif action_family == "dismiss":
        expected = "NoUnexpectedDialog"
    return Action(
        action=action,
        semantic_target=semantic_target,
        text=text,
        action_family=action_family,
        reversible=reversible,
        rationale=rationale,
        expected_predicate=expected,
    )


def _coerce_strategy(result: Any) -> tuple[Optional[BranchStrategy], Dict[str, Any]]:
    if isinstance(result, tuple) and len(result) == 2:
        strategy, trace = result
        if isinstance(strategy, BranchStrategy) or strategy is None:
            return strategy, dict(trace or {})
        if isinstance(strategy, dict):
            parsed = strategy
            coerced = BranchStrategy(
                strategy_id=str(parsed.get("strategy_id") or ""),
                preferred_family=str(parsed.get("preferred_family") or "").strip().lower(),
                backtrack_family=str(parsed.get("backtrack_family") or "").strip().lower(),
                avoid_families=[str(x).strip().lower() for x in list(parsed.get("avoid_families") or []) if str(x).strip()],
                branch_hypothesis=str(parsed.get("branch_hypothesis") or "").strip(),
                expected_surface=str(parsed.get("expected_surface") or "").strip().lower(),
                confidence=float(parsed.get("confidence") or 0.0),
                reason=str(parsed.get("reason") or "").strip(),
            )
            return coerced, dict(trace or {})
    if isinstance(result, BranchStrategy):
        return result, {"strategy": result.to_dict()}
    if isinstance(result, dict):
        parsed = result.get("parsed") if isinstance(result.get("parsed"), dict) else result
        strategy = BranchStrategy(
            strategy_id=str(parsed.get("strategy_id") or ""),
            preferred_family=str(parsed.get("preferred_family") or "").strip().lower(),
            backtrack_family=str(parsed.get("backtrack_family") or "").strip().lower(),
            avoid_families=[str(x).strip().lower() for x in list(parsed.get("avoid_families") or []) if str(x).strip()],
            branch_hypothesis=str(parsed.get("branch_hypothesis") or "").strip(),
            expected_surface=str(parsed.get("expected_surface") or "").strip().lower(),
            confidence=float(parsed.get("confidence") or 0.0),
            reason=str(parsed.get("reason") or "").strip(),
        )
        return strategy, dict(result)
    return None, {"raw": _json_safe(result)}


def evaluate_case(
    case: StrategicSearchRescueCase,
    *,
    invoker: Optional[Callable[[StrategicSearchRescueCase], Any]] = None,
) -> StrategicSearchRescueResult:
    import time

    started = time.time()
    if invoker is None:
        strategy, trace = select_branch_strategy_with_llm(
            case.goal,
            case.world,
            case.features,
            [action for _, action in case.candidates],
            frontier_summary=case.frontier_summary,
            branch=case.branch,
            task="branch_strategy_rescue_eval",
            call_kwargs={"timeout": 35.0},
        )
        payload = trace or {}
    else:
        strategy, payload = _coerce_strategy(invoker(case))

    latency_s = time.time() - started
    strategy = strategy or BranchStrategy()
    predicted_avoid = list(strategy.avoid_families or [])
    expected_avoid = list(case.expected_avoid_families or [])

    preferred_match = _norm(strategy.preferred_family) == _norm(case.expected_preferred_family)
    backtrack_match = _norm(strategy.backtrack_family) == _norm(case.expected_backtrack_family)
    avoid_precision = len(set(predicted_avoid) & set(expected_avoid)) / max(1, len(set(predicted_avoid)))
    avoid_recall = len(set(predicted_avoid) & set(expected_avoid)) / max(1, len(set(expected_avoid)))
    avoid_f1 = _f1(avoid_precision, avoid_recall)
    branch_overlap = _text_overlap(case.expected_branch_hypothesis, strategy.branch_hypothesis)
    expected_surface_match = bool(
        _norm(case.expected_expected_surface) in _norm(strategy.expected_surface)
        or _norm(strategy.expected_surface) in _norm(case.expected_expected_surface)
    )
    components = [
        1.0 if preferred_match else 0.0,
        1.0 if backtrack_match else 0.0,
        avoid_f1,
        branch_overlap,
        1.0 if expected_surface_match else 0.0,
    ]
    overall = sum(components) / len(components)
    return StrategicSearchRescueResult(
        case_id=case.case_id,
        description=case.description,
        preferred_family=strategy.preferred_family,
        backtrack_family=strategy.backtrack_family,
        avoid_families=predicted_avoid,
        branch_hypothesis=strategy.branch_hypothesis,
        expected_surface=strategy.expected_surface,
        confidence=float(strategy.confidence or 0.0),
        latency_s=latency_s,
        preferred_family_match=preferred_match,
        backtrack_family_match=backtrack_match,
        avoid_precision=avoid_precision,
        avoid_recall=avoid_recall,
        avoid_f1=avoid_f1,
        branch_hypothesis_overlap=branch_overlap,
        expected_surface_match=expected_surface_match,
        overall_score=overall,
        raw=_json_safe(payload),
    )


def run_strategic_search_rescue_eval(
    cases: Optional[Sequence[StrategicSearchRescueCase]] = None,
    *,
    invoker: Optional[Callable[[StrategicSearchRescueCase], Any]] = None,
) -> StrategicSearchRescueSummary:
    cases = list(cases or build_default_cases())
    results: List[StrategicSearchRescueResult] = []
    notes: List[str] = []
    preferred_hits = 0
    backtrack_hits = 0
    branch_overlaps: List[float] = []
    surface_hits = 0
    avoid_precisions: List[float] = []
    avoid_recalls: List[float] = []
    avoid_f1s: List[float] = []
    latencies: List[float] = []

    for case in cases:
        result = evaluate_case(case, invoker=invoker)
        results.append(result)
        preferred_hits += 1 if result.preferred_family_match else 0
        backtrack_hits += 1 if result.backtrack_family_match else 0
        branch_overlaps.append(result.branch_hypothesis_overlap)
        surface_hits += 1 if result.expected_surface_match else 0
        avoid_precisions.append(result.avoid_precision)
        avoid_recalls.append(result.avoid_recall)
        avoid_f1s.append(result.avoid_f1)
        latencies.append(result.latency_s)
        if not result.preferred_family_match:
            notes.append(
                f"{case.case_id}: preferred family expected={case.expected_preferred_family!r} got={result.preferred_family!r}"
            )
        if not result.backtrack_family_match:
            notes.append(
                f"{case.case_id}: backtrack family expected={case.expected_backtrack_family!r} got={result.backtrack_family!r}"
            )
        if result.avoid_f1 < 1.0 and case.expected_avoid_families:
            notes.append(
                f"{case.case_id}: avoid_families expected={case.expected_avoid_families!r} got={result.avoid_families!r}"
            )

    total_cases = max(1, len(results))
    all_expected_avoid = set()
    all_predicted_avoid = set()
    for result in results:
        all_predicted_avoid.update(result.avoid_families)
    for case in cases:
        all_expected_avoid.update(case.expected_avoid_families)
    avoid_micro_precision = len(all_expected_avoid & all_predicted_avoid) / max(1, len(all_predicted_avoid))
    avoid_micro_recall = len(all_expected_avoid & all_predicted_avoid) / max(1, len(all_expected_avoid))
    avoid_micro_f1 = _f1(avoid_micro_precision, avoid_micro_recall)

    return StrategicSearchRescueSummary(
        case_count=len(results),
        preferred_family_accuracy=preferred_hits / total_cases,
        backtrack_family_accuracy=backtrack_hits / total_cases,
        avoid_micro_precision=avoid_micro_precision,
        avoid_micro_recall=avoid_micro_recall,
        avoid_micro_f1=avoid_micro_f1,
        avoid_macro_precision=sum(avoid_precisions) / total_cases,
        avoid_macro_recall=sum(avoid_recalls) / total_cases,
        avoid_macro_f1=sum(avoid_f1s) / total_cases,
        branch_hypothesis_match_rate=sum(branch_overlaps) / total_cases,
        expected_surface_match_rate=surface_hits / total_cases,
        mean_overall_score=sum(result.overall_score for result in results) / total_cases,
        median_latency_s=statistics.median(latencies) if latencies else 0.0,
        cases=results,
        notes=notes,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Synthetic strategic-search rescue eval")
    parser.add_argument("--case", action="append", default=[], help="Run only the named case(s)")
    parser.add_argument("--report", default="", help="Optional JSON report path")
    parser.add_argument("--json", action="store_true", help="Print JSON only")
    args = parser.parse_args(list(argv) if argv is not None else None)

    cases = build_default_cases()
    if args.case:
        wanted = {str(item).strip() for item in args.case if str(item).strip()}
        cases = [case for case in cases if case.case_id in wanted]
    summary = run_strategic_search_rescue_eval(cases)
    payload = summary.to_dict()
    if args.report:
        Path(args.report).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False) if not args.json else json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
