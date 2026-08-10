"""LLM-backed action selector for ambiguous actuator choices.

The core agent still builds candidates deterministically from the world model.
This module is the final discriminator: given grounded candidate actions and
the current world view, ask an LLM which actuator best advances the goal.
If the model is unavailable or returns junk, callers may fall back to the
legacy compatibility path, but the live selector path itself stays
model-driven.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from dataclasses import asdict, is_dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from plugin.agent.action import Action
from plugin.agent.features import StateFeatures
from plugin.agent.goal import Goal
from plugin.agent.reasoning_consultation import consult_reasoning
from plugin.agent.transition.types import BranchStrategy
from plugin.perception.representation import structured_perception_bridge
from plugin.worldmodel.capability import CapabilityGraph, project_capability_graph
from plugin.worldmodel.model import WorldModel

logger = logging.getLogger(__name__)


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if hasattr(value, "to_dict") and callable(value.to_dict):
        try:
            return _json_safe(value.to_dict())
        except Exception:
            pass
    return str(value)


_MAX_VISIBLE_ENTITIES = 24


def _compact_world_view(world: WorldModel, features: StateFeatures) -> Dict[str, Any]:
    """The screen as a chooser needs it: state flags plus what is on it.

    This deliberately carries the conclusions of perception and not its
    transcript. It used to also embed ``perception_summary``, ``perception_llm``
    and ``structured_perception``, which are records of how the scene was read
    -- including, nested inside the consultation entry, the base64 screenshot it
    was read from. That made a single selector prompt 282k tokens, about two
    thirds of it one JPEG repeated four times as a string no model can decode.
    The question here is which of a few grounded candidates to actuate, and the
    entities and flags below are what that question turns on.
    """
    scene = getattr(world, "last_scene_graph", None) or {}
    surface_state = scene.get("surface_state") or {}
    active_subgraph = (
        features.extras.get("active_cognitive_subgraph")
        or scene.get("active_subgraph")
        or getattr(world, "last_active_subgraph", None)
        or {}
    )
    # Everything except the relation ids, which run to hundreds of opaque edge
    # keys naming nothing that can be chosen; the ids that can be are kept.
    focus = {
        str(key): _json_safe(value)
        for key, value in dict(active_subgraph or {}).items()
        if key != "relevant_relation_ids"
    }

    visible_entities: List[Dict[str, Any]] = []
    for entity in world.entities.values():
        if not getattr(entity, "visible", False):
            continue
        visible_entities.append(
            {
                "id": getattr(entity, "id", None),
                "label": getattr(entity, "label", "") or getattr(entity, "semantic_role", ""),
                "role": getattr(entity, "role", ""),
                "region_id": getattr(entity, "region_id", "") or "",
                "region_kind": getattr(entity, "region_kind", "") or "",
            }
        )
        if len(visible_entities) >= _MAX_VISIBLE_ENTITIES:
            break

    return {
        "screen_kind": str(getattr(features, "screen_kind", "") or features.screen_bucket or "unknown"),
        "screen_bucket": features.screen_bucket,
        "conversation_open": features.conversation_open,
        "call_available": features.call_available,
        "call_ringing": features.call_ringing,
        "leftover_call": features.leftover_call,
        "search_focused": features.search_focused,
        "query_matches_goal": features.query_matches_goal,
        "goal_progress": round(float(features.goal_progress or 0.0), 3),
        "worldview_score": round(float(features.worldview_score or 1.0), 3),
        "active_surface": str(features.extras.get("active_surface") or ""),
        "surface_state": _json_safe(surface_state),
        "branch_active": bool(features.extras.get("branch_active")),
        "branch_depth": int(features.extras.get("branch_depth") or 0),
        "branch_affordances": list(features.extras.get("branch_affordances") or []),
        "active_cognitive_subgraph": focus,
        "focus_phase": str(focus.get("phase") or features.extras.get("forward_phase") or ""),
        "result_surface_visible": bool(features.extras.get("result_surface_visible")),
        "search_query": str(features.extras.get("search_query") or ""),
        "selected_capability_id": str(features.extras.get("selected_capability_id") or ""),
        "selected_capability_type": str(features.extras.get("selected_capability_type") or ""),
        # Where the run stands in the selected procedure. The stage definition
        # travels separately and in full; these are the live readings taken
        # against it, which a static definition cannot carry.
        "procedure_progress": {
            "stage_id": str(features.extras.get("selected_procedure_stage_id") or ""),
            "objective": str(features.extras.get("selected_procedure_stage_objective") or ""),
            "satisfied_predicates": list(
                features.extras.get("selected_procedure_stage_satisfied_predicates") or []
            ),
            "missing_predicates": list(
                features.extras.get("selected_procedure_stage_missing_predicates") or []
            ),
            "stage_progress": round(float(features.extras.get("selected_procedure_stage_progress") or 0.0), 4),
            "procedure_progress": round(float(features.extras.get("selected_procedure_progress") or 0.0), 4),
        },
        "visible_entities": visible_entities,
    }


# What perception concluded about the screen, as opposed to how it read it.
_VERDICT_FIELDS = (
    "screen_type",
    "phase",
    "active_surface",
    "primary_surface_id",
    "likely_next_family",
    "likely_next_target",
    "likely_next_text",
    "transition_status",
    "transition_summary",
    "confidence",
)
_MAX_NARRATIVE_CHARS = 600


def _perception_verdict(world: WorldModel, features: StateFeatures) -> Dict[str, Any]:
    """Perception's reading of the screen, named field by field.

    A fixed projection rather than the whole bridge, because the bridge folds in
    the synthesis summary wholesale: anything later attached to that summary
    would otherwise ride into every decision prompt uninvited, which is how a
    base64 screenshot came to be in here four times over.
    """
    bridge = structured_perception_bridge(features=features, world=world)
    verdict: Dict[str, Any] = {}
    for key in _VERDICT_FIELDS:
        value = bridge.get(key)
        if value not in (None, "", [], {}):
            verdict[key] = _json_safe(value)
    narrative = str(bridge.get("narrative") or "").strip()
    if narrative:
        verdict["narrative"] = narrative[:_MAX_NARRATIVE_CHARS]
    return verdict


def _candidate_payload(candidate: Action, *, candidate_id: str) -> Dict[str, Any]:
    return {
        "id": candidate_id,
        "action": candidate.action,
        "family": candidate.action_family,
        "target": candidate.semantic_target,
        "text": candidate.text,
        "hypothesis": candidate.frontier_label,
        "capability_id": candidate.capability_id,
        "capability_type": candidate.capability_type,
        "target_entity_id": candidate.target_entity_id,
        "visible_world": candidate.observed_in_world,
        "score_hint": round(float(candidate.score or 0.0), 4),
        "reason": candidate.rationale,
        "grounding_reason": candidate.grounding_reason,
        "grounding_confidence": round(float(candidate.grounding_confidence or 0.0), 4),
        "reversible": getattr(candidate, "reversible", None),
    }


def _projected_capability_payload(
    cap_graph: Optional[CapabilityGraph],
    *,
    world: WorldModel,
    features: StateFeatures,
    goal: Goal,
) -> Optional[Dict[str, Any]]:
    if cap_graph is None:
        return None
    active_subgraph = (
        features.extras.get("active_cognitive_subgraph")
        or getattr(world, "last_active_subgraph", None)
        or {}
    )
    projected = project_capability_graph(
        cap_graph,
        active_entity_ids=list((active_subgraph or {}).get("active_entity_ids") or []),
        focus_region_ids=list((active_subgraph or {}).get("focus_region_ids") or []),
        goal=goal,
    )
    return _json_safe(projected.to_dict())


def _extract_text(response: Any) -> str:
    if isinstance(response, str):
        return response.strip()
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()
    choices = getattr(response, "choices", None)
    if isinstance(choices, list) and choices:
        message = getattr(choices[0], "message", None)
        if message is not None:
            content = getattr(message, "content", None)
            if isinstance(content, str) and content.strip():
                return content.strip()
    if isinstance(response, dict):
        for key in ("output_text", "text", "content"):
            val = response.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return str(response).strip()


def _extract_json_block(text: str) -> Optional[Dict[str, Any]]:
    raw = (text or "").strip()
    if not raw:
        return None
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL | re.IGNORECASE)
    if fenced:
        raw = fenced.group(1).strip()
    if not raw.startswith("{"):
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            raw = raw[start : end + 1]
    try:
        parsed = json.loads(raw)
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def _normalize_choice(value: Any) -> str:
    return str(value or "").strip().lower()


def _load_agent_timeout_config() -> Dict[str, Any]:
    module = sys.modules.get("hermes_cli.config")
    if module is None:
        try:
            import hermes_cli.config as module  # type: ignore[no-redef]
        except Exception:
            return {}
    try:
        loader = getattr(module, "load_config_readonly", None)
        if callable(loader):
            cfg = loader() or {}
            if isinstance(cfg, dict):
                agent_cfg = cfg.get("agent")
                if isinstance(agent_cfg, dict):
                    return agent_cfg
    except Exception:
        return {}
    return {}


def _resolve_choice(
    parsed: Dict[str, Any],
    options: Sequence[Tuple[str, Action]],
    *,
    allow_observe: bool = False,
) -> Optional[Action]:
    choice = parsed.get("choice_id", parsed.get("choice", parsed.get("selected", "")))
    normalized = _normalize_choice(choice)
    if not normalized:
        return None
    if normalized in {"observe", "none", "no-op", "noop"}:
        if allow_observe:
            return Action(action="Observe", action_family="observe", rationale="selector chose observe")
        return None
    for option_id, candidate in options:
        if normalized == option_id.lower():
            return candidate
    for option_id, candidate in options:
        if normalized == _normalize_choice(candidate.semantic_target):
            return candidate
        if normalized == _normalize_choice(candidate.capability_id):
            return candidate
        if normalized == _normalize_choice(candidate.action_family):
            return candidate
        if normalized == _normalize_choice(candidate.action):
            return candidate
    return None


# Static text belongs in the system message, not in the user JSON. The user
# message is rebuilt from live state every call, so anything placed there is
# re-sent and re-prefilled each time; providers cache on a byte-identical
# prefix, and the system message is the only part of this prompt that is one.
# Keep this string free of interpolated state or the prefix stops matching.
_SELECTOR_SYSTEM_PROMPT = (
    "You are a UI action selector. Your job is to pick one grounded actuator "
    "from the candidates in the user message. Return strict JSON with keys: "
    "choice_id, confidence, reason. choice_id must be one of the provided "
    "candidate ids or 'observe'.\n"
    "\n"
    "Choose the single next actuator that best advances the goal from the "
    "current world view. Take perception_summary as the screen-level reading of "
    "what is showing. Read the procedure stage and its missing predicates as the "
    "trajectory contract, the frontier and goal hypotheses as the open lines of "
    "attack, and the model-prior proposals as a secondary hint, not a command. "
    "Treat the active_cognitive_subgraph as the immediate reasoning scope: "
    "prefer affordances, regions, entities and capabilities inside that focus "
    "slice, and down-rank unrelated sidebar/list/header noise. Check "
    "already_tried before choosing: a move listed there with no effect has been "
    "tested and failed, so repeating it needs a reason the earlier attempt did "
    "not have. Prefer the candidate whose capability, region and visible context "
    "match the goal; do not optimize for visually familiar controls alone. Treat "
    "irreversible actions as high-cost: choose one only when the world evidence, "
    "the active procedure stage and the risk gate justify it. If a concrete "
    "candidate is better grounded than observe, choose it instead of idling. If "
    "no candidate is suitable, choose 'observe'."
)


def build_selector_messages(
    goal: Goal,
    world: WorldModel,
    features: StateFeatures,
    candidates: Sequence[Tuple[str, Action]],
    *,
    cap_graph: Optional[CapabilityGraph] = None,
    frontier_summary: Optional[Sequence[Dict[str, Any]]] = None,
    action_prior_runs: Optional[Sequence[Dict[str, Any]]] = None,
    already_tried: Optional[Sequence[Dict[str, Any]]] = None,
    irreversible_threshold: float = 0.7,
) -> List[Dict[str, Any]]:
    candidate_payloads: List[Dict[str, Any]] = []
    for candidate_id, cand in candidates:
        payload = _candidate_payload(cand, candidate_id=candidate_id)
        if cap_graph is not None:
            cap = cap_graph.capability_for_action(
                action_family=cand.action_family,
                semantic_target=cand.semantic_target,
                text=cand.text,
            )
            if cap is not None:
                payload["reversible"] = bool(cap.reversibility)
                payload["capability_risk"] = round(float(cap.risk), 4)
                payload["capability_confidence"] = round(float(cap.confidence), 4)
        candidate_payloads.append(payload)
    payload = {
        "goal": {
            "kind": goal.kind,
            "contact": goal.contact,
            "description": goal.description,
            "app": goal.app,
            "procedure_id": goal.procedure_id,
            "procedure_score": round(float(goal.procedure_score or 0.0), 4),
        },
        "perception_summary": _perception_verdict(world, features),
        "world_view": _compact_world_view(world, features),
        "frontier_hypotheses": list(frontier_summary or []),
        "already_tried": list(already_tried or []),
        "action_prior_runs": list(action_prior_runs or []),
        "goal_hypotheses": list(features.extras.get("goal_hypotheses") or []),
        "selected_procedure": _json_safe(features.extras.get("selected_procedure") or {}),
        "selected_procedure_stage": _json_safe(features.extras.get("selected_procedure_stage") or {}),
        "risk_gate": {
            "irreversible_threshold": round(float(irreversible_threshold or 0.7), 3),
            "irreversible_actions_require_extra_confidence": True,
        },
        "candidates": candidate_payloads,
    }
    return [
        {
            "role": "system",
            "content": _SELECTOR_SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        },
    ]


_BRANCH_STRATEGY_SYSTEM_PROMPT = (
    "You are a branch strategy planner for a persistent UI agent. Given the "
    "current branch state in the user message, choose the best strategic search "
    "direction for the next few steps. Return only strict JSON with keys: "
    "preferred_family, backtrack_family, avoid_families, branch_hypothesis, "
    "expected_surface, confidence, reason.\n"
    "\n"
    "preferred_family should be a candidate family such as open_contact, "
    "type_query, open_search, explore_chrome, probe_hover, probe_context_menu, "
    "probe_focus, start_call, dismiss, end_call, observe. backtrack_family "
    "should be the family to try if the current local branch is stale. "
    "avoid_families should list only dead-end families for this branch; do not "
    "include the preferred_family or backtrack_family unless the current branch "
    "evidence shows they are also dead ends. Choose a strategy that changes the "
    "search direction when the current frontier has stalled, rather than just "
    "restating the nearest action."
)


def _branch_strategy_payload(
    goal: Goal,
    world: WorldModel,
    features: StateFeatures,
    candidates: Sequence[Tuple[str, Action]],
    *,
    cap_graph: Optional[CapabilityGraph] = None,
    frontier_summary: Optional[Sequence[Dict[str, Any]]] = None,
    branch: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    candidate_payloads: List[Dict[str, Any]] = []
    for candidate_id, cand in candidates:
        payload = _candidate_payload(cand, candidate_id=candidate_id)
        if cap_graph is not None:
            cap = cap_graph.capability_for_action(
                action_family=cand.action_family,
                semantic_target=cand.semantic_target,
                text=cand.text,
            )
            if cap is not None:
                payload["reversible"] = bool(cap.reversibility)
                payload["capability_risk"] = round(float(cap.risk), 4)
                payload["capability_confidence"] = round(float(cap.confidence), 4)
        candidate_payloads.append(payload)
    return {
        "goal": {
            "kind": goal.kind,
            "contact": goal.contact,
            "description": goal.description,
            "app": goal.app,
            "procedure_id": goal.procedure_id,
            "procedure_score": round(float(goal.procedure_score or 0.0), 4),
        },
        "world_view": _compact_world_view(world, features),
        "frontier_hypotheses": list(frontier_summary or []),
        "branch": _json_safe(branch or {}),
        "candidates": candidate_payloads,
        "capability_graph": _projected_capability_payload(cap_graph, world=world, features=features, goal=goal),
    }


def build_branch_strategy_messages(
    goal: Goal,
    world: WorldModel,
    features: StateFeatures,
    candidates: Sequence[Tuple[str, Action]],
    *,
    cap_graph: Optional[CapabilityGraph] = None,
    frontier_summary: Optional[Sequence[Dict[str, Any]]] = None,
    branch: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    payload = _branch_strategy_payload(
        goal,
        world,
        features,
        candidates,
        cap_graph=cap_graph,
        frontier_summary=frontier_summary,
        branch=branch,
    )
    return [
        {
            "role": "system",
            "content": _BRANCH_STRATEGY_SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        },
    ]


def _parse_branch_strategy(parsed: Dict[str, Any]) -> BranchStrategy:
    avoid = parsed.get("avoid_families") or []
    if not isinstance(avoid, list):
        avoid = [avoid]
    confidence = 0.0
    try:
        confidence = float(parsed.get("confidence") or 0.0)
    except Exception:
        confidence = 0.0
    return BranchStrategy(
        strategy_id=str(parsed.get("strategy_id") or ""),
        preferred_family=str(parsed.get("preferred_family") or "").strip().lower(),
        backtrack_family=str(parsed.get("backtrack_family") or "").strip().lower(),
        avoid_families=[str(x).strip().lower() for x in avoid if str(x).strip()],
        branch_hypothesis=str(parsed.get("branch_hypothesis") or "").strip(),
        expected_surface=str(parsed.get("expected_surface") or "").strip().lower(),
        confidence=max(0.0, min(1.0, confidence)),
        reason=str(parsed.get("reason") or "").strip(),
    )


def select_branch_strategy_with_llm(
    goal: Goal,
    world: WorldModel,
    features: StateFeatures,
    scored_candidates: Sequence[Action],
    *,
    cap_graph: Optional[CapabilityGraph] = None,
    caller: Optional[Callable[..., Any]] = None,
    frontier_summary: Optional[Sequence[Dict[str, Any]]] = None,
    branch: Optional[Dict[str, Any]] = None,
    task: str = "branch_strategy",
    call_kwargs: Optional[Dict[str, Any]] = None,
) -> tuple[Optional[BranchStrategy], Dict[str, Any]]:
    candidate_pool = list(scored_candidates[:12])
    non_observe = [cand for cand in candidate_pool if cand.action_family != "observe"]
    if not non_observe:
        return None, {"reason": "not_ambiguous_enough"}
    options = [(f"c{i + 1}", cand) for i, cand in enumerate(candidate_pool)]
    messages = build_branch_strategy_messages(
        goal,
        world,
        features,
        options,
        cap_graph=cap_graph,
        frontier_summary=frontier_summary,
        branch=branch,
    )
    try:
        if caller is None:
            from agent.auxiliary_client import call_llm as caller
        effective_call_kwargs = dict(call_kwargs or {})
        if "timeout" not in effective_call_kwargs:
            effective_call_kwargs["timeout"] = 35.0
        logger.info(
            "Branch strategy selector: task=%s candidates=%d timeout=%.0fs",
            task,
            len(options),
            float(effective_call_kwargs.get("timeout") or 0.0),
        )
        consultation = consult_reasoning(
            task,
            messages,
            caller=caller,
            call_kwargs=effective_call_kwargs,
            temperature=0.0,
            max_tokens=180,
        )
        text = consultation.raw_response
        parsed = consultation.parsed or {}
        strategy = _parse_branch_strategy(parsed)
        trace = {
            "task": task,
            "prompt": messages,
            "raw_response": text,
            "parsed": parsed,
            "consultation": consultation.to_dict(),
            "strategy": strategy.to_dict(),
        }
        if not strategy.preferred_family and not strategy.backtrack_family and not strategy.avoid_families:
            return None, {**trace, "reason": "no_strategy"}
        logger.info(
            "Branch strategy selector: task=%s preferred=%s backtrack=%s confidence=%.3f",
            task,
            strategy.preferred_family or "-",
            strategy.backtrack_family or "-",
            strategy.confidence,
        )
        return strategy, trace
    except Exception as exc:
        from agent.auxiliary_client import LLMProviderExhaustedError

        if isinstance(exc, LLMProviderExhaustedError):
            raise
        return None, {"task": task, "error": str(exc)}


def select_action_with_llm(
    goal: Goal,
    world: WorldModel,
    features: StateFeatures,
    scored_candidates: Sequence[Action],
    *,
    cap_graph: Optional[CapabilityGraph] = None,
    task: str = "decision",
    caller: Optional[Callable[..., Any]] = None,
    allow_single_candidate: bool = False,
    frontier_summary: Optional[Sequence[Dict[str, Any]]] = None,
    action_prior_runs: Optional[Sequence[Dict[str, Any]]] = None,
    already_tried: Optional[Sequence[Dict[str, Any]]] = None,
    irreversible_threshold: float = 0.7,
    grounding_threshold: float = 0.7,
    call_kwargs: Optional[Dict[str, Any]] = None,
) -> tuple[Optional[Action], Dict[str, Any]]:
    """Return a model-selected candidate, or ``(None, trace)`` on failure."""
    non_observe = [cand for cand in scored_candidates if cand.action_family != "observe"]
    if not non_observe:
        return None, {"reason": "not_ambiguous_enough"}

    grounded_non_observe = [
        cand
        for cand in non_observe
        if (
            cand.target_entity_id is not None
            or float(getattr(cand, "grounding_confidence", 0.0) or 0.0) >= float(grounding_threshold or 0.0)
        )
    ]
    if not grounded_non_observe:
        return None, {
            "reason": "grounding_recovery",
            "grounded_candidates": 0,
            "non_observe_candidates": len(non_observe),
            "grounding_threshold": round(float(grounding_threshold or 0.0), 4),
        }
    if len(grounded_non_observe) < 2 and not allow_single_candidate:
        return None, {
            "reason": "grounding_recovery",
            "grounded_candidates": len(grounded_non_observe),
            "non_observe_candidates": len(non_observe),
            "grounding_threshold": round(float(grounding_threshold or 0.0), 4),
        }

    selected_pool = grounded_non_observe[:12]
    options = [(f"c{i + 1}", cand) for i, cand in enumerate(selected_pool)]
    messages = build_selector_messages(
        goal,
        world,
        features,
        options,
        cap_graph=cap_graph,
        frontier_summary=frontier_summary,
        action_prior_runs=action_prior_runs,
        already_tried=already_tried,
        irreversible_threshold=irreversible_threshold,
    )

    try:
        if caller is None:
            from agent.auxiliary_client import call_llm as caller

        effective_call_kwargs = dict(call_kwargs or {})
        timeout_source = "caller"
        if "timeout" not in effective_call_kwargs:
            try:
                env_key = (
                    "HERMES_DECISION_HIGH_RISK_SELECTOR_TIMEOUT_SECONDS"
                    if task == "decision_high_risk"
                    else "HERMES_DECISION_SELECTOR_TIMEOUT_SECONDS"
                )
                env_timeout = os.getenv(env_key, "").strip()
                if env_timeout:
                    effective_call_kwargs["timeout"] = max(5.0, float(env_timeout))
                    timeout_source = f"env:{env_key}"
                else:
                    key = (
                        "decision_high_risk_selector_timeout_seconds"
                        if task == "decision_high_risk"
                        else "decision_selector_timeout_seconds"
                    )
                    agent_cfg = _load_agent_timeout_config()
                    raw_timeout = agent_cfg.get(key, 5 if task != "decision_high_risk" else 8)
                    effective_call_kwargs["timeout"] = max(5.0, float(raw_timeout))
                    timeout_source = f"config:{key}"
            except Exception:
                effective_call_kwargs["timeout"] = 5.0 if task != "decision_high_risk" else 8.0
                timeout_source = "default"

        timeout_s = float(effective_call_kwargs.get("timeout") or 0.0)
        logger.info(
            "Decision selector: task=%s candidates=%d timeout=%.0fs",
            task,
            len(options),
            timeout_s,
        )
        consultation = consult_reasoning(
            task,
            messages,
            caller=caller,
            call_kwargs=effective_call_kwargs,
            temperature=0.0,
            max_tokens=220,
        )
        text = consultation.raw_response
        parsed = consultation.parsed or {}
        chosen = _resolve_choice(parsed, options, allow_observe=True)
        confidence = float(consultation.confidence or 0.0)
        trace = {
            "task": task,
            "prompt": messages,
            "raw_response": text,
            "parsed": parsed,
            "consultation": consultation.to_dict(),
            "selected_candidate_id": None,
            "confidence": confidence,
            "allow_single_candidate": bool(allow_single_candidate),
            "grounding_threshold": round(float(grounding_threshold or 0.0), 4),
            "grounded_candidates": len(grounded_non_observe),
            "timeout_s": timeout_s,
            "timeout_source": timeout_source,
        }
        if chosen is not None:
            for option_id, candidate in options:
                if candidate is chosen:
                    trace["selected_candidate_id"] = option_id
                    break
            logger.info(
                "Decision selector: task=%s chose=%s confidence=%.3f",
                task,
                trace.get("selected_candidate_id") or chosen.action_family,
                confidence,
            )
            return chosen, trace
        if consultation.abstained and not trace.get("reason"):
            trace["reason"] = consultation.reason or "consultation_abstained"
        logger.info("Decision selector: task=%s returned no usable choice", task)
        return None, trace
    except Exception as exc:
        from agent.auxiliary_client import LLMProviderExhaustedError

        if isinstance(exc, LLMProviderExhaustedError):
            raise
        return None, {"task": task, "error": str(exc)}
