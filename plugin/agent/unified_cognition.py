"""Unified multimodal cognition: one model, one latent world representation.

The earlier design split cognition in two: a vision model described the screen
in prose, then a text-only model chose an action from that description. Every
detail that survived the boundary had to be re-derived by the second model, and
everything that did not survive was simply lost -- spatial grouping, which
control belongs to which row, whether an overlay covers the target, and the
perceptor's own uncertainty.

    pixels -> latent world A -> text -> latent world B

This module collapses that into a single forward pass:

    prior world document + screenshot + AX evidence + last action result + goal
        -> updated world document + grounded next action

The world document is the identity path. The runtime does not recompute the
world from accessibility -- it cannot see, so it would only be guessing -- it
carries the model's document forward verbatim and hands it back next call. That
makes each call a pure function of (world, observation, last result), so a step
can be replayed exactly and scored offline.

The runtime keeps authority over actuation, not over truth: which action
families are legal, whether a target resolves to something clickable, whether
an irreversible action has enough support, and the step budget.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from plugin.agent.action import Action
from plugin.agent.capabilities.catalog import model_allowed_actions
from plugin.agent.features import StateFeatures
from plugin.agent.goal import Goal
from plugin.agent.reasoning_consultation import consult_reasoning
from plugin.agent.world_document import (
    document_summary,
    empty_document,
    normalize_document,
    record_attempt,
    stale_beliefs,
)
from plugin.worldmodel.model import WorldModel

logger = logging.getLogger(__name__)

# Reuse the screen_understanding task so the unified call inherits the existing
# vision-model routing, env overrides and fallback chain rather than growing a
# parallel configuration surface.
UNIFIED_TASK = "screen_understanding"

MAX_AX_EVIDENCE = 24

# Motor primitives plus every *realized* general capability. Contract-only
# catalog entries stay out until they have a realization.
# docs/design/representation-capability-substrate.md
ALLOWED_ACTIONS: Tuple[str, ...] = model_allowed_actions()

_VERB_TO_RUNTIME: Dict[str, str] = {
    "click": "Click",
    "right_click": "ContextClick",
    "context_click": "ContextClick",
    "hover": "Hover",
    "type": "Type",
    "scroll": "Scroll",
    "press_escape": "Dismiss",
    "dismiss": "Dismiss",
    "compose_search_query": "ComposeSearchQuery",
    "locate_content": "LocateContent",
    "open_entity": "OpenEntity",
    "resolve_entity": "ResolveEntity",
    "select_content": "SelectContent",
    "reveal_actions": "RevealActions",
    "invoke_affordance": "InvokeAffordance",
    "dismiss_transient": "Dismiss",
    "commit_irreversible": "CommitIrreversible",
    "observe": "Observe",
    "request_more_evidence": "Observe",
}

# Default family when the model names a verb but not a family.
_VERB_TO_FAMILY: Dict[str, str] = {
    "click": "open_contact",
    "right_click": "reveal_actions",
    "context_click": "reveal_actions",
    "hover": "reveal_actions",
    "type": "type_query",
    "scroll": "scroll_content",
    "press_escape": "dismiss_transient",
    "dismiss": "dismiss_transient",
    "dismiss_transient": "dismiss_transient",
    "compose_search_query": "compose_search_query",
    "locate_content": "locate_content",
    "open_entity": "open_entity",
    "resolve_entity": "resolve_entity",
    "select_content": "select_content",
    "reveal_actions": "reveal_actions",
    "invoke_affordance": "invoke_affordance",
    "commit_irreversible": "commit_irreversible",
    "observe": "observe",
    "request_more_evidence": "observe",
}

# Families whose execution is keyboard-driven, so a confident screen reading is
# sufficient grounding; they need no entity id or coordinate.
_KEYBOARD_FAMILIES = frozenset(
    {
        "type_query",
        "open_search",
        "compose_search_query",
        "resolve_entity",
        "dismiss",
        "dismiss_transient",
        "scroll_content",
        "locate_content",
        # Affordance name is the judgment; point is optional when AX finds the label.
        "invoke_affordance",
        "commit_irreversible",
    }
)

# Above this, the model is confident enough to act despite naming evidence gaps.
_CONFIDENT_DESPITE_GAPS = 0.75

# Surface names are consumed as state-machine input, so the model is given a
# closed vocabulary. Left free-text, one static screen drew five different
# labels across ten frames of a single run.
CANONICAL_SURFACES: Tuple[str, ...] = (
    "chat_list",
    "conversation",
    "search",
    "context_menu",
    "forward_picker",
    "dialog",
    "blank",
)


def unified_cognition_enabled() -> bool:
    """Opt-in while the unified loop is proven on live tasks.

    Defaulting this on would silently reroute every existing decision path,
    so the live experiment turns it on explicitly.
    """
    raw = os.getenv("HERMES_UNIFIED_COGNITION", "0").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def unified_min_confidence() -> float:
    try:
        return max(0.0, min(1.0, float(os.getenv("HERMES_UNIFIED_MIN_CONFIDENCE", "0.55"))))
    except (TypeError, ValueError):
        return 0.55


@dataclass
class UnifiedProposal:
    """A belief update plus a proposed action, as returned by one model call."""

    world_model: Dict[str, Any] = field(default_factory=dict)
    backtrack: Dict[str, Any] = field(default_factory=dict)
    # Screen points per unit of the (downscaled) image the model was shown.
    # The document keeps the model's own coordinates so they stay consistent
    # with the pictures it sees; conversion happens only at execution.
    point_scale: float = 1.0
    observed_state: Dict[str, Any] = field(default_factory=dict)
    belief_updates: List[Dict[str, Any]] = field(default_factory=list)
    next_action: Dict[str, Any] = field(default_factory=dict)
    # The whole ranked frontier the model returned, best first. next_action is
    # its head; the rest are the runtime's siblings when the head turns out to
    # be inadmissible, which beats discarding a considered ranking and asking
    # the model to think again from scratch.
    next_actions: List[Dict[str, Any]] = field(default_factory=list)
    expected_transition: Dict[str, Any] = field(default_factory=dict)
    visible_objects: List[Dict[str, Any]] = field(default_factory=list)
    missing_evidence: List[str] = field(default_factory=list)
    # What the model could not establish this frame, phrased as questions the
    # executive can act on ("is the target message below the fold?"). Distinct
    # from missing_evidence, which is a flat list of absent facts.
    evidence_gaps: List[str] = field(default_factory=list)
    # How much of the surface the model believes it saw, 0..1. The executive
    # reads this to decide whether one more look is worth taking before acting.
    coverage: float = 1.0
    missing_affordance_information: List[str] = field(default_factory=list)
    recommended_probe: Dict[str, Any] = field(default_factory=dict)
    scene_summary: str = ""
    confidence: float = 0.0
    model: str = ""
    latency_s: float = 0.0
    raw: Dict[str, Any] = field(default_factory=dict)

    def summary_text(self) -> str:
        """The model's own prose, or a rendering of its structured reading."""
        return self.scene_summary.strip() or render_scene_summary(self)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "world_model": self.world_model,
            "backtrack": self.backtrack,
            "observed_state": self.observed_state,
            "belief_updates": self.belief_updates,
            "next_action": self.next_action,
            "next_actions": self.next_actions,
            "expected_transition": self.expected_transition,
            "visible_objects": self.visible_objects,
            "missing_evidence": self.missing_evidence,
            "evidence_gaps": self.evidence_gaps,
            "coverage": round(float(self.coverage if self.coverage is not None else 1.0), 3),
            "missing_affordance_information": self.missing_affordance_information,
            "recommended_probe": self.recommended_probe,
            "scene_summary": self.summary_text(),
            "confidence": round(float(self.confidence or 0.0), 4),
            "model": self.model,
            "latency_s": round(float(self.latency_s or 0.0), 3),
        }


def render_scene_summary(proposal: "UnifiedProposal") -> str:
    """Describe the scene when the model gave no prose.

    When a layer stack is present it is enumerated in full (every layer and
    overlay with its state and objects), so perception can be eyeballed against
    the screenshot; otherwise a one-sentence flat summary is produced.
    """
    state = proposal.observed_state or {}
    raw_layers = state.get("layers") or (proposal.world_model or {}).get("layers")
    if raw_layers:
        try:
            from plugin.agent.scene_layers import normalize_layers, render_layers

            action = proposal.next_action or {}
            family = str(action.get("family") or "").strip()
            ctx = f"next: {family}" if family else ""
            return render_layers(normalize_layers(raw_layers), task_context=ctx)
        except Exception:
            pass
    surface = str(state.get("surface") or "unknown surface").replace("_", " ")
    parts = [f"Screen shows {surface}"]
    conversation = str(state.get("open_conversation") or "").strip()
    if conversation:
        parts.append(f"conversation with {conversation} is open")
    if state.get("target_object_visible"):
        target_id = state.get("target_object_id")
        parts.append(
            f"the target object is visible (id {target_id})" if target_id not in (None, "")
            else "the target object is visible"
        )
    else:
        parts.append("the target object is not visible")
    action = proposal.next_action or {}
    family = str(action.get("family") or "").strip()
    if family:
        target = str(action.get("target_label") or action.get("text") or "").strip()
        parts.append(f"next: {family} {target}".strip() if target else f"next: {family}")
    if proposal.missing_evidence:
        parts.append("missing " + ", ".join(str(item) for item in proposal.missing_evidence[:3]))
    return "; ".join(parts) + "."


def _bounds_tuple(bounds: Any) -> Optional[List[int]]:
    try:
        x, y, w, h = bounds
    except (TypeError, ValueError):
        return None
    try:
        return [int(x), int(y), int(w), int(h)]
    except (TypeError, ValueError):
        return None


def _ax_evidence(world: WorldModel, goal: Goal, limit: int = MAX_AX_EVIDENCE) -> List[Dict[str, Any]]:
    """Serialize visible entities with stable ids AND bounds.

    Bounds matter: without them the model can describe a control but cannot
    tell the runtime which pixel region it means, which is what forced the old
    label-matching guesswork.
    """
    goal_terms = {
        str(term).strip().lower()
        for term in (goal.contact, goal.target_contact, goal.link_query)
        if str(term or "").strip()
    }
    scored: List[Tuple[float, Dict[str, Any]]] = []
    for entity in world.entities.values():
        if not getattr(entity, "visible", True):
            continue
        label = str(getattr(entity, "label", "") or "")
        role = str(getattr(entity, "role", "") or "")
        bounds = _bounds_tuple(getattr(entity, "bounds", None))
        haystack = f"{label} {getattr(entity, 'attributes', {}).get('description', '')}".lower()
        score = 0.0
        if any(term and term in haystack for term in goal_terms):
            score += 10.0
        if getattr(entity, "actions", None):
            score += 1.0
        if bounds and bounds[2] > 0 and bounds[3] > 0:
            score += 1.0
        if label:
            score += 0.5
        item: Dict[str, Any] = {
            "id": getattr(entity, "id", None),
            "role": role,
            "label": label[:120],
        }
        if bounds:
            item["bounds"] = bounds
        description = str((getattr(entity, "attributes", {}) or {}).get("description") or "")
        if description:
            item["description"] = description[:160]
        actions = list(getattr(entity, "actions", None) or [])
        if actions:
            item["actions"] = actions[:6]
        scored.append((score, item))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in scored[:limit]]


def repeated_readings(execution_state: Any) -> int:
    """How many consecutive frames produced an identical reading.

    The model is handed only its previous document, so it cannot see a run of
    identical frames stretching further back. The runtime can, and reports the
    count as a bare fact -- not as a verdict that the last action failed, which
    is the model's call to make against the pixels.
    """
    return int(getattr(execution_state, "unified_same_reading_count", 0) or 0)


_SURFACE_TO_SCREEN_TYPE = {
    "chat_list": "list",
    "conversation": "conversation",
    "search": "search",
    "context_menu": "dialog",
    "forward_picker": "dialog",
    "dialog": "dialog",
    "blank": "unknown",
}


# Vision-derived entities live above the AX id range so the two sources can
# coexist in one world model without colliding.
_VISION_ENTITY_ID_BASE = 900_000
# Half-width of the clickable box synthesized around a model-supplied point.
_VISION_ENTITY_HALF = 24


def materialize_vision_entities(world: WorldModel, proposal: Optional["UnifiedProposal"]) -> int:
    """Turn the objects in the model's world document into actionable entities.

    The objects on screen frequently exist only in the model's reading, so
    query matching, object binding and clicking have nothing to work with
    without this. Promoting them to entities lets every existing mechanism
    operate on the model's world unchanged, instead of each one needing a
    separate vision code path.

    These are materialized whenever the model reports them, without checking
    whether accessibility also has content. Deciding that AX should win would
    be the runtime adjudicating which account of the screen is true, which it
    has no way to judge -- the model sees both and has already weighed them.
    """
    if world is None or proposal is None:
        return 0
    objects = [o for o in (proposal.visible_objects or []) if isinstance(o, dict)]
    if not objects:
        return 0

    from plugin.worldmodel.entities.entity import Entity

    for stale in [i for i in world.entities if int(i) >= _VISION_ENTITY_ID_BASE]:
        world.entities.pop(stale, None)

    created = 0
    for index, item in enumerate(objects):
        text = str(item.get("text") or "").strip()
        screen = _to_screen_point(
            item.get("point") or item.get("target_point"), proposal.point_scale
        )
        if screen is None or not text:
            continue
        x, y = float(screen[0]), float(screen[1])
        entity_id = _VISION_ENTITY_ID_BASE + index
        half = _VISION_ENTITY_HALF
        world.entities[entity_id] = Entity(
            id=entity_id,
            entity_type=str(item.get("kind") or "message") or "message",
            semantic_role="message",
            label=text,
            role="AXStaticText",
            bounds=(x - half, y - half, half * 2, half * 2),
            visible=True,
            confidence=float(proposal.confidence or 0.0),
            attributes={
                "source": "vision",
                "matches_goal": bool(item.get("matches_goal")),
                "description": text,
            },
        )
        created += 1
    return created


def publish_scene_to_world(world: WorldModel, proposal: Optional["UnifiedProposal"]) -> None:
    """Make the perceptor's reading visible to the rest of the runtime.

    The reading was previously used to pick one action and then discarded, so
    the symbolic view stayed blind: with WhatsApp publishing no AX content the
    phase machine kept demanding a conversation that was already open, and the
    agent dutifully undid its own progress. Publishing through the existing
    perception-synthesis overlay lets predicates, phase and goal status see
    what the model saw.
    """
    if world is None or proposal is None:
        return
    state = proposal.observed_state or {}
    surface = str(state.get("surface") or "").strip().lower()
    action = proposal.next_action or {}
    try:
        world.last_perception_synthesis = {
            "source": "unified_cognition",
            "model": proposal.model,
            "confidence": float(proposal.confidence or 0.0),
            "summary": {
                "screen_type": _SURFACE_TO_SCREEN_TYPE.get(surface, "unknown"),
                "active_surface": surface,
                "open_conversation": str(state.get("open_conversation") or ""),
                "likely_next_family": str(action.get("family") or ""),
                "likely_next_target": str(action.get("target_label") or ""),
                "target_object_visible": bool(state.get("target_object_visible")),
                "visible_objects": list(proposal.visible_objects or []),
                "scene_summary": proposal.summary_text(),
            },
        }
    except Exception:
        pass


def reproject_unified_reading(world: WorldModel, execution_state: Any) -> int:
    """Re-apply the last accepted unified reading onto the world, every cycle.

    Unified cognition is the single source of truth for the scene; accessibility
    and the screenshot are inputs *to* it, not competing accounts. Its accepted
    reading (surface, open_conversation, objects) is produced during ``decide``
    via :func:`publish_scene_to_world` / :func:`materialize_vision_entities`, but
    the next accessibility ``ingest`` rebuilds the world and wipes it — leaving
    the symbolic view (which already knows how to read the reading) blind at the
    following ``pre_decide``. That gap is what made the forward phase machine
    oscillate on WhatsApp, whose AX tree is window chrome only.

    Re-applying the persisted document at the single view/features funnel keeps
    the reading authoritative between model calls. It is deliberately one step
    stale — the next ``consult`` refines it from fresh pixels — but a one-frame
    lag beats a permanently empty world. Idempotent: ``materialize_vision_entities``
    prunes its own prior entities before rebuilding, and a fresh ``consult`` in
    the same iteration overwrites whatever this restored.
    """
    if world is None or execution_state is None:
        return 0
    doc = getattr(execution_state, "unified_world_document", None)
    if not isinstance(doc, dict) or not doc:
        return 0
    objects = [o for o in (doc.get("objects") or []) if isinstance(o, dict)]
    surface = str(doc.get("surface") or "").strip()
    open_conversation = str(doc.get("open_conversation") or "").strip()
    if not objects and not open_conversation:
        return 0
    proposal = UnifiedProposal(
        world_model=dict(doc),
        observed_state={
            "surface": surface,
            "open_conversation": open_conversation,
            "target_object_visible": any(bool(o.get("matches_goal")) for o in objects),
            "layers": list(doc.get("layers") or []),
        },
        visible_objects=objects,
        confidence=float(doc.get("confidence") or 0.6),
        point_scale=float(getattr(execution_state, "unified_point_scale", 1.0) or 1.0),
        model="reprojected",
    )
    created = materialize_vision_entities(world, proposal)
    publish_scene_to_world(world, proposal)
    # Expose the raw general document so app overlays can bind the task from it
    # (the app-general transfer binder) instead of re-deriving from AX heuristics.
    try:
        if getattr(world, "overlay_hints", None) is None:
            world.overlay_hints = {}
        world.overlay_hints["unified_document"] = dict(doc)
    except Exception:
        pass
    return created


def _remember_reading(execution_state: Any, proposal: Optional["UnifiedProposal"]) -> None:
    """Carry the perceptor's reading forward so the next frame has a baseline."""
    if execution_state is None or proposal is None:
        return
    state = proposal.observed_state or {}
    # The object inventory is part of the reading: a scroll that reveals new
    # messages keeps the surface name identical while genuinely making
    # progress, and calling that a repeat would push the model off the very
    # action that is searching the history.
    objects = [
        str(item.get("text") or "")[:60]
        for item in (proposal.visible_objects or [])
        if isinstance(item, dict)
    ]
    current = {
        "surface": str(state.get("surface") or ""),
        "open_conversation": str(state.get("open_conversation") or ""),
        "target_object_visible": bool(state.get("target_object_visible")),
        "objects": "|".join(sorted(objects)),
    }
    previous = getattr(execution_state, "unified_last_state", None) or {}
    unchanged = all(previous.get(key) == value for key, value in current.items()) if previous else False
    _record_transition(execution_state, previous, current)
    try:
        execution_state.unified_same_reading_count = (
            int(getattr(execution_state, "unified_same_reading_count", 0) or 0) + 1 if unchanged else 0
        )
        execution_state.unified_last_state = current
        execution_state.unified_last_expectation = dict(proposal.expected_transition or {}) or None
    except Exception:
        pass


def _record_transition(
    execution_state: Any, previous: Dict[str, Any], current: Dict[str, Any]
) -> None:
    """Remember which surface the last action actually reached.

    This is the only place that sees both ends of an edge -- the surface the
    agent was on and the one it is on now -- so it is where prediction gets
    corrected by what happened.
    """
    from_surface = str(previous.get("surface") or "").strip()
    to_surface = str(current.get("surface") or "").strip()
    if not from_surface or not to_surface:
        return
    step = getattr(execution_state, "last_plan_step", None)
    family = str(getattr(step, "action_family", "") or "").strip()
    if not family:
        return
    result = getattr(execution_state, "last_result", None)
    if isinstance(result, dict) and result.get("ok") is False:
        return
    try:
        from plugin.agent.affordance_frontier import memory_for

        memory_for(execution_state).record(from_surface, family, to_surface)
    except Exception:
        pass


def prior_document(execution_state: Any) -> Dict[str, Any]:
    """The world document the model produced last step, or an empty one."""
    document = getattr(execution_state, "unified_world_document", None)
    return document if isinstance(document, dict) and document else empty_document()


def build_decision_packet(
    goal: Goal,
    world: WorldModel,
    features: StateFeatures,
    execution_state: Any = None,
) -> Dict[str, Any]:
    """Assemble the multimodal decision packet.

    The packet carries the model's own previous world document rather than a
    world the runtime recomputed from accessibility. That document is the
    identity path: the model receives its prior understanding plus fresh
    evidence and returns the update, instead of the runtime deriving state the
    runtime cannot see.

    Deliberately compact: the full AX tree, every prior world and the whole
    capability graph would reintroduce the context bloat this design avoids.
    """
    extras = features.extras if isinstance(features.extras, dict) else {}
    document = prior_document(execution_state)
    frame = int(getattr(execution_state, "unified_frame", 0) or 0)

    observation: Dict[str, Any] = {
        "frame": frame,
        "app": str(features.app or ""),
        "window_name": str(extras.get("window_name") or ""),
        "ax_node_count": int(extras.get("observation_node_count") or 0),
        "ax_content_node_count": int(extras.get("app_content_node_count") or 0),
        "ax_evidence": _ax_evidence(world, goal),
    }

    packet: Dict[str, Any] = {
        "goal": {
            "operation": goal.kind,
            "source_conversation": goal.contact,
            "source_query": goal.link_query,
            "destination": goal.target_contact,
            "description": goal.description,
        },
        "world_model": document,
        "observation": observation,
        "allowed_actions": list(ALLOWED_ACTIONS),
    }

    frontier = _frontier_for_packet(
        goal,
        world,
        features,
        document,
        execution_state,
        list(observation.get("ax_evidence") or []),
    )
    if frontier is not None:
        packet["affordance_frontier"] = frontier.to_packet()

    last = _last_action_report(features, execution_state)
    if last:
        packet["last_action"] = last

    repeats = repeated_readings(execution_state)
    if repeats:
        packet["identical_readings_in_a_row"] = repeats + 1

    unconfirmed = stale_beliefs(document, frame=frame)
    if unconfirmed:
        packet["unconfirmed_beliefs"] = unconfirmed

    # The executive's perception objective for this look: the concrete questions
    # it needs answered, where to focus, and how deep. A look is not a blank
    # refresh — it carries what the executive is trying to learn, so the model
    # prioritises resolving those questions (and reports them as evidence_gaps
    # when it cannot). Derived from the prior frame's sufficiency judgement.
    query = getattr(execution_state, "last_perception_query", None) if execution_state is not None else None
    if isinstance(query, dict) and (query.get("questions") or query.get("objective")):
        packet["perception_objective"] = {
            "questions": [str(q) for q in (query.get("questions") or [])][:6],
            "focus": str(query.get("focus") or ""),
            "depth": str(query.get("depth") or "shallow"),
            "objective": str(query.get("objective") or ""),
            "completion_condition": str(query.get("completion_condition") or ""),
        }
    return packet


def _frontier_for_packet(
    goal: Goal,
    world: WorldModel,
    features: StateFeatures,
    document: Dict[str, Any],
    execution_state: Any,
    ax_evidence: List[Dict[str, Any]],
) -> Optional["AffordanceFrontier"]:
    """The action topology of the current screen, for the model to reason over.

    Objects come from the model's own previous document because WhatsApp
    publishes no AX nodes for messages or chat rows: without them the frontier
    would describe a conversation as nothing but window chrome. Their points
    are already in the model's coordinate space, so no rescaling happens here.
    """
    from plugin.agent.affordance_frontier import (
        affordance_frontier_enabled,
        build_affordance_frontier,
        memory_for,
    )

    if not affordance_frontier_enabled():
        return None
    try:
        from plugin.agent.apps.registry import get_overlay

        overlay = get_overlay(str(features.app or ""), world)
    except Exception:
        overlay = None
    try:
        return build_affordance_frontier(
            surface=str(document.get("surface") or ""),
            goal_kind=str(goal.kind or ""),
            ax_evidence=ax_evidence,
            objects=[o for o in (document.get("objects") or []) if isinstance(o, dict)],
            overlay=overlay,
            memory=memory_for(execution_state) if execution_state is not None else None,
        )
    except Exception:
        # A missing frontier costs the model context; a raised one costs the run.
        return None


def _last_action_report(features: StateFeatures, execution_state: Any) -> Dict[str, Any]:
    """What the runtime actually executed, and what came back.

    Only the runtime knows this, so it is reported as raw fact and left for the
    model to interpret rather than being pre-judged as progress or failure.
    """
    out: Dict[str, Any] = {}
    step = getattr(execution_state, "last_plan_step", None)
    if step is not None:
        out["action"] = str(getattr(step, "action", "") or "")
        out["family"] = str(getattr(step, "action_family", "") or "")
        out["target"] = str(getattr(step, "semantic_target", "") or "")
        out["text"] = str(getattr(step, "text", "") or "")
    result = getattr(execution_state, "last_result", None)
    if isinstance(result, dict) and result:
        out["result"] = {
            "ok": bool(result.get("ok")),
            "message": str(result.get("message") or "")[:160],
        }
    # The prediction made last step, replayed so the model can check it against
    # the screen it is looking at now.
    expectation = getattr(execution_state, "unified_last_expectation", None)
    if expectation:
        out["you_predicted"] = expectation

    # Reflection substrate: the runtime alone measured what the last action
    # actually did to the world. Report that verdict as raw fact so the model
    # can course-correct instead of re-issuing a move that already failed.
    # ``ok`` only says the executor fired; ``effect`` says whether the world
    # moved. A ``no_transition`` after an ok click is the classic "I clicked
    # the wrong pixel / it opened something unexpected" signal.
    attribution = getattr(execution_state, "last_attribution", None)
    if isinstance(attribution, dict) and attribution:
        effect = str(attribution.get("effect_kind") or "")
        if effect:
            out["effect"] = effect
        domain = str(attribution.get("likely_failure_domain") or "")
        if domain and domain != "none":
            out["failure_domain"] = domain
        ev = attribution.get("evidence") if isinstance(attribution.get("evidence"), dict) else {}
        # "Nothing changed" is the strongest anti-repeat evidence there is.
        change_score = ev.get("change_score")
        if change_score is not None:
            try:
                out["world_change_score"] = round(float(change_score), 3)
            except (TypeError, ValueError):
                pass
        for key in ("open_before", "open_after"):
            val = str(ev.get(key) or "").strip()
            if val:
                out[key] = val[:80]
        notes = [str(n) for n in (attribution.get("notes") or []) if str(n).strip()]
        if notes:
            out["diagnosis_hints"] = notes[:4]

    # Ground-truth repeat counter the model cannot fabricate: how many times in
    # a row the runtime has executed the same move. >=2 means the last move did
    # not change the situation enough to warrant trying it again unchanged.
    repeats = int(getattr(execution_state, "repeated_action_count", 0) or 0)
    if repeats >= 2:
        out["times_repeated_in_a_row"] = repeats

    # Perception-history contract: the recent *pattern* of surprises, not just
    # the last one. When the agent has been surprised more than once, feed the
    # short history so the model can reason over the sequence (e.g. "twice a
    # click on this row opened a link") and re-perceive at finer granularity.
    history = getattr(execution_state, "recent_surprises", None)
    if isinstance(history, list) and len(history) >= 2:
        compact: List[Dict[str, Any]] = []
        for s in history[-4:]:
            if not isinstance(s, dict):
                continue
            compact.append({k: v for k, v in s.items() if v not in (None, "", [])})
        if compact:
            out["recent_surprises"] = compact
    return out


_SYSTEM_PROMPT = (
    "You are the world model for a macOS UI agent. You own the agent's "
    "understanding of the world; the runtime only executes what you decide and "
    "reports back what happened.\n\n"
    "Each call you receive your own previous world_model, a fresh screenshot, "
    "accessibility (AX) evidence, the raw result of the last action, and the "
    "goal. Reason over the image and the AX evidence jointly: AX is frequently "
    "incomplete or stale, so trust the pixels when they disagree, but prefer an "
    "AX id as an action target whenever one matches what you see.\n\n"
    "Return the updated world_model together with one action. Strict JSON only:\n"
    "{\n"
    '  "world_model": {\n'
    '    "surface": enum,\n'
    '    "open_conversation": str,\n'
    '    "objects": [{"id": str, "kind": str, "text": str, "point": [x, y], '
    '"matches_goal": bool}],\n'
    '    "beliefs": [{"predicate": str, "value": bool, "confidence": float, '
    '"evidence": [str], "confirmed_on_frame": int}],\n'
    '    "progress": {"phase": str, "objective": str, "notes": str},\n'
    '    "attempts": [{"frame": int, "action": str, "target": str, "result": str}],\n'
    '    "exhausted": [str]\n'
    "  },\n"
    '  "next_actions": [{"rank": int, "family": str, "target_id": int|null, '
    '"target_point": [x, y]|null, "text": str, "confidence": float, '
    '"expected_progress": float, "expected_information_gain": float, '
    '"risk": float, "reason": str}],\n'
    '  "expected_transition": {"surface": str, "likely_controls": [str]},\n'
    '  "backtrack": {"reason": str, "to": str}|null,\n'
    '  "missing_evidence": [str],\n'
    '  "evidence_gaps": [str],\n'
    '  "coverage": float,\n'
    '  "missing_affordance_information": [str],\n'
    '  "recommended_probe": {"family": str, "target_id": int|null, '
    '"may_reveal": [str], "reason": str}|null,\n'
    '  "scene_summary": str\n'
    "}\n\n"
    "next_actions is ranked best first, up to three entries. Rank 1 is the move "
    "you want taken now; the others are what you would try instead if it turns "
    "out to be inadmissible. Only propose alternatives you would genuinely "
    "accept -- the runtime executes one at a time, and falls to rank 2 rather "
    "than asking you again. expected_progress is how much the move advances the "
    "goal; expected_information_gain is how much it tells you about the screen. "
    "A probe scores low on the first and high on the second, and that is a "
    "legitimate move when the frontier is uncertain.\n\n"
    "affordance_frontier in the packet is the runtime's reading of what can be "
    "done on this surface, in three classes you must keep apart. "
    "observed_actions are available right now and backed by AX or by the object "
    "inventory you yourself reported. latent_actions are NOT on screen: each "
    "names the trigger (available_after) expected to reveal it, with a "
    "probability -- treat one as a reason to take its trigger, never as a "
    "control you can invoke. probe_actions are moves worth taking for what they "
    "would reveal. known_transition_edges say which surface an action tends to "
    "reach; enumeration_status observed means the runtime watched it happen "
    "this session, predicted means it is a structural guess. unknown_frontiers "
    "mark objects whose full action set is not yet known -- each carries the "
    "question that would resolve it and the probes that would answer it; treat "
    "one as unexplored topology to probe, never as an empty object. "
    "excluded_actions "
    "exist on screen but cannot advance the goal. The frontier is evidence, not "
    "instruction: it is incomplete for hover-only and custom-drawn controls, so "
    "if the screenshot shows a control it omits, act on what you see and say so "
    "in missing_affordance_information.\n\n"
    "expected_transition is your prediction of the screen the action will "
    "produce. State it even when unsure: next call you will see whether it "
    "held, and a surprise is the strongest evidence your world is wrong.\n\n"
    "evidence_gaps names, as questions, what you could not establish from this "
    "frame but need in order to act with confidence -- e.g. 'is the target "
    "message below the current fold?' or 'which of two similar rows is the "
    "destination?'. coverage is your estimate, 0.0 to 1.0, of how much of the "
    "task-relevant surface you actually saw this frame: 1.0 when the screen is "
    "fully legible, low when it is occluded, mid-scroll, or AX-starved. The "
    "executive uses both to decide whether to look again before it acts, so "
    "under-report coverage rather than overclaim.\n\n"
    "perception_objective, when present, is what the executive needs this look "
    "to establish: its questions are the uncertainties blocking progress, focus "
    "is where to look, and completion_condition is what would end the look. "
    "Prioritise resolving those questions -- answer them in your beliefs and "
    "next_action, and if you cannot, name exactly what is missing in "
    "evidence_gaps. A look that ignores the objective and returns a generic "
    "refresh is wasted.\n\n"
    "world_model is carried forward verbatim, so it is the only memory you "
    "have. Return the whole updated document every time, not a diff. Keep what "
    "is still true, revise what the new evidence contradicts, and drop what no "
    "longer applies.\n\n"
    "objects is the inventory of task-relevant things currently on screen: chat "
    "rows in a list, messages in a conversation. At most 10, each with its text "
    "truncated to about 60 characters and the screen point you would click to "
    "act on it. AX often reports none of these, so this inventory is how the "
    "rest of the agent learns what exists.\n\n"
    "beliefs are what you have concluded that is not visible in this one frame. "
    "Every belief must carry the evidence for it and the frame it was last "
    "confirmed on. If the packet lists a belief under unconfirmed_beliefs, look "
    "for it in the current screenshot: reconfirm it with fresh evidence and "
    "update confirmed_on_frame, or retract it. Never carry a belief forward "
    "just because you asserted it earlier.\n\n"
    "progress.phase and progress.objective are yours to set and are how you "
    "remember where you are in the task. attempts and exhausted are your search "
    "record: what you have tried on this surface and which branches are "
    "finished. Use them to avoid repeating a move that achieved nothing, and to "
    "recognise when a branch is exhausted.\n\n"
    "Prefer general capabilities over inventing motor procedures. Compose them; "
    "do not reinvent click scripts.\n"
    "Forwarding a message typically composes as:\n"
    "  resolve_entity(source) -> open_entity(chosen) -> locate_content(query) "
    "-> select_content(message) -> reveal_actions(message) -> "
    "invoke_affordance(Forward) -> resolve_entity(destination) -> "
    "open_entity(chosen) -> commit_irreversible(Send).\n"
    "AX often reports no nodes even when the screen plainly shows the rows. "
    "The objects you report each carry the screen point you would click, so "
    "open_entity acts on that point directly: a target you can see is never "
    "unreachable just because ax_content_node_count is 0 — click what you see. "
    "Reach for search only when the target is genuinely not on screen (for "
    "instance far up a long list you have not scrolled to). Then "
    "compose_search_query authors the query from goal evidence (combining "
    "tokens is judgment, not a fixed template) and type_query types it; open "
    "the matching result once it appears, and compose a *different* query if "
    "the hit list is empty. Never convert a visible target into a guessed "
    "search.\n"
    "On forward_picker, act on the visible destination rows. Prefer "
    "resolve_entity over bare open_entity/type of the destination name when "
    "multiple rows could match (e.g. aliases, self markers). "
    "Skip a step when the screen already shows its result. "
    "dismiss_transient if the wrong menu/overlay is open.\n"
    "compose_search_query: author the next search string. "
    "resolve_entity: choose which visible candidate matches a goal referent. "
    "locate_content: text=query. open_entity: open a chat/channel/thread. "
    "select_content: focus a message/row inside an open surface. "
    "reveal_actions: expose Forward/Reply/etc on that object. "
    "invoke_affordance: text=reversible control name (Forward, not Send). "
    "commit_irreversible: text=Send/Delete/Confirm only — never bury Send "
    "inside invoke_affordance. "
    "Capabilities report actuation facts, never task relevance — read the next "
    "screenshot and decide. Prefer locate_content over scroll when hunting. "
    "If a surface is exhausted, record it and try another branch. Do not "
    "restart an earlier phase once the needed conversation is open.\n\n"
    "Set backtrack when the current branch is exhausted and you want to "
    "abandon it, saying why and where to return to. Otherwise leave it null.\n\n"
    "surface must be exactly one of: "
    + ", ".join(CANONICAL_SURFACES)
    + ". Never invent a new label or a prose variant; put extra description in "
    "scene_summary.\n\n"
    "scene_summary is one or two plain sentences a human can read describing "
    "what is on screen right now and what you intend to do next. Describe what "
    "you actually see, not what you expect to see.\n\n"
    "Every point you report -- in objects and in next_actions[].target_point -- "
    "must be in the pixel coordinates of the screenshot you were given, whose "
    "dimensions are in observation.image_size, with the origin at its top "
    "left. Do not rescale to any other resolution; the runtime converts.\n\n"
    "Every family in next_actions must be one of the allowed_actions in the packet. Use "
    "target_id from ax_evidence when one matches; otherwise give target_point "
    "as the center of the control.\n\n"
    "REFLECT before you act. last_action reports what the runtime just did and, "
    "as raw measured fact, what it did to the world: result.ok says the click "
    "fired; effect says whether the world actually moved (no_transition means it "
    "did not), world_change_score near 0 and open_before==open_after mean "
    "nothing changed, failure_domain and diagnosis_hints name the runtime's "
    "guess at why, and times_repeated_in_a_row counts how often you have already "
    "issued this same move. Compare the screen you now see against you_predicted: "
    "if they differ, that surprise is strong evidence your last move or your "
    "world model was wrong.\n"
    "When the last action succeeded and the screen already shows the result you "
    "wanted, advance — do not repeat it (after focusing a search field, type the "
    "query). But when the last action did NOT produce what you predicted, or "
    "effect shows no_transition/regression, or times_repeated_in_a_row is set, "
    "you MUST NOT reissue the same family on the same target or point. First say, "
    "in progress.notes, your hypothesis for why it failed (wrong pixel just below "
    "the row, clicked a link so a browser opened, an overlay intercepted it, the "
    "element is elsewhere), then choose a materially DIFFERENT move: a different "
    "target point (e.g. a little higher on the intended row), a different element, "
    "or a different capability. If your action caused an unexpected surface — a "
    "browser or another app opened, a wrong menu appeared — your next move is to "
    "return to the task surface (dismiss/close/go back), then retry the intended "
    "action corrected. Trying the same thing again and expecting a different "
    "result is the one move that is never allowed.\n"
    "last_action.recent_surprises, when present, is the short history of your "
    "recent failed moves — read it as a pattern, not isolated events. If the "
    "same kind of surprise recurs (e.g. clicking a conversation row keeps "
    "opening a link), treat it as evidence that your segmentation of the scene "
    "is wrong: re-perceive that region at finer granularity and describe, in "
    "the world_model, the distinct sub-regions you now resolve (the link text "
    "vs. the safe area of the row that opens the conversation) before choosing "
    "where to act. Let the accumulated surprises sharpen your perception, the "
    "way prior context sharpens a prediction."
)


# Added to the system prompt only when HERMES_LAYERED_PERCEPTION is on. Teaches
# the model to report the scene as a stack of layers with object permanence,
# instead of a single flat surface. See scene_layers.py.
_LAYERED_PERCEPTION_ADDENDUM = (
    "\n\nLAYERS. Real screens stack: a right-click menu floats *over* a chat "
    "that is still open beneath it; a confirm dialog floats over that menu. "
    "Report this as world_model.layers, a list ordered bottom -> top:\n"
    '  "layers": [{"role": enum, "name": str, "state": "active"|"occluded", '
    '"objects": [{"id","kind","text","point","matches_goal"}]}]\n'
    "role is one of: container (the conversation/folder/page that holds the "
    "object), list, search, action_menu (a Forward/Share/right-click menu), "
    "destination (a forward/share picker), dialog, blank. Exactly the topmost "
    "layer is state=active; every layer beneath an overlay is state=occluded "
    "but STILL PRESENT — never drop the conversation just because a menu covers "
    "it (object permanence). Put each layer's objects on that layer: the "
    "messages on the container, the menu items on the action_menu. At most 3 "
    "layers within the current action subscene. Keep the flat surface/"
    "open_conversation/objects fields consistent with the top and base layers. "
    "In scene_summary, list every layer and overlay you see so a human can "
    "verify the reading against the screenshot."
)


def _max_image_width() -> int:
    try:
        return max(320, int(os.getenv("HERMES_UNIFIED_IMAGE_MAX_WIDTH", "1280")))
    except (TypeError, ValueError):
        return 1280


def _downscaled_data_url(screenshot_path: str) -> Tuple[str, Tuple[int, int]]:
    """Shrink the frame before sending it, and report the size the model sees.

    The size matters as much as the image: the model answers in the coordinate
    space of the picture it was given, so the runtime has to know that space to
    turn a point back into a place on screen.

    A full Retina window is mostly redundant pixels for this decision, and
    image tokens dominate both latency and cost on the fast path.
    """
    import base64
    import io

    try:
        from PIL import Image
    except Exception:
        return "", (0, 0)
    try:
        with Image.open(screenshot_path) as image:
            image = image.convert("RGB")
            limit = _max_image_width()
            if image.width > limit:
                height = max(1, round(image.height * limit / image.width))
                image = image.resize((limit, height), Image.LANCZOS)
            size = (image.width, image.height)
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=80, optimize=True)
        encoded = base64.b64encode(buffer.getvalue()).decode()
        return f"data:image/jpeg;base64,{encoded}", size
    except Exception as exc:
        logger.debug("Unified cognition: downscale failed (%s); using original", exc)
        return "", (0, 0)


def screen_point_scale(screenshot_path: str, image_width: int) -> float:
    """Points on screen per unit in the image the model was shown.

    The frame is downscaled before it is sent, so the model answers in the
    picture's coordinates, not the screen's. Executing those numbers directly
    put every pointer action off by the downscale ratio -- far enough to
    right-click the message below the one that was chosen, which read as the
    model misidentifying the target rather than as a units bug.
    """
    if image_width <= 0:
        return 1.0
    try:
        from PIL import Image

        with Image.open(screenshot_path) as image:
            captured_width = image.width
    except Exception:
        return 1.0
    if captured_width <= 0:
        return 1.0

    # A capture is in backing pixels; clicks are in points. On a 2x display the
    # two differ, so go via the screen rather than assuming they match.
    points_per_pixel = 1.0
    try:
        from AppKit import NSScreen

        screen_width = float(NSScreen.mainScreen().frame().size.width)
        if screen_width > 0 and abs(screen_width - captured_width) > 1:
            points_per_pixel = screen_width / captured_width
    except Exception:
        points_per_pixel = 1.0
    return (captured_width / float(image_width)) * points_per_pixel


def _build_messages(
    packet: Dict[str, Any], screenshot_path: str
) -> Tuple[List[Dict[str, Any]], Tuple[int, int]]:
    from plugin.agent.perception_synthesis import _screenshot_to_data_url

    data_url = ""
    size: Tuple[int, int] = (0, 0)
    if screenshot_path:
        data_url, size = _downscaled_data_url(screenshot_path)
        if not data_url:
            data_url = _screenshot_to_data_url(screenshot_path)

    if size[0] > 0:
        # Tell the model the frame it is looking at, so its coordinates are
        # anchored to something stated rather than inferred.
        observation = packet.get("observation")
        if isinstance(observation, dict):
            observation["image_size"] = [size[0], size[1]]

    text_block = {"type": "text", "text": json.dumps(packet, ensure_ascii=False)}
    content: Any = [text_block]
    if data_url:
        content.append({"type": "image_url", "image_url": {"url": data_url}})
    else:
        # No pixels available this cycle: fall back to a text-only request
        # rather than sending an empty image block the provider will reject.
        content = json.dumps(packet, ensure_ascii=False)
    system_prompt = _SYSTEM_PROMPT
    try:
        from plugin.agent.scene_layers import layered_perception_enabled

        if layered_perception_enabled():
            system_prompt = _SYSTEM_PROMPT + _LAYERED_PERCEPTION_ADDENDUM
    except Exception:
        pass
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": content},
    ], size


def _observed_state_from(document: Dict[str, Any]) -> Dict[str, Any]:
    """Project the document into the flat reading downstream code expects."""
    objects = [o for o in (document.get("objects") or []) if isinstance(o, dict)]
    match = next((o for o in objects if o.get("matches_goal")), None)
    return {
        "surface": document.get("surface") or "",
        "open_conversation": document.get("open_conversation") or "",
        "target_object_visible": match is not None,
        "target_object_id": (match or {}).get("id"),
        "layers": list(document.get("layers") or []),
    }


MAX_NEXT_ACTIONS = 4


def _coverage_value(raw: Any) -> float:
    """Coerce the model's coverage claim into 0..1, defaulting to full."""
    if raw in (None, ""):
        return 1.0
    try:
        return max(0.0, min(1.0, float(raw)))
    except (TypeError, ValueError):
        return 1.0


def action_min_confidence() -> float:
    try:
        return max(0.0, min(1.0, float(os.getenv("HERMES_ACTION_MIN_CONFIDENCE", "0.55"))))
    except (TypeError, ValueError):
        return 0.55


def action_min_progress() -> float:
    try:
        return max(0.0, min(1.0, float(os.getenv("HERMES_ACTION_MIN_PROGRESS", "0.30"))))
    except (TypeError, ValueError):
        return 0.30


def _action_eligible(action: Dict[str, Any]) -> bool:
    """Whether an alternative is worth spending a step on.

    Only stated values are tested. A model that omits expected_progress has
    not said the action is unpromising, and dropping it on a missing field
    would quietly shrink the frontier back to a single choice.
    """
    if not str(action.get("family") or "").strip():
        return False
    for key, floor in (
        ("confidence", action_min_confidence()),
        ("expected_progress", action_min_progress()),
    ):
        raw = action.get(key)
        if raw in (None, ""):
            continue
        try:
            if float(raw) < floor:
                return False
        except (TypeError, ValueError):
            continue
    return True


def normalize_next_actions(raw: Any, *, fallback: Any = None) -> List[Dict[str, Any]]:
    """Order the model's proposed actions best-first and drop weak ones.

    Accepts the older single ``next_action`` shape as a one-element frontier so
    a model (or a replayed trace) that predates the ranked contract keeps
    working unchanged.
    """
    items: List[Dict[str, Any]] = [item for item in (raw or []) if isinstance(item, dict)] if isinstance(raw, (list, tuple)) else []
    if not items and isinstance(fallback, dict) and fallback:
        items = [dict(fallback)]

    def sort_key(pair: Tuple[int, Dict[str, Any]]) -> Tuple[float, float, int]:
        index, action = pair
        try:
            rank = float(action.get("rank")) if action.get("rank") not in (None, "") else float(index + 1)
        except (TypeError, ValueError):
            rank = float(index + 1)
        try:
            score = float(action.get("score") or action.get("confidence") or 0.0)
        except (TypeError, ValueError):
            score = 0.0
        return (rank, -score, index)

    ordered = [action for _, action in sorted(enumerate(items), key=sort_key)]
    eligible = [dict(action) for action in ordered if _action_eligible(action)]
    # Never return empty when the model did name a move: an action below
    # threshold is still the model's best reading, and admissibility, cycle
    # detection and the irreversible gate all still stand between it and the
    # screen.
    if not eligible and ordered:
        eligible = [dict(ordered[0])]
    return eligible[:MAX_NEXT_ACTIONS]


def ranked_action_candidates(proposal: "UnifiedProposal") -> List[Dict[str, Any]]:
    """The head action followed by the siblings the runtime may fall back to.

    The head is whatever currently sits in ``next_action`` -- possibly rewritten
    by decision consultation -- so a consulted override stays first and the
    model's own ranking supplies the alternatives behind it.
    """
    head = dict(proposal.next_action or {})
    out: List[Dict[str, Any]] = [head] if head.get("family") else []
    seen = {
        (
            str(head.get("family") or "").lower(),
            str(head.get("target_id") or ""),
            str(head.get("text") or ""),
        )
    }
    for action in proposal.next_actions or []:
        if not isinstance(action, dict):
            continue
        key = (
            str(action.get("family") or "").lower(),
            str(action.get("target_id") or ""),
            str(action.get("text") or ""),
        )
        if key in seen or not key[0]:
            continue
        seen.add(key)
        out.append(dict(action))
    return out[:MAX_NEXT_ACTIONS]


def _parse_proposal(parsed: Dict[str, Any], *, frame: int = 0) -> UnifiedProposal:
    def _as_dict(value: Any) -> Dict[str, Any]:
        return dict(value) if isinstance(value, dict) else {}

    def _as_list(value: Any) -> List[Any]:
        if isinstance(value, (list, tuple)):
            return list(value)
        if value in (None, ""):
            return []
        return [value]

    ranked = normalize_next_actions(
        parsed.get("next_actions"), fallback=parsed.get("next_action")
    )
    next_action = ranked[0] if ranked else _as_dict(parsed.get("next_action"))
    try:
        confidence = max(0.0, min(1.0, float(next_action.get("confidence", parsed.get("confidence", 0.0)) or 0.0)))
    except (TypeError, ValueError):
        confidence = 0.0

    document = normalize_document(parsed.get("world_model"), frame=frame)
    # observed_state, belief_updates and visible_objects are projections of the
    # document rather than separate outputs, so existing consumers keep working
    # while the document stays the single thing the model owns.
    observed_state = _as_dict(parsed.get("observed_state")) or _observed_state_from(document)
    beliefs = [_as_dict(item) for item in _as_list(parsed.get("belief_updates"))] or list(
        document.get("beliefs") or []
    )
    objects = [_as_dict(item) for item in _as_list(parsed.get("visible_objects"))] or list(
        document.get("objects") or []
    )

    return UnifiedProposal(
        world_model=document,
        backtrack=_as_dict(parsed.get("backtrack")),
        observed_state=observed_state,
        belief_updates=beliefs,
        next_action=next_action,
        next_actions=ranked,
        expected_transition=_as_dict(parsed.get("expected_transition")),
        visible_objects=objects,
        missing_evidence=[str(item) for item in _as_list(parsed.get("missing_evidence")) if str(item).strip()],
        evidence_gaps=[str(item) for item in _as_list(parsed.get("evidence_gaps")) if str(item).strip()][:6],
        coverage=_coverage_value(parsed.get("coverage")),
        missing_affordance_information=[
            str(item)
            for item in _as_list(parsed.get("missing_affordance_information"))
            if str(item).strip()
        ][:6],
        recommended_probe=_as_dict(parsed.get("recommended_probe")),
        scene_summary=str(parsed.get("scene_summary") or parsed.get("summary") or "").strip(),
        confidence=confidence,
        raw=dict(parsed),
    )


def consult_unified_cognition(
    goal: Goal,
    world: WorldModel,
    features: StateFeatures,
    execution_state: Any = None,
) -> Optional[UnifiedProposal]:
    """Make the single multimodal call that produces belief + action."""
    from plugin.agent.perception_synthesis import (
        _call_llm_hard_timeout,
        _main_runtime_snapshot,
        _perception_extra_body,
        _perception_max_tokens,
        _perception_reasoning_config,
        _perception_task_targets,
        _perception_timeout_seconds,
    )

    extras = features.extras if isinstance(features.extras, dict) else {}
    screenshot_path = str(
        extras.get("screenshot_path") or getattr(world, "last_screenshot_path", "") or ""
    ).strip()
    if not screenshot_path:
        # Without pixels this is just the old text-only path wearing a new
        # name; let the regular pipeline handle the frame.
        logger.info("Unified cognition skipped: no screenshot for this frame")
        return None
    frame = _advance_frame(execution_state)
    packet = build_decision_packet(goal, world, features, execution_state)
    messages, image_size = _build_messages(packet, screenshot_path)
    point_scale = screen_point_scale(screenshot_path, image_size[0])

    main_runtime = _main_runtime_snapshot()
    targets = _perception_task_targets(main_runtime, task_name=UNIFIED_TASK)
    timeout_s = _perception_timeout_seconds()
    max_tokens = max(512, _perception_max_tokens())

    logger.info(
        "Unified cognition frame=%d: entities=%d carried[%s] targets=%s",
        frame,
        len(packet["observation"]["ax_evidence"]),
        document_summary(packet["world_model"]),
        [f"{t.get('provider')}/{t.get('model')}" for t in targets],
    )

    record_to = recording_dir()
    recorded = False

    for index, target in enumerate(targets, start=1):
        start = time.time()
        try:
            consultation = consult_reasoning(
                UNIFIED_TASK,
                messages,
                caller=lambda **kwargs: _call_llm_hard_timeout(timeout_s, **kwargs),
                call_kwargs={
                    "task": UNIFIED_TASK,
                    "provider": target.get("provider") or None,
                    "model": target.get("model") or None,
                    "base_url": target.get("base_url") or None,
                    "api_key": target.get("api_key") or None,
                    "timeout": timeout_s,
                    "main_runtime": main_runtime,
                    "extra_body": _perception_extra_body(main_runtime),
                    "reasoning_config": _perception_reasoning_config(target),
                },
                temperature=0.0,
                max_tokens=max_tokens,
            )
        except TimeoutError:
            logger.warning(
                "Unified cognition timed out on target %d/%d (%s) — advancing",
                index,
                len(targets),
                target.get("model"),
            )
            continue
        except Exception as exc:
            logger.warning("Unified cognition call failed on %s: %s", target.get("model"), exc)
            continue
        if not consultation.parsed:
            continue
        proposal = _parse_proposal(consultation.parsed, frame=frame)
        proposal.model = str(target.get("model") or "")
        proposal.latency_s = time.time() - start
        proposal.point_scale = point_scale
        # Carry the scale forward so the reading can be faithfully re-projected
        # onto the world between model calls (see reproject_unified_reading).
        if execution_state is not None:
            try:
                execution_state.unified_point_scale = point_scale
            except Exception:
                pass
        logger.info(
            "Unified cognition proposal: frame=%d task=%s provider=%s model=%s surface=%s action=%s target=%s confidence=%.2f summary=%s",
            frame,
            UNIFIED_TASK,
            str(target.get("provider") or ""),
            proposal.model,
            str(proposal.observed_state.get("surface") or proposal.world_model.get("surface") or ""),
            str(proposal.next_action.get("family") or ""),
            str(proposal.next_action.get("text") or proposal.next_action.get("target_label") or ""),
            float(proposal.confidence or 0.0),
            proposal.summary_text()[:260],
        )
        logger.info(
            "Unified cognition: family=%s target_id=%s conf=%.2f world[%s] in %.2fs via %s",
            proposal.next_action.get("family"),
            proposal.next_action.get("target_id"),
            proposal.confidence,
            document_summary(proposal.world_model),
            proposal.latency_s,
            proposal.model,
        )
        logger.info("Unified cognition scene: %s", proposal.summary_text())
        if proposal.backtrack:
            logger.info(
                "Unified cognition backtrack: %s -> %s",
                proposal.backtrack.get("reason"),
                proposal.backtrack.get("to"),
            )
        _remember_reading(execution_state, proposal)
        persist_world_document(execution_state, proposal)
        # The critic has settled what is true; now decide what to do about it.
        consult_next_capability(proposal, goal, features, execution_state)
        materialize_vision_entities(world, proposal)
        publish_scene_to_world(world, proposal)
        if record_to:
            _record_frame(
                packet,
                screenshot_path,
                proposal,
                directory=record_to,
                shadow=_shadow_task_state(features),
            )
            recorded = True
        return proposal

    # Every target failed. The frame is still worth keeping: a scene no model
    # could read is exactly the kind of case the eval set should contain.
    if record_to and not recorded:
        _record_frame(
            packet,
            screenshot_path,
            None,
            directory=record_to,
            shadow=_shadow_task_state(features),
        )
    return None


def _advance_frame(execution_state: Any) -> int:
    frame = int(getattr(execution_state, "unified_frame", 0) or 0) + 1
    try:
        execution_state.unified_frame = frame
    except Exception:
        pass
    return frame


def _apply_layer_permanence(
    execution_state: Any,
    proposal: Optional[UnifiedProposal],
    prior: Dict[str, Any],
) -> None:
    """Compute the accepted document's layer stack with object permanence.

    Uses the prior document's stack as memory: if the fresh reading is an
    overlay that dropped the container beneath it, the container is carried
    forward occluded (with its objects). The flat ``open_conversation`` is then
    restored from the base layer, so even flat consumers see the chat is still
    open behind the menu -- the fix the ``transfer_task`` stickiness used to hack.

    Gated by :func:`scene_layers.layered_perception_enabled`; a no-op otherwise,
    so the flat path is unchanged until the flag is set.
    """
    from plugin.agent.scene_layers import (
        base_layer,
        derive_flat,
        flat_objects,
        layered_perception_enabled,
        layers_from_flat,
        layers_to_dicts,
        merge_permanence,
        normalize_layers,
    )

    if not layered_perception_enabled() or proposal is None:
        return
    accepted = getattr(execution_state, "unified_world_document", None)
    if not isinstance(accepted, dict):
        return

    prior_layers = normalize_layers(prior.get("layers")) if isinstance(prior, dict) else []
    raw_new = accepted.get("layers")
    if raw_new:
        new_layers = normalize_layers(raw_new)
    else:
        new_layers = layers_from_flat(
            accepted.get("surface"),
            accepted.get("open_conversation"),
            accepted.get("objects"),
        )
    merged = merge_permanence(prior_layers, new_layers)
    accepted["layers"] = layers_to_dicts(merged)
    # Keep the flat inventory in step with the stack so the persisted document
    # (read back by reproject/materialize) has every clickable object.
    union = flat_objects(merged)
    if union:
        accepted["objects"] = union[:12]

    # Restore the base container name for flat back-compat readers (permanence).
    _, base_name = derive_flat(merged)
    if base_name and not str(accepted.get("open_conversation") or "").strip():
        accepted["open_conversation"] = base_name

    execution_state.unified_world_document = accepted
    proposal.world_model = accepted
    if isinstance(proposal.observed_state, dict):
        proposal.observed_state["layers"] = accepted["layers"]
        if base_name and not str(proposal.observed_state.get("open_conversation") or "").strip():
            proposal.observed_state["open_conversation"] = base_name
    # Keep the materializable inventory in step with the stack so overlay menu
    # items and occluded container messages are both clickable.
    base = base_layer(merged)
    if base is not None or any(l.role == "action_menu" for l in merged):
        proposal.visible_objects = flat_objects(merged)


def persist_world_document(execution_state: Any, proposal: Optional[UnifiedProposal]) -> None:
    """Critique the model's proposal, then carry the *accepted* document.

    The perceptor proposes. The world critic accepts/rejects structural deltas
    against the prior document and last action so illegal surface jumps (and
    the motors that follow them) cannot silently rewrite belief state.
    """
    if proposal is None or not proposal.world_model:
        return
    try:
        from plugin.agent.world_critic import critique_world_proposal

        prior = getattr(execution_state, "unified_world_document", None)
        last_action = str(getattr(execution_state, "last_action", "") or "")
        if getattr(execution_state, "last_plan_step", None) is not None:
            step = execution_state.last_plan_step
            last_action = str(
                getattr(step, "action_family", "") or getattr(step, "action", "") or last_action
            )
        observed = ""
        if isinstance(proposal.observed_state, dict):
            observed = str(proposal.observed_state.get("surface") or "")
        verdict = critique_world_proposal(
            prior if isinstance(prior, dict) else {},
            dict(proposal.world_model),
            last_action=last_action,
            observed_surface=observed,
        )
        try:
            decisions = [d.to_dict() for d in verdict.decisions[:8]]
        except Exception:
            decisions = []
        logger.info(
            "World critic verdict: surface=%s field_role=%s accepted_surface=%s accepted_open=%s decisions=%s",
            observed or str((prior or {}).get("surface") or ""),
            str(getattr(verdict, "focused_field_role", "") or ""),
            str(verdict.surface or ""),
            str((verdict.accepted_document or {}).get("open_conversation") or ""),
            decisions,
        )
        execution_state.unified_world_document = dict(verdict.accepted_document)
        execution_state.focused_field_role = verdict.focused_field_role
        execution_state.last_critic_verdict = verdict.to_dict()
        # Keep proposal.world_model aligned with what control will obey.
        proposal.world_model = dict(verdict.accepted_document)
        if isinstance(proposal.observed_state, dict):
            proposal.observed_state["surface"] = verdict.surface
            proposal.observed_state["focused_field_role"] = verdict.focused_field_role
        # Object permanence lives in perception: build the layer stack for the
        # accepted document, carrying the container beneath any overlay so the
        # binder never has to reconstruct it from prior task state.
        _apply_layer_permanence(
            execution_state, proposal, prior if isinstance(prior, dict) else {}
        )
    except Exception:
        try:
            execution_state.unified_world_document = dict(proposal.world_model)
        except Exception:
            pass


def consult_next_capability(
    proposal: Optional[UnifiedProposal],
    goal: Goal,
    features: Optional[StateFeatures] = None,
    execution_state: Any = None,
) -> Dict[str, Any]:
    """Ask the decision-maker which capability advances the accepted world.

    Perception owns the reading, the critic owns what is true, and this owns
    what to do next. Keeping them separate is what stops a screen-reading model
    from also being the planner by accident.
    """
    if proposal is None:
        return {}
    try:
        from plugin.agent.decision_consultation import apply_decision_consultation

        return apply_decision_consultation(
            proposal, goal, features=features, execution_state=execution_state
        )
    except Exception as exc:  # never let the chooser break the loop
        logger.warning("Decision consultation skipped: %s", exc)
        return {}


def note_executed_action(execution_state: Any, step: Any, result: Any) -> None:
    """Project the executive's attempt record into the carried document.

    The model's proposal is an intention; the workspace holds the fact. The
    document the model reads next call is a rendering of that fact, not a
    second place attempts are written.
    """
    document = getattr(execution_state, "unified_world_document", None)
    if not isinstance(document, dict) or not document:
        return
    workspace = getattr(execution_state, "workspace", None)
    attempts = list(getattr(workspace, "attempts", []) or [])
    latest = attempts[-1] if attempts else None
    if latest is not None:
        action, target, outcome = latest.action, latest.target, latest.outcome
    else:
        ok = bool((result or {}).get("ok")) if isinstance(result, dict) else bool(result)
        message = str((result or {}).get("message") or "") if isinstance(result, dict) else ""
        action = str(getattr(step, "action_family", "") or getattr(step, "action", "") or "")
        target = str(getattr(step, "semantic_target", "") or "")
        outcome = ("ok: " if ok else "failed: ") + (message or ("done" if ok else "no effect"))
    try:
        execution_state.unified_world_document = record_attempt(
            dict(document),
            frame=int(getattr(execution_state, "unified_frame", 0) or 0),
            action=action,
            target=target,
            result=outcome,
        )
    except Exception:
        pass


def _shadow_task_state(features: StateFeatures) -> Dict[str, Any]:
    """The AX-derived predicates, recorded for comparison but never sent.

    These used to drive the packet. They are kept only so the eval can measure
    how often accessibility and the model disagree, and which one was right.
    """
    extras = features.extras if isinstance(features.extras, dict) else {}
    forward = extras.get("forward_task") if isinstance(extras.get("forward_task"), dict) else {}
    predicates = forward.get("predicates") if isinstance(forward.get("predicates"), dict) else {}
    return {
        "phase": str(extras.get("forward_phase") or forward.get("derived_phase") or ""),
        "local_objective": str(forward.get("local_objective") or ""),
        "predicates": {key: bool(value) for key, value in predicates.items()},
        "ax_content_node_count": int(extras.get("app_content_node_count") or 0),
        "open_conversation": str(extras.get("open_conversation") or ""),
        "wa_screen": str(extras.get("wa_screen") or ""),
    }


def recording_dir() -> str:
    """Directory to record perceptor frames into, or '' when disabled."""
    return os.getenv("HERMES_PERCEPTOR_RECORD_DIR", "").strip()


def _record_frame(
    packet: Dict[str, Any],
    screenshot_path: str,
    proposal: Optional[UnifiedProposal],
    *,
    directory: str,
    shadow: Optional[Dict[str, Any]] = None,
) -> None:
    """Persist the exact multimodal input, and what the model made of it.

    Recording during a real run is the only way to get eval scenes from a
    genuinely complex flow. Replaying them afterwards keeps the eval
    deterministic and off the critical path of a live task.
    """
    import shutil

    try:
        target = Path(directory)
        target.mkdir(parents=True, exist_ok=True)
        index = len(list(target.glob("frame_*.json"))) + 1
        stem = f"frame_{index:04d}"
        image_name = ""
        if screenshot_path and Path(screenshot_path).exists():
            image_name = f"{stem}.png"
            shutil.copyfile(screenshot_path, target / image_name)
        (target / f"{stem}.json").write_text(
            json.dumps(
                {
                    "frame": index,
                    "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "screenshot": image_name,
                    "packet": packet,
                    "response": proposal.to_dict() if proposal is not None else None,
                    "shadow_task_state": shadow or {},
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        logger.info("Perceptor frame recorded: %s (image=%s)", stem, bool(image_name))
    except Exception as exc:
        logger.warning("Perceptor frame recording failed: %s", exc)


def _to_screen_point(point: Any, scale: float) -> Optional[Tuple[int, int]]:
    """Convert a point in the model's image into a point on the screen."""
    if not isinstance(point, (list, tuple)) or len(point) != 2:
        return None
    try:
        factor = float(scale) if scale and float(scale) > 0 else 1.0
        return (round(float(point[0]) * factor), round(float(point[1]) * factor))
    except (TypeError, ValueError):
        return None


def _resolve_target_entity(world: WorldModel, target_id: Any) -> Any:
    if target_id in (None, ""):
        return None
    try:
        key = int(target_id)
    except (TypeError, ValueError):
        return None
    entity = world.entities.get(key)
    if entity is None or not getattr(entity, "visible", True):
        return None
    return entity


# Pointer families whose target must be a concrete perceived object. When the
# model names one by label but gives no resolvable target_id, we ground the
# label to a perceived entity so the decision carries geometry (an entity id +
# bounds), not a bare string the runtime would have to re-resolve.
_GROUNDED_POINTER_FAMILIES = frozenset(
    {"open_entity", "open_contact", "select_content", "reveal_actions"}
)


def _entity_has_bounds(entity: Any) -> bool:
    bounds = getattr(entity, "bounds", None)
    try:
        return bool(bounds) and float(bounds[2]) > 0 and float(bounds[3]) > 0
    except (TypeError, ValueError, IndexError):
        return False


def _ground_label_to_entity(world: WorldModel, label: str) -> Any:
    """Ground a model target *label* to a perceived entity with real bounds.

    Routes through the vision-aware reference resolver, which scores candidates by
    name match — so 'Kulvinder Ji' resolves to the chat row, not the search-box
    OCR echo or a '…- Video call' affordance the downstream shortest-label rescan
    would grab. Returns None when nothing resolves confidently, leaving the
    existing label path untouched.
    """
    lbl = str(label or "").strip()
    if not lbl:
        return None
    try:
        from plugin.agent.resolver import get_reference_resolver

        res = get_reference_resolver().resolve(world, lbl)
    except Exception:
        return None
    winner = getattr(res, "winner", None)
    if winner is not None and _entity_has_bounds(winner):
        return winner
    for cand in getattr(res, "candidates", None) or []:
        ent = getattr(cand, "entity", None)
        if ent is None:
            eid = getattr(cand, "entity_id", None)
            ent = world.entities.get(eid) if eid is not None else None
        if (
            ent is not None
            and getattr(ent, "visible", True)
            and _entity_has_bounds(ent)
            and float(getattr(cand, "name_similarity", 0.0) or 0.0) >= 0.6
        ):
            return ent
    return None


def proposal_to_action(
    proposal: UnifiedProposal,
    goal: Goal,
    world: WorldModel,
    features: Optional[StateFeatures] = None,
) -> Tuple[Optional[Action], str]:
    """Validate a proposal and convert it into an executable Action.

    Returns ``(action, reason)``. ``action`` is None when the proposal is not
    admissible; ``reason`` always explains the outcome for the trace.
    """
    from plugin.agent.decision import DecisionEngine

    raw_family = str(proposal.next_action.get("family") or "").strip().lower().replace("-", "_")
    if not raw_family:
        return None, "no_family"
    if raw_family in {"observe", "request_more_evidence"}:
        return None, f"model_requested_{raw_family}"

    verb = _VERB_TO_RUNTIME.get(raw_family, "")
    if verb:
        family = _VERB_TO_FAMILY.get(raw_family, raw_family)
        # Motor aliases (right_click → reveal_actions) should carry the
        # capability's runtime verb, not the motor's.
        if family != raw_family and family in _VERB_TO_RUNTIME:
            verb = _VERB_TO_RUNTIME[family]
    else:
        # The model named an action family rather than a verb.
        family = DecisionEngine._classify_perception_family(raw_family)
        if family not in DecisionEngine._CANONICAL_ACTION_FAMILIES:
            return None, f"unknown_family:{raw_family}"
        verb = _family_verb(family)
    if not verb:
        return None, f"no_verb_for_family:{family}"

    text = str(proposal.next_action.get("text") or "").strip()
    entity = _resolve_target_entity(world, proposal.next_action.get("target_id"))
    semantic_target = str(getattr(entity, "label", "") or "").strip()
    if not semantic_target:
        semantic_target = str(proposal.next_action.get("target_label") or "").strip()
    # Entity-shaped capabilities: models often put the name in text.
    if family in {"open_entity", "select_content", "reveal_actions"} and not semantic_target:
        semantic_target = text
    # Geometry-first grounding: the model named a pointer target but gave no
    # resolvable target_id. Ground the label to a *perceived* entity now so the
    # decision carries an entity id + bounds — the runtime then clicks exactly
    # where the perceptor saw the target instead of re-resolving a noisy-OCR
    # string downstream (which grabbed the search-box echo / a call affordance).
    if entity is None and family in _GROUNDED_POINTER_FAMILIES:
        grounded = _ground_label_to_entity(world, semantic_target or text)
        if grounded is not None:
            entity = grounded
            if not semantic_target:
                semantic_target = str(getattr(entity, "label", "") or "").strip()

    confidence = proposal.confidence
    rationale_family = raw_family
    action = Action(
        action=verb,
        semantic_target=semantic_target,
        text=text,
        rationale=(
            f"unified multimodal cognition: {rationale_family} "
            f"(surface={proposal.observed_state.get('surface') or 'unknown'}) "
            f"confidence={round(confidence, 3)}"
        ),
        expected_predicate=str((proposal.expected_transition or {}).get("surface") or ""),
        action_family=family,
        evidence_score=confidence,
        target_entity_id=getattr(entity, "id", None) if entity is not None else None,
        grounding_confidence=confidence,
        grounding_reason="unified_multimodal",
        frontier_label=f"unified:{family}:{text or semantic_target}".strip(":"),
        frontier_score=round(confidence, 4),
        reversible=family != "commit_irreversible",
    )
    if family == "scroll_content":
        action.scroll_direction = str(proposal.next_action.get("direction") or "down")
        action.scroll_amount = int(proposal.next_action.get("amount") or 3)

    # Runtime admissibility: a pointer action must resolve to something real --
    # an AX entity, a screen point, or at minimum a label to search for.
    if family not in _KEYBOARD_FAMILIES and entity is None:
        action.target_point = _to_screen_point(
            proposal.next_action.get("target_point"), proposal.point_scale
        )
        if action.target_point is None and not semantic_target:
            return None, "pointer_action_without_target"
    if family == "type_query" and not text:
        return None, "type_without_text"
    if family == "locate_content" and not text:
        # The runtime supplies the mechanism, never the query -- what to look
        # for is the judgment the model is here to make.
        return None, "locate_without_query"
    if family in {"open_entity", "select_content", "reveal_actions"}:
        if not action.semantic_target and action.target_point is None:
            return None, f"{family}_without_target"
    if family in {"invoke_affordance", "commit_irreversible"} and not text:
        return None, f"{family}_without_label"
    return action, "admissible"


def _family_verb(family: str) -> str:
    return {
        "open_contact": "Click",
        "select_content": "SelectContent",
        "open_search": "Click",
        "forward_message": "Click",
        "select_forward_target": "Click",
        "start_call": "Click",
        "end_call": "Click",
        "explore_chrome": "Click",
        "type_query": "Type",
        "probe_hover": "RevealActions",
        "probe_context_menu": "RevealActions",
        "probe_focus": "Click",
        "scroll_content": "Scroll",
        "dismiss": "Dismiss",
        "dismiss_transient": "Dismiss",
        "compose_search_query": "ComposeSearchQuery",
        "resolve_entity": "ResolveEntity",
        "locate_content": "LocateContent",
        "open_entity": "OpenEntity",
        "reveal_actions": "RevealActions",
        "invoke_affordance": "InvokeAffordance",
        "commit_irreversible": "CommitIrreversible",
    }.get(family, "")


def should_escalate(
    proposal: Optional[UnifiedProposal],
    features: StateFeatures,
    *,
    admissible: bool,
) -> Tuple[bool, str]:
    """Decide whether to consult the deep text reasoner.

    Escalation is the exception, not the fast path: only on low confidence,
    unresolved contradictions, repeated failure, or an inadmissible proposal.
    """
    extras = features.extras if isinstance(features.extras, dict) else {}
    if proposal is None:
        return True, "no_proposal"
    if not admissible:
        return True, "inadmissible_proposal"
    if proposal.confidence < unified_min_confidence():
        return True, f"low_confidence:{round(proposal.confidence, 3)}"
    # Missing evidence is not by itself a veto. A perceptor that notes "AX
    # publishes no node for the search bar" while still locating that bar in
    # the pixels and proposing a confident, grounded click is doing exactly
    # what the unified design asks of it. Only escalate when the gaps come
    # with genuine doubt.
    if proposal.missing_evidence and proposal.confidence < _CONFIDENT_DESPITE_GAPS:
        return True, f"missing_evidence_at_confidence:{round(proposal.confidence, 3)}"
    try:
        stalled = int(extras.get("no_progress_replans") or 0)
    except (TypeError, ValueError):
        stalled = 0
    if stalled >= 3:
        return True, f"branch_exhaustion:{stalled}"
    return False, ""
