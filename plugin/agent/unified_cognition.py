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
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

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
    "revert_effects": "RevertEffects",
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
    "revert_effects": "revert_effects",
    "revert": "revert_effects",
    "rollback": "revert_effects",
    "backtrack": "revert_effects",
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

# Families that are not pointer-bound (chord / scroll). Geometry-required UI
# families (compose_search_query, type_query, open_entity, …) are *not* here —
# they inherit GroundedUiTarget and must carry point/bounds.
_KEYBOARD_FAMILIES = frozenset(
    {
        "dismiss",
        "dismiss_transient",
        "revert_effects",
        "scroll_content",
        "observe",
        "request_more_evidence",
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
    "selection_mode",
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
    """Stage1 perceptor reading: world update + advisory suggestions.

    ``suggested_actions`` is a visual ranking over the frontier with reasons for
    the brain. ``next_action`` is filled only by the brain after critic + node
    closure. ``next_actions`` mirrors legacy traces into suggestions.
    """

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
    # Legacy alias of suggested_actions (old traces).
    next_actions: List[Dict[str, Any]] = field(default_factory=list)
    # Ranked visual advice for the brain: family/target + why. Never executed.
    suggested_actions: List[Dict[str, Any]] = field(default_factory=list)
    expected_transition: Dict[str, Any] = field(default_factory=dict)
    # REFLECT mode: why the last prediction disagreed with the new world.
    surprise_explanation: Dict[str, Any] = field(default_factory=dict)
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
    # Internal QC: did stage0/frontier already surface task-critical affordances?
    affordance_qc: Dict[str, Any] = field(default_factory=dict)
    # Perceptor judgment: act already clear vs still need affordance exploration.
    # act_clear | explore_needed | ambiguous
    affordance_stance: str = ""
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
            "suggested_actions": self.suggested_actions,
            "expected_transition": self.expected_transition,
            "surprise_explanation": self.surprise_explanation,
            "visible_objects": self.visible_objects,
            "missing_evidence": self.missing_evidence,
            "evidence_gaps": self.evidence_gaps,
            "coverage": round(float(self.coverage if self.coverage is not None else 1.0), 3),
            "missing_affordance_information": self.missing_affordance_information,
            "recommended_probe": self.recommended_probe,
            "affordance_qc": self.affordance_qc,
            "affordance_stance": self.affordance_stance,
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


def _label_is_search_chrome(label: Any) -> bool:
    low = str(label or "").strip().lower()
    if not low:
        return False
    if re.match(r"^(q\s+|•\s+|·\s+)?search\|?$", low):
        return True
    return "search" in low and len(low) < 48 and "result" not in low


def _filter_geometry_from_ax_and_ocr(
    ax_evidence: Sequence[Dict[str, Any]],
    world: Optional[WorldModel] = None,
) -> Dict[str, Any]:
    """Screen-point Search site for exclusive filter_input binding (live 123746)."""
    for item in ax_evidence or ():
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or item.get("text") or "").strip()
        if not _label_is_search_chrome(label):
            continue
        bounds = item.get("bounds") or item.get("bbox")
        try:
            x, y, w, h = (float(bounds[0]), float(bounds[1]), float(bounds[2]), float(bounds[3]))
        except (TypeError, ValueError, IndexError):
            continue
        if w <= 1 or h <= 1:
            continue
        return {
            "target_id": item.get("id"),
            "target_label": "Search",
            "target_point": [x + w / 2.0, y + h / 2.0],
            "bounds": [x, y, w, h],
            "coordinate_space": "screen",
            "geometry_source": "ax_evidence",
            "kind": "search_field",
        }
    lines = list(getattr(world, "last_ocr_lines", None) or []) if world is not None else []
    for line in lines:
        if not isinstance(line, dict):
            continue
        text = str(line.get("text") or line.get("label") or "").strip()
        if not _label_is_search_chrome(text):
            continue
        bounds = line.get("bounds") or line.get("bbox")
        try:
            x, y, w, h = (float(bounds[0]), float(bounds[1]), float(bounds[2]), float(bounds[3]))
        except (TypeError, ValueError, IndexError):
            continue
        if w <= 1 or h <= 1:
            continue
        return {
            "target_label": "Search",
            "target_point": [x + w / 2.0, y + h / 2.0],
            "bounds": [x, y, w, h],
            "coordinate_space": "screen",
            "geometry_source": "ocr_search",
            "kind": "search_field",
        }
    return {}


def _filter_geometry_from_frontier_packet(frontier: Any) -> Dict[str, Any]:
    if not isinstance(frontier, dict):
        return {}
    for bucket in ("observed_actions", "latent_actions"):
        for aff in frontier.get(bucket) or []:
            if not isinstance(aff, dict):
                continue
            if str(aff.get("family") or "") not in _SEARCH_FIELD_FAMILIES:
                continue
            label = str(aff.get("target_label") or aff.get("label") or "").strip()
            if label and not _label_is_search_chrome(label):
                continue
            point = None
            for act in aff.get("actuators") or []:
                if not isinstance(act, dict):
                    continue
                raw = act.get("point") or act.get("target_point")
                if isinstance(raw, (list, tuple)) and len(raw) >= 2:
                    try:
                        point = [float(raw[0]), float(raw[1])]
                    except (TypeError, ValueError):
                        point = None
                    if point is not None:
                        break
            bounds = aff.get("bounds")
            if point is None and isinstance(bounds, (list, tuple)) and len(bounds) >= 4:
                try:
                    x, y, w, h = (float(bounds[0]), float(bounds[1]), float(bounds[2]), float(bounds[3]))
                    if w > 1 and h > 1:
                        point = [x + w / 2.0, y + h / 2.0]
                except (TypeError, ValueError, IndexError):
                    point = None
            if point is None:
                continue
            site: Dict[str, Any] = {
                "target_label": "Search",
                "target_point": point,
                "coordinate_space": "screen",
                "geometry_source": "ax_frontier",
                "kind": "search_field",
            }
            if aff.get("target_id") is not None:
                site["target_id"] = aff.get("target_id")
            if isinstance(bounds, (list, tuple)) and len(bounds) >= 4:
                try:
                    site["bounds"] = [float(x) for x in bounds[:4]]
                except (TypeError, ValueError):
                    pass
            return site
    return {}


def _stash_overlay_ocr_menu(
    execution_state: Any,
    world: Optional[WorldModel] = None,
) -> None:
    """Stash OCR menu-verb lines while reveal_handoff is owed (125715)."""
    if execution_state is None:
        return
    handoff = getattr(execution_state, "reveal_handoff", None)
    active = isinstance(handoff, dict) and bool(str(handoff.get("surface") or "").strip())
    if not active:
        try:
            execution_state.last_overlay_ocr_menu = None
        except Exception:
            pass
        return
    lines = [
        ln for ln in (getattr(world, "last_ocr_lines", None) or []) if isinstance(ln, dict)
    ]
    if not lines:
        return
    try:
        from plugin.agent.world_critic import _label_looks_like_menu_verb
    except Exception:
        return
    hints: List[Dict[str, Any]] = []
    for line in lines:
        text = str(line.get("text") or line.get("label") or "").strip()
        if not _label_looks_like_menu_verb(text):
            continue
        hint: Dict[str, Any] = {"text": text, "label": text}
        bounds = line.get("bounds")
        if isinstance(bounds, (list, tuple)) and len(bounds) >= 4:
            try:
                hint["bounds"] = [float(x) for x in bounds[:4]]
                x, y, w, h = hint["bounds"]
                hint["point"] = [x + w / 2.0, y + h / 2.0]
            except (TypeError, ValueError):
                continue
        elif isinstance(line.get("point"), (list, tuple)) and len(line["point"]) >= 2:
            try:
                hint["point"] = [float(line["point"][0]), float(line["point"][1])]
            except (TypeError, ValueError):
                continue
        else:
            continue
        hints.append(hint)
    if hints:
        try:
            execution_state.last_overlay_ocr_menu = hints[:12]
        except Exception:
            pass


def _stash_filter_geometry(
    execution_state: Any,
    *,
    ax_evidence: Sequence[Dict[str, Any]],
    world: Optional[WorldModel] = None,
    frontier_packet: Optional[Dict[str, Any]] = None,
    features: Any = None,
) -> None:
    """Persist Search geometry for brain grounding (VLM often omits the field)."""
    site = _filter_geometry_from_frontier_packet(frontier_packet)
    if not site.get("target_point") and not site.get("bounds"):
        site = _filter_geometry_from_ax_and_ocr(ax_evidence, world)
    if not site.get("target_point") and not site.get("bounds"):
        return
    if execution_state is not None:
        try:
            execution_state.last_filter_geometry = dict(site)
        except Exception:
            pass
    if features is not None and isinstance(getattr(features, "extras", None), dict):
        features.extras["filter_geometry"] = dict(site)


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
        # Sidebar Search must stay near the top: compose_search_query binds it
        # when VLM objects are only chat rows (live 123746).
        if _label_is_search_chrome(label):
            score += 8.0
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
        # Parentage lets the model attribute claims to containing surfaces
        # (architect: surface ownership — not a flattened bag of labels).
        parent_id = getattr(entity, "parent_id", None)
        if parent_id is not None:
            item["parent_id"] = parent_id
            parent = world.entities.get(int(parent_id)) if parent_id is not None else None
            if parent is not None:
                parent_label = str(getattr(parent, "label", "") or "")[:80]
                parent_role = str(getattr(parent, "role", "") or "")[:40]
                if parent_label:
                    item["parent_label"] = parent_label
                if parent_role:
                    item["parent_role"] = parent_role
        if getattr(entity, "enabled", True) is False:
            item["enabled"] = False
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


def _ocr_bounds_for(
    text: str, lines: Sequence[Dict[str, Any]]
) -> Optional[Tuple[float, float, float, float]]:
    """The measured rectangle for the object the model described, if OCR read it.

    The model describes an object in its own words -- "Kulvinder Ji -
    zarooratwala.com link message" -- while OCR returns the literal rendered
    lines, so the two never match as strings. What does hold is containment:
    the model's description is assembled from what is written there, so the
    right line's words are a subset of it. Containment is therefore the test,
    and it has to be the test in that direction only: a chat row reads as
    "Kulvinder Ji" while the model calls it "Kulvinder Ji - zarooratwala.com
    link message", so requiring the line to account for much of the description
    rejects the very line that names it. Among contained lines the longest
    match wins, which separates the row from the one-word fragment that half
    the screen would also satisfy.

    Returns None rather than a poor guess when nothing is convincing; the
    caller then falls back to the model's own point, which is at least aimed at
    the right object even when it is aimed badly.
    """
    wanted = {w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(w) > 2}
    if not wanted:
        return None
    best: Optional[Tuple[float, float, float, float]] = None
    best_matched = 0
    for line in lines:
        words = {
            w for w in re.findall(r"[a-z0-9]+", str(line.get("text") or "").lower()) if len(w) > 2
        }
        if not words:
            continue
        overlap = words & wanted
        # Most of the line has to appear in the description, or this is a
        # different piece of text that merely shares a word.
        if not overlap or (len(overlap) / len(words)) < 0.6:
            continue
        # Characters rather than words: one long distinctive token is better
        # evidence than two short common ones.
        matched = sum(len(w) for w in overlap)
        if matched < 4 or matched <= best_matched:
            continue
        bounds = line.get("bounds")
        if not isinstance(bounds, (list, tuple)) or len(bounds) < 4:
            continue
        try:
            candidate = tuple(float(v) for v in tuple(bounds)[:4])
        except (TypeError, ValueError):
            continue
        if candidate[2] <= 0 or candidate[3] <= 0:
            continue
        best, best_matched = candidate, matched  # type: ignore[assignment]
    return best


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
    # Menu items often live on action_menu layers; fold them in so reveal
    # grounding has the same entity thoroughness as message bubbles.
    seen_keys = {
        (
            str(o.get("text") or o.get("label") or "").strip().lower(),
            str(o.get("point") or ""),
        )
        for o in objects
    }
    state = proposal.observed_state or {}
    for layer in state.get("layers") or []:
        if not isinstance(layer, dict):
            continue
        for obj in layer.get("objects") or []:
            if not isinstance(obj, dict):
                continue
            key = (
                str(obj.get("text") or obj.get("label") or "").strip().lower(),
                str(obj.get("point") or ""),
            )
            if not key[0] or key in seen_keys:
                continue
            seen_keys.add(key)
            objects.append(obj)
    if not objects:
        return 0

    from plugin.worldmodel.entities.entity import Entity

    for stale in [i for i in world.entities if int(i) >= _VISION_ENTITY_ID_BASE]:
        world.entities.pop(stale, None)

    ocr_lines = [ln for ln in (getattr(world, "last_ocr_lines", None) or []) if isinstance(ln, dict)]

    created = 0
    for index, item in enumerate(objects):
        text = str(item.get("text") or item.get("label") or "").strip()
        if not text:
            continue
        # Where, measured, in preference to where, guessed. The model is the
        # authority on *which* object this is -- it is the only source that
        # reads the screen as a screen -- but its coordinates are an estimate,
        # and a poor one: live runs placed a correctly-named chat row 200px
        # below itself, and named the link card at a point outside the very
        # image it had been shown, which resolved off the display entirely and
        # sent the right-click nowhere. OCR does not know what anything means
        # but it measures to the pixel, so it supplies the geometry and the
        # model supplies the identity.
        ocr_bounds = _ocr_bounds_for(text, ocr_lines)
        bounds = ocr_bounds
        if bounds is None:
            screen = _to_screen_point(
                item.get("point") or item.get("target_point"),
                proposal.point_scale,
                proposal.point_origin,
            )
            if screen is None:
                continue
            x, y = float(screen[0]), float(screen[1])
            half = _VISION_ENTITY_HALF
            bounds = (x - half, y - half, half * 2, half * 2)
        # Do not mutate proposal object points — those stay in image space for
        # the next multimodal turn. Stamp screen geometry only on the entity.
        entity_id = _VISION_ENTITY_ID_BASE + index
        kind = str(item.get("kind") or "message") or "message"
        is_menu = kind.lower() in {"menu_item", "menuitem", "menu", "action"}
        world.entities[entity_id] = Entity(
            id=entity_id,
            entity_type=kind,
            semantic_role="menu_item" if is_menu else "message",
            label=text,
            role="AXStaticText",
            bounds=bounds,
            visible=True,
            confidence=float(proposal.confidence or 0.0),
            attributes={
                "source": "vision",
                "matches_goal": bool(item.get("matches_goal")),
                "description": text,
                "coordinate_space": "screen",
                "is_menu_item": is_menu,
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
    try:
        world.last_perception_synthesis = {
            "source": "unified_cognition",
            "model": proposal.model,
            "confidence": float(proposal.confidence or 0.0),
            "summary": {
                "screen_type": _SURFACE_TO_SCREEN_TYPE.get(surface, "unknown"),
                "active_surface": surface,
                "open_conversation": str(state.get("open_conversation") or ""),
                # Brain owns the next capability; do not publish a perception nudge.
                "likely_next_family": "",
                "likely_next_target": "",
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


# Family → (expected surface, likely controls) when the decision omits a prediction.
# Used only to stamp the *act's* claim for post-act scoring — not as surprise heuristics.
_FAMILY_ACT_INTENTION: Dict[str, Tuple[str, List[str]]] = {
    "reveal_actions": ("context_menu", ["Forward", "Reply", "Copy"]),
    "probe_context_menu": ("context_menu", ["Forward", "Reply", "Copy"]),
    "select_content": ("selection_mode", ["Forward", "Copy", "Share", "Cancel"]),
    "open_entity": ("conversation", []),
    "open_contact": ("conversation", []),
    # Ranking/judgment only — must not inherit a conversation-open prediction.
    "resolve_entity": ("search", []),
    "open_search": ("search", ["search"]),
    "compose_search_query": ("search", ["search"]),
    "type_query": ("search", ["search"]),
    "select_destination": ("forward_picker", ["search", "cancel"]),
    "choose_destination": ("forward_picker", ["search", "cancel"]),
    "invoke_forward": ("forward_picker", ["search contacts", "cancel"]),
    "scroll_content": ("conversation", []),
    "locate_content": ("conversation", []),
}

# Families whose contract is search-scope (compose/type/rank), never navigation into
# an open conversation. A look's expected_transition may wish for conversation
# because the *goal* is a chat; that wish must not become the act's prediction.
_SEARCH_SCOPE_FAMILIES: Set[str] = {
    "resolve_entity",
    "compose_search_query",
    "type_query",
    "open_search",
    "search",
}

# open_entity / open_contact navigate into a container. A look may wish for a
# message-action surface (context_menu) because the *goal* is forward — that
# wish must not become the open act's prediction (live 131030: OpenEntity +
# context_menu → motor OK, effect missing, retry thrash).
_OPEN_NAV_FAMILIES: Set[str] = {
    "open_entity",
    "open_contact",
}
_REVEAL_EFFECT_SURFACES: Set[str] = {
    "context_menu",
    "action_menu",
    "selection_mode",
    "message_actions",
}


def intention_expectation_from_decision(decision: Any) -> Dict[str, Any]:
    """What this ACT claims the next perceive should show.

    Sourced from the decision's prediction when present; otherwise a thin
    family default. This is the agent's intention for *this* motor move — the
    post-act look scores it; mismatch becomes multimodal surprise → REFLECT.
    """
    if decision is None:
        return {}
    fam = str(getattr(decision, "action_family", "") or "").strip().lower()
    if fam in {"", "observe"}:
        return {}
    pred = getattr(decision, "prediction", None)
    pred_d = dict(pred) if isinstance(pred, dict) else {}
    surface = str(
        pred_d.get("expected_surface")
        or pred_d.get("predicted_outcome")
        or getattr(decision, "expected_predicate", "")
        or ""
    ).strip()
    # predicted_outcome is sometimes a predicate like ConversationOpen(X).
    if surface and "(" in surface:
        head = surface.split("(", 1)[0].strip().lower()
        _PRED_SURFACE = {
            "conversationopen": "conversation",
            "contextmenu": "context_menu",
            "context_menu": "context_menu",
            "forwardpicker": "forward_picker",
            "forward_picker": "forward_picker",
            "searchopen": "search",
            "search": "search",
        }
        surface = _PRED_SURFACE.get(head, "") or (
            "conversation" if "conversation" in head else ""
        )
    controls = [
        str(c).strip()
        for c in (
            pred_d.get("expected_affordances")
            or pred_d.get("likely_controls")
            or []
        )
        if str(c).strip()
    ][:8]
    target = str(
        getattr(decision, "semantic_target", "") or getattr(decision, "text", "") or ""
    ).strip()
    # Resolution ≠ navigation: never let a look's conversation wish override.
    if fam in _SEARCH_SCOPE_FAMILIES:
        default = _FAMILY_ACT_INTENTION.get(fam) or ("search", [])
        surface, default_controls = default
        if not controls or fam == "resolve_entity":
            controls = list(default_controls)
        # Drop conversation chrome claims on ranking/compose acts.
        controls = [
            c
            for c in controls
            if str(c).strip().lower()
            not in {"message_bubbles", "input_field", "header_info", "composer"}
        ]
    elif fam in _OPEN_NAV_FAMILIES and (
        not surface or surface in _REVEAL_EFFECT_SURFACES
    ):
        # Desired-effect coherence: OpenEntity claims container open, never
        # reveal/select surfaces. Reveal-shaped wishes belong to reveal_actions.
        default = _FAMILY_ACT_INTENTION.get(fam) or ("conversation", [])
        surface, default_controls = default
        controls = list(default_controls)
    elif not surface:
        if fam == "invoke_affordance" and target.lower() in {"forward", "share"}:
            surface, controls = "forward_picker", ["search contacts", "cancel", "Tanmay"]
        else:
            default = _FAMILY_ACT_INTENTION.get(fam)
            if default:
                surface, default_controls = default
                if not controls:
                    controls = list(default_controls)
    if not surface:
        return {}
    out: Dict[str, Any] = {
        "surface": surface,
        "source": "act_intention",
        "action_family": fam,
    }
    if controls:
        out["likely_controls"] = controls
    if target:
        out["semantic_target"] = target
    if fam == "resolve_entity":
        # Explicit contract: ranking establishes EntityRef, not conversation_open.
        out["claims_navigation"] = False
        out["claims_resolution"] = True
    return out


def stamp_act_intention(execution_state: Any, decision: Any) -> Dict[str, Any]:
    """Record the act's intended world so the next perceive can score it."""
    if execution_state is None:
        return {}
    expectation = intention_expectation_from_decision(decision)
    if not expectation:
        try:
            execution_state.act_intention_pending = False
        except Exception:
            pass
        return {}
    try:
        from plugin.agent.executive.intention_frame import new_attempt_id

        attempt_id = new_attempt_id()
        expectation = dict(expectation)
        expectation["attempt_id"] = attempt_id
        execution_state.unified_last_expectation = dict(expectation)
        execution_state.act_intention_pending = True
        execution_state.active_attempt_id = attempt_id
        # Immutable causal stamp on the Action / plan step (not ambient-only).
        try:
            if decision is not None and hasattr(decision, "attempt_id"):
                decision.attempt_id = attempt_id
        except Exception:
            pass
        try:
            step = getattr(execution_state, "last_plan_step", None)
            if step is not None and hasattr(step, "attempt_id"):
                step.attempt_id = attempt_id
        except Exception:
            pass
        fam = str(expectation.get("action_family") or "").strip().lower()
        if fam and fam not in {"observe", "perceive", "look"}:
            execution_state.last_instrumental_family = fam
    except Exception:
        try:
            execution_state.unified_last_expectation = dict(expectation)
            execution_state.act_intention_pending = True
        except Exception:
            return expectation
    try:
        from plugin.agent.capabilities.revert_effects import record_act_on_effect_trace

        geo = None
        if decision is not None:
            geo = getattr(decision, "target_point", None)
            if geo is None and isinstance(getattr(decision, "next_action", None), dict):
                geo = decision.next_action.get("target_point")
        record_act_on_effect_trace(
            execution_state,
            capability=str(
                expectation.get("action_family")
                or getattr(decision, "capability", "")
                or getattr(decision, "action_family", "")
                or ""
            ),
            target=str(expectation.get("semantic_target") or ""),
            geometry=geo if isinstance(geo, (list, tuple)) else None,
            intention=expectation,
        )
    except Exception:
        pass
    logger.info(
        "Act intention stamped: family=%s surface=%s controls=%s",
        expectation.get("action_family"),
        expectation.get("surface"),
        (expectation.get("likely_controls") or [])[:4],
    )
    return expectation


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
        try:
            execution_state.last_affordance_stance = str(
                getattr(proposal, "affordance_stance", "") or ""
            ).strip()
        except Exception:
            pass
        new_exp = dict(proposal.expected_transition or {}) if isinstance(
            proposal.expected_transition, dict
        ) else {}
        new_surface = str(new_exp.get("surface") or "").strip()
        if new_surface:
            execution_state.unified_last_expectation = new_exp
            execution_state.act_intention_pending = False
        elif bool(getattr(execution_state, "act_intention_pending", False)):
            # Compact/fast looks often omit expected_transition — do not wipe
            # the act-stamped intention before (or instead of) scoring it.
            pass
        else:
            execution_state.unified_last_expectation = None
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

    Once REFLECT has consumed a mismatch, do not re-arm the same predicted
    surface as *meta* surprise on the next look — that looped 134822
    (reflect → look → note_prediction_error → reflect forever → IG → ask_user).

    Do **not** falsify ``matched`` for that latch (154356): motor escalate and
    effect verification need an honest effect-absent judgment. Thrash
    prevention is ``surprise_armed=False`` / ``suppressed_rearm`` only.
    """
    if execution_state is None or proposal is None:
        return {}
    expectation = getattr(execution_state, "unified_last_expectation", None)
    error = prediction_error(expectation, proposal.world_model)
    # Bind verification to the attempt that made the prediction — never to the
    # current PERCEIVE family.
    if isinstance(error, dict) and isinstance(expectation, dict):
        error = dict(error)
        error.setdefault(
            "action_family",
            str(
                expectation.get("action_family")
                or expectation.get("family")
                or expectation.get("capability")
                or getattr(execution_state, "last_instrumental_family", "")
                or ""
            ),
        )
        error.setdefault(
            "attempt_id",
            str(
                expectation.get("attempt_id")
                or getattr(execution_state, "active_attempt_id", "")
                or ""
            ),
        )
        error.setdefault(
            "target",
            str(expectation.get("semantic_target") or expectation.get("target") or ""),
        )
    prior = getattr(execution_state, "last_prediction_error", None)
    if (
        isinstance(error, dict)
        and error.get("matched") is False
        and isinstance(prior, dict)
        and prior.get("consumed_by_reflect")
        and str(prior.get("predicted_surface") or "")
        == str(error.get("predicted_surface") or "")
    ):
        error = dict(error)
        # Keep matched=False (effect still absent). Disarm meta surprise only.
        error["effect_absent"] = True
        error["consumed_by_reflect"] = True
        error["suppressed_rearm"] = True
        error["surprise_armed"] = False
    # Selection + branch fitness: wrong multi-select or barren filtered search
    # can leave surface matched while the branch cannot admit goal progress.
    try:
        from plugin.agent.capabilities.branch_fitness import (
            compute_branch_fitness,
            needed_evidence_kinds_for_goal,
        )
        from plugin.agent.capabilities.revert_effects import (
            goal_referents_from_context,
            selection_consistency_error,
            update_effect_trace_after_look,
        )

        doc = dict(proposal.world_model) if isinstance(proposal.world_model, dict) else {}
        extras = {}
        feats = getattr(execution_state, "last_features", None)
        if feats is not None and isinstance(getattr(feats, "extras", None), dict):
            extras = dict(feats.extras)
        try:
            from plugin.agent.apps.registry import get_overlay

            app_name = str(
                extras.get("app")
                or getattr(getattr(execution_state, "goal", None), "app", None)
                or "WhatsApp"
            )
            overlay = get_overlay(app_name, None)
            enrich = getattr(overlay, "enrich_world_document", None)
            if callable(enrich):
                doc = enrich(doc)
                proposal.world_model = doc
        except Exception:
            pass
        exp = expectation if isinstance(expectation, dict) else {}
        referents = goal_referents_from_context(
            execution_state=execution_state, extras=extras
        )
        for tok in getattr(execution_state, "goal_referents", None) or []:
            if str(tok).strip() and str(tok) not in referents:
                referents.append(str(tok))
        sel = selection_consistency_error(
            doc,
            goal_referents=referents,
            semantic_target=str(exp.get("semantic_target") or ""),
            selected_label=str(
                extras.get("selected_object_label")
                or getattr(execution_state, "selected_object_label", "")
                or ""
            ),
        )
        execution_state.last_selection_consistency = sel
        goal_obj = getattr(execution_state, "goal", None)
        needed = needed_evidence_kinds_for_goal(
            goal_obj,
            goal_kind=str(
                getattr(goal_obj, "kind", "") or extras.get("goal_kind") or ""
            ),
        )
        if referents and not needed:
            needed = needed_evidence_kinds_for_goal(
                goal_kind="whatsapp_forward_message"
            )
        fitness = compute_branch_fitness(
            doc,
            needed_kinds=needed,
            goal=goal_obj,
            goal_referents=referents,
            selection_consistency=sel,
        )
        execution_state.last_branch_fitness = fitness
        execution_state.last_branch_consistency = fitness
        bad_sel = isinstance(sel, dict) and sel.get("consistent") is False
        bad_branch = isinstance(fitness, dict) and fitness.get("admissible") is False
        if bad_sel or bad_branch:
            error = dict(error) if isinstance(error, dict) else {}
            error["matched"] = False
            if bad_sel:
                error["selection_consistent"] = False
                error["selection_consistency"] = sel
            if bad_branch:
                error["branch_fitness"] = fitness
                error["branch_consistent"] = False
                error["branch_consistency"] = fitness
                error["needs_backtrack"] = True
            error["verdict"] = str(
                (fitness.get("verdict") if bad_branch else None)
                or (sel.get("verdict") if bad_sel else None)
                or error.get("verdict")
                or ""
            )
            if not error.get("observed_surface"):
                error["observed_surface"] = str(doc.get("surface") or "")
            if not error.get("predicted_surface") and isinstance(exp, dict):
                error["predicted_surface"] = str(exp.get("surface") or "")
            if bad_sel:
                try:
                    ft = getattr(execution_state, "forward_task", None)
                    preds = getattr(ft, "predicates", None) if ft is not None else None
                    if preds is not None and getattr(
                        preds, "source_object_selected", False
                    ):
                        preds.source_object_selected = False
                    if hasattr(execution_state, "do_not_advance"):
                        execution_state.do_not_advance(
                            "source_object_selected",
                            "selection_consistency failed",
                        )
                except Exception:
                    pass
        update_effect_trace_after_look(
            execution_state,
            prediction_error=error if isinstance(error, dict) else None,
            selection_consistency=sel if isinstance(sel, dict) else None,
            document=doc,
        )
    except Exception:
        logger.debug("selection/branch fitness enrichment failed", exc_info=True)

    try:
        execution_state.last_prediction_error = error
        # Intention was for this post-act look. Release the pending flag so
        # _remember_reading may replace/clear the claim; keep
        # last_prediction_error so meta can infer surprise → REFLECT.
        if getattr(execution_state, "act_intention_pending", False):
            execution_state.act_intention_pending = False
    except Exception:
        pass
    return error


def prior_document(execution_state: Any) -> Dict[str, Any]:
    """The world document the model produced last step, or an empty one."""
    document = getattr(execution_state, "unified_world_document", None)
    return document if isinstance(document, dict) and document else empty_document()


def stamp_task_surface(
    document: Dict[str, Any],
    *,
    world: Optional[WorldModel] = None,
    execution_state: Any = None,
    app: str = "",
) -> Dict[str, Any]:
    """Attach live multi-display topology to the world document."""
    try:
        from plugin.perception.display_topology import (
            attach_task_surface,
            build_task_surface,
        )

        app_name = (
            str(app or "").strip()
            or str(getattr(world, "active_app", "") or "").strip()
            or "WhatsApp"
        )
        origin = getattr(execution_state, "unified_point_origin", None) if execution_state else None
        scale = getattr(execution_state, "unified_point_scale", None) if execution_state else None
        capture = getattr(world, "last_capture_frame", None) if world is not None else None
        surface = build_task_surface(
            app_name,
            capture_frame=capture if isinstance(capture, dict) else None,
            point_origin=origin if isinstance(origin, (list, tuple)) else None,
            point_scale=float(scale) if scale is not None else None,
        )
        stamped = attach_task_surface(document, surface)
        if world is not None:
            try:
                world.overlay_hints = dict(getattr(world, "overlay_hints", None) or {})
                world.overlay_hints["task_surface"] = surface.to_dict()
            except Exception:
                pass
        if execution_state is not None:
            try:
                execution_state.task_surface = surface.to_dict()
            except Exception:
                pass
        return stamped
    except Exception:
        return dict(document or {})


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
    document = stamp_task_surface(
        prior_document(execution_state),
        world=world,
        execution_state=execution_state,
        app=str(features.app or goal.app or ""),
    )
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

    ax_for_frontier = list(observation.get("ax_evidence") or [])
    frontier = _frontier_for_packet(
        goal,
        world,
        features,
        document,
        execution_state,
        ax_for_frontier,
    )
    frontier_packet: Optional[Dict[str, Any]] = None
    if frontier is not None:
        frontier_packet = frontier.to_packet()
        packet["affordance_frontier"] = frontier_packet
        # Brain consultation reads the same frontier the perceptor saw.
        if execution_state is not None:
            try:
                execution_state.last_affordance_frontier = frontier_packet
            except Exception:
                pass
    # Persist Search geometry for exclusive filter bind even when VLM objects
    # omit the field and the chooser brief strips frontier actuators.
    _stash_filter_geometry(
        execution_state,
        ax_evidence=ax_for_frontier,
        world=world,
        frontier_packet=frontier_packet,
        features=features,
    )
    _stash_overlay_ocr_menu(execution_state, world)

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
    # Destination-picker looks: inject / merge a scoped executive question so
    # the multimodal model attributes selection by owner surface (live 184742).
    dest_obj = _destination_search_perception_objective(goal, document)
    if dest_obj is not None:
        prior = packet.get("perception_objective")
        if isinstance(prior, dict) and (prior.get("questions") or prior.get("objective")):
            merged_q = list(prior.get("questions") or [])
            for q in dest_obj.get("questions") or []:
                if q not in merged_q:
                    merged_q.append(q)
            packet["perception_objective"] = {
                **prior,
                "questions": merged_q[:8],
                "focus": str(prior.get("focus") or dest_obj.get("focus") or ""),
                "depth": "deep",
                "objective": str(dest_obj.get("objective") or prior.get("objective") or ""),
                "completion_condition": str(
                    dest_obj.get("completion_condition")
                    or prior.get("completion_condition")
                    or ""
                ),
                "active_interaction_surface": dest_obj.get("active_interaction_surface"),
                "destination_visible": dest_obj.get("destination_visible"),
                "destination_selected": dest_obj.get("destination_selected"),
                "destination_search_available": dest_obj.get(
                    "destination_search_available"
                ),
            }
        else:
            packet["perception_objective"] = dest_obj
        observation["active_interaction_surface"] = dest_obj.get(
            "active_interaction_surface"
        )

    # Locate effect verification: answer the named YES/NO/UNKNOWN question —
    # do not invent absence from a capped object inventory.
    if execution_state is not None and bool(
        getattr(execution_state, "locate_effect_verify_owed", False)
    ):
        link_q = str(getattr(execution_state, "last_locate_query", "") or "").strip()
        realize = str(
            getattr(execution_state, "last_locate_realization", "") or ""
        ).strip()
        verify_q = (
            f"Did locate({link_q!r} via {realize or 'find'}) surface a "
            "binding-eligible content patient for the source query?"
        )
        try:
            from plugin.agent.executive.intention_frame import active_intention_frame

            iframe = active_intention_frame(execution_state)
            pkt = getattr(iframe, "last_motivated_perceive", None) if iframe else None
            if isinstance(pkt, dict) and str(pkt.get("question") or "").strip():
                verify_q = str(pkt.get("question")).strip()
        except Exception:
            pass
        locate_obj = {
            "questions": [verify_q],
            "focus": "searchable_surface_content",
            "depth": "deep",
            "objective": "locate_effect_verification",
            "completion_condition": (
                "Answer the locate-effect question explicitly: set "
                "world_model.locate_effect_answer to yes|no|unknown. "
                "If no and you can establish absence of the query patient, "
                "also set world_model.source_query_not_surfaced=true. "
                "Missing from the top-10 objects inventory alone is not enough "
                "for no — use unknown when unsure."
            ),
        }
        prior = packet.get("perception_objective")
        if isinstance(prior, dict) and (prior.get("questions") or prior.get("objective")):
            merged_q = list(prior.get("questions") or [])
            for q in locate_obj["questions"]:
                if q not in merged_q:
                    merged_q.insert(0, q)
            packet["perception_objective"] = {
                **prior,
                "questions": merged_q[:8],
                "focus": str(prior.get("focus") or locate_obj["focus"]),
                "depth": "deep",
                "objective": "locate_effect_verification",
                "completion_condition": locate_obj["completion_condition"],
            }
        else:
            packet["perception_objective"] = locate_obj

    reflect = _reflect_packet(execution_state)
    if reflect:
        packet["reflect"] = reflect
        packet["perception_mode"] = "reflect"
    return packet


# Canonical ReflectDiagnosis schema — surprise_explanation is its wire form.
from plugin.agent.reflect_diagnosis import (  # noqa: E402
    CAUSES as _SURPRISE_CAUSES,
    NEXT_MOVES as _SURPRISE_NEXT,
    diagnosis_is_authoritative as _diagnosis_is_authoritative,
    enrich_reflect_packet,
    merge_diagnoses,
    normalize_reflect_diagnosis,
    reflect_schema_addendum,
    seed_reflect_diagnosis_from_measured,
)


def normalize_surprise_explanation(raw: Any) -> Dict[str, Any]:
    """Clamp surprise_explanation to ReflectDiagnosis (backward compatible)."""
    return normalize_reflect_diagnosis(raw).to_surprise_explanation()


def explanation_is_authoritative(explanation: Optional[Dict[str, Any]]) -> bool:
    """High-confidence diagnoses may steer act/backtrack; weak ones only look."""
    from plugin.agent.executive.meta_action import REFLECT_EXPLANATION_CONFIDENCE

    if not isinstance(explanation, dict) or not explanation:
        return False
    return _diagnosis_is_authoritative(
        normalize_reflect_diagnosis(explanation),
        floor=REFLECT_EXPLANATION_CONFIDENCE,
    )


def finalize_surprise_explanation(
    raw: Any,
    *,
    reflect_packet: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Merge model explanation with runtime seed diagnosis."""
    from plugin.agent.reflect_diagnosis import ReflectDiagnosis

    model = normalize_reflect_diagnosis(raw if isinstance(raw, dict) else {})
    if isinstance(reflect_packet, dict) and reflect_packet:
        seed = seed_reflect_diagnosis_from_measured(reflect_packet)
    else:
        seed = ReflectDiagnosis(source="runtime_seed")
    return merge_diagnoses(model, seed).to_surprise_explanation()


def _as_xy(raw: Any) -> Optional[List[float]]:
    if not isinstance(raw, (list, tuple)) or len(raw) < 2:
        return None
    try:
        return [float(raw[0]), float(raw[1])]
    except (TypeError, ValueError):
        return None


def discover_surprise_hypotheses(reflect: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Derive *candidate* causes from measured reflect facts only.

    This is not the perceptor and not task-specific. It names what the runtime
    can already prove (geometry mismatch, surface miss, no movement) so the
    perceptor has a discovery substrate — and so evals can check that inputs
    actually support genuine explanation, rather than injecting gold causes.
    """
    if not isinstance(reflect, dict) or not reflect:
        return []
    measured = reflect.get("measured") if isinstance(reflect.get("measured"), dict) else {}
    expected = reflect.get("expected") if isinstance(reflect.get("expected"), dict) else {}
    actual = reflect.get("actual") if isinstance(reflect.get("actual"), dict) else {}
    action = reflect.get("action") if isinstance(reflect.get("action"), dict) else {}
    hyps: List[Dict[str, Any]] = []

    intended = _as_xy(action.get("intended_point") or action.get("point"))
    landed = _as_xy(action.get("motor_landed_point") or measured.get("motor_landed_point"))
    if intended and landed:
        dist = ((intended[0] - landed[0]) ** 2 + (intended[1] - landed[1]) ** 2) ** 0.5
        if dist >= 80.0:
            hyps.append(
                {
                    "cause": "wrong_target",
                    "confidence": min(0.95, 0.7 + dist / 1000.0),
                    "evidence": [
                        f"intended_point={intended}",
                        f"motor_landed_point={landed}",
                        f"distance_px={round(dist, 1)}",
                    ],
                    "recommended_next": "act",
                    # Prefer a prior object near intended that is not near landed,
                    # left for the perceptor; runtime only flags the mismatch.
                }
            )
            hyps.append(
                {
                    "cause": "stale_geometry",
                    "confidence": min(0.9, 0.65 + dist / 1200.0),
                    "evidence": [
                        f"intended_point={intended}",
                        f"motor_landed_point={landed}",
                    ],
                    "recommended_next": "act",
                }
            )

    pred = _norm_text(expected.get("surface") or actual.get("predicted_surface"))
    obs = _norm_text(actual.get("observed_surface") or actual.get("surface"))
    matched = actual.get("matched")
    if pred and obs and matched is False and pred != obs:
        hyps.append(
            {
                "cause": "wrong_surface",
                "confidence": 0.8,
                "evidence": [f"predicted_surface={pred}", f"observed_surface={obs}"],
                "recommended_next": "reperceive",
            }
        )

    effect = _norm_text(measured.get("effect") or actual.get("effect"))
    if effect in {"no_transition", "no_effect", "regression"}:
        hyps.append(
            {
                "cause": "no_effect",
                "confidence": 0.75,
                "evidence": [f"effect={effect}"],
                "recommended_next": "reperceive",
            }
        )

    if measured.get("executor_ok") is False:
        hyps.append(
            {
                "cause": "motor_miss",
                "confidence": 0.85,
                "evidence": ["executor_ok=false"],
                "recommended_next": "reperceive",
            }
        )

    # De-dupe by cause, keep highest confidence.
    best: Dict[str, Dict[str, Any]] = {}
    for h in hyps:
        c = str(h.get("cause") or "")
        prev = best.get(c)
        if prev is None or float(h.get("confidence") or 0) > float(prev.get("confidence") or 0):
            best[c] = h
    return sorted(best.values(), key=lambda h: -float(h.get("confidence") or 0))


def _reflect_packet(execution_state: Any) -> Dict[str, Any]:
    """Build the REFLECT brief: context for the perceptor to *discover* why.

    Inputs are measured facts (intended vs landed geometry, expectation vs
    observed surface, attribution, prior looks). The perceptor's job is to
    explain; the runtime must not pre-answer with a task-specific story.
    """
    if execution_state is None:
        return {}
    meta = str(getattr(execution_state, "last_meta_action", "") or "").strip().lower()
    mode = str(getattr(execution_state, "perception_mode", "") or "").strip().lower()
    # Controller sets perception_mode=reflect on surprise_demands_relook before
    # the look; sync also sets it when meta=REFLECT. Ordinary PERCEIVE stays quiet.
    if mode != "reflect" and meta != "reflect":
        return {}

    from plugin.agent.transition.attribution import (
        parse_execution_detail,
        parse_motor_landed_point,
    )

    step = getattr(execution_state, "last_plan_step", None)
    action_block: Dict[str, Any] = {
        "action": str(getattr(execution_state, "last_action", "") or ""),
        "family": str(
            getattr(step, "action_family", None)
            or getattr(execution_state, "last_action", "")
            or ""
        ),
        "target": str(getattr(step, "semantic_target", "") or ""),
        "text": str(getattr(step, "text", "") or ""),
    }
    intended = _as_xy(getattr(step, "target_point", None) if step is not None else None)
    if intended:
        action_block["intended_point"] = intended
        action_block["point"] = list(intended)  # alias for older readers

    result = getattr(execution_state, "last_result", None)
    result_msg = ""
    if isinstance(result, dict):
        result_msg = str(result.get("message") or "")
        action_block["executor_ok"] = bool(result.get("ok"))
        action_block["executor_message"] = result_msg[:200]
    landed = parse_motor_landed_point(result_msg)
    if landed is None:
        detail = parse_execution_detail(result if isinstance(result, dict) else {})
        landed = detail.get("motor_landed_point")
    if isinstance(landed, (list, tuple)):
        action_block["motor_landed_point"] = list(landed)

    expected = getattr(execution_state, "unified_last_expectation", None)
    if not isinstance(expected, dict):
        expected = {}
    error = getattr(execution_state, "last_prediction_error", None)
    actual: Dict[str, Any] = {}
    if isinstance(error, dict) and error:
        actual = {
            "predicted_surface": error.get("predicted_surface"),
            "observed_surface": error.get("observed_surface"),
            "matched": error.get("matched"),
            "verdict": error.get("verdict"),
            "controls_absent": error.get("controls_absent"),
        }
    doc = getattr(execution_state, "unified_world_document", None)
    if isinstance(doc, dict):
        actual.setdefault("surface", doc.get("surface"))
        actual.setdefault("open_conversation", doc.get("open_conversation"))
        # Before note_prediction_error runs, still expose expected-vs-prior-world.
        if "matched" not in actual and expected.get("surface"):
            pred = _norm_text(expected.get("surface"))
            obs = _norm_text(doc.get("surface"))
            if pred and obs:
                actual["predicted_surface"] = pred
                actual["observed_surface"] = obs
                actual["matched"] = pred == obs or pred in obs or obs in pred

    attrib = getattr(execution_state, "last_attribution", None)
    measured: Dict[str, Any] = {}
    if isinstance(attrib, dict) and attrib:
        measured["effect"] = str(attrib.get("effect_kind") or "")
        measured["outcome"] = str(attrib.get("outcome") or "")
        measured["failure_domain"] = str(attrib.get("likely_failure_domain") or "")
        ev = attrib.get("evidence") if isinstance(attrib.get("evidence"), dict) else {}
        if ev.get("change_score") is not None:
            try:
                measured["world_change_score"] = round(float(ev.get("change_score")), 3)
            except (TypeError, ValueError):
                pass
        if "executor_ok" in ev:
            measured["executor_ok"] = bool(ev.get("executor_ok"))
        notes = [str(n) for n in (attrib.get("notes") or []) if str(n).strip()][:4]
        if notes:
            measured["attribution_notes"] = notes
    if landed:
        measured["motor_landed_point"] = list(landed)
    if intended and landed:
        dist = ((intended[0] - landed[0]) ** 2 + (intended[1] - landed[1]) ** 2) ** 0.5
        measured["intended_vs_landed_distance_px"] = round(dist, 1)
        measured["geometry_mismatch"] = dist >= 80.0

    priors = list(getattr(execution_state, "recent_perceptions", None) or [])
    frame = int(getattr(execution_state, "unified_frame", 0) or 0)
    prior_compact = [p for p in priors if isinstance(p, dict) and p.get("iteration") != frame][-4:]

    # Post-act accepted world (if any) — needed to spot partial transitions
    # (selection toolbar Forward after a failed picker prediction).
    post_world: Dict[str, Any] = {}
    if isinstance(doc, dict):
        post_world = {
            "surface": doc.get("surface"),
            "open_conversation": doc.get("open_conversation"),
            "objects": [
                o for o in (doc.get("objects") or []) if isinstance(o, dict)
            ][:24],
        }

    sel = getattr(execution_state, "last_selection_consistency", None)
    if isinstance(sel, dict) and sel:
        measured["selection_consistency"] = {
            "consistent": sel.get("consistent"),
            "selection_count": sel.get("selection_count"),
            "verdict": str(sel.get("verdict") or "")[:160],
            "reasons": list(sel.get("reasons") or [])[:6],
        }
        if isinstance(error, dict) and error.get("selection_consistency"):
            measured["selection_consistency"] = error.get("selection_consistency")

    packet = {
        "task": (
            "LOCALIZE the fault and emit one repair (ReflectDiagnosis). Measured "
            "facts: intended_point vs motor_landed_point, expected vs observed "
            "surface, executor_message, attribution, prior_perceptions. Do not "
            "invent a motor path. World_model update is secondary and critic-gated."
        ),
        "discovery_questions": [
            "Did the motor land where the brain intended?",
            "Did the executor use a degraded path (background AXPress)?",
            "Did the expected surface appear, or a partial/wrong transition?",
            "Is there an observed control that advances the goal?",
            "Is selection chrome goal-inconsistent (wrong multi-select → revert_effects)?",
        ],
        "action": action_block,
        "expected": expected,
        "actual": actual,
        "measured": measured,
        "prior_perceptions": prior_compact,
        "post_world": post_world,
    }
    pending = getattr(execution_state, "pending_repair_after_revert", None)
    if isinstance(pending, dict) and pending:
        packet["pending_repair_after_revert"] = dict(pending)
    if isinstance(sel, dict) and sel:
        packet["selection_consistency"] = sel
    # Goal content tokens help wrong-selection seeds without task-specific forks.
    if isinstance(error, dict) and isinstance(error.get("selection_consistency"), dict):
        tokens = error["selection_consistency"].get("goal_tokens") or []
        if tokens:
            packet["goal_referents"] = list(tokens)[:6]
    packet = enrich_reflect_packet(packet)
    # Measured hypotheses — evidence for the perceptor, not a decision.
    hyps = discover_surprise_hypotheses(packet)
    if hyps:
        packet["discovery_hypotheses"] = hyps[:4]
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
        frame_graph = document.get("frame_graph")
        if frame_graph is None:
            surface_meta = document.get("task_surface")
            if isinstance(surface_meta, dict):
                frame_graph = surface_meta.get("frame_graph")
            elif execution_state is not None:
                surface_meta = getattr(execution_state, "task_surface", None)
                if isinstance(surface_meta, dict):
                    frame_graph = surface_meta.get("frame_graph")
                elif surface_meta is not None:
                    frame_graph = getattr(surface_meta, "frame_graph", None)
        frontier = build_affordance_frontier(
            surface=str(document.get("surface") or ""),
            goal_kind=str(goal.kind or ""),
            ax_evidence=ax_evidence,
            objects=[o for o in (document.get("objects") or []) if isinstance(o, dict)],
            overlay=overlay,
            memory=memory_for(execution_state) if execution_state is not None else None,
            # Producer stamps — frame_id comes from FrameGraph per coordinate_space.
            capture_id=str(document.get("capture_id") or "").strip(),
            frame_graph=frame_graph,
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
    # Close reveal → affordance_set: publish grounded controls or tick handoff TTL.
    try:
        from plugin.agent.affordance_frontier import finalize_reveal_handoff

        finalize_reveal_handoff(execution_state, frontier)
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

    reader = getattr(execution_state, "repeated_attempts", None)
    tried = reader() if callable(reader) else []
    if tried:
        out["moves_already_tried_more_than_once"] = tried
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
    "You are the stage-1 perceptor for a macOS UI agent. Upstream assembly "
    "already packed vision structure (screenshot), OCR geometry (lines with "
    "screen-point bounds), AX, and a passive affordance_frontier. You propose "
    "the world document and may visually rank suggested actions over that "
    "frontier. You do NOT commit belief and you do NOT execute — a critic "
    "accepts or rejects your world update, then same-node affordance closure "
    "runs, then the brain decides.\n\n"
    "Each call you receive your previous world_model, screenshot, OCR lines "
    "with bounds, AX evidence, last action result, affordance_frontier, and "
    "goal. Reason over pixels and OCR jointly: use the screenshot for "
    "structure/roles; prefer OCR bounds when an object matches a line — do not "
    "invent a click point that contradicts a matching OCR rectangle. AX is "
    "often chrome-only; trust pixels when they disagree, but prefer an AX id "
    "when one matches what you see.\n\n"
    "task_surface (when present) describes multi-display geometry: which "
    "display holds the task window, window_bounds in global desktop points, "
    "and capture_origin. Image (0,0) is the window top-left — not the main "
    "display origin. Prefer OCR/AX screen points; if you emit image-relative "
    "points set coordinate_space=image.\n\n"
    "observation.sources lists every input and the state of each. accessibility "
    "state chrome_only means read the pixels. ocr state off means nobody read "
    "text this frame. ocr state on carries lines with bounds in screen points; "
    "treat a partial match as support rather than contradiction.\n\n"
    "Return the updated world_model, optional suggested_actions with why, and "
    "frontier enrichment. Do not return next_action (the brain fills that). "
    "Strict JSON only:\n"
    "{\n"
    '  "world_model": {\n'
    '    "surface": enum,\n'
    '    "open_conversation": str,\n'
    '    "objects": [{"id": str, "kind": str, "text": str, "point": [x, y], '
    '"matches_goal": bool, "owner_surface": str, "selected": bool}],\n'
    '    "beliefs": [{"predicate": str, "value": bool, "confidence": float, '
    '"evidence": [str], "owner_surface": str, "semantic_role": str, '
    '"rejected_evidence": [{"text": str, "reason": str}], '
    '"confirmed_on_frame": int}],\n'
    '    "progress": {"phase": str, "objective": str, "notes": str},\n'
    '    "attempts": [{"frame": int, "action": str, "target": str, "result": str}],\n'
    '    "exhausted": [str]\n'
    "  },\n"
    '  "suggested_actions": [{"rank": int, "family": str, "target_id": int|null, '
    '"text": str, "confidence": float, "why": str}],\n'
    '  "expected_transition": {"surface": str, "likely_controls": [str]},\n'
    '  "backtrack": {"reason": str, "to": str}|null,\n'
    '  "missing_evidence": [str],\n'
    '  "evidence_gaps": [str],\n'
    '  "coverage": float,\n'
    '  "missing_affordance_information": [str],\n'
    '  "recommended_probe": {"family": str, "target_id": int|null, '
    '"may_reveal": [str], "reason": str}|null,\n'
    '  "affordance_qc": {"expected_found": bool, "missing": [str], "notes": str},\n'
    '  "affordance_stance": "act_clear"|"explore_needed"|"ambiguous",\n'
    '  "scene_summary": str,\n'
    '  "confidence": float\n'
    "}\n\n"
    "suggested_actions is optional visual advice for the brain: up to three "
    "entries, best first, each with a short why tied to what you see (object, "
    "frontier entry, or OCR line). The brain may accept or override; nothing "
    "here executes. Prefer families that appear on affordance_frontier.\n\n"
    "affordance_qc is your internal quality check against the stage0 frontier "
    "and the screenshot: set expected_found=true when the task-critical "
    "same-node control is already represented (e.g. Forward latent/probe on a "
    "conversation with the target message, Send on a forward picker, or "
    "Forward observed on an open context menu). If it is not figured out yet, "
    "expected_found=false and list missing labels — the brain may then ask to "
    "reperceive rather than transition.\n\n"
    "affordance_stance is your judgment of whether the goal act is already "
    "clear on this screen: act_clear when the goal verb/control is visible "
    "(e.g. Forward on an open context/action menu) — then top suggested_actions "
    "must be invoke_affordance/commit on that control, not reveal_actions. "
    "On a destination picker, act_clear for the commit control only after a "
    "recipient matching the goal destination is selected *inside that picker*; "
    "otherwise explore_needed and prefer searching/selecting the destination. "
    "ambiguous when several plausible acts compete.\n\n"
    "affordance_frontier is the runtime's passive reading of this UI node "
    "(current state). observed_actions are visible now; latent_actions need a "
    "reversible stimulus on this same node; probe_actions are unknown worth "
    "revealing in place; known_transition_edges leave this node when invoked. "
    "If the screenshot shows a control the frontier omits, name it in "
    "missing_affordance_information and put it in objects with a point.\n\n"
    "recommended_probe names one reversible same-node stimulus (hover / "
    "reveal_actions) that would expose latent controls. expected_transition "
    "predicts what that probe or the last action would produce.\n\n"
    "evidence_gaps names, as questions, what you could not establish from this "
    "frame — e.g. 'is the target message below the current fold?' or 'which of "
    "two similar rows is the destination?'. coverage is your estimate, 0.0 to "
    "1.0, of how much of the task-relevant surface you actually saw. "
    "Under-report coverage rather than overclaim.\n\n"
    "perception_objective, when present, is what the executive needs this look "
    "to establish. Prioritise answering those questions in beliefs and objects; "
    "if you cannot, name exactly what is missing in evidence_gaps.\n\n"
    "world_model is carried forward verbatim, so it is the only memory you "
    "have. Return the whole updated document every time, not a diff. Keep what "
    "is still true, revise what the new evidence contradicts, and drop what no "
    "longer applies.\n\n"
    "objects is the inventory of task-relevant things currently on screen: chat "
    "rows in a list, messages in a conversation. At most 10, each with its text "
    "truncated to about 60 characters and the screen point the brain would use "
    "to act on it. Mark matches_goal on the object that matches the current "
    "goal referent. When the goal is a link/URL hunt, prefer the URL-bearing "
    "message (http/https) — do not mark a plain caption that only contains "
    "the query tokens. AX often reports none of these, so this inventory is how "
    "the rest of the agent learns what exists. Never treat search-field text "
    "as open_conversation.\n\n"
    "beliefs are what you have concluded that is not visible in this one frame. "
    "Every belief must carry the evidence for it and the frame it was last "
    "confirmed on. If the packet lists a belief under unconfirmed_beliefs, look "
    "for it in the current screenshot: reconfirm it with fresh evidence and "
    "update confirmed_on_frame, or retract it. Never carry a belief forward "
    "just because you asserted it earlier.\n\n"
    "progress.phase and progress.objective describe where the task appears to "
    "be from the screen (not a plan to execute). attempts and exhausted record "
    "what the runtime has already tried — use them when updating beliefs, not "
    "to invent the next capability.\n\n"
    "Set backtrack when the current branch looks exhausted, saying why and "
    "where to return to. Otherwise leave it null.\n\n"
    "surface must be exactly one of: "
    + ", ".join(CANONICAL_SURFACES)
    + ". Never invent a new label or a prose variant; put extra description in "
    "scene_summary.\n\n"
    "scene_summary is one or two plain sentences describing what is on screen "
    "right now. Describe what you actually see, not what you expect to see, "
    "and do not announce the next capability.\n\n"
    "Every point you report in objects must be in the pixel coordinates of the "
    "screenshot you were given, whose dimensions are in observation.image_size, "
    "with the origin at its top left. Do not rescale; the runtime converts.\n\n"
    "REFLECT on the last outcome before you update the world. last_action reports "
    "what the runtime just did and, as raw measured fact, what it did to the "
    "world: result.ok says the click fired; effect says whether the world "
    "actually moved (no_transition means it did not), world_change_score near 0 "
    "and open_before==open_after mean nothing changed, failure_domain and "
    "diagnosis_hints name the runtime's guess at why, and "
    "times_repeated_in_a_row counts how often that move has already been issued. "
    "you_predicted / prediction_error score the prior expected_transition against "
    "this screen. Treat a prediction_error as the most informative thing in the "
    "packet: your model of what that control does was wrong. State the hypothesis "
    "in progress.notes (wrong pixel, wrong object, overlay intercept, unexpected "
    "app) and revise objects, beliefs, and frontier enrichment accordingly — do "
    "not invent the next capability.\n"
    "stuck_signals is the clock and the ledger: seconds_since_anything_advanced "
    "and moves_already_tried_more_than_once. Use them when updating exhausted / "
    "beliefs; they are measurements, not orders.\n"
    "last_action.recent_surprises, when present, is a short history of failed "
    "moves. If the same surprise recurs (e.g. clicking a conversation row keeps "
    "opening a link), re-perceive that region at finer granularity and describe "
    "in world_model.objects the distinct sub-regions (link text vs. the safe "
    "area of the row). Let surprises sharpen perception, not pick the next move."
)


# Fast path: keep completions tiny (paired with max_tokens ≤ 250).
_COMPACT_OUTPUT_ADDENDUM = (
    "\n\nOUTPUT BUDGET. Prefer compact JSON. Do not write essays. "
    "scene_summary: at most two short sentences. Omit empty optional fields. "
    "Cap objects at the task-relevant set (≤12) and suggested_actions at ≤4. "
    "Include confidence (0..1) and needs_more_evidence (bool) at the top level "
    "when unsure."
)

# Local small-VLM path: tiny prompt + tiny JSON. Generation, not vision, was the
# warm-latency bottleneck (~5s for ~77 tokens on qwen3.5:4b).
_FAST_SYSTEM_PROMPT = (
    "UI perceptor. Screenshot only. ONE minified JSON line "
    "(no spaces/newlines/markdown). Example:\n"
    '{"surface":"search","objects":[{"id":"m1","role":"field","text":"q",'
    '"point":[10,20],"match":0.9}],'
    '"actions":[{"family":"observe","target":"m1","score":0.5}],'
    '"needs_more_evidence":false,"confidence":0.9}\n'
    "surface∈chat_list|conversation|search|dialog|forward_picker|other. "
    "≤2 objects, ≤1 action, text≤24 chars, points in image_size. End at }."
)

# Architect band: 150–250. Truncated-JSON repair still covers early stops.
_FAST_MAX_TOKENS = 200
_FAST_AX_CAP = 8

# Added when packet.perception_mode == reflect (surprise / prediction error).
# Canonical schema lives in reflect_diagnosis.reflect_schema_addendum().
_REFLECT_ADDENDUM = reflect_schema_addendum()


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

# Always on: compositional surface ownership (architect review of live 184742).
# Selection/status claims belong to an owner surface; foreground scopes evidence
# for the active intention. Do NOT flatten the screen into a bag of labels.
_SURFACE_OWNERSHIP_ADDENDUM = (
    "\n\nSURFACE OWNERSHIP. Screens are compositional. A foreground modal/"
    "picker can sit over a background conversation that still has its own "
    "selection chrome. Every object and every belief claim must name its "
    "owner_surface (and, for selection claims, semantic_role).\n"
    "Typed selection predicates are distinct namespaces:\n"
    "  - source_message_selected_count / source_object_selected "
    "(owner_surface on the background conversation / selection bar)\n"
    "  - destination_selected_count / destination_selected "
    "(owner_surface on the foreground destination picker only)\n"
    "Never use selection indicators from one surface as evidence about another. "
    "When the active interaction surface is a destination picker, answer "
    "destination questions from picker evidence (rows, checkboxes, picker search "
    "field) — background selection chrome is irrelevant to destination_selected.\n"
    "Belief schema (extend the usual fields):\n"
    '  {"predicate","value","confidence","evidence","owner_surface",'
    '"semantic_role","rejected_evidence":[{"text","reason","owner_surface"}]}\n'
    "Objects should include owner_surface when overlays are present. "
    "If destination D is the goal and is neither visible nor selected inside "
    "the picker while a picker search field is available, set "
    "destination_selected=false (owner_surface=forward_picker), put the search "
    "field in objects, affordance_stance=explore_needed, and rank "
    "type_query/search of D — not invoke of the commit control."
)


def _max_image_width() -> int:
    """Default 640 — task ROI + small VLM; override with HERMES_UNIFIED_IMAGE_MAX_WIDTH."""
    try:
        return max(320, int(os.getenv("HERMES_UNIFIED_IMAGE_MAX_WIDTH", "640")))
    except (TypeError, ValueError):
        return 640


def _full_window_max_width() -> int:
    """Wider cap when phase ROI is unknown (orientation look)."""
    try:
        return max(320, int(os.getenv("HERMES_UNIFIED_FULL_IMAGE_MAX_WIDTH", "896")))
    except (TypeError, ValueError):
        return 896


def _perception_roi_enabled() -> bool:
    raw = str(os.getenv("HERMES_PERCEPTION_ROI", "phase") or "").strip().lower()
    return raw not in {"0", "false", "no", "off", "none", "full"}


def resolve_phase_roi(
    phase: str,
    width: int,
    height: int,
    *,
    focus_y_px: Optional[float] = None,
) -> Optional[Tuple[int, int, int, int]]:
    """WhatsApp-forward phase → crop box in capture pixels, or None for full window.

    Matches the bench win (sidebar @ 640 ≈ −62% latency). Coordinates are in the
    screenshot file's pixel space (Retina-backed when capture.scale == 2).
    """
    if width <= 0 or height <= 0:
        return None
    p = str(phase or "").strip().upper()
    if p in {"OPEN_SOURCE"}:
        left = int(width * 0.07)
        right = int(width * 0.42)
        return (left, 0, max(left + 1, right), height)
    if p in {"FIND_LINK", "PICK_DEST", "SELECT_DESTINATION"}:
        left = int(width * 0.42)
        return (left, 0, width, height)
    if p in {"OPEN_FORWARD"}:
        left = int(width * 0.42)
        if focus_y_px is not None and focus_y_px >= 0:
            band = max(180, int(height * 0.35))
            top = max(0, int(focus_y_px - band / 2.0))
            bottom = min(height, top + band)
            if bottom - top < 80:
                return (left, 0, width, height)
            return (left, top, width, max(top + 1, bottom))
        return (left, 0, width, height)
    return None


def _phase_from_features(features: StateFeatures) -> str:
    extras = features.extras if isinstance(features.extras, dict) else {}
    phase = str(extras.get("forward_phase") or "").strip()
    if not phase:
        ft = extras.get("forward_task")
        if isinstance(ft, dict):
            phase = str(ft.get("derived_phase") or "").strip()
    return phase


def _focus_y_capture_px(
    execution_state: Any, capture: CaptureFrame
) -> Optional[float]:
    """Last motor target Y in capture-pixel space, for OPEN_FORWARD neighborhood crops."""
    if execution_state is None:
        return None
    step = getattr(execution_state, "last_plan_step", None)
    pt = getattr(step, "target_point", None) if step is not None else None
    if not isinstance(pt, (list, tuple)) or len(pt) < 2:
        uni = getattr(execution_state, "last_unified_proposal", None)
        if isinstance(uni, dict):
            na = uni.get("next_action") if isinstance(uni.get("next_action"), dict) else {}
            pt = na.get("target_point") or na.get("point")
    if not isinstance(pt, (list, tuple)) or len(pt) < 2:
        return None
    try:
        screen_y = float(pt[1])
    except (TypeError, ValueError):
        return None
    scale = capture.scale if capture.scale > 0 else 1.0
    return (screen_y - float(capture.origin_y)) * scale


def _encode_perception_image(
    screenshot_path: str,
    *,
    crop_box: Optional[Tuple[int, int, int, int]] = None,
    max_width: Optional[int] = None,
) -> Tuple[str, Tuple[int, int], Optional[Tuple[int, int, int, int]], int]:
    """Crop (optional) then width-cap JPEG. Returns data_url, size, applied_crop, bytes."""
    import base64
    import io

    try:
        from PIL import Image
    except Exception:
        return "", (0, 0), None, 0
    try:
        with Image.open(screenshot_path) as image:
            image = image.convert("RGB")
            applied: Optional[Tuple[int, int, int, int]] = None
            if crop_box is not None:
                left, top, right, bottom = crop_box
                left = max(0, min(image.width - 1, int(left)))
                top = max(0, min(image.height - 1, int(top)))
                right = max(left + 1, min(image.width, int(right)))
                bottom = max(top + 1, min(image.height, int(bottom)))
                image = image.crop((left, top, right, bottom))
                applied = (left, top, right, bottom)
            limit = int(max_width) if max_width is not None else _max_image_width()
            if limit > 0 and image.width > limit:
                height = max(1, round(image.height * limit / image.width))
                image = image.resize((limit, height), Image.LANCZOS)
            size = (image.width, image.height)
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=80, optimize=True)
            raw = buffer.getvalue()
        encoded = base64.b64encode(raw).decode()
        return f"data:image/jpeg;base64,{encoded}", size, applied, len(raw)
    except Exception as exc:
        logger.debug("Unified cognition: encode failed (%s); using original", exc)
        return "", (0, 0), None, 0


def _downscaled_data_url(screenshot_path: str) -> Tuple[str, Tuple[int, int]]:
    """Shrink the frame before sending it, and report the size the model sees.

    The size matters as much as the image: the model answers in the coordinate
    space of the picture it was given, so the runtime has to know that space to
    turn a point back into a place on screen.

    A full Retina window is mostly redundant pixels for this decision, and
    image tokens dominate both latency and cost on the fast path.
    """
    data_url, size, _crop, _nbytes = _encode_perception_image(screenshot_path)
    return data_url, size


def screen_point_scale(
    screenshot_path: str,
    image_width: int,
    capture: Optional[CaptureFrame] = None,
    *,
    source_width_px: Optional[int] = None,
) -> float:
    """Points on screen per unit in the image the model was shown.

    Two reductions separate the model's picture from the screen. The frame is
    downscaled before it is sent, so the model answers in the picture's
    coordinates; and the capture itself is in backing pixels, which on a Retina
    panel are half a point each. Executing the model's numbers unconverted put
    every pointer action off by the product of the two -- far enough to
    right-click the message below the one that was chosen, which read as the
    model misidentifying the target rather than as a units bug.

    When a phase ROI crop was applied, ``source_width_px`` must be the *crop*
    width in capture pixels — not the full screenshot width — or clicks drift
    by full_w / crop_w.

    The Retina half is taken from the measured capture transform rather than
    from the main screen's width. The capture is scoped to a *window*, so
    comparing its width to the whole display's answers a different question and
    silently returns a plausible wrong number.
    """
    if image_width <= 0:
        return 1.0
    captured_width = int(source_width_px or 0)
    if captured_width <= 0:
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


def _fast_perception_enabled() -> bool:
    # Off unless explicitly enabled — compact/4b latency path is not SoT.
    raw = str(os.getenv("HERMES_PERCEPTION_COMPACT", "0") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _is_fast_vlm_target(target: Dict[str, Any]) -> bool:
    """True for local small VLMs on the compact path (not cloud escalate)."""
    if not _fast_perception_enabled():
        return False
    provider = str(target.get("provider") or "").strip().lower()
    model = str(target.get("model") or "").strip().lower()
    source = str(target.get("source") or "")
    if source.startswith("env:HERMES_PERCEPTION_ESCALATE_MODEL"):
        return False
    if "cloud" in provider or model.endswith(":cloud") or "397b" in model or "120b" in model:
        return False
    if provider in {"ollama", "ollama-remote"}:
        return True
    # Explicit fast pin.
    if source.startswith("env:HERMES_PERCEPTION_FAST_MODEL"):
        return True
    return False


def _compact_fast_packet(packet: Dict[str, Any], *, phase: str = "") -> Dict[str, Any]:
    """Strip the user packet to what a small VLM needs for grounding."""
    goal = packet.get("goal") if isinstance(packet.get("goal"), dict) else {}
    obs = packet.get("observation") if isinstance(packet.get("observation"), dict) else {}
    prior = packet.get("world_model") if isinstance(packet.get("world_model"), dict) else {}
    last = packet.get("last_action") if isinstance(packet.get("last_action"), dict) else {}
    ax = list(obs.get("ax_evidence") or [])[:_FAST_AX_CAP]
    compact_ax = []
    for item in ax:
        if not isinstance(item, dict):
            continue
        compact_ax.append(
            {
                k: item.get(k)
                for k in ("id", "role", "name", "label", "text", "point")
                if item.get(k) not in (None, "", [], ())
            }
        )
    out: Dict[str, Any] = {
        "goal": {
            k: goal.get(k)
            for k in (
                "operation",
                "source_conversation",
                "source_query",
                "destination",
            )
            if goal.get(k)
        },
        "phase": phase or str((prior.get("progress") or {}).get("phase") or ""),
        "prior": {
            "surface": prior.get("surface") or "",
            "open_conversation": prior.get("open_conversation") or "",
        },
        "observation": {
            "image_size": obs.get("image_size"),
            "image_roi": obs.get("image_roi"),
            "ax": compact_ax,
        },
    }
    if last:
        out["last_action"] = {
            k: last.get(k)
            for k in ("family", "action", "target", "ok", "effect")
            if last.get(k) not in (None, "")
        }
    obj = packet.get("perception_objective")
    if isinstance(obj, dict) and obj.get("questions"):
        out["questions"] = [str(q) for q in (obj.get("questions") or [])][:3]
    return out


def _repair_truncated_json(raw: str) -> Optional[Dict[str, Any]]:
    """Best-effort close of a truncated minified JSON object from a token cap."""
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        pass
    # Trim to last complete-looking value boundary, then close brackets.
    cut = text
    for end in ("}", "]", '"', "e", "0", "1", "2", "3", "4", "5", "6", "7", "8", "9"):
        idx = cut.rfind(end)
        if idx > 0:
            cut = cut[: idx + 1]
            break
    opens = cut.count("{") - cut.count("}")
    opens_list = cut.count("[") - cut.count("]")
    # Balance quotes if odd.
    if cut.count('"') % 2 == 1:
        cut += '"'
    cut += "]" * max(0, opens_list)
    cut += "}" * max(0, opens)
    try:
        parsed = json.loads(cut)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _expand_fast_parsed(parsed: Dict[str, Any], *, frame: int = 0) -> Dict[str, Any]:
    """Map architect-style compact JSON into the rich proposal shape."""
    if not isinstance(parsed, dict):
        return {}
    # Already rich?
    if isinstance(parsed.get("world_model"), dict):
        return parsed
    objects_in = parsed.get("objects") if isinstance(parsed.get("objects"), list) else []
    objects_out: List[Dict[str, Any]] = []
    for i, item in enumerate(objects_in[:2]):
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or item.get("role") or item.get("id") or "").strip()
        if not text:
            continue
        match = item.get("match")
        try:
            match_f = float(match) if match is not None else 0.0
        except (TypeError, ValueError):
            match_f = 0.0
        objects_out.append(
            {
                "id": str(item.get("id") or f"m{i + 1}")[:24],
                "kind": str(item.get("role") or item.get("kind") or "object")[:24],
                "text": text[:60],
                "point": item.get("point"),
                "matches_goal": bool(item.get("matches_goal") or match_f >= 0.7),
            }
        )
    actions_in = parsed.get("actions") if isinstance(parsed.get("actions"), list) else []
    if not actions_in and isinstance(parsed.get("suggested_actions"), list):
        actions_in = list(parsed.get("suggested_actions") or [])
    suggested: List[Dict[str, Any]] = []
    for i, item in enumerate(actions_in[:1]):
        if not isinstance(item, dict):
            continue
        fam = str(item.get("family") or item.get("action") or "").strip()
        if not fam:
            continue
        try:
            score = float(item.get("score") if item.get("score") is not None else item.get("confidence") or 0.0)
        except (TypeError, ValueError):
            score = 0.0
        suggested.append(
            {
                "rank": i + 1,
                "family": fam,
                "target_id": item.get("target_id"),
                "text": str(item.get("target") or item.get("text") or "")[:60],
                "confidence": score,
                "why": "fast_path",
            }
        )
    needs_more = bool(parsed.get("needs_more_evidence"))
    surface = str(parsed.get("surface") or "").strip()
    return {
        "world_model": {
            "surface": surface,
            "open_conversation": str(parsed.get("open_conversation") or ""),
            "objects": objects_out,
            "progress": {
                "phase": str(parsed.get("phase") or ""),
                "objective": "",
                "notes": "",
            },
            "beliefs": [],
            "attempts": [],
            "exhausted": [],
        },
        "suggested_actions": suggested,
        "missing_evidence": ["needs_more_evidence"] if needs_more else [],
        "evidence_gaps": ["needs_more_evidence"] if needs_more else [],
        "coverage": 0.55 if needs_more else 0.85,
        "confidence": parsed.get("confidence"),
        "scene_summary": str(parsed.get("scene_summary") or "")[:160],
        "needs_more_evidence": needs_more,
    }


def _build_messages(
    packet: Dict[str, Any],
    screenshot_path: str,
    *,
    crop_box: Optional[Tuple[int, int, int, int]] = None,
    max_width: Optional[int] = None,
    fast_path: bool = False,
    phase: str = "",
    data_url: str = "",
    image_size: Optional[Tuple[int, int]] = None,
    encoded_bytes: int = 0,
    applied_crop: Optional[Tuple[int, int, int, int]] = None,
) -> Tuple[List[Dict[str, Any]], Tuple[int, int]]:
    from plugin.agent.perception_synthesis import _screenshot_to_data_url

    size: Tuple[int, int] = image_size or (0, 0)
    if screenshot_path and not data_url:
        data_url, size, applied_crop, encoded_bytes = _encode_perception_image(
            screenshot_path, crop_box=crop_box, max_width=max_width
        )
        if not data_url:
            data_url = _screenshot_to_data_url(screenshot_path)

    use_packet = _compact_fast_packet(packet, phase=phase) if fast_path else packet
    if size[0] > 0:
        # Tell the model the frame it is looking at, so its coordinates are
        # anchored to something stated rather than inferred.
        observation = use_packet.get("observation")
        if isinstance(observation, dict):
            observation["image_size"] = [size[0], size[1]]
            if applied_crop is not None:
                observation["image_roi"] = list(applied_crop)
            if encoded_bytes and not fast_path:
                observation["encoded_bytes"] = int(encoded_bytes)
        # Keep encode meta on the full packet for callers.
        full_obs = packet.get("observation")
        if isinstance(full_obs, dict):
            full_obs["image_size"] = [size[0], size[1]]
            if applied_crop is not None:
                full_obs["image_roi"] = list(applied_crop)
            if encoded_bytes:
                full_obs["encoded_bytes"] = int(encoded_bytes)

    text_block = {"type": "text", "text": json.dumps(use_packet, ensure_ascii=False)}
    content: Any = [text_block]
    if data_url:
        content.append({"type": "image_url", "image_url": {"url": data_url}})
    else:
        # No pixels available this cycle: fall back to a text-only request
        # rather than sending an empty image block the provider will reject.
        content = json.dumps(use_packet, ensure_ascii=False)
    if fast_path:
        system_prompt = _FAST_SYSTEM_PROMPT
    else:
        system_prompt = (
            _SYSTEM_PROMPT + _COMPACT_OUTPUT_ADDENDUM + _SURFACE_OWNERSHIP_ADDENDUM
        )
        try:
            from plugin.agent.scene_layers import layered_perception_enabled

            if layered_perception_enabled():
                system_prompt = system_prompt + _LAYERED_PERCEPTION_ADDENDUM
        except Exception:
            pass
        if str(packet.get("perception_mode") or "") == "reflect" or isinstance(
            packet.get("reflect"), dict
        ):
            system_prompt = system_prompt + _REFLECT_ADDENDUM
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": content},
    ], size


def _destination_search_perception_objective(
    goal: Goal, document: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """Executive look objective when destination must be resolved in a picker."""
    dest = str(getattr(goal, "target_contact", "") or "").strip()
    surface = str(document.get("surface") or "").strip().lower()
    if not dest or surface not in {"forward_picker", "destination_picker", "dialog"}:
        return None
    dest_l = dest.lower()
    visible = False
    selected = False
    search_field = False
    for obj in document.get("objects") or []:
        if not isinstance(obj, dict):
            continue
        text = str(obj.get("text") or obj.get("label") or "").strip().lower()
        kind = str(obj.get("kind") or obj.get("semantic_role") or "").strip().lower()
        if "search" in text or kind in {"search_input", "textfield", "field"}:
            search_field = True
        if dest_l and (dest_l in text or text in dest_l):
            visible = True
            if bool(obj.get("selected")) or bool(obj.get("matches_goal")):
                selected = True
    if selected:
        return None
    questions = [
        "Which surfaces are present and which is the foreground interaction surface?",
        "What selection state belongs to the foreground destination picker vs background surfaces?",
        f"Is destination {dest} visible or selected inside the destination picker?",
        "Which grounded actions advance destination resolution within the picker?",
    ]
    search_ops = []
    if search_field or surface in {"forward_picker", "destination_picker"}:
        search_ops.append(
            {
                "scope": surface or "forward_picker",
                "search_field": "destination_search",
                "searchable_entity_type": "contact",
                "query_supported": bool(search_field or surface == "forward_picker"),
                "grounding_confidence": 0.98 if search_field else 0.85,
            }
        )
    return {
        "questions": questions,
        "focus": "forward_picker",
        "depth": "deep",
        "objective": (
            f"Resolve destination selection for {dest} within the foreground "
            "destination picker; do not attribute background selection chrome "
            "to destination_selected"
        ),
        "completion_condition": (
            f"destination_selected for {dest} inside picker, or picker search "
            f"path clear (search_field_visible={search_field}, "
            f"destination_visible={visible})"
        ),
        "active_interaction_surface": surface,
        "destination_visible": visible,
        "destination_selected": False,
        "destination_search_available": search_field or surface == "forward_picker",
        "search_opportunities": search_ops,
    }


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


def _normalize_affordance_qc(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    missing = [
        str(x).strip()
        for x in (raw.get("missing") or [])
        if str(x).strip()
    ][:8]
    found = raw.get("expected_found")
    return {
        "expected_found": bool(found) if found is not None else (len(missing) == 0 and bool(raw)),
        "missing": missing,
        "notes": str(raw.get("notes") or "")[:200],
    }


_AFFORDANCE_STANCES = frozenset({"act_clear", "explore_needed", "ambiguous"})
_ACT_CLEAR_OVERLAY_SURFACES = frozenset(
    {"context_menu", "action_menu", "selection_mode", "forward_picker"}
)
_OVERLAY_CONTROL_KINDS = frozenset(
    {
        "menu_item",
        "menuitem",
        "button",
        "toolbar_button",
        "action",
        "control",
        "menuitemcheckbox",
        "menuitemradio",
    }
)


def _normalize_affordance_stance(raw: Any) -> str:
    text = str(raw or "").strip().lower().replace("-", "_").replace(" ", "_")
    if text in _AFFORDANCE_STANCES:
        return text
    aliases = {
        "clear": "act_clear",
        "act": "act_clear",
        "ready": "act_clear",
        "explore": "explore_needed",
        "explore_affordances": "explore_needed",
        "need_explore": "explore_needed",
        "unclear": "ambiguous",
    }
    return aliases.get(text, "")


def _proposal_surface(proposal: "UnifiedProposal") -> str:
    state = proposal.observed_state or {}
    doc = proposal.world_model or {}
    return str(state.get("surface") or doc.get("surface") or "").strip().lower()


def _inventory_objects(proposal: "UnifiedProposal") -> List[Dict[str, Any]]:
    objects: List[Dict[str, Any]] = []
    for src in (
        proposal.visible_objects,
        (proposal.world_model or {}).get("objects"),
        (proposal.observed_state or {}).get("objects"),
    ):
        if not isinstance(src, (list, tuple)):
            continue
        for item in src:
            if isinstance(item, dict):
                objects.append(item)
    return objects


def _object_has_actuatable_geometry(obj: Dict[str, Any]) -> bool:
    """True when the object carries a clickable point or bounds."""
    if not isinstance(obj, dict):
        return False
    pt = obj.get("point") or obj.get("target_point")
    if isinstance(pt, (list, tuple)) and len(pt) >= 2:
        try:
            float(pt[0])
            float(pt[1])
            return True
        except (TypeError, ValueError):
            pass
    bounds = obj.get("bounds")
    if isinstance(bounds, (list, tuple)) and len(bounds) >= 4:
        try:
            [float(v) for v in bounds[:4]]
            return True
        except (TypeError, ValueError):
            pass
    return False


def _object_is_enabled(obj: Dict[str, Any]) -> bool:
    """False when inventory marks the control disabled/dimmed."""
    if not isinstance(obj, dict):
        return False
    if obj.get("enabled") is False:
        return False
    state = str(obj.get("state") or obj.get("ax_state") or "").strip().lower()
    if state in {"disabled", "dimmed", "unavailable"}:
        return False
    return True


def _goal_destination_name(goal: Any) -> str:
    if goal is None:
        return ""
    if isinstance(goal, dict):
        return str(
            goal.get("destination")
            or goal.get("target_contact")
            or goal.get("target")
            or ""
        ).strip()
    return str(
        getattr(goal, "target_contact", None)
        or getattr(goal, "destination", None)
        or ""
    ).strip()


def _text_matches_name(text: str, wanted: str) -> bool:
    a = str(text or "").strip().lower()
    b = str(wanted or "").strip().lower()
    if not a or not b:
        return False
    if a == b or b in a or a in b:
        return True
    try:
        from plugin.agent.transfer_task import _name_matches

        return bool(_name_matches(a, b))
    except Exception:
        return False


def _forward_picker_destination_state(
    proposal: "UnifiedProposal", *, goal: Any = None
) -> Dict[str, Any]:
    """Inventory-backed destination evidence on Send-to (not 'N Selected' chrome).

    WhatsApp shows '1 Selected' for the *source message* while the picker is
    open; that must not be read as destination_selected (live 184742).
    """
    dest = _goal_destination_name(goal)
    out: Dict[str, Any] = {
        "destination": dest,
        "contact_visible": False,
        "contact_selected": False,
        "contact_obj": None,
        "forward_enabled": False,
        "forward_obj": None,
    }
    if not dest:
        return out
    for obj in _inventory_objects(proposal):
        if not isinstance(obj, dict):
            continue
        text = str(obj.get("text") or obj.get("label") or "").strip()
        text_l = text.lower()
        if text_l in {"forward", "forward message", "forward messages", "share", "send"}:
            if _object_has_actuatable_geometry(obj) and _object_is_enabled(obj):
                out["forward_enabled"] = True
                out["forward_obj"] = obj
            continue
        if _text_matches_name(text, dest):
            out["contact_visible"] = True
            out["contact_obj"] = obj
            if bool(obj.get("selected")) or bool(obj.get("matches_goal")):
                out["contact_selected"] = True
    return out


def _goal_control_from_inventory(
    proposal: "UnifiedProposal", *, goal: Any = None
) -> Optional[Dict[str, Any]]:
    """Return a visible overlay control that already realizes the goal act.

    Honesty contract: label-only verbs without point/bounds do **not** count —
    those cannot be actuated, so stance must not claim ``act_clear``.
    On ``forward_picker``, Forward/Send is act_clear only after the destination
    contact is inventory-selected; otherwise the contact row (if visible) is
    the goal control — never the source-message 'N Selected' chrome.
    """
    surface = _proposal_surface(proposal)
    if surface not in _ACT_CLEAR_OVERLAY_SURFACES:
        return None
    try:
        from plugin.agent.world_critic import _label_looks_like_menu_verb
    except Exception:
        _label_looks_like_menu_verb = None  # type: ignore[assignment]

    if surface == "forward_picker":
        dest_state = _forward_picker_destination_state(proposal, goal=goal)
        if dest_state.get("contact_selected") and dest_state.get("forward_enabled"):
            return dest_state.get("forward_obj")
        contact = dest_state.get("contact_obj")
        if (
            isinstance(contact, dict)
            and _object_has_actuatable_geometry(contact)
            and _object_is_enabled(contact)
        ):
            return contact
        # Stash why Forward must wait / search is owed.
        if isinstance(getattr(proposal, "raw", None), dict):
            proposal.raw = {
                **dict(proposal.raw or {}),
                "forward_picker_dest": {
                    "destination": dest_state.get("destination"),
                    "contact_visible": bool(dest_state.get("contact_visible")),
                    "contact_selected": bool(dest_state.get("contact_selected")),
                    "forward_enabled": bool(dest_state.get("forward_enabled")),
                },
            }
        return None

    preferred: List[str] = []
    kind = str(getattr(goal, "kind", "") or "").lower() if goal is not None else ""
    if "forward" in kind:
        preferred = ["forward", "forward message", "forward messages", "share"]
    elif surface == "forward_picker":
        preferred = ["send"]

    label_only: Optional[Dict[str, Any]] = None
    for obj in _inventory_objects(proposal):
        text = str(obj.get("text") or obj.get("label") or "").strip()
        kind_name = str(obj.get("kind") or obj.get("role") or "").strip().lower()
        text_l = text.lower()
        if not _object_is_enabled(obj):
            continue
        looks_verb = bool(
            _label_looks_like_menu_verb(text)
            if callable(_label_looks_like_menu_verb)
            else text_l in {"forward", "share", "copy", "reply", "send", "delete"}
        )
        if preferred:
            if text_l not in preferred and not any(p == text_l for p in preferred):
                # Allow exact menu-verb match even when preferred is set.
                if not looks_verb:
                    continue
                if text_l not in preferred and "forward" in preferred and "forward" not in text_l:
                    continue
        elif not looks_verb and kind_name not in _OVERLAY_CONTROL_KINDS:
            continue
        if kind_name in _OVERLAY_CONTROL_KINDS or looks_verb:
            if _object_has_actuatable_geometry(obj):
                return obj
            if label_only is None:
                label_only = obj
    # Stash label-only hit on proposal.raw for gaps (not actuatable).
    if label_only is not None and isinstance(getattr(proposal, "raw", None), dict):
        proposal.raw = {
            **dict(proposal.raw or {}),
            "goal_control_label_only": str(
                label_only.get("text") or label_only.get("label") or ""
            )[:80],
        }
    return None


def _commit_known_menu_affordance(
    proposal: "UnifiedProposal", *, goal: Any = None, state: Any = None
) -> None:
    """Stick thin AffordanceCommitment when a goal menu verb is observed."""
    if state is None:
        return
    raw = getattr(proposal, "raw", None) or {}
    label = str(raw.get("goal_control_label_only") or "").strip()
    if not label:
        # Also commit when control is grounded — still executive stickiness.
        control = _goal_control_from_inventory(proposal, goal=goal)
        if isinstance(control, dict):
            label = str(control.get("text") or control.get("label") or "").strip()
    if not label:
        return
    try:
        from plugin.agent.executive.affordance_commitment import (
            ensure_commitment_from_menu_observation,
        )

        patient = str(
            getattr(state, "grounding_reground_patient_ref", "") or ""
        )
        if not patient:
            doc = getattr(state, "unified_world_document", None) or {}
            if isinstance(doc, dict):
                patient = str(
                    doc.get("source_object_label")
                    or doc.get("open_conversation")
                    or ""
                )
            feats = getattr(state, "last_features", None)
            extras = getattr(feats, "extras", None) if feats is not None else None
            if not patient and isinstance(extras, dict):
                ft = extras.get("forward_task") or {}
                if isinstance(ft, dict):
                    patient = str(
                        (ft.get("bindings") or {})
                        .get("source_object", {})
                        .get("resolved_label")
                        or ft.get("source_object_label")
                        or ""
                    )
        ensure_commitment_from_menu_observation(
            state,
            label=label,
            patient_ref=patient,
            owner_surface=str(
                _proposal_surface(proposal) or "context_menu"
            ),
            desired_effect=(
                "forward_picker"
                if label.strip().lower() in {"forward", "share"}
                else ""
            ),
        )
    except Exception:
        return


def apply_affordance_stance(
    proposal: "UnifiedProposal", *, goal: Any = None, state: Any = None
) -> "UnifiedProposal":
    """Coerce stance + suggestions when the goal act is already actuatable.

    Perception still owns affordance coverage; this is a deterministic safety net
    so an open menu with a *clickable* goal control cannot keep advising
    reveal/explore. Label-only verbs without geometry stay explore_needed /
    grounding recovery (not patient substitute).
    """
    stance = _normalize_affordance_stance(
        getattr(proposal, "affordance_stance", None)
        or (proposal.raw or {}).get("affordance_stance")
    )
    control = _goal_control_from_inventory(proposal, goal=goal)
    qc = dict(proposal.affordance_qc or {})
    surface = _proposal_surface(proposal)
    gaps = [
        str(g)
        for g in (proposal.evidence_gaps or [])
        if str(g).strip()
    ]
    # Stick commitment for observed menu verbs (label-only or grounded).
    _commit_known_menu_affordance(proposal, goal=goal, state=state)

    if control is not None:
        stance = "act_clear"
    else:
        # Model/QC may claim clear without geometry — demote (live 171627).
        if stance == "act_clear":
            stance = "explore_needed"
            gaps.append(
                "goal control label seen but lacking actuatable geometry (point/bounds)"
            )
            if str((proposal.raw or {}).get("goal_control_label_only") or "").strip():
                gaps.append("grounding_recovery_owed_for_known_affordance")
        elif not stance:
            if qc.get("expected_found") is False or list(
                proposal.missing_affordance_information or []
            ):
                stance = "explore_needed"
            elif surface in _ACT_CLEAR_OVERLAY_SURFACES:
                # Overlay open but no clickable goal control yet.
                stance = "explore_needed"
                if str((proposal.raw or {}).get("goal_control_label_only") or "").strip():
                    gaps.append(
                        "goal control inventoried without point/bounds — re-look or escalate probe"
                    )
            else:
                stance = "ambiguous"
        # Live 184742: '1 Selected' on Send-to is source-message chrome, not dest.
        if surface == "forward_picker":
            dest_state = _forward_picker_destination_state(proposal, goal=goal)
            if not dest_state.get("contact_selected"):
                stance = "explore_needed"
                if dest_state.get("contact_visible"):
                    gaps.append(
                        "destination contact visible on picker surface but not selected — "
                        "invoke that recipient row before commit"
                    )
                else:
                    gaps.append(
                        "destination unresolved on foreground picker — "
                        "search/type within picker scope (do not treat background "
                        "selection chrome as destination_selected)"
                    )

    proposal.affordance_stance = stance or "ambiguous"
    if gaps:
        # Dedupe while preserving order.
        seen: set[str] = set()
        ordered: List[str] = []
        for g in list(proposal.evidence_gaps or []) + gaps:
            t = str(g).strip()
            if t and t not in seen:
                seen.add(t)
                ordered.append(t)
        proposal.evidence_gaps = ordered[:6]

    if proposal.affordance_stance == "act_clear":
        control_text = ""
        control_point = None
        if isinstance(control, dict):
            control_text = str(control.get("text") or control.get("label") or "").strip()
            pt = control.get("point") or control.get("target_point")
            if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                try:
                    control_point = [float(pt[0]), float(pt[1])]
                except (TypeError, ValueError):
                    control_point = None
        suggestions = [
            dict(item) for item in (proposal.suggested_actions or []) if isinstance(item, dict)
        ]
        if suggestions:
            head = dict(suggestions[0])
            fam = str(head.get("family") or "").strip()
            if fam in {"reveal_actions", "observe", "request_more_evidence", "locate_content"}:
                head["family"] = (
                    "commit_irreversible"
                    if surface == "forward_picker"
                    else "invoke_affordance"
                )
                head["why"] = (
                    str(head.get("why") or "")[:120]
                    + (" | " if head.get("why") else "")
                    + "act clear on overlay — invoke, do not re-reveal"
                )[:200]
            # Always attach actuatable control geometry (even when family was
            # already invoke) so decision/promote do not drop the click site.
            if control_text and not str(head.get("text") or "").strip():
                head["text"] = control_text
            elif control_text and fam in {
                "reveal_actions",
                "observe",
                "request_more_evidence",
                "locate_content",
                "invoke_affordance",
                "commit_irreversible",
            }:
                head["text"] = control_text
            if control_point is not None:
                head["target_point"] = control_point
                head["coordinate_space"] = (
                    str(control.get("coordinate_space") or "screen")
                    if isinstance(control, dict)
                    else "screen"
                )
            suggestions[0] = head
            proposal.suggested_actions = suggestions
            proposal.next_actions = list(suggestions)
        probe = dict(proposal.recommended_probe or {})
        if str(probe.get("family") or "").strip() in {
            "reveal_actions",
            "hover",
            "observe",
        }:
            proposal.recommended_probe = {}
        if qc:
            qc["expected_found"] = True
            qc["missing"] = []
            proposal.affordance_qc = qc
        raw = dict(proposal.raw or {})
        raw["affordance_stance"] = proposal.affordance_stance
        raw["needs_more_evidence"] = False
        proposal.raw = raw
    else:
        raw = dict(proposal.raw or {})
        raw["affordance_stance"] = proposal.affordance_stance
        # Label-only overlay verbs: keep probing for geometry, not pretend clear.
        if (
            surface in _ACT_CLEAR_OVERLAY_SURFACES
            and str(raw.get("goal_control_label_only") or "").strip()
            and not proposal.recommended_probe
        ):
            proposal.recommended_probe = {
                "family": "observe",
                "may_reveal": [str(raw.get("goal_control_label_only"))],
                "reason": "goal control lacks point/bounds — finer look before invoke",
            }
        proposal.raw = raw
    return proposal


def normalize_suggested_actions(raw: Any, *, fallback: Any = None) -> List[Dict[str, Any]]:
    """Advisory ranking for the brain: keep why; do not require progress scores."""
    items: List[Dict[str, Any]] = []
    if isinstance(raw, (list, tuple)):
        items = [dict(item) for item in raw if isinstance(item, dict)]
    elif isinstance(raw, dict) and raw:
        items = [dict(raw)]
    if not items:
        if isinstance(fallback, (list, tuple)):
            items = [dict(item) for item in fallback if isinstance(item, dict)]
        elif isinstance(fallback, dict) and fallback:
            items = [dict(fallback)]

    def sort_key(pair: Tuple[int, Dict[str, Any]]) -> Tuple[float, float, int]:
        index, action = pair
        try:
            rank = float(action.get("rank")) if action.get("rank") not in (None, "") else float(index + 1)
        except (TypeError, ValueError):
            rank = float(index + 1)
        try:
            score = float(action.get("confidence") or 0.0)
        except (TypeError, ValueError):
            score = 0.0
        return (rank, -score, index)

    ordered = [action for _, action in sorted(enumerate(items), key=sort_key)]
    out: List[Dict[str, Any]] = []
    for index, action in enumerate(ordered):
        family = str(action.get("family") or "").strip()
        if not family:
            continue
        entry = dict(action)
        entry["family"] = family
        entry["rank"] = int(entry.get("rank") or (index + 1))
        entry["why"] = str(entry.get("why") or entry.get("reason") or "")[:200]
        out.append(entry)
        if len(out) >= MAX_NEXT_ACTIONS:
            break
    return out


def ranked_action_candidates(proposal: "UnifiedProposal") -> List[Dict[str, Any]]:
    """The brain's chosen head only — no perception-ranked siblings or probes."""
    head = dict(proposal.next_action or {})
    if not head.get("family"):
        return []
    return [head]


def _parse_proposal(parsed: Dict[str, Any], *, frame: int = 0) -> UnifiedProposal:
    def _as_dict(value: Any) -> Dict[str, Any]:
        return dict(value) if isinstance(value, dict) else {}

    def _as_list(value: Any) -> List[Any]:
        if isinstance(value, (list, tuple)):
            return list(value)
        if value in (None, ""):
            return []
        return [value]

    # Advisory ranking for the brain. Prefer suggested_actions; map legacy
    # next_actions. Executable next_action stays empty until the brain fills it.
    suggested = normalize_suggested_actions(
        parsed.get("suggested_actions"),
        fallback=parsed.get("next_actions") or parsed.get("next_action"),
    )
    coverage = _coverage_value(parsed.get("coverage"))
    try:
        confidence = max(
            0.0,
            min(
                1.0,
                float(
                    parsed.get("confidence")
                    if parsed.get("confidence") is not None
                    else coverage
                )
                or 0.0,
            ),
        )
    except (TypeError, ValueError):
        confidence = float(coverage or 0.0)

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
        next_action={},
        next_actions=suggested,
        suggested_actions=suggested,
        expected_transition=_as_dict(parsed.get("expected_transition")),
        surprise_explanation=normalize_surprise_explanation(
            parsed.get("surprise_explanation")
        ),
        visible_objects=objects,
        missing_evidence=[str(item) for item in _as_list(parsed.get("missing_evidence")) if str(item).strip()],
        evidence_gaps=[str(item) for item in _as_list(parsed.get("evidence_gaps")) if str(item).strip()][:6],
        coverage=coverage,
        missing_affordance_information=[
            str(item)
            for item in _as_list(parsed.get("missing_affordance_information"))
            if str(item).strip()
        ][:6],
        recommended_probe=_as_dict(parsed.get("recommended_probe")),
        affordance_qc=_normalize_affordance_qc(parsed.get("affordance_qc")),
        affordance_stance=_normalize_affordance_stance(parsed.get("affordance_stance")),
        scene_summary=str(parsed.get("scene_summary") or parsed.get("summary") or "").strip(),
        confidence=confidence,
        raw=dict(parsed),
    )


def _vlm_timing_fields(response: Any, *, wall_ms: float, encoded_bytes: int = 0) -> Dict[str, Any]:
    """Best-effort Ollama / OpenAI-compat latency split for perception logs."""
    out: Dict[str, Any] = {
        "total_ms": round(float(wall_ms), 1),
        "encoded_bytes": int(encoded_bytes or 0),
    }
    if response is None:
        return out

    def _ns_to_ms(value: Any) -> Optional[float]:
        try:
            v = float(value)
        except (TypeError, ValueError):
            return None
        # Ollama native durations are nanoseconds; OpenAI-style are often ms/s.
        if v > 1e7:
            return round(v / 1e6, 1)
        if v > 1e4:
            return round(v, 1)
        return round(v * 1000.0, 1) if v < 100 else round(v, 1)

    for src in (response, getattr(response, "model_extra", None), getattr(response, "usage", None)):
        if src is None:
            continue
        getter = src.get if isinstance(src, dict) else lambda k, d=None: getattr(src, k, d)
        for key, dest in (
            ("total_duration", "total_ms"),
            ("load_duration", "load_ms"),
            ("prompt_eval_duration", "prompt_eval_ms"),
            ("eval_duration", "generation_ms"),
        ):
            ms = _ns_to_ms(getter(key))
            if ms is not None and dest not in out:
                out[dest] = ms
        for key, dest in (
            ("prompt_eval_count", "prompt_tokens"),
            ("eval_count", "output_tokens"),
            ("completion_tokens", "output_tokens"),
            ("prompt_tokens", "prompt_tokens"),
        ):
            try:
                n = int(getter(key))
            except (TypeError, ValueError):
                n = 0
            if n and dest not in out:
                out[dest] = n
    usage = getattr(response, "usage", None)
    if usage is not None and "output_tokens" not in out:
        try:
            out["output_tokens"] = int(getattr(usage, "completion_tokens", 0) or 0)
        except (TypeError, ValueError):
            pass
    return out


def _should_try_next_vlm(proposal: UnifiedProposal, features: StateFeatures) -> Tuple[bool, str]:
    """Escalate to the next (usually larger) VLM target — not the text deep-path."""
    escalate, reason = should_escalate(proposal, features, admissible=True)
    if escalate:
        return True, reason
    raw = proposal.raw if isinstance(proposal.raw, dict) else {}
    if bool(raw.get("needs_more_evidence")):
        return True, "needs_more_evidence"
    return False, ""


_OVERLAY_EXPECTATION_SURFACES = frozenset(
    {"context_menu", "forward_picker", "dialog", "action_menu", "selection_mode"}
)


def expects_overlay_perception(execution_state: Any) -> bool:
    """True when the next look must actually see an overlay (not phash-skip it).

    After ``reveal_actions`` the menu is often a small pixel delta on an 8×8
    ahash. Skipping vision then reuses the pre-reveal conversation world and
    the affordance_set never materializes — the 112904 stall class.

    Terminal ``failed_reveal`` episodes no longer expect an overlay ingest;
    pending unpaid handoffs always do.
    """
    if execution_state is None:
        return False
    handoff = getattr(execution_state, "reveal_handoff", None)
    if isinstance(handoff, dict) and str(handoff.get("surface") or "").strip():
        if bool(handoff.get("failed_reveal")) or str(
            handoff.get("status") or ""
        ).strip().lower() in {"failed_reveal", "failed"}:
            return False
        return True
    expectation = getattr(execution_state, "unified_last_expectation", None)
    if isinstance(expectation, dict):
        surf = str(expectation.get("surface") or "").strip().lower()
        if surf in _OVERLAY_EXPECTATION_SURFACES:
            return True
    return False


def _try_unified_phash_reuse(
    *,
    goal: Goal,
    screenshot_path: str,
    phase: str,
    execution_state: Any,
    frame: int,
    point_scale: float,
    point_origin: Tuple[float, float],
) -> Optional[UnifiedProposal]:
    """Reuse last unified reading when the focused pixels have not changed."""
    from plugin.agent.perception_synthesis import (
        _hamming,
        _image_ahash,
        _perception_phash_max_distance,
    )

    phash_max = _perception_phash_max_distance()
    if not phash_max or execution_state is None:
        return None
    post_act = bool(getattr(execution_state, "must_executive_reperceive", False)) or bool(
        getattr(execution_state, "post_action_reperceive_pending", False)
    )
    if str(getattr(execution_state, "perception_mode", "") or "").strip().lower() == "reflect":
        return None
    # Overlay intentions / pending reveal handoffs require a real VLM (+ OCR)
    # read — including when the executive reuses a look while the episode is
    # still open (not only post_act). Small menus often stay under the phash
    # threshold and must not reuse the prior conversation document.
    if expects_overlay_perception(execution_state):
        logger.info(
            "Unified cognition phash blocked: overlay expectation/handoff requires VLM"
            " (post_act=%s)",
            post_act,
        )
        return None
    cache = getattr(execution_state, "unified_perception_cache", None)
    if not isinstance(cache, dict):
        return None
    sig = f"{getattr(goal, 'kind', '')}|{getattr(goal, 'contact', '')}|{phase}"
    if str(cache.get("sig") or "") != sig:
        return None
    current = _image_ahash(screenshot_path)
    prev = cache.get("phash")
    raw = cache.get("parsed")
    if (
        current is None
        or not isinstance(prev, int)
        or not isinstance(raw, dict)
        or _hamming(current, prev) > phash_max
    ):
        return None
    # Post-act: cheap pixel delta → classify no_visible_change without a VLM
    # call. Still returns the prior world so prediction_error can score the
    # absent transition. Idle (non post-act) looks may fully reuse belief.
    if post_act:
        proposal = apply_affordance_stance(
            _parse_proposal(dict(raw), frame=frame),
            goal=goal,
            state=execution_state,
        )
        proposal.model = "no_visible_change"
        proposal.latency_s = 0.0
        proposal.point_scale = float(cache.get("point_scale") or point_scale)
        proposal.point_origin = tuple(cache.get("point_origin") or point_origin)  # type: ignore[assignment]
        raw_out = dict(proposal.raw or {})
        raw_out["no_visible_change"] = True
        # Predicted movement + unchanged pixels → ask escalate path next time
        # only when confidence was already weak; otherwise keep the cheap read.
        expectation = getattr(execution_state, "unified_last_expectation", None)
        if isinstance(expectation, dict) and str(expectation.get("surface") or "").strip():
            raw_out["needs_more_evidence"] = False
            proposal.missing_evidence = list(proposal.missing_evidence or [])
        proposal.raw = raw_out
        logger.info(
            "Unified cognition no_visible_change: phase=%s dist<=%d (post-act delta)",
            phase or "full",
            phash_max,
        )
        return proposal
    proposal = apply_affordance_stance(
        _parse_proposal(raw, frame=frame), goal=goal, state=execution_state
    )
    proposal.model = str(cache.get("model") or "phash_reuse")
    proposal.latency_s = 0.0
    proposal.point_scale = float(cache.get("point_scale") or point_scale)
    proposal.point_origin = tuple(cache.get("point_origin") or point_origin)  # type: ignore[assignment]
    logger.info(
        "Unified cognition phash reuse: phase=%s dist<=%d model=%s",
        phase or "full",
        phash_max,
        proposal.model,
    )
    return proposal


def _store_unified_phash(
    execution_state: Any,
    *,
    goal: Goal,
    phase: str,
    screenshot_path: str,
    proposal: UnifiedProposal,
    point_scale: float,
    point_origin: Tuple[float, float],
) -> None:
    if execution_state is None:
        return
    from plugin.agent.perception_synthesis import _image_ahash

    try:
        execution_state.unified_perception_cache = {
            "sig": f"{getattr(goal, 'kind', '')}|{getattr(goal, 'contact', '')}|{phase}",
            "phash": _image_ahash(screenshot_path),
            "parsed": dict(proposal.raw or {}),
            "model": proposal.model,
            "point_scale": point_scale,
            "point_origin": list(point_origin),
            "phase": phase,
        }
    except Exception:
        pass


def consult_unified_cognition(
    goal: Goal,
    world: WorldModel,
    features: StateFeatures,
    execution_state: Any = None,
) -> Optional[UnifiedProposal]:
    """Stage1 multimodal call: world proposal (+ suggested_actions).

    After parse: critic → current-node affordance closure → return.
    ``DecisionEngine`` then calls ``brain.choose_next_capability``.
    """
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
    capture = CaptureFrame.from_dict(getattr(world, "last_capture_frame", None))
    phase = _phase_from_features(features)
    crop_box: Optional[Tuple[int, int, int, int]] = None
    max_width = _max_image_width()
    if _perception_roi_enabled():
        try:
            from PIL import Image

            with Image.open(screenshot_path) as im:
                w0, h0 = im.size
        except Exception:
            w0, h0 = 0, 0
        focus_y = _focus_y_capture_px(execution_state, capture)
        crop_box = resolve_phase_roi(phase, w0, h0, focus_y_px=focus_y)
        if crop_box is None:
            max_width = _full_window_max_width()
    else:
        max_width = _full_window_max_width()

    packet = build_decision_packet(goal, world, features, execution_state)
    # Encode image once; rebuild text messages per target (fast vs escalate).
    data_url, image_size, applied_crop, encoded_bytes = _encode_perception_image(
        screenshot_path, crop_box=crop_box, max_width=max_width
    )
    obs = packet.get("observation") if isinstance(packet.get("observation"), dict) else {}
    if isinstance(obs, dict) and image_size[0] > 0:
        obs["image_size"] = [image_size[0], image_size[1]]
        if applied_crop is not None:
            obs["image_roi"] = list(applied_crop)
        if encoded_bytes:
            obs["encoded_bytes"] = int(encoded_bytes)

    source_width_px = (
        int(crop_box[2] - crop_box[0]) if crop_box is not None else None
    )
    point_scale = screen_point_scale(
        screenshot_path,
        image_size[0],
        capture,
        source_width_px=source_width_px,
    )
    if crop_box is not None:
        sx = capture.scale if capture.scale > 0 else 1.0
        point_origin = (
            float(capture.origin_x) + float(crop_box[0]) / sx,
            float(capture.origin_y) + float(crop_box[1]) / sx,
        )
    else:
        point_origin = (capture.origin_x, capture.origin_y)

    reused = _try_unified_phash_reuse(
        goal=goal,
        screenshot_path=screenshot_path,
        phase=phase,
        execution_state=execution_state,
        frame=frame,
        point_scale=point_scale,
        point_origin=point_origin,
    )
    if reused is not None:
        if execution_state is not None:
            try:
                execution_state.last_perception_latency_s = 0.0
                execution_state.unified_point_scale = reused.point_scale
                execution_state.unified_point_origin = reused.point_origin
            except Exception:
                pass
            # Still score act intention against the reused world — post-act
            # no_visible_change is exactly when prediction mismatch must arm.
            error = note_prediction_error(execution_state, reused)
            if error:
                logger.info(
                    "Prediction %s (reuse/%s): %s",
                    "held" if error.get("matched") else "ERROR",
                    reused.model,
                    error.get("verdict"),
                )
            _remember_reading(execution_state, reused)
            persist_world_document(execution_state, reused)
        return reused

    main_runtime = _main_runtime_snapshot()
    targets = _perception_task_targets(main_runtime, task_name=UNIFIED_TASK)
    timeout_s = _perception_timeout_seconds()
    token_budget = _perception_max_tokens()

    logger.info(
        "Unified cognition frame=%d: entities=%d carried[%s] targets=%s roi=%s phase=%s img=%sx%s bytes=%d",
        frame,
        len(packet["observation"]["ax_evidence"]),
        document_summary(packet["world_model"]),
        [f"{t.get('provider')}/{t.get('model')}" for t in targets],
        list(crop_box) if crop_box else "full",
        phase or "unknown",
        image_size[0],
        image_size[1],
        encoded_bytes,
    )

    record_to = recording_dir()
    recorded = False

    for index, target in enumerate(targets, start=1):
        start = time.time()
        last_response: Dict[str, Any] = {"r": None}
        fast = _is_fast_vlm_target(target)
        if fast:
            max_tokens = max(64, min(_FAST_MAX_TOKENS, token_budget))
            messages, _ = _build_messages(
                packet,
                screenshot_path,
                crop_box=crop_box,
                max_width=max_width,
                fast_path=True,
                phase=phase,
                data_url=data_url,
                image_size=image_size,
                encoded_bytes=encoded_bytes,
                applied_crop=applied_crop,
            )
        else:
            if os.getenv("HERMES_PERCEPTION_LLM_MAX_TOKENS", "").strip():
                max_tokens = max(64, token_budget)
            else:
                max_tokens = max(100, min(250, token_budget))
            messages, _ = _build_messages(
                packet,
                screenshot_path,
                crop_box=crop_box,
                max_width=max_width,
                fast_path=False,
                phase=phase,
                data_url=data_url,
                image_size=image_size,
                encoded_bytes=encoded_bytes,
                applied_crop=applied_crop,
            )

        extra_body = _perception_extra_body(
            main_runtime, target=target, fast_path=fast
        )

        def _caller(**kwargs: Any) -> Any:
            r = _call_llm_hard_timeout(timeout_s, **kwargs)
            last_response["r"] = r
            return r

        try:
            consultation = consult_reasoning(
                UNIFIED_TASK,
                messages,
                caller=_caller,
                call_kwargs={
                    "task": UNIFIED_TASK,
                    "provider": target.get("provider") or None,
                    "model": target.get("model") or None,
                    "base_url": target.get("base_url") or None,
                    "api_key": target.get("api_key") or None,
                    "timeout": timeout_s,
                    "main_runtime": main_runtime,
                    "extra_body": extra_body,
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

        parsed_raw = consultation.parsed
        if (not parsed_raw) and fast and consultation.raw_response:
            parsed_raw = _repair_truncated_json(consultation.raw_response) or {}
        if not parsed_raw:
            continue
        parsed = (
            _expand_fast_parsed(parsed_raw, frame=frame)
            if fast
            else parsed_raw
        )
        proposal = apply_affordance_stance(
            _parse_proposal(parsed, frame=frame),
            goal=goal,
            state=execution_state,
        )

        proposal.model = str(target.get("model") or "")
        proposal.latency_s = time.time() - start
        timing = _vlm_timing_fields(
            last_response.get("r"),
            wall_ms=proposal.latency_s * 1000.0,
            encoded_bytes=encoded_bytes,
        )
        timing.update(
            {
                "model": proposal.model,
                "roi": list(crop_box) if crop_box else "full",
                "phase": phase or "unknown",
                "output_chars": len(consultation.raw_response or ""),
            }
        )
        logger.info("Unified cognition timing: %s", json.dumps(timing, ensure_ascii=False))
        # The single largest cost in an iteration, and previously visible only
        # inside the decision trace, where nothing summarising the run would find
        # it. The loop reports it per iteration so time spent is attributable.
        if execution_state is not None:
            try:
                execution_state.last_perception_latency_s = float(proposal.latency_s)
                execution_state.last_perception_timing = timing
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
        # Small-VLM first: low confidence / gaps → try next (larger) target.
        try_next, escalate_reason = _should_try_next_vlm(proposal, features)
        if try_next and index < len(targets):
            logger.info(
                "Unified cognition escalate VLM (%s): %s → next target",
                escalate_reason,
                proposal.model,
            )
            continue
        _store_unified_phash(
            execution_state,
            goal=goal,
            phase=phase,
            screenshot_path=screenshot_path,
            proposal=proposal,
            point_scale=point_scale,
            point_origin=point_origin,
        )
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
        # Critic accepted/edited the world. Close the current UI node's
        # affordance set (same-node reveals) before the brain picks a transition.
        try:
            from plugin.agent.affordance_explore import close_current_node_frontier

            accepted = getattr(execution_state, "unified_world_document", None)
            passive = getattr(execution_state, "last_affordance_frontier", None)
            closure = close_current_node_frontier(
                accepted_world=accepted if isinstance(accepted, dict) else proposal.world_model,
                passive_frontier=passive if isinstance(passive, dict) else None,
                proposal=proposal,
                execution_state=execution_state,
            )
            if bool(closure.get("needs_relook")):
                try:
                    execution_state.must_executive_reperceive = True
                except Exception:
                    pass
            if features is not None and isinstance(features.extras, dict):
                features.extras["node_closure"] = {
                    "needs_relook": bool(closure.get("needs_relook")),
                    "closure": closure.get("closure"),
                    "probes_run": list(closure.get("probes_run") or [])[:4],
                }
        except Exception as exc:
            logger.warning("Node affordance closure skipped: %s", exc)
        # DecisionEngine calls plugin.agent.brain after this returns.
        materialize_vision_entities(world, proposal)
        publish_scene_to_world(world, proposal)
        # Perception extras are the reading only — never a next-action nudge.
        try:
            if features is not None and isinstance(features.extras, dict):
                verdict_obj = getattr(execution_state, "last_critic_verdict", None)
                extras_payload = unified_perception_extras(
                    proposal, verdict_obj, execution_state=execution_state
                )
                if extras_payload:
                    features.extras["perception_llm"] = extras_payload
                    features.extras["perception_task"] = UNIFIED_TASK
                    features.extras["perception_summary"] = {
                        "screen_type": extras_payload.get("screen_type"),
                        "application": extras_payload.get("application"),
                        "active_surface": extras_payload.get("active_surface"),
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
    execution_state: Any = None,
) -> Dict[str, Any]:
    """Perception extras from the unified reading — scene only, not next move.

    ``likely_next_*`` are intentionally empty: the brain chooses the capability
    after the critic. Candidate scoring must not treat perception as a planner.
    Coverage / gaps / contradictions remain load-bearing for sufficiency and
    selector prompts.
    """
    if proposal is None:
        return {}
    view = _verdict_view(verdict)
    accepted = dict(view["accepted_document"] or proposal.world_model or {})
    state = proposal.observed_state or {}
    surface = str(accepted.get("surface") or state.get("surface") or "").strip().lower()
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
    avoid_keys = list(getattr(execution_state, "avoid_motor_keys", None) or [])[:8]
    return {
        "source": "unified_cognition",
        "screen_type": _SURFACE_TO_SCREEN_TYPE.get(surface, "unknown"),
        "application": str(state.get("app") or ""),
        "active_surface": surface,
        "likely_next_family": "",
        "likely_next_target": "",
        "likely_next_text": "",
        "confidence": round(float(proposal.confidence or 0.0), 4),
        "supporting_evidence": ([summary] if summary else []) + evidence[:4],
        "contradictions": contradictions[:4],
        "needs_followup_observe": bool(gaps) or coverage < 0.7,
        "coverage": round(coverage, 3),
        "evidence_gaps": gaps[:6],
        # Failed motors from prediction mismatches — block identical re-offers.
        "avoid_families": [str(k).split("|", 1)[0] for k in avoid_keys if str(k).strip()][:8],
        "avoid_motor_keys": avoid_keys,
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
        pe = getattr(execution_state, "last_prediction_error", None)
        verdict = critique_world_proposal(
            prior if isinstance(prior, dict) else {},
            dict(proposal.world_model),
            last_action=last_action,
            observed_surface=observed,
            prediction_error=pe if isinstance(pe, dict) else None,
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
        accepted = dict(verdict.accepted_document)
        # Preserve / refresh multi-display topology on the carried document.
        app_hint = str(
            (accepted.get("task_surface") or {}).get("app")
            if isinstance(accepted.get("task_surface"), dict)
            else ""
        ) or "WhatsApp"
        accepted = stamp_task_surface(
            accepted,
            execution_state=execution_state,
            app=app_hint,
        )
        # Downgrade opaque matches_goal when role constraints fail
        # (query identity + originator; live 214025 / 171216).
        try:
            from plugin.agent.source_query_binding import scrub_matches_goal_flags

            goal = getattr(execution_state, "goal", None)
            link_q = str(getattr(goal, "link_query", "") or "").strip()
            contact = str(getattr(goal, "contact", "") or "").strip()
            # Authorship only when the goal expressed it — never alias from contact.
            originator = str(getattr(goal, "originator", "") or "").strip()
            if link_q or originator:
                accepted = scrub_matches_goal_flags(
                    accepted,
                    query=link_q,
                    expected_container=contact,
                    expected_originator=originator,
                )
                # Keep vision entities aligned with the scrubbed document —
                # otherwise materialize_vision_entities can re-stamp unscrubbed
                # matches_goal from the raw proposal.
                if isinstance(getattr(proposal, "raw", None), dict):
                    proposal.raw["objects"] = list(accepted.get("objects") or [])
                elif hasattr(proposal, "objects"):
                    try:
                        proposal.objects = list(accepted.get("objects") or [])
                    except Exception:
                        pass
        except Exception:
            pass
        execution_state.unified_world_document = accepted
        execution_state.focused_field_role = verdict.focused_field_role
        execution_state.last_critic_verdict = verdict.to_dict()
        # Compact prior for future REFLECT looks.
        try:
            shot = ""
            if isinstance(getattr(proposal, "raw", None), dict):
                shot = str(proposal.raw.get("screenshot_path") or "")
            execution_state.note_perception(
                accepted,
                iteration=int(getattr(execution_state, "unified_frame", 0) or 0),
                screenshot_path=shot,
            )
        except Exception:
            pass
        # Persist ReflectDiagnosis: merge model explanation with runtime seed.
        mode = str(getattr(execution_state, "perception_mode", "") or "").strip().lower()
        meta = str(getattr(execution_state, "last_meta_action", "") or "").strip().lower()
        if mode == "reflect" or meta == "reflect":
            reflect_pkt = _reflect_packet(execution_state)
            expl = finalize_surprise_explanation(
                getattr(proposal, "surprise_explanation", None),
                reflect_packet=reflect_pkt,
            )
        else:
            expl = normalize_surprise_explanation(
                getattr(proposal, "surprise_explanation", None)
            )
        if expl:
            execution_state.last_surprise_explanation = expl
            proposal.surprise_explanation = expl
            try:
                execution_state.last_reflect_diagnosis = expl
            except Exception:
                pass
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
        # Multi-pass discovery timing fix: promote from the *accepted* document
        # (menu objects written this look), not the prior doc used pre-stage1.
        try:
            from plugin.agent.world_critic import promote_frontier_after_accept

            promote_status = promote_frontier_after_accept(
                execution_state,
                accepted_document=getattr(
                    execution_state, "unified_world_document", None
                ),
                last_action_family=last_action,
            )
            if promote_status.get("promoted"):
                logger.info(
                    "Post-accept affordance promote: grounded=%s",
                    promote_status.get("grounded"),
                )
        except Exception as exc:
            logger.debug("Post-accept affordance promote skipped: %s", exc)
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
    """Deprecated shim — use ``plugin.agent.brain.choose_next_capability``."""
    from plugin.agent.brain import choose_next_capability

    return choose_next_capability(
        proposal, goal, features=features, execution_state=execution_state
    )


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


def eval_candidates_dir() -> str:
    """Directory for semantic perception eval candidates, or '' when disabled.

    When set (e.g. ``plugin/evals/perception_semantic/eval_candidates``), every
    recorded cognition frame is also frozen in the architect candidate layout
    (screenshot + ax + executive_context + model_input/output) so live failures
    can be annotated without re-capturing.
    """
    return os.getenv("HERMES_PERCEPTION_EVAL_CANDIDATES_DIR", "").strip()


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
        response = proposal.to_dict() if proposal is not None else None
        (target / f"{stem}.json").write_text(
            json.dumps(
                {
                    "frame": index,
                    "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "screenshot": image_name,
                    "packet": packet,
                    "response": response,
                    "shadow_task_state": shadow or {},
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        logger.info("Perceptor frame recorded: %s (image=%s)", stem, bool(image_name))
        cand_root = eval_candidates_dir()
        if cand_root:
            try:
                from plugin.evals.perception_semantic.harvest_failure import (
                    dump_candidate_from_live_packet,
                )

                stamp = target.name
                dump_candidate_from_live_packet(
                    packet,
                    str(target / image_name) if image_name else screenshot_path,
                    response,
                    directory=cand_root,
                    step=index,
                    stamp=stamp,
                    shadow=shadow,
                )
            except Exception as cand_exc:
                logger.warning("Eval candidate dump failed: %s", cand_exc)
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
def _search_field_families() -> frozenset:
    from plugin.agent.capabilities.action_area import filter_field_families

    return filter_field_families()


_SEARCH_FIELD_FAMILIES = frozenset(
    {"compose_search_query", "type_query", "locate_content", "open_search"}
)


def _entity_is_search_field(entity: Any) -> bool:
    """True only for filter-input controls — not composers or contacts."""
    from plugin.agent.capabilities.action_area import (
        ActionAreaContract,
        ActionArea,
        ErrorCost,
        object_matches_area,
    )

    attrs = getattr(entity, "attributes", None) or {}
    probe = {
        "kind": str(getattr(entity, "entity_type", "") or "").lower(),
        "text": str(getattr(entity, "label", "") or ""),
        "label": str(getattr(entity, "label", "") or ""),
        "role": str(attrs.get("role") or getattr(entity, "role", "") or ""),
    }
    # Reuse filter_input matching (search/find tokens + filter kinds).
    contract = ActionAreaContract(
        area=ActionArea.FILTER_INPUT,
        error_cost=ErrorCost.HIGH,
        exclusive=True,
        allowed_kinds=frozenset(
            {"text_field", "search_field", "search_input", "search_bar", "field", "textfield"}
        ),
        forbidden_kinds=frozenset(),
        canonical_label="Search",
    )
    if object_matches_area(probe, contract):
        return True
    blob = " ".join(
        str(x or "")
        for x in (
            getattr(entity, "label", ""),
            getattr(entity, "entity_type", ""),
            attrs.get("role"),
            attrs.get("description"),
            attrs.get("text"),
        )
    ).lower()
    return "search" in blob or "axsearchfield" in blob or "find" in blob


def _vision_blob(entity: Any) -> str:
    attrs = getattr(entity, "attributes", None) or {}
    return (
        f"{getattr(entity, 'label', '') or ''} "
        f"{attrs.get('description', '')} {attrs.get('text', '')}"
    ).lower()


def _blob_looks_like_url(blob: str) -> bool:
    b = str(blob or "").lower()
    return (
        "http://" in b
        or "https://" in b
        or ".goo." in b
        or ".com/" in b
        or ".com?" in b
        or b.rstrip(".").endswith(".com")
    )


def _goal_matched_object(world: WorldModel, *, prefer_url: bool = False) -> Any:
    """Unique vision object that is *binding-eligible*, not merely matches_goal.

    ``matches_goal`` is recall/task-relevance only. Authoritative act targeting
    requires constraint-level eligibility (query + originator when known) from
    ``goal_match.binding_eligible`` or a fresh ``evaluate_source_object_match``.
    """
    if world is None:
        return None
    from plugin.agent.source_query_binding import evaluate_source_object_match

    goal = getattr(world, "goal", None)
    query = ""
    expected_container = ""
    expected_originator = ""
    if goal is not None:
        query = str(
            getattr(goal, "link_query", None)
            or getattr(goal, "source_query", None)
            or ""
        ).strip()
        expected_container = str(
            getattr(goal, "contact", None)
            or getattr(goal, "source_conversation", None)
            or ""
        ).strip()
        # Typed sender relation only — container must not imply originator.
        expected_originator = str(getattr(goal, "originator", None) or "").strip()
    open_c = str(getattr(world, "open_conversation", "") or "")

    matched = []
    for entity in getattr(world, "entities", {}).values():
        if not getattr(entity, "visible", True):
            continue
        attrs = getattr(entity, "attributes", None)
        if not isinstance(attrs, dict):
            continue
        if str(attrs.get("source") or "") != "vision":
            continue
        gm_raw = attrs.get("goal_match")
        if isinstance(gm_raw, dict) and "binding_eligible" in gm_raw:
            eligible = bool(gm_raw.get("binding_eligible"))
        elif bool(attrs.get("matches_goal")) or query or expected_originator:
            gm = evaluate_source_object_match(
                text=_vision_blob(entity),
                kind=str(getattr(entity, "kind", "") or attrs.get("kind") or ""),
                query=query,
                container_open=open_c,
                expected_container=expected_container,
                expected_originator=expected_originator,
                sender=attrs.get("sender") or attrs.get("originator"),
                perception_matches_goal=bool(attrs.get("matches_goal")),
            )
            eligible = bool(gm.binding_eligible)
            attrs["goal_match"] = gm.to_dict()
        else:
            continue
        if eligible:
            matched.append(entity)
    if not matched:
        return None
    if prefer_url:
        url_matched = [e for e in matched if _blob_looks_like_url(_vision_blob(e))]
        if url_matched:
            return url_matched[0] if len(url_matched) == 1 else None
        return None
    return matched[0] if len(matched) == 1 else None


def _referent_matched_entity(world: WorldModel, referents: Sequence[str]) -> Any:
    """Unique visible vision entity whose blob overlaps goal content referents."""
    from plugin.agent.capabilities.revert_effects import _text_matches_goal

    tokens = [str(t).strip() for t in (referents or []) if str(t).strip()]
    if world is None or not tokens:
        return None
    hits = []
    for entity in getattr(world, "entities", {}).values():
        if not getattr(entity, "visible", True):
            continue
        attrs = getattr(entity, "attributes", None)
        if not isinstance(attrs, dict) or str(attrs.get("source") or "") != "vision":
            continue
        blob = _vision_blob(entity)
        label = str(getattr(entity, "label", "") or "")
        if _text_matches_goal(f"{blob} {label}", tokens):
            hits.append(entity)
    # Dedup by id
    uniq = []
    seen = set()
    for e in hits:
        eid = getattr(e, "id", None)
        if eid in seen:
            continue
        seen.add(eid)
        uniq.append(e)
    if len(uniq) == 1:
        return uniq[0]
    url_hits = [e for e in uniq if _blob_looks_like_url(_vision_blob(e))]
    if len(url_hits) == 1:
        return url_hits[0]
    return None


def _entity_has_bounds(entity: Any) -> bool:
    bounds = getattr(entity, "bounds", None)
    try:
        return bool(bounds) and float(bounds[2]) > 0 and float(bounds[3]) > 0
    except (TypeError, ValueError, IndexError):
        return False


def _entity_in_sidebar(world: WorldModel, entity: Any) -> bool:
    """True when the entity sits in the WhatsApp left rail / chat-list band."""
    if entity is None:
        return False
    try:
        from plugin.agent.apps.whatsapp_targets import in_sidebar_band

        ents = list(getattr(world, "entities", {}).values())
        return bool(
            in_sidebar_band(
                entity,
                ents,
                scene_graph=getattr(world, "last_scene_graph", None) or {},
            )
        )
    except Exception:
        return False


def _forward_source_object_entity(world: WorldModel) -> Any:
    """Task-bound source message/link — not a sidebar preview echo.

    Live 013229: forward_task had source_object=80 while reveal grounded to
    sidebar entity 7 at (320,160). Prefer the binding when it still has bounds.
    """
    hints = getattr(world, "overlay_hints", None) or {}
    ft = hints.get("forward_task") if isinstance(hints, dict) else None
    if not isinstance(ft, dict):
        return None
    bindings = ft.get("bindings") if isinstance(ft.get("bindings"), dict) else {}
    obj = bindings.get("source_object") if isinstance(bindings, dict) else None
    if not isinstance(obj, dict):
        return None
    eid = obj.get("resolved_entity_id")
    if eid is None:
        cands = obj.get("candidate_entity_ids") or []
        eid = cands[0] if cands else None
    if eid is None:
        return None
    try:
        ent = world.entities.get(int(eid))
    except (TypeError, ValueError):
        return None
    if ent is None or not getattr(ent, "visible", True) or not _entity_has_bounds(ent):
        return None
    if _entity_in_sidebar(world, ent):
        return None
    return ent


def _ground_label_to_entity(
    world: WorldModel,
    label: str,
    *,
    reject_sidebar: bool = False,
) -> Any:
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
    if (
        winner is not None
        and _entity_has_bounds(winner)
        and not (reject_sidebar and _entity_in_sidebar(world, winner))
    ):
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
            and not (reject_sidebar and _entity_in_sidebar(world, ent))
        ):
            return ent
    return None


def proposal_to_action(
    proposal: UnifiedProposal,
    goal: Goal,
    world: WorldModel,
    features: Optional[StateFeatures] = None,
    execution_state: Any = None,
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

    # Desired-effect coherence (live 131030): open_entity + context_menu means
    # the model wanted reveal/select effects but named the open family.
    # On an open conversation → rewrite to reveal_actions. Elsewhere → keep
    # open but the prediction attach below forces the open-nav contract.
    exp_surface = str(
        (proposal.expected_transition or {}).get("surface") or ""
    ).strip().lower()
    obs_surface = str(
        (proposal.observed_state or {}).get("surface") or ""
    ).strip().lower()
    if (
        family in _OPEN_NAV_FAMILIES
        and exp_surface in _REVEAL_EFFECT_SURFACES
        and obs_surface == "conversation"
    ):
        family = "reveal_actions"
        verb = _VERB_TO_RUNTIME.get("reveal_actions") or "RevealActions"
        raw_family = "reveal_actions"

    text = str(proposal.next_action.get("text") or "").strip()
    entity = _resolve_target_entity(world, proposal.next_action.get("target_id"))
    semantic_target = str(getattr(entity, "label", "") or "").strip()
    if not semantic_target:
        semantic_target = str(proposal.next_action.get("target_label") or "").strip()
    # Entity-shaped capabilities: models often put the name in text.
    if family in {"open_entity", "select_content", "reveal_actions"} and not semantic_target:
        semantic_target = text
    # Affordance labels: collapse "Click 'Links' tab…" into the control name.
    if family in {"invoke_affordance", "commit_irreversible", "reveal_actions"}:
        from plugin.agent.decision_consultation import _affordance_label

        text = _affordance_label(text) or text
        semantic_target = _affordance_label(semantic_target) or semantic_target

    # locate/type SEARCH query must be goal link_query — never a distractor URL
    # (live 225807: perception called YouTube "the target"; locate typed it
    # into sidebar Search).
    link_q = str(getattr(goal, "link_query", "") or "").strip()
    if family in {"locate_content", "type_query", "compose_search_query"} and link_q:
        try:
            from plugin.agent.source_query_binding import (
                host_contradicts_query,
                query_supported_by_text,
            )

            cand = text or semantic_target
            cand_l = str(cand or "").strip().lower()
            # TEMPORARY debt: perception object ids (msg_link_*) must not become
            # locate queries (live 113806). Proper fix is typed —
            # locate_content.query accepts only semantic query text; object IDs
            # travel through target refs. Do not expand this shape heuristic.
            object_id_query = bool(
                cand_l.startswith("msg_")
                or cand_l.startswith("obj_")
                or (
                    bool(re.match(r"^[a-z]+_[a-z0-9_]+$", cand_l))
                    and "http" not in cand_l
                    and " " not in cand_l
                    and len(cand_l) > len(link_q) + 2
                )
            )
            distractor = bool(cand) and (
                host_contradicts_query(cand, link_q)
                or (
                    ("http://" in cand.lower() or "https://" in cand.lower() or "youtu" in cand.lower())
                    and not query_supported_by_text(cand, link_q)
                )
            )
            if family == "locate_content" and (
                not cand
                or distractor
                or object_id_query
                or not query_supported_by_text(cand, link_q)
            ):
                text = link_q
                semantic_target = link_q
            elif distractor:
                text = link_q

        except Exception:
            if family == "locate_content":
                text = link_q
                semantic_target = link_q
    # Forward: select/reveal/invoke must land on the bound conversation-pane
    # object, never the left-rail preview that echoes the query (013229).
    # invoke_affordance is included so left-click cannot bind a caption bubble
    # when the task has a URL-grade source_object (live 024851).
    # Exception: on open overlay surfaces, verb labels (Forward/Copy/…) bind to
    # menu/toolbar controls — never rebind onto the content patient URL.
    content_families = {"select_content", "reveal_actions", "invoke_affordance"}
    surface = str(
        (proposal.observed_state or {}).get("surface")
        or (proposal.world_model or {}).get("surface")
        or ""
    ).strip().lower()
    try:
        from plugin.agent.world_critic import _label_looks_like_menu_verb as _is_menu_verb
    except Exception:
        def _is_menu_verb(label: str) -> bool:  # type: ignore[misc]
            return str(label or "").strip().lower() in {
                "forward",
                "share",
                "copy",
                "reply",
                "send",
                "delete",
            }

    verb_on_overlay = surface in _ACT_CLEAR_OVERLAY_SURFACES and (
        _is_menu_verb(semantic_target or text)
        or (
            family == "invoke_affordance"
            and surface in {"context_menu", "action_menu", "selection_mode"}
        )
    )
    # Prefer explicit geometry on next_action for overlay verbs before any
    # content-entity rebind can steal the click.
    overlay_action_point = None
    if verb_on_overlay:
        raw_pt = proposal.next_action.get("target_point") or proposal.next_action.get(
            "point"
        )
        if isinstance(raw_pt, (list, tuple)) and len(raw_pt) >= 2:
            try:
                overlay_action_point = (float(raw_pt[0]), float(raw_pt[1]))
            except (TypeError, ValueError):
                overlay_action_point = None
    if family in content_families and not verb_on_overlay:
        # Hierarchical gate: committed known-ungrounded method must not silently
        # rebind invoke/select onto the patient merely because it has geometry.
        forbid_patient = False
        try:
            from plugin.agent.executive.affordance_commitment import (
                forbids_wrong_locus,
            )

            est = execution_state
            if est is None:
                est = getattr(proposal, "execution_state", None)
            if est is None and features is not None:
                est = getattr(features, "execution_state", None)
            forbid_patient = bool(
                est is not None
                and forbids_wrong_locus(
                    est,
                    family=family,
                    semantic_target=str(semantic_target or text or ""),
                )
            )
        except Exception:
            forbid_patient = False
        if forbid_patient and family == "invoke_affordance":
            return None, "committed_affordance_ungrounded_no_patient_substitute"
        bound = None if forbid_patient else _forward_source_object_entity(world)
        if bound is not None:
            entity = bound
            if not semantic_target:
                semantic_target = str(getattr(entity, "label", "") or "").strip()
        elif entity is not None and _entity_in_sidebar(world, entity):
            entity = None
    # Search/type families: never bind a contact/message as the type target
    # (live 095344: Pallavi entity + mid-list point → chat composer).
    if family in _SEARCH_FIELD_FAMILIES:
        if entity is not None and not _entity_is_search_field(entity):
            entity = None
        st_low = str(semantic_target or "").strip().lower()
        if not st_low or ("search" not in st_low and "find" not in st_low):
            tl = str(proposal.next_action.get("target_label") or "").strip()
            if tl and ("search" in tl.lower() or "find" in tl.lower()):
                semantic_target = tl
            else:
                semantic_target = "Search"
    # Geometry-first grounding: the model named a pointer target but gave no
    # resolvable target_id. Ground the label to a *perceived* entity now so the
    # decision carries an entity id + bounds — the runtime then clicks exactly
    # where the perceptor saw the target instead of re-resolving a noisy-OCR
    # string downstream (which grabbed the search-box echo / a call affordance).
    # invoke_affordance is not in _GROUNDED_POINTER_FAMILIES (geometry often
    # comes from affordance_set), but overlay verb labels still need label→entity
    # grounding so Forward lands on the menu control, not nowhere / content URL.
    if entity is None and (
        family in _GROUNDED_POINTER_FAMILIES
        or (verb_on_overlay and family == "invoke_affordance")
    ):
        # The model's own relevance verdict first, its label second. Reversing
        # these grounds the click on whichever perceived text reads most like the
        # query, and the query's own echo in the search field always wins that.
        if verb_on_overlay:
            grounded = _ground_label_to_entity(
                world,
                semantic_target or text,
                reject_sidebar=False,
            )
            if grounded is None:
                # Resolver often skips short menu verbs; exact/role match is enough.
                want = str(semantic_target or text or "").strip().lower()
                for cand in (world.entities or {}).values():
                    if cand is None or not getattr(cand, "visible", True):
                        continue
                    if not _entity_has_bounds(cand):
                        continue
                    label = str(getattr(cand, "label", "") or "").strip().lower()
                    role = str(
                        getattr(cand, "semantic_role", "")
                        or getattr(cand, "role", "")
                        or ""
                    ).strip().lower()
                    if label == want or (
                        want
                        and want in label
                        and (
                            "menu" in role
                            or "button" in role
                            or "control" in str(getattr(cand, "entity_type", "") or "").lower()
                        )
                    ):
                        grounded = cand
                        break
            if grounded is not None:
                entity = grounded
                if not semantic_target:
                    semantic_target = str(getattr(entity, "label", "") or "").strip()
        else:
            reject_sidebar = family in content_families
            prefer_url = bool(str(getattr(goal, "link_query", "") or "").strip())
            grounded = None
            if not reject_sidebar:
                grounded = _goal_matched_object(world, prefer_url=prefer_url)
            elif prefer_url and family in {
                "invoke_affordance",
                "reveal_actions",
                "select_content",
            }:
                # Content hunt with referents: unique URL/goal match, never a
                # non-overlapping model-named entity (live 154356 / 024851).
                grounded = _goal_matched_object(world, prefer_url=True)
            if grounded is None:
                grounded = _ground_label_to_entity(
                    world,
                    semantic_target or text,
                    reject_sidebar=reject_sidebar,
                )
            if grounded is not None and not (
                reject_sidebar and _entity_in_sidebar(world, grounded)
            ):
                entity = grounded
                if not semantic_target:
                    semantic_target = str(getattr(entity, "label", "") or "").strip()

    # Overlay verb invoke: never keep a content-URL entity as the click target.
    if verb_on_overlay and family in {"invoke_affordance", "commit_irreversible"}:
        if entity is not None:
            elabel = str(getattr(entity, "label", "") or "").strip().lower()
            if ("http://" in elabel or "https://" in elabel or "www." in elabel) and not _is_menu_verb(
                elabel
            ):
                entity = None
        if entity is None and overlay_action_point is None:
            # Last chance: inventory object with matching verb + geometry.
            for obj in _inventory_objects(proposal):
                if not _object_has_actuatable_geometry(obj):
                    continue
                ot = str(obj.get("text") or obj.get("label") or "").strip()
                if not _is_menu_verb(ot) and ot.lower() != str(
                    semantic_target or text or ""
                ).strip().lower():
                    continue
                pt = obj.get("point") or obj.get("target_point")
                try:
                    overlay_action_point = (float(pt[0]), float(pt[1]))  # type: ignore[index]
                except (TypeError, ValueError, IndexError):
                    continue
                semantic_target = ot or semantic_target
                break
        if entity is None and overlay_action_point is None:
            return None, "overlay_verb_without_geometry"

    # Content-probe referent fitness: kind-ok + motor-ok is insufficient when
    # the goal carries content tokens (154356 wrong-entity reveal).
    # Skip for overlay verb targets — Forward is not a content referent.
    if family in {"select_content", "reveal_actions"} and not verb_on_overlay:
        from plugin.agent.capabilities.revert_effects import content_target_fits_referents

        referents: List[str] = []
        for attr in ("link_query", "content_query", "query"):
            t = str(getattr(goal, attr, "") or "").strip()
            if t and t not in referents:
                referents.append(t)
        if referents:
            blob = _vision_blob(entity) if entity is not None else ""
            label = semantic_target or text
            if not content_target_fits_referents(
                target_label=label,
                object_blob=blob,
                goal_referents=referents,
            ):
                rebound = _goal_matched_object(world, prefer_url=True)
                if rebound is None:
                    rebound = _referent_matched_entity(world, referents)
                if rebound is not None and not _entity_in_sidebar(world, rebound):
                    entity = rebound
                    semantic_target = (
                        str(getattr(entity, "label", "") or "").strip() or semantic_target
                    )
                else:
                    return None, "content_referent_mismatch"

    confidence = proposal.confidence
    rationale_family = raw_family
    na = proposal.next_action if isinstance(proposal.next_action, dict) else {}
    est_roles = na.get("establishes_roles") or []
    if not isinstance(est_roles, list):
        est_roles = []
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
        target_kind=str(
            na.get("target_kind")
            or getattr(entity, "kind", "")
            or getattr(entity, "object_type", "")
            or ""
        ),
        establishes_roles=[str(r) for r in est_roles if str(r).strip()],
        action_is_navigation=bool(na.get("action_is_navigation")),
        attempt_id=str(na.get("attempt_id") or "").strip(),
        legacy_semantics=bool(na.get("legacy_semantics")),
        prefer_realization=str(na.get("prefer_realization") or "").strip(),
    )
    # The prediction, in the shape the transition and experience layers read. It
    # was empty on every model-chosen action, so record_outcome() compared each
    # result against nothing and the capability memory learned nothing from the
    # whole fast path — the agent executed thousands of steps without
    # accumulating what any of its controls actually do. The model already states
    # this prediction; it only needed carrying.
    expectation = dict(proposal.expected_transition or {})
    predicted_surface = str(expectation.get("surface") or "").strip()
    likely = [
        str(c).strip()
        for c in (expectation.get("likely_controls") or [])
        if str(c).strip()
    ][:8]
    # Search-scope families: family contract beats a look that wished for
    # conversation_open (live 210526: compose/resolve stamped conversation).
    # Open-nav families: family contract beats a reveal-shaped wish
    # (live 131030: open_entity + context_menu).
    fam_l = str(family or "").strip().lower()
    if fam_l in _SEARCH_SCOPE_FAMILIES:
        fallback = intention_expectation_from_decision(
            Action(action=verb, action_family=family, semantic_target=semantic_target, text=text)
        )
        predicted_surface = str(fallback.get("surface") or "search").strip()
        likely = list(fallback.get("likely_controls") or [])[:8]
        expectation = {
            "surface": predicted_surface,
            "likely_controls": likely,
            "source": "family_contract",
        }
    elif fam_l in _OPEN_NAV_FAMILIES and (
        not predicted_surface or predicted_surface in _REVEAL_EFFECT_SURFACES
    ):
        fallback = intention_expectation_from_decision(
            Action(action=verb, action_family=family, semantic_target=semantic_target, text=text)
        )
        predicted_surface = str(fallback.get("surface") or "conversation").strip()
        likely = list(fallback.get("likely_controls") or [])[:8]
        expectation = {
            "surface": predicted_surface,
            "likely_controls": likely,
            "source": "family_contract",
        }
    elif not predicted_surface:
        # Model omitted expected_transition — still attach a family claim so
        # ACT can stamp intention for the post-act score.
        fallback = intention_expectation_from_decision(
            Action(action=verb, action_family=family, semantic_target=semantic_target, text=text)
        )
        predicted_surface = str(fallback.get("surface") or "").strip()
        if not likely:
            likely = list(fallback.get("likely_controls") or [])[:8]
    if predicted_surface or likely:
        action.prediction = {
            "action_family": family,
            "semantic_target": semantic_target,
            "predicted_outcome": predicted_surface,
            "expected_surface": predicted_surface,
            "expected_affordances": likely,
            "expected_progress": round(float(confidence or 0.0), 4),
            "confidence": round(float(confidence or 0.0), 4),
            "reversible": family != "commit_irreversible",
            "source": (
                "family_contract"
                if fam_l in _SEARCH_SCOPE_FAMILIES
                or (
                    fam_l in _OPEN_NAV_FAMILIES
                    and str(expectation.get("source") or "") == "family_contract"
                )
                else ("unified_multimodal" if expectation.get("surface") else "act_intention_default")
            ),
        }
        action.expected_predicate = predicted_surface or action.expected_predicate
        if fam_l == "resolve_entity":
            action.prediction["claims_navigation"] = False
            action.prediction["claims_resolution"] = True

    if family == "scroll_content":
        action.scroll_direction = str(proposal.next_action.get("direction") or "down")
        action.scroll_amount = int(proposal.next_action.get("amount") or 3)

    # Carry grounded geometry even for keyboard families like type_query — the
    # motor uses it to click a local filter instead of Cmd+F sidebar Search.
    #
    # Coordinate contract:
    # - entity.bounds from OCR/AX are already screen points — use their center.
    # - coordinate_space=screen on next_action means the same (do not re-scale).
    # - otherwise next_action points are image/window-relative and need origin+scale.
    # Live zarooratwala: transforming an already-screen Search point produced
    # [403,149] and confirm read '1110 pernvory' instead of Search.
    raw_point = proposal.next_action.get("target_point")
    coord_space = str(
        proposal.next_action.get("coordinate_space") or "image"
    ).strip().lower()
    entity_screen_point = None
    if entity is not None and _entity_has_bounds(entity):
        try:
            b = getattr(entity, "bounds", None)
            entity_screen_point = (
                round(float(b[0]) + float(b[2]) / 2.0),
                round(float(b[1]) + float(b[3]) / 2.0),
            )
        except (TypeError, ValueError, IndexError):
            entity_screen_point = None
    # Resolve VLM/image point to screen first — never let a disagreeing AX
    # entity center silently replace it (open Pallavi 011539: [270,143]→138).
    if coord_space == "screen" and isinstance(raw_point, (list, tuple)) and len(raw_point) >= 2:
        try:
            vlm_screen_point = (round(float(raw_point[0])), round(float(raw_point[1])))
        except (TypeError, ValueError):
            vlm_screen_point = None
    else:
        vlm_screen_point = _to_screen_point(
            raw_point,
            proposal.point_scale,
            proposal.point_origin,
        )
    _AGREE_PAD = 96.0
    if entity_screen_point is not None and vlm_screen_point is not None:
        try:
            agree = (
                abs(float(entity_screen_point[0]) - float(vlm_screen_point[0])) <= _AGREE_PAD
                and abs(float(entity_screen_point[1]) - float(vlm_screen_point[1])) <= _AGREE_PAD
            )
        except (TypeError, ValueError):
            agree = False
        if agree:
            action.target_point = entity_screen_point
        elif family in {"select_content", "reveal_actions"} and not _entity_in_sidebar(
            world, entity
        ):
            # Content acts: bound conversation-pane geometry beats a leftover
            # chat-list VLM point (013229: reveal kept [320,160] after open).
            action.target_point = entity_screen_point
        elif coord_space == "screen":
            # Explicit screen VLM beats a disagreeing AX fragment center (011539).
            action.target_point = vlm_screen_point
        else:
            # Image-space points must not be origin-scaled over screen entity bounds
            # (Search field: [223,93]+origin → (403,149) while entity center is (260,94)).
            action.target_point = entity_screen_point
    elif entity_screen_point is not None:
        action.target_point = entity_screen_point
    else:
        action.target_point = vlm_screen_point
    # Overlay verbs: prefer explicit control geometry; refuse content click.
    if verb_on_overlay and family in {"invoke_affordance", "commit_irreversible"}:
        if overlay_action_point is not None and (
            action.target_point is None
            or entity_screen_point is None
            or (
                entity is not None
                and ("http" in str(getattr(entity, "label", "") or "").lower())
            )
        ):
            action.target_point = (
                round(float(overlay_action_point[0])),
                round(float(overlay_action_point[1])),
            )
            action.grounding_reason = "overlay_verb_control_point"
        if action.target_point is None:
            return None, "overlay_verb_without_geometry"

    # Skip AX entities already proven inert for this open (repair path).
    try:
        hints = getattr(world, "overlay_hints", None) or {}
        repair = hints.get("open_repair") if isinstance(hints, dict) else None
        failed_ids = set()
        if isinstance(repair, dict):
            failed_ids = {int(x) for x in (repair.get("failed_entity_ids") or []) if str(x).lstrip("-").isdigit()}
        eid = getattr(action, "target_entity_id", None)
        if eid is not None and int(eid) in failed_ids and vlm_screen_point is not None:
            action.target_point = vlm_screen_point
            action.target_entity_id = None
            action.grounding_reason = "open_repair_vlm_point"
    except Exception:
        pass

    # Argument checks before geometry — empty type/locate should say so clearly.
    if family == "type_query" and not text:
        return None, "type_without_text"
    if family == "locate_content" and not text:
        # The runtime supplies the mechanism, never the query -- what to look
        # for is the judgment the model is here to make.
        return None, "locate_without_query"

    # GroundedUiTarget family: UI actuation without geometry is not admissible.
    # Cmd+F invent is closed, so type_query needs a field site too.
    try:
        from plugin.agent.capabilities.catalog import geometry_required_capabilities

        needs_geo = family in geometry_required_capabilities()
    except Exception:
        needs_geo = family in {
            "compose_search_query",
            "type_query",
            "open_entity",
            "select_content",
            "reveal_actions",
            "resolve_entity",
            "invoke_affordance",
            "commit_irreversible",
            "locate_content",
        }
    if needs_geo and action.target_point is None and entity is None:
        return None, f"{family}_without_geometry"

    # Runtime admissibility: a pointer action must resolve to something real --
    # an AX entity, a screen point, or at minimum a label to search for.
    if family not in _KEYBOARD_FAMILIES and entity is None:
        if action.target_point is None and not semantic_target:
            return None, "pointer_action_without_target"
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
