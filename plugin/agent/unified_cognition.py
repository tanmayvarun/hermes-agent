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

from plugin.perception.capture_frame import CaptureFrame

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

# A safety bound on a pathological tree, not a relevance filter. It was 24, with
# entities *ranked by goal-term overlap* and the rest discarded — which withheld
# exactly the controls a task needs and never names: the Forward menu item, the
# composer, the New-chat button all score near zero against "zarooratwala" and
# were dropped, while the affordance frontier went on telling the model those
# actions existed. Redundant evidence costs a capable model nothing; missing
# evidence costs it the inference. Measured, the saving was not worth having:
# 24 entities is ~1.25k tokens and a full 120-entity window ~6.5k, against a
# context two orders of magnitude larger. Scoring now decides *order* only, so
# the goal-relevant items still arrive first where attention is cheapest.
MAX_AX_EVIDENCE = 200

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
    """Authoritative perceptor path: one multimodal pass is the primary loop.

    This is the perceptor -> world-critic -> brain loop the architecture targets:
    it carries the prior world document plus the last action's predicted-vs-actual
    outcome back into the model, so surprise forces a history-aware re-perception.
    The split ``perception_synthesis`` path is retained only as a fallback for when
    this declines or returns a low-confidence / inadmissible proposal. Set
    ``HERMES_UNIFIED_COGNITION=0`` to A/B against the legacy split path.
    """
    raw = os.getenv("HERMES_UNIFIED_COGNITION", "1").strip().lower()
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
    # Where the model's (0, 0) sits on screen, in points. Non-zero whenever the
    # frame was scoped to a window rather than the whole display, which is the
    # normal case: the capture deliberately excludes occluding windows.
    point_origin: Tuple[float, float] = (0.0, 0.0)
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


# The whole read reaches the model. A cap here would drop lines the AX tree also
# withheld -- the two sources are blind in different places, which is the reason
# for having both -- and trimming the tail silently loses whatever sits at the
# bottom of a list, where an unread message usually is.
MAX_PACKET_OCR_LINES = 200


def _enumerate_sources(
    world: WorldModel, goal: Goal, features: StateFeatures
) -> List[Dict[str, Any]]:
    """Declare every perception input, whether it fired, and why.

    One perceptor, all inputs enumerated. The model is the only party that can
    sensibly decide whether a line of read text and an accessibility element are
    the same control, so it is handed each source and told the state of each --
    rather than the runtime reconciling them first and showing the model its
    verdict.

    Declaring a source that did *not* fire matters as much as one that did. A
    model told nothing about OCR cannot tell "there is no text on this surface"
    from "nobody read the text", and those call for opposite responses: trust the
    empty reading, or look harder at the pixels. The same holds for a chrome-only
    accessibility tree, which is not evidence that the screen is empty.
    """
    extras = features.extras if isinstance(features.extras, dict) else {}
    node_count = int(extras.get("observation_node_count") or 0)
    content_count = int(extras.get("app_content_node_count") or 0)
    sources: List[Dict[str, Any]] = []

    screenshot = str(getattr(world, "last_screenshot_path", "") or "")
    sources.append(
        {
            "source": "screenshot",
            "state": "on" if screenshot else "unavailable",
            "why": (
                "always supplied; the authoritative account of the screen"
                if screenshot
                else "no capture this frame — reason with the other sources only"
            ),
        }
    )

    if content_count > 0:
        ax_state, ax_why = "on", f"{content_count} content nodes exposed"
    elif node_count > 0:
        ax_state, ax_why = (
            "chrome_only",
            "window chrome only, no content — absence here is not evidence the "
            "screen is empty; read the pixels",
        )
    else:
        ax_state, ax_why = "empty", "the app exposed no accessibility tree this frame"
    sources.append(
        {
            "source": "accessibility",
            "state": ax_state,
            "why": ax_why,
            "node_count": node_count,
            "content_node_count": content_count,
        }
    )

    ocr_lines = [
        line for line in (getattr(world, "last_ocr_lines", None) or []) if isinstance(line, dict)
    ]
    try:
        from plugin.perception.macos.fusion.coverage import ocr_enabled

        ocr_allowed = ocr_enabled()
    except Exception:
        ocr_allowed = True
    if not ocr_allowed:
        ocr_entry: Dict[str, Any] = {
            "source": "ocr",
            "state": "off",
            "why": "disabled for this run — no text was read, so do not treat "
            "missing text as absent text",
        }
    elif ocr_lines:
        ocr_entry = {
            "source": "ocr",
            "state": "on",
            "why": "text read from the screenshot, bounds in screen points; "
            "corroborates the pixels but may split or clip words",
            "lines": ocr_lines[:MAX_PACKET_OCR_LINES],
        }
    else:
        ocr_entry = {
            "source": "ocr",
            "state": "empty",
            "why": "ran but read no text on this surface",
        }
    sources.append(ocr_entry)
    return sources


def _ax_evidence(world: WorldModel, goal: Goal, limit: int = MAX_AX_EVIDENCE) -> List[Dict[str, Any]]:
    """Serialize every visible entity with stable ids AND bounds.

    Bounds matter: without them the model can describe a control but cannot
    tell the runtime which pixel region it means, which is what forced the old
    label-matching guesswork.

    The goal-term score orders the list; it does not decide who is in it. Ranking
    by relevance and truncating is the runtime pre-judging what the model needs,
    which is the judgement being moved *into* the model — and it withholds the
    unnamed controls (Forward, the composer) that a task turns on.
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
            item.get("point") or item.get("target_point"),
            proposal.point_scale,
            proposal.point_origin,
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
                # The model's own name for this object ("kulvinder_ji_row"). Its
                # ids are strings and these entities are keyed by int, so without
                # keeping it there is no way back from the id the model cites in
                # target_id to the object it meant, and the runtime has to guess
                # from the label instead — which is how a click aimed at a chat
                # row landed on the search field echoing the same name.
                "vision_object_id": str(item.get("id") or "").strip(),
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
        point_origin=tuple(getattr(execution_state, "unified_point_origin", (0.0, 0.0)) or (0.0, 0.0)),
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


def _norm_text(value: Any) -> str:
    """Lowercased, whitespace-collapsed text for comparing names across sources."""
    return " ".join(str(value or "").strip().lower().split())


def prediction_error(
    expectation: Optional[Dict[str, Any]], document: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """Compare what the last action was predicted to produce against what appeared.

    The agent predicts a surface and the controls it expects to find there, and
    that prediction is the only thing that makes a result informative: without it
    a screen is just a screen, and with it an unchanged screen is evidence that
    the agent's model of what a control does is wrong. Naming the mismatch is
    what turns an execution into something to learn from.

    Both halves already existed -- the model emitted expected_transition, the
    runtime stored it and handed it back as you_predicted -- but nothing ever put
    them side by side. The comparison was left implicit, for the model to notice
    on its own while simultaneously perceiving the screen, updating its world
    model and choosing a move. It did not notice: on a live run it predicted a
    context menu, got the unchanged conversation, and re-issued the same
    right-click three times.

    Deliberately structural rather than task-specific: a predicted surface and a
    set of expected controls describe a step in any application, so this reads
    the same for a file dialog or a checkout page as for a chat.
    """
    if not isinstance(expectation, dict) or not expectation:
        return {}
    predicted_surface = _norm_text(expectation.get("surface"))
    if not predicted_surface:
        return {}

    doc = document if isinstance(document, dict) else {}
    observed_surface = _norm_text(doc.get("surface"))

    # What the screen actually offers, by visible text and by the kind the model
    # assigned. Both are consulted because a control is named either way: a menu
    # item reads "Forward", while a composer is recognised as kind=input_field.
    haystack: List[str] = []
    for item in doc.get("objects") or []:
        if not isinstance(item, dict):
            continue
        for key in ("text", "kind", "id"):
            value = _norm_text(item.get(key))
            if value:
                haystack.append(value)

    expected_controls = [
        _norm_text(control)
        for control in (expectation.get("likely_controls") or [])
        if _norm_text(control)
    ]
    found = [c for c in expected_controls if any(c in text or text in c for text in haystack)]
    missing = [c for c in expected_controls if c not in found]

    surface_matched = bool(observed_surface) and (
        observed_surface == predicted_surface
        or predicted_surface in observed_surface
        or observed_surface in predicted_surface
    )
    # A prediction is borne out when the surface arrived, or -- when the surface
    # name differs but the controls are all there -- when the thing predicted is
    # plainly present under another name. Surface vocabularies drift between
    # frames ("context_menu" vs "message_actions") and punishing that would
    # manufacture errors out of synonyms.
    controls_matched = bool(expected_controls) and not missing
    matched = surface_matched or controls_matched

    if matched:
        verdict = (
            f"prediction held: expected {predicted_surface!r} and the screen reads "
            f"{observed_surface or 'the same'!r}"
        )
    elif not observed_surface:
        verdict = (
            f"you predicted {predicted_surface!r}; this frame reports no surface at all, "
            "so the prediction could not be checked"
        )
    else:
        verdict = (
            f"you predicted {predicted_surface!r} and the screen is {observed_surface!r}. "
            + (
                f"None of the controls you expected are present ({', '.join(expected_controls[:4])})."
                if expected_controls and not found
                else f"Missing: {', '.join(missing[:4])}."
                if missing
                else "The surface you expected did not appear."
            )
        )

    out: Dict[str, Any] = {
        "predicted_surface": predicted_surface,
        "observed_surface": observed_surface,
        "matched": matched,
        "verdict": verdict,
    }
    if expected_controls:
        out["controls_predicted"] = expected_controls[:8]
        out["controls_present"] = found[:8]
        out["controls_absent"] = missing[:8]
    return out


def note_prediction_error(execution_state: Any, proposal: Optional["UnifiedProposal"]) -> Dict[str, Any]:
    """Score the standing prediction against this reading, before it is replaced.

    Order matters: ``_remember_reading`` overwrites the stored expectation with
    the *new* prediction, so the comparison has to happen while the previous one
    is still there.
    """
    if execution_state is None or proposal is None:
        return {}
    expectation = getattr(execution_state, "unified_last_expectation", None)
    error = prediction_error(expectation, proposal.world_model)
    try:
        execution_state.last_prediction_error = error
    except Exception:
        pass
    return error


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

    Complete over compact, where completeness is affordable. Redundancy between
    the sources costs a capable model nothing — it can ignore an OCR line that
    repeats an AX label — whereas an input withheld because the runtime judged it
    irrelevant can cost the whole inference, and that judgement is precisely what
    this design moves into the model. So sources are gated on *cost and
    availability*, never on relevance, and a source that was withheld is declared
    as such rather than silently omitted (see _enumerate_sources).

    What stays out is bounded by measurement rather than instinct: every prior
    world document and the whole capability graph are genuinely large, while the
    visible entity list and the OCR read are a few thousand tokens against a
    context two orders of magnitude bigger.
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
        # Every input, with its gate state. See _enumerate_sources: the model
        # does the fusing, so it needs to know what it was and was not given.
        "sources": _enumerate_sources(world, goal, features),
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

    stuck = _stuck_report(execution_state)
    if stuck:
        packet["stuck_signals"] = stuck

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
        frontier = build_affordance_frontier(
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
    # The build is memoryless — it re-derives every control from this frame's
    # evidence. The critic's accepted reality is what carries across frames:
    # controls already measured inert are withdrawn, and controls a confirmed
    # reveal put on screen stop being described as latent.
    try:
        from plugin.agent.world_critic import reconcile_frontier

        step = getattr(execution_state, "last_plan_step", None)
        frontier = reconcile_frontier(
            frontier,
            document=document,
            execution_state=execution_state,
            last_action_family=str(getattr(step, "action_family", "") or ""),
        )
    except Exception:
        pass
    return frontier


def _stuck_report(execution_state: Any) -> Dict[str, Any]:
    """How long nothing has advanced, and which moves have been tried repeatedly.

    Facts the runtime measures and the model cannot: it sees one frame and its
    own previous document, so it has no clock and no memory of a loop it has
    been in. Reported as measurements, not as instructions — whether ten minutes
    on one step means "keep going, this is a slow search" or "this branch is
    dead" depends on the screen, which is the model's to read.
    """
    out: Dict[str, Any] = {}
    try:
        since = float(getattr(execution_state, "seconds_since_progress", 0.0) or 0.0)
    except (TypeError, ValueError):
        since = 0.0
    budget = 0.0
    try:
        budget = float(getattr(execution_state, "no_progress_budget_s", 0.0) or 0.0)
    except (TypeError, ValueError):
        budget = 0.0
    if since > 0:
        out["seconds_since_anything_advanced"] = round(since, 1)
        if budget > 0:
            out["seconds_before_this_counts_as_stalled"] = round(budget, 1)
            out["stalled"] = since >= budget

    ledger = getattr(execution_state, "action_attempts", None)
    if isinstance(ledger, dict) and ledger:
        tried = [
            {
                "family": str(entry.get("family") or ""),
                "target": str(entry.get("target") or ""),
                "attempts": int(entry.get("attempts") or 0),
                "effects": [str(e) for e in (entry.get("effects") or [])][-3:],
            }
            for entry in ledger.values()
            if isinstance(entry, dict) and int(entry.get("attempts") or 0) >= 2
        ]
        tried.sort(key=lambda item: item["attempts"], reverse=True)
        if tried:
            out["moves_already_tried_more_than_once"] = tried[:8]
    return out


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

    # The prediction scored against what actually appeared. Handing over the
    # prediction and the screen separately and leaving the comparison implicit was
    # not enough: the model has to perceive, update its world model and choose a
    # move in the same call, and the check quietly went unmade — three identical
    # right-clicks after three predictions of a menu that never opened. The
    # mismatch is cheap for the runtime to compute and unambiguous once named.
    error = getattr(execution_state, "last_prediction_error", None)
    if isinstance(error, dict) and error:
        out["prediction_error"] = error

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

    # The same fact without the "in a row" qualifier, which is the one that
    # matters. A stuck agent rarely repeats a move twice running: the failure
    # prompts a different move, which fails too and leads back. So the
    # consecutive counter stays at 1 through a loop that has burned ten minutes,
    # and the model — told nothing — reads every attempt as its first. This is
    # the total, so an alternating loop is visible as one.
    try:
        total = execution_state.attempts_for(
            family=out.get("family") or out.get("action") or "",
            target=str(getattr(step, "semantic_target", "") or getattr(step, "text", "") or ""),
            surface=str(getattr(execution_state, "accepted_surface", "") or ""),
        )
    except Exception:
        total = 0
    if total >= 2:
        out["times_tried_here_in_total"] = total

    # Perception-history contract: the surprise history, fed from the *first*
    # surprise. Withholding it until a second failure meant the one look that
    # could diagnose the first failure was the one look that lacked the evidence
    # to do it — the agent had to fail twice before it was allowed to reason
    # about failing. The model needs the attempt that just failed in hand to
    # infer why it failed and what to try instead.
    history = getattr(execution_state, "recent_surprises", None)
    if isinstance(history, list) and history:
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
    "observation.sources lists every input and the state of each, because you "
    "are the one who reconciles them -- nothing upstream has decided which "
    "source is right. Read the state before trusting an absence. accessibility "
    "state chrome_only means the app exposed a window frame and no content: that "
    "is not evidence the screen is empty, it means read the pixels. ocr state "
    "off means nobody read the text this frame, so missing text is not absent "
    "text. ocr state on carries lines with bounds already in screen points; they "
    "corroborate what you see but may clip or split words, so treat a partial "
    "match as support rather than contradiction.\n\n"
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
    "Whenever the next action acts on something you can see, set "
    "next_action.target_id to that object's id from world_model.objects, and "
    "mark that object matches_goal. The id is how you say which one you mean: "
    "a name alone is ambiguous on exactly the screens that matter, because a "
    "search field holding the query reads as the same text as the row you typed "
    "it to find, and without an id the choice falls back to text and takes the "
    "field.\n"
    "compose_search_query: author the next search string. "
    "resolve_entity: choose which visible candidate matches a goal referent — "
    "name it with target_id. "
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
    "issued this same move. you_predicted is what you said this action would "
    "produce, and prediction_error is that prediction already scored against the "
    "screen: matched=false with a verdict naming what you expected and what is "
    "actually there. Treat a prediction_error as the most informative thing in "
    "the packet. It does not merely say the move failed; it says your model of "
    "what that control does is wrong, and that is what has to change. Before "
    "choosing, state in progress.notes why you think the prediction failed — the "
    "control was not where you thought, it needed a different gesture, something "
    "intercepted it, the object you aimed at was not the one you meant — and let "
    "that hypothesis pick your next move. Reissuing the move that produced the "
    "error is never the answer.\n"
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
    "stuck_signals is the clock and the ledger, which you have no other way to "
    "see: you get one frame and your own last document, so you cannot tell a "
    "first attempt from a tenth, or ten seconds from ten minutes. "
    "seconds_since_anything_advanced is real elapsed time with no measurable "
    "progress, and moves_already_tried_more_than_once lists what you have "
    "issued repeatedly with what came of it — including moves you alternated "
    "with something else, which times_repeated_in_a_row cannot show. A move "
    "listed there with no effect will not start working on this attempt: change "
    "the target, the capability, or the branch. If minutes have passed on one "
    "step, say in progress.notes what you believe is blocking it and act on a "
    "different hypothesis. These are measurements, not orders — a long hunt "
    "through a conversation is legitimately slow, and you can see whether the "
    "screen is moving.\n"
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


def screen_point_scale(
    screenshot_path: str, image_width: int, capture: Optional[CaptureFrame] = None
) -> float:
    """Points on screen per unit in the image the model was shown.

    Two reductions separate the model's picture from the screen. The frame is
    downscaled before it is sent, so the model answers in the picture's
    coordinates; and the capture itself is in backing pixels, which on a Retina
    panel are half a point each. Executing the model's numbers unconverted put
    every pointer action off by the product of the two -- far enough to
    right-click the message below the one that was chosen, which read as the
    model misidentifying the target rather than as a units bug.

    The Retina half is taken from the measured capture transform rather than
    from the main screen's width. The capture is scoped to a *window*, so
    comparing its width to the whole display's answers a different question and
    silently returns a plausible wrong number.
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
    frame = capture or CaptureFrame()
    pixels_per_point = frame.scale if frame.scale > 0 else 1.0
    return (captured_width / float(image_width)) / pixels_per_point


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
    capture = CaptureFrame.from_dict(getattr(world, "last_capture_frame", None))
    point_scale = screen_point_scale(screenshot_path, image_size[0], capture)
    point_origin = (capture.origin_x, capture.origin_y)

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
        # The single largest cost in an iteration, and previously visible only
        # inside the decision trace, where nothing summarising the run would find
        # it. The loop reports it per iteration so time spent is attributable.
        if execution_state is not None:
            try:
                execution_state.last_perception_latency_s = float(proposal.latency_s)
            except Exception:
                pass
        proposal.point_scale = point_scale
        proposal.point_origin = point_origin
        # Carry the transform forward so the reading can be faithfully
        # re-projected onto the world between model calls (see
        # reproject_unified_reading).
        if execution_state is not None:
            try:
                execution_state.unified_point_scale = point_scale
                execution_state.unified_point_origin = point_origin
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
        # Score the standing prediction first: _remember_reading replaces it with
        # this frame's prediction, and after that the previous one is gone.
        error = note_prediction_error(execution_state, proposal)
        if error:
            logger.info(
                "Prediction %s: %s",
                "held" if error.get("matched") else "ERROR",
                error.get("verdict"),
            )
        _remember_reading(execution_state, proposal)
        persist_world_document(execution_state, proposal)
        # The critic has settled what is true; now decide what to do about it.
        consult_next_capability(proposal, goal, features, execution_state)
        materialize_vision_entities(world, proposal)
        publish_scene_to_world(world, proposal)
        # Fill the perception extras the decision layer reads, from this reading
        # rather than from a second perceptor's.
        try:
            if features is not None and isinstance(features.extras, dict):
                verdict_obj = getattr(execution_state, "last_critic_verdict", None)
                extras_payload = unified_perception_extras(proposal, verdict_obj)
                if extras_payload:
                    features.extras["perception_llm"] = extras_payload
                    features.extras["perception_task"] = UNIFIED_TASK
                    features.extras["perception_summary"] = {
                        "screen_type": extras_payload.get("screen_type"),
                        "application": extras_payload.get("application"),
                        "active_surface": extras_payload.get("active_surface"),
                        "likely_next_family": extras_payload.get("likely_next_family"),
                        "likely_next_target": extras_payload.get("likely_next_target"),
                        "confidence": extras_payload.get("confidence"),
                    }
                narration = str(
                    getattr(execution_state, "last_perception_narration", "") or ""
                )
                if narration:
                    features.extras["perception_human_readable"] = narration
        except Exception:
            pass
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


def _verdict_view(verdict: Any) -> Dict[str, Any]:
    """Normalise a ``CriticVerdict`` or its serialized form into one shape.

    The verdict is an object where it is produced and a dict where it is carried
    on execution state. Accepting both spares every caller from having to know
    which side of that boundary it is on.
    """
    if verdict is None:
        return {"accepted_document": {}, "decisions": []}
    if isinstance(verdict, dict):
        raw_decisions = verdict.get("decisions") or []
        accepted = verdict.get("accepted_document") or {}
    else:
        raw_decisions = list(getattr(verdict, "decisions", None) or [])
        accepted = getattr(verdict, "accepted_document", None) or {}
    decisions: List[Dict[str, Any]] = []
    for item in raw_decisions:
        if isinstance(item, dict):
            decisions.append(item)
            continue
        decisions.append(
            {
                "field": str(getattr(item, "field", "") or ""),
                "verdict": str(getattr(item, "verdict", "") or ""),
                "reason": str(getattr(item, "reason", "") or ""),
            }
        )
    return {
        "accepted_document": dict(accepted) if isinstance(accepted, dict) else {},
        "decisions": decisions,
    }


def unified_perception_extras(
    proposal: Optional[UnifiedProposal],
    verdict: Optional[Any] = None,
) -> Dict[str, Any]:
    """The perception extras the decision layer reads, from the unified reading.

    These keys originated with the legacy perceptor, but six places in the
    decision layer read them -- candidate value scoring, both selector prompts,
    storage-pressure recovery and the obscured-app check -- so they are
    load-bearing no matter which perceptor produced them. Deriving them from the
    unified reading is what makes the second perceptor *redundant* rather than
    merely switched off; disabling it without this would silently drop the
    family recommendation that decision promotion depends on.

    Two mappings are worth naming. ``contradictions`` is the critic's override
    list: a field the critic refused is, precisely, a contradiction between what
    the model proposed and what the carried document can support. And
    ``needs_followup_observe`` comes from the model's own declared coverage and
    evidence gaps, which is the honest form of the question the old mechanical
    source-agreement score was reaching for.
    """
    if proposal is None:
        return {}
    view = _verdict_view(verdict)
    accepted = dict(view["accepted_document"] or proposal.world_model or {})
    state = proposal.observed_state or {}
    surface = str(accepted.get("surface") or state.get("surface") or "").strip().lower()
    action = proposal.next_action or {}
    gaps = [str(gap).strip() for gap in (proposal.evidence_gaps or []) if str(gap).strip()]
    coverage = float(proposal.coverage if proposal.coverage is not None else 1.0)

    contradictions: List[str] = []
    for decision in view["decisions"]:
        if str(decision.get("verdict") or "") == "accept":
            continue
        field_name = str(decision.get("field") or "?")
        contradictions.append(f"{field_name}: {str(decision.get('reason') or '')[:140]}")

    evidence = [str(item).strip() for item in (proposal.missing_evidence or []) if str(item).strip()]
    summary = proposal.summary_text().strip()
    return {
        "source": "unified_cognition",
        "screen_type": _SURFACE_TO_SCREEN_TYPE.get(surface, "unknown"),
        "application": str(state.get("app") or ""),
        "active_surface": surface,
        "likely_next_family": str(action.get("family") or ""),
        "likely_next_target": str(action.get("target_label") or action.get("target") or ""),
        "likely_next_text": str(action.get("text") or ""),
        "confidence": round(float(proposal.confidence or 0.0), 4),
        "supporting_evidence": ([summary] if summary else []) + evidence[:4],
        "contradictions": contradictions[:4],
        "needs_followup_observe": bool(gaps) or coverage < 0.7,
        "coverage": round(coverage, 3),
        "evidence_gaps": gaps[:6],
        # No source for this in the unified reading: the legacy perceptor named
        # families to avoid, whereas the unified path withdraws dead controls
        # through the affordance frontier instead. Left empty rather than
        # invented, since value scoring turns it straight into a penalty.
        "avoid_families": [],
    }


def narrate_perception(
    proposal: Optional[UnifiedProposal],
    verdict: Optional[Any] = None,
    *,
    frame: int = 0,
) -> str:
    """Render one perception frame as prose a developer can read mid-run.

    Perception is the stage most in need of narration and the least able to
    supply it: the model's reading is a nested JSON document and the critic's
    judgement is a list of per-field verdicts, neither legible while a run is in
    flight. Both are rendered together because the useful question is rarely
    what the model saw on its own -- it is what the model saw and how much of
    that the critic let through. A reading that was overruled and a reading that
    was accepted look identical in the accepted document, and the difference is
    usually the whole story.
    """
    if proposal is None:
        return ""
    view = _verdict_view(verdict)
    accepted = dict(view["accepted_document"] or proposal.world_model or {})
    surface = str(accepted.get("surface") or "").strip()
    open_conversation = str(accepted.get("open_conversation") or "").strip()
    head = f"Perception frame {frame}: surface={surface or 'unknown'}"
    if open_conversation:
        head += f" open={open_conversation!r}"
    reading = proposal.summary_text().strip() or "no reading returned"
    lines = [f"{head} — {reading}"]

    objects = [item for item in (accepted.get("objects") or []) if isinstance(item, dict)]
    if objects:
        shown: List[str] = []
        for item in objects[:6]:
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            kind = str(item.get("kind") or "").strip()
            mark = " <-- matches goal" if item.get("matches_goal") else ""
            shown.append(f"{text[:48]!r}{f' [{kind}]' if kind else ''}{mark}")
        if shown:
            more = len(objects) - len(shown)
            noun = "object" if len(objects) == 1 else "objects"
            lines.append(
                f"  saw {len(objects)} {noun}: "
                + ", ".join(shown)
                + (f" (+{more} more)" if more > 0 else "")
            )

    coverage = float(proposal.coverage if proposal.coverage is not None else 1.0)
    gaps = [str(gap).strip() for gap in (proposal.evidence_gaps or []) if str(gap).strip()]
    if coverage < 0.999 or gaps:
        note = f"  coverage {coverage:.2f}"
        if gaps:
            note += "; could not establish: " + "; ".join(gaps[:3])
        lines.append(note)

    # The critic's half. Only its interventions are worth spelling out: a run of
    # accepts means the reading passed intact, which is one line rather than one
    # line per field.
    overrides: List[str] = []
    accepted_fields = 0
    for decision in view["decisions"]:
        call = str(decision.get("verdict") or "")
        if call == "accept":
            accepted_fields += 1
            continue
        name = str(decision.get("field") or "?")
        reason = str(decision.get("reason") or "")[:110]
        overrides.append(f"{name} {call} ({reason})")
    if overrides:
        lines.append("  critic overrode: " + "; ".join(overrides[:4]))
    elif accepted_fields:
        lines.append(f"  critic accepted the update intact ({accepted_fields} fields)")
    return "\n".join(lines)


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
        # The judge is consulted only for a change the deterministic rules cannot
        # account for, which on an ordinary frame is never. None when disabled,
        # in which case the rules decide alone.
        try:
            from plugin.agent.critic_coherence import (
                judge_for_critic,
                surface_judge_for_critic,
            )

            judge = judge_for_critic()
            surface_judge = surface_judge_for_critic()
        except Exception:
            judge = None
            surface_judge = None
        verdict = critique_world_proposal(
            prior if isinstance(prior, dict) else {},
            dict(proposal.world_model),
            last_action=last_action,
            observed_surface=observed,
            coherence_judge=judge,
            surface_judge=surface_judge,
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
        # The completed perception, in prose. Stashed rather than logged here so
        # the controller can put it in the run log next to the decision it
        # produced; a developer reading a run needs the two adjacent.
        narration = narrate_perception(
            proposal, verdict, frame=int(getattr(execution_state, "unified_frame", 0) or 0)
        )
        if narration:
            execution_state.last_perception_narration = narration
            # Stamp the frame the prose describes. The narration outlives the call
            # that produced it, so a frame where the perceptor did not run (no
            # screenshot, a failed call) would otherwise re-log the previous
            # reading as though it were current — the most misleading thing a
            # perception log can do, since it reads as confirmation that the agent
            # saw a screen it never looked at.
            execution_state.last_perception_narration_frame = int(
                getattr(execution_state, "unified_frame", 0) or 0
            )
            logger.info("%s", narration)
        # The same measured outcome that settles what is true also settles what
        # can be done: now that the accepted surface is known, record whether the
        # last action proved its affordance inert. The next frontier withdraws it.
        try:
            from plugin.agent.world_critic import note_topology_evidence

            attribution = getattr(execution_state, "last_attribution", None) or {}
            step = getattr(execution_state, "last_plan_step", None)
            condemned = note_topology_evidence(
                execution_state,
                last_action_family=last_action,
                last_target=str(getattr(step, "semantic_target", "") or ""),
                effect_kind=str(attribution.get("effect_kind") or ""),
                surface=verdict.surface,
            )
            if condemned is not None:
                logger.info(
                    "World critic condemned affordance %s (%s)",
                    condemned.get("key"),
                    condemned.get("reason"),
                )
        except Exception:
            pass
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


def _to_screen_point(
    point: Any, scale: float, origin: Tuple[float, float] = (0.0, 0.0)
) -> Optional[Tuple[int, int]]:
    """Convert a point in the model's image into a point on the screen.

    The origin matters as much as the scale: perception grabs the task app's
    window, not the whole screen, so the model's (0, 0) is the window's corner
    and not the display's. Scaling alone leaves every click short by the window
    offset -- roughly the height of the menu bar vertically, which is enough to
    land on the row above the one that was chosen.
    """
    if not isinstance(point, (list, tuple)) or len(point) != 2:
        return None
    try:
        factor = float(scale) if scale and float(scale) > 0 else 1.0
        return (
            round(float(origin[0]) + float(point[0]) * factor),
            round(float(origin[1]) + float(point[1]) * factor),
        )
    except (TypeError, ValueError):
        return None


def _resolve_target_entity(world: WorldModel, target_id: Any) -> Any:
    """Find the entity the model cited, by int key or by its own object id.

    The model names its objects in words ("kulvinder_ji_row"); the entity table
    is keyed by int. Accepting only the int form silently dropped every explicit
    choice the model made and left the target to be re-derived from its label,
    where an exact-string echo of the same name in a search field outscores the
    row that was actually meant. The model's choice is the least ambiguous signal
    available and should be the first thing consulted, not the discarded one.
    """
    if target_id in (None, ""):
        return None
    try:
        key = int(target_id)
    except (TypeError, ValueError):
        key = None
    if key is not None:
        entity = world.entities.get(key)
        if entity is None or not getattr(entity, "visible", True):
            return None
        return entity

    wanted = str(target_id).strip().lower()
    if not wanted:
        return None
    for entity in world.entities.values():
        if not getattr(entity, "visible", True):
            continue
        attrs = getattr(entity, "attributes", None)
        if not isinstance(attrs, dict):
            continue
        if str(attrs.get("vision_object_id") or "").strip().lower() == wanted:
            return entity
    return None


# Pointer families whose target must be a concrete perceived object. When the
# model names one by label but gives no resolvable target_id, we ground the
# label to a perceived entity so the decision carries geometry (an entity id +
# bounds), not a bare string the runtime would have to re-resolve.
#
# resolve_entity belongs here even though it reads as bookkeeping: the protocol
# offers it as "choose which visible candidate matches a goal referent", and the
# runtime turns that choice into a click. Leaving it out meant the one step whose
# entire purpose is picking between look-alike candidates was the only step that
# threaded no geometry, so the pick was redone downstream from the label — and a
# search field echoing the query beats the row it was typed to find.
_GROUNDED_POINTER_FAMILIES = frozenset(
    {"open_entity", "open_contact", "select_content", "reveal_actions", "resolve_entity"}
)


def _goal_matched_object(world: WorldModel) -> Any:
    """The one object the model flagged as matching the goal, if it is unique.

    ``matches_goal`` is the model's own verdict on task relevance, formed while
    looking at the screen. It outranks label similarity, which cannot tell a
    chat row from a search field containing the same characters — and reliably
    prefers the wrong one, since the echo matches the query exactly while the
    row carries extra words. Uniqueness is required: two claimed matches is the
    ambiguity resolve_entity exists to settle, and guessing between them here
    would just relocate the coin toss.
    """
    if world is None:
        return None
    matched = [
        entity
        for entity in getattr(world, "entities", {}).values()
        if getattr(entity, "visible", True)
        and isinstance(getattr(entity, "attributes", None), dict)
        and bool(entity.attributes.get("matches_goal"))
        and str(entity.attributes.get("source") or "") == "vision"
    ]
    return matched[0] if len(matched) == 1 else None


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
        # The model's own relevance verdict first, its label second. Reversing
        # these grounds the click on whichever perceived text reads most like the
        # query, and the query's own echo in the search field always wins that.
        grounded = _goal_matched_object(world) or _ground_label_to_entity(
            world, semantic_target or text
        )
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
    # The prediction, in the shape the transition and experience layers read. It
    # was empty on every model-chosen action, so record_outcome() compared each
    # result against nothing and the capability memory learned nothing from the
    # whole fast path — the agent executed thousands of steps without
    # accumulating what any of its controls actually do. The model already states
    # this prediction; it only needed carrying.
    expectation = proposal.expected_transition or {}
    predicted_surface = str(expectation.get("surface") or "").strip()
    if predicted_surface or expectation.get("likely_controls"):
        action.prediction = {
            "action_family": family,
            "semantic_target": semantic_target,
            "predicted_outcome": predicted_surface,
            "expected_surface": predicted_surface,
            "expected_affordances": [
                str(c).strip()
                for c in (expectation.get("likely_controls") or [])
                if str(c).strip()
            ][:8],
            "expected_progress": round(float(confidence or 0.0), 4),
            "confidence": round(float(confidence or 0.0), 4),
            "reversible": family != "commit_irreversible",
            "source": "unified_multimodal",
        }

    if family == "scroll_content":
        action.scroll_direction = str(proposal.next_action.get("direction") or "down")
        action.scroll_amount = int(proposal.next_action.get("amount") or 3)

    # Runtime admissibility: a pointer action must resolve to something real --
    # an AX entity, a screen point, or at minimum a label to search for.
    if family not in _KEYBOARD_FAMILIES and entity is None:
        action.target_point = _to_screen_point(
            proposal.next_action.get("target_point"),
            proposal.point_scale,
            proposal.point_origin,
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
