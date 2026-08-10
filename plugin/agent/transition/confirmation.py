"""LLM-backed confirmation for positive but not fully verified transitions.

This is generic: the helper does not know about WhatsApp specifics. It asks a
reasoning model whether a just-executed action appears to have landed the
intended surface / target, then returns a structured confirmation the controller
can stamp into latent interaction state.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from plugin.agent.action import Action
from plugin.agent.features import StateFeatures
from plugin.agent.goal import Goal
from plugin.agent.reasoning_consultation import consult_reasoning
from plugin.agent.transition.types import InteractionContext, TransitionAttempt, TransitionOutcome
from plugin.agent.transition.post_perceive import feature_get
from plugin.worldmodel.model import WorldModel

logger = logging.getLogger(__name__)

_DEFAULT_TRANSITION_CONFIRMATION_THRESHOLD = 0.7
_DEFAULT_TRANSITION_CONFIRMATION_ENABLED = True


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
    return str(value)


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


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    raw = (text or "").strip()
    if not raw:
        return None
    if raw.startswith("```"):
        raw = raw.strip("`")
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        raw = raw[start : end + 1]
    try:
        parsed = json.loads(raw)
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def _transition_confirmation_enabled() -> bool:
    if os.environ.get("PYTEST_CURRENT_TEST"):
        try:
            from hermes_cli.config import load_config_readonly

            cfg = load_config_readonly() or {}
            agent_cfg = cfg.get("agent") if isinstance(cfg.get("agent"), dict) else {}
            if not bool(agent_cfg.get("transition_confirmation_enabled", False)):
                return False
        except Exception:
            return False
    try:
        from hermes_cli.config import load_config_readonly

        cfg = load_config_readonly() or {}
        agent_cfg = cfg.get("agent") if isinstance(cfg.get("agent"), dict) else {}
        raw = agent_cfg.get("transition_confirmation_enabled", _DEFAULT_TRANSITION_CONFIRMATION_ENABLED)
        return bool(raw)
    except Exception:
        return _DEFAULT_TRANSITION_CONFIRMATION_ENABLED


def _main_runtime_snapshot() -> Dict[str, Any]:
    try:
        from agent.auxiliary_client import get_runtime_main_snapshot

        return get_runtime_main_snapshot()
    except Exception:
        return {}


def _transition_confirmation_threshold() -> float:
    try:
        from hermes_cli.config import load_config_readonly

        cfg = load_config_readonly() or {}
        agent_cfg = cfg.get("agent") if isinstance(cfg.get("agent"), dict) else {}
        raw = agent_cfg.get(
            "transition_confirmation_threshold",
            _DEFAULT_TRANSITION_CONFIRMATION_THRESHOLD,
        )
        return max(0.0, min(1.0, float(raw)))
    except Exception:
        return _DEFAULT_TRANSITION_CONFIRMATION_THRESHOLD


def _coerce_features(features: Any) -> tuple[StateFeatures, Optional[Dict[str, Any]]]:
    if isinstance(features, StateFeatures):
        return features, None
    if isinstance(features, dict):
        extras = features.get("extras")
        if not isinstance(extras, dict):
            extras = {}
        return (
            StateFeatures(
                app=str(features.get("app") or ""),
                screen_kind=str(features.get("screen_kind") or features.get("screen_bucket") or "unknown"),
                screen_bucket=str(features.get("screen_bucket") or "unknown"),
                has_dialog=bool(features.get("has_dialog")),
                has_text_query=bool(features.get("has_text_query")),
                query_matches_goal=bool(features.get("query_matches_goal")),
                has_named_entity=bool(features.get("has_named_entity")),
                conversation_open=bool(features.get("conversation_open")),
                call_available=bool(features.get("call_available")),
                call_ringing=bool(features.get("call_ringing")),
                leftover_call=bool(features.get("leftover_call")),
                search_focused=bool(features.get("search_focused")),
                goal_progress=float(features.get("goal_progress") or 0.0),
                worldview_score=float(features.get("worldview_score") or 1.0),
                mean_belief=float(features.get("mean_belief") or 1.0),
                needs_reobserve=bool(features.get("needs_reobserve")),
                extras=dict(extras),
            ),
            features,
        )
    return StateFeatures(), None


@dataclass
class TransitionConfirmation:
    confirmed: bool = False
    confidence: float = 0.0
    confirmed_surface: str = ""
    confirmed_target: str = ""
    confirmed_open_conversation: str = ""
    confirmed_source_object_selected: bool = False
    needs_followup_observe: bool = False
    reason: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "confirmed": bool(self.confirmed),
            "confidence": round(float(self.confidence or 0.0), 4),
            "confirmed_surface": self.confirmed_surface,
            "confirmed_target": self.confirmed_target,
            "confirmed_open_conversation": self.confirmed_open_conversation,
            "confirmed_source_object_selected": bool(self.confirmed_source_object_selected),
            "needs_followup_observe": bool(self.needs_followup_observe),
            "reason": self.reason,
            "raw": _json_safe(self.raw),
        }


# Invariant across calls, so it belongs in the system message where it forms a
# cacheable prefix, rather than inside the user JSON that is rebuilt each time.
_CONFIRMATION_SYSTEM_PROMPT = (
    "You are a transition confirmation model. Your job is to validate whether a "
    "recent action succeeded enough for the controller to keep the new latent "
    "state: decide whether the action appears to have landed the intended "
    "surface or target.\n"
    "\n"
    "Return only strict JSON with keys: confirmed, confidence, "
    "confirmed_surface, confirmed_target, confirmed_open_conversation, "
    "confirmed_source_object_selected, needs_followup_observe, reason. Use the "
    "supplied screen evidence only. Prefer saying unconfirmed if the evidence is "
    "weak or contradictory. Be conservative about marking success."
)


def _confirmation_prompt(
    goal: Goal,
    world: WorldModel,
    view: Dict[str, Any],
    features: StateFeatures,
    action: Action,
    attempt: TransitionAttempt,
    interaction_context: InteractionContext,
) -> list[Dict[str, Any]]:
    features_obj, _ = _coerce_features(features)
    scene = getattr(world, "last_scene_graph", None) or {}
    payload = {
        "goal": {
            "kind": goal.kind,
            "description": goal.description,
            "contact": goal.contact,
            "target_contact": goal.target_contact,
            "link_query": goal.link_query,
            "app": goal.app,
        },
        "action": _json_safe(action),
        "transition_attempt": _json_safe(attempt.to_dict()),
        "screen": {
            "view": _json_safe(view),
            "features": {
                "screen_bucket": features_obj.screen_bucket,
                "conversation_open": features_obj.conversation_open,
                "call_available": features_obj.call_available,
                "call_ringing": features_obj.call_ringing,
                "leftover_call": features_obj.leftover_call,
                "search_focused": features_obj.search_focused,
                "query_matches_goal": features_obj.query_matches_goal,
                "goal_progress": round(float(features_obj.goal_progress or 0.0), 3),
                "worldview_score": round(float(features_obj.worldview_score or 1.0), 3),
                "mean_belief": round(float(features_obj.mean_belief or 1.0), 3),
            },
            "scene_report": scene.get("report") or {},
            "scene_attention": scene.get("attention") or {},
            "conversation_context": list(features_obj.extras.get("conversation_context_text") or [])[:100],
        },
        "interaction_context": interaction_context.to_dict(),
    }
    return [
        {
            "role": "system",
            "content": _CONFIRMATION_SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        },
    ]


def _parse_confirmation(
    parsed: Dict[str, Any],
    action: Action,
    attempt: TransitionAttempt,
    interaction_context: InteractionContext,
) -> TransitionConfirmation:
    conf_raw = parsed.get("confidence", 0.0)
    try:
        confidence = max(0.0, min(1.0, float(conf_raw or 0.0)))
    except (TypeError, ValueError):
        confidence = 0.0
    return TransitionConfirmation(
        confirmed=bool(parsed.get("confirmed", parsed.get("success", False))),
        confidence=confidence,
        confirmed_surface=str(parsed.get("confirmed_surface") or parsed.get("surface") or "").strip().lower(),
        confirmed_target=str(parsed.get("confirmed_target") or parsed.get("target") or "").strip(),
        confirmed_open_conversation=str(
            parsed.get("confirmed_open_conversation") or parsed.get("open_conversation") or ""
        ).strip(),
        confirmed_source_object_selected=bool(
            parsed.get(
                "confirmed_source_object_selected",
                parsed.get("source_object_selected", False),
            )
        ),
        needs_followup_observe=bool(parsed.get("needs_followup_observe", parsed.get("needs_observe", False))),
        reason=str(parsed.get("reason") or parsed.get("explanation") or "").strip(),
        raw=parsed,
    )


def _synthetic_confirmation_from_view(
    *,
    view: Dict[str, Any],
    features: StateFeatures,
    action: Action,
) -> Optional[TransitionConfirmation]:
    """
    Accept clearly landed split-pane conversation states without asking the LLM
    to rediscover them.
    """
    if action.action_family not in {"open_contact", "select_content", "select_forward_target", "forward_message"}:
        return None
    open_conversation = str(
        view.get("open_conversation")
        or feature_get(features.to_dict() if hasattr(features, "to_dict") else None, "open_conversation")
        or feature_get(features.to_dict() if hasattr(features, "to_dict") else None, "conversation_open")
        or ""
    ).strip()
    composer_visible = bool(view.get("composer_visible") or feature_get(features.to_dict() if hasattr(features, "to_dict") else None, "composer_visible"))
    search_visible = bool(view.get("search_visible") or feature_get(features.to_dict() if hasattr(features, "to_dict") else None, "search_visible"))
    screen = str(view.get("screen") or "").upper()
    if not open_conversation or not composer_visible:
        return None
    if screen not in {"SEARCH_RESULTS", "CONVERSATION", "DIALOG", "LIST"} and not search_visible:
        return None
    target = open_conversation or action.semantic_target or action.text or ""
    return TransitionConfirmation(
        confirmed=True,
        confidence=0.86,
        confirmed_surface="conversation",
        confirmed_target=target,
        confirmed_open_conversation=open_conversation,
        confirmed_source_object_selected=False,
        needs_followup_observe=False,
        reason="split-pane conversation visible after action; treating as landed",
        raw={
            "mode": "synthetic_split_pane_confirmation",
            "screen": screen,
            "open_conversation": open_conversation,
            "composer_visible": composer_visible,
            "search_visible": search_visible,
        },
    )


def _should_confirm_transition(
    action: Action,
    attempt: TransitionAttempt,
) -> bool:
    if action.action_family == "observe":
        return False
    if action.action_family not in {
        "open_contact",
        "select_content",
        "select_forward_target",
        "forward_message",
        "start_call",
        "open_search",
        "dismiss",
        "end_call",
        "explore_chrome",
        "type_query",
    }:
        return False
    if attempt.outcome not in {
        TransitionOutcome.PROGRESS.value,
        TransitionOutcome.PROMISING_UNRESOLVED.value,
        TransitionOutcome.GOAL_SATISFIED.value,
    }:
        return False
    if action.action_family == "type_query":
        return False
    assessment = attempt.assessment or {}
    if not bool(assessment.get("state_understood", True)):
        return True
    if str(assessment.get("goal_progress") or "") in {"promising", "unknown"}:
        return True
    if not bool(getattr(action, "reversible", True)):
        return True
    try:
        risk = float(assessment.get("irreversible_risk_delta") or 0.0)
    except (TypeError, ValueError):
        risk = 0.0
    return risk >= _transition_confirmation_threshold()


def confirm_transition_with_llm(
    goal: Goal,
    world: WorldModel,
    view: Dict[str, Any],
    features: StateFeatures,
    action: Action,
    attempt: TransitionAttempt,
    interaction_context: InteractionContext,
) -> Optional[TransitionConfirmation]:
    """LLM-backed confirmation for a positive but not fully verified transition."""
    if not _transition_confirmation_enabled():
        return None
    synthetic = _synthetic_confirmation_from_view(view=view, features=features, action=action)
    if synthetic is not None:
        return synthetic
    if not _should_confirm_transition(action, attempt):
        return None

    try:
        from agent.auxiliary_client import call_llm

        consultation = consult_reasoning(
            "transition_confirmation",
            _confirmation_prompt(goal, world, view, features, action, attempt, interaction_context),
            caller=call_llm,
            call_kwargs={
                "main_runtime": _main_runtime_snapshot(),
            },
            temperature=0.0,
            max_tokens=384,
        )
        parsed = consultation.parsed or _extract_json(consultation.raw_response)
        if not parsed:
            raise RuntimeError("Transition confirmation LLM returned non-JSON response")
        confirmation = _parse_confirmation(parsed, action, attempt, interaction_context)
        confirmation.raw = {
            "consultation": consultation.to_dict(),
            "parsed": parsed,
        }
        return confirmation
    except Exception:
        from agent.auxiliary_client import LLMProviderExhaustedError

        raise


def apply_transition_confirmation(
    runtime: Any,
    *,
    goal: Goal,
    action: Action,
    attempt: TransitionAttempt,
    confirmation: TransitionConfirmation,
    after_view: Dict[str, Any],
    after_features: StateFeatures,
    world_id: str,
) -> None:
    """Stamp successful confirmation into latent interaction + forward task state."""
    if not confirmation.confirmed:
        return

    after_features_obj, original_features = _coerce_features(after_features)

    ctx = runtime.execution_state.interaction_context
    ctx.selected_target = (
        confirmation.confirmed_open_conversation
        or confirmation.confirmed_target
        or ctx.selected_target
        or action.semantic_target
    )
    ctx.target_confidence = max(ctx.target_confidence, confirmation.confidence, 0.75)
    ctx.originating_world = world_id or ctx.originating_world
    ctx.active_surface = confirmation.confirmed_surface or ctx.active_surface or str(
        after_features_obj.extras.get("active_surface") or ""
    )
    if confirmation.confirmed_open_conversation:
        ctx.open_conversation.value = True
        ctx.open_conversation.confidence = max(ctx.open_conversation.confidence, confirmation.confidence, 0.75)
        ctx.open_conversation.observability = "confirmed_true"
        ctx.open_conversation.last_confirmed_world = world_id or ctx.open_conversation.last_confirmed_world
    if confirmation.confirmed_source_object_selected:
        ctx.selected_object.value = True
        ctx.selected_object.confidence = max(ctx.selected_object.confidence, confirmation.confidence, 0.7)
        ctx.selected_object.observability = "confirmed_true"
        ctx.selected_object.last_confirmed_world = world_id or ctx.selected_object.last_confirmed_world
    ctx.reversible = bool(getattr(action, "reversible", True))

    hints = runtime.world_model.overlay_hints
    if hints is None:
        runtime.world_model.overlay_hints = {}
        hints = runtime.world_model.overlay_hints

    ft = dict(hints.get("forward_task") or after_features_obj.extras.get("forward_task") or {})
    from plugin.agent.task_binding import ForwardTaskState

    state = ForwardTaskState.from_dict(ft)
    state.binding_repair = False
    if confirmation.confirmed_open_conversation:
        state.predicates.source_conversation_open = True
        state.predicates.source_conversation_visible = True
        state.predicates.forward_surface_open = False
        state.predicates.destination_picker_visible = bool(state.predicates.destination_picker_visible)
        source_conv = state.binding("source_conversation")
        source_conv.status = "confirmed"
        source_conv.confidence = max(source_conv.confidence, confirmation.confidence, 0.75)
        source_conv.evidence.append(f"llm_confirmed:{action.action_family}")
    if confirmation.confirmed_source_object_selected:
        state.predicates.source_object_visible = True
        state.predicates.source_object_selected = True
        source_obj = state.binding("source_object")
        source_obj.status = "confirmed"
        source_obj.confidence = max(source_obj.confidence, confirmation.confidence, 0.7)
        source_obj.evidence.append(f"llm_confirmed:{action.action_family}")
    if confirmation.confirmed_surface:
        state.derived_phase = "OPEN_FORWARD" if state.predicates.source_conversation_open else state.derived_phase
    state.derive_phase(leftover=False)
    hints["forward_task"] = state.to_dict()

    extras = after_features_obj.extras
    extras["forward_task"] = hints["forward_task"]
    extras["active_surface"] = ctx.active_surface
    extras["open_conversation"] = (
        confirmation.confirmed_open_conversation
        or ctx.selected_target
        or action.semantic_target
    )
    after_features_obj.conversation_open = True
    extras["transition_confirmation"] = confirmation.to_dict()
    if isinstance(original_features, dict):
        original_features["extras"] = extras
        original_features["conversation_open"] = True
        original_features["screen_bucket"] = after_features_obj.screen_bucket
        original_features["screen_kind"] = after_features_obj.screen_kind
        original_features["goal_progress"] = after_features_obj.goal_progress
        original_features["worldview_score"] = after_features_obj.worldview_score
        original_features["mean_belief"] = after_features_obj.mean_belief
    runtime.execution_state.world_exploration_needed = False
    runtime.execution_state.suppress_observe = False
    runtime.execution_state.exploration_branch.reversible = bool(getattr(action, "reversible", True))
