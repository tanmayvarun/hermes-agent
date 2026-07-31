"""Latent interaction context + goal-relevant affordance detection.

Object permanence for overlays: occluded predicates stay believed until contradicted.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from plugin.agent.goal import Goal
from plugin.agent.transition.types import (
    AffordanceDelta,
    ContextualBelief,
    InteractionContext,
    Observability,
)
from plugin.worldmodel.entities.normalize import _clean_label

# Goal-kind → (affordance_id, label patterns). Order matters for ranking.
_GOAL_AFFORDANCES: Dict[str, List[Tuple[str, Tuple[str, ...]]]] = {
    "whatsapp_voice_call": [
        ("initiate_voice", (r"^voice$", r"\bvoice call\b", r"\baudio call\b")),
        ("initiate_video", (r"^video$", r"\bvideo call\b")),
        ("select_participants", (r"select people", r"add people", r"add participant")),
        ("open_call_menu", (r"open call dropdown", r"call menu", r"call dropdown")),
        ("start_call", (r"^call$", r"\bphone\b")),
    ],
}


def _stem_match(haystack: str, needle: str) -> bool:
    h = _clean_label(haystack or "").lower().rstrip("….")
    n = _clean_label(needle or "").lower().rstrip("….")
    if not h or not n or len(n) < 2:
        return False
    return n in h or h.startswith(n) or n.startswith(h[: max(2, min(len(h), len(n)))])


def _labels_from_view(view: Dict[str, Any]) -> List[str]:
    raw = list(view.get("visible_contacts") or [])
    extra = []
    for key in ("open_conversation", "search_query"):
        v = view.get(key)
        if v:
            extra.append(str(v))
    for msg in view.get("conversation_messages") or []:
        if isinstance(msg, dict):
            for key in ("text", "label", "description", "action", "sender"):
                val = msg.get(key)
                if val:
                    extra.append(str(val))
            actions = msg.get("actions") or []
            if isinstance(actions, list):
                extra.extend(str(a) for a in actions if str(a).strip())
        else:
            extra.append(str(msg))
    return [str(x) for x in raw + extra if x]


def detect_goal_affordances(goal: Goal, view: Dict[str, Any]) -> List[str]:
    """Return affordance ids currently visible for this goal."""
    specs = _GOAL_AFFORDANCES.get(goal.kind) or []
    labels = [_clean_label(x).lower() for x in _labels_from_view(view)]
    found: List[str] = []
    for aid, patterns in specs:
        hit = False
        for lab in labels:
            for pat in patterns:
                if re.search(pat, lab, re.I):
                    hit = True
                    break
            if hit:
                break
        if hit:
            found.append(aid)
    return found


def detect_latent_affordances(view: Dict[str, Any]) -> List[str]:
    """Return generic affordances that are not always visible until probe/hover."""
    labels = [_clean_label(x).lower() for x in _labels_from_view(view)]
    screen = str(view.get("screen") or view.get("screen_kind") or view.get("wa_screen") or "").strip().lower()
    blob = " | ".join(labels)

    if not labels:
        return []

    latent: List[str] = []
    row_like = bool(view.get("conversation_messages")) or any(
        token in blob for token in ("message", "chat", "timeline", "row", "card", "preview")
    )
    interactive_surface = screen in {"conversation", "list", "search_results", "detail", "sidebar"} or bool(
        view.get("open_conversation") or view.get("search_query")
    )

    if row_like and interactive_surface:
        latent.extend(["probe_hover", "probe_context_menu"])
        if any(token in blob for token in ("forward", "reply", "react", "star", "pin", "copy", "info", "delete", "select messages", "message actions", "more options", "dropdown")):
            latent.append("reveal_message_actions")
        for token, affordance in (
            ("forward", "forward_message"),
            ("reply", "reply_message"),
            ("react", "react_message"),
            ("star", "star_message"),
            ("pin", "pin_message"),
            ("copy", "copy_message"),
            ("info", "inspect_message_info"),
            ("delete", "delete_message"),
            ("select messages", "select_messages"),
        ):
            if token in blob:
                latent.append(affordance)
    if interactive_surface and any(token in blob for token in ("header", "toolbar", "actions", "more", "options")):
        latent.append("probe_focus")
    return list(dict.fromkeys(latent))


def affordance_delta(goal: Goal, before_view: Dict[str, Any], after_view: Dict[str, Any]) -> AffordanceDelta:
    before = set(detect_goal_affordances(goal, before_view))
    after = set(detect_goal_affordances(goal, after_view))
    newly = sorted(after - before)
    lost = sorted(before - after)
    latent_before = set(detect_latent_affordances(before_view))
    latent_after = set(detect_latent_affordances(after_view))
    newly_latent = sorted(latent_after - latent_before)
    # Voice-call goals: initiate_voice / open_call_menu highly relevant
    weights = {
        "initiate_voice": 1.0,
        "initiate_video": 0.35,
        "select_participants": 0.55,
        "open_call_menu": 0.7,
        "start_call": 0.5,
        "probe_hover": 0.2,
        "probe_context_menu": 0.22,
        "probe_focus": 0.12,
        "reveal_message_actions": 0.45,
        "forward_message": 0.45,
        "reply_message": 0.26,
        "react_message": 0.18,
        "star_message": 0.16,
        "pin_message": 0.16,
        "copy_message": 0.1,
        "inspect_message_info": 0.12,
        "delete_message": 0.08,
        "select_messages": 0.24,
    }
    relevance = (
        sum(weights.get(a, 0.2) for a in newly)
        + sum(weights.get(a, 0.15) for a in newly_latent)
        - 0.15 * sum(weights.get(a, 0.2) for a in lost)
    )
    return AffordanceDelta(
        newly_available=sorted(dict.fromkeys(newly + newly_latent)),
        lost=lost,
        relevance_score=round(relevance, 4),
    )


def infer_active_surface(view: Dict[str, Any], affordances: Sequence[str]) -> str:
    labels = " | ".join(_labels_from_view(view)).lower()
    if "initiate_voice" in affordances or "select_participants" in affordances:
        if re.search(r"select people|voice|video", labels):
            return "call_picker"
    if view.get("open_conversation"):
        return "conversation"
    if view.get("search_query") or view.get("search_focused"):
        if view.get("visible_contacts"):
            return "search_results"
        return "search"
    screen = str(view.get("screen") or "").upper()
    if screen == "CONVERSATION":
        return "conversation"
    if screen in {"LIST", "SEARCH_RESULTS"}:
        return "list"
    return "unknown"


def update_interaction_context(
    ctx: InteractionContext,
    *,
    goal: Goal,
    view: Dict[str, Any],
    features: Optional[Dict[str, Any]] = None,
    world_id: str = "",
) -> InteractionContext:
    """Update latent context from a new observation (object permanence for overlays)."""
    features = features or {}
    ref = goal.ensure_reference() if goal.contact else None
    name = (ref.active_name if ref else goal.contact) or ""
    open_c = str(view.get("open_conversation") or "")
    conf = float(features.get("resolution_confidence") or ctx.target_confidence or 0)
    aff = detect_goal_affordances(goal, view)
    latent = detect_latent_affordances(view)
    surface = infer_active_surface(view, aff)
    selected_label = _clean_label(str(features.get("selected_object_label") or ""))
    selected_conf = features.get("selected_object_confidence")
    selected_visible = features.get("selected_object_visible")
    selected_obs = str(features.get("selected_object_observability") or "").strip().lower()

    bel = ctx.open_conversation
    if open_c and (not name or _stem_match(open_c, name) or _stem_match(open_c, (goal.contact or "").split()[0])):
        bel = ContextualBelief(
            value=True,
            confidence=max(conf, 0.75),
            observability=Observability.CONFIRMED_TRUE.value,
            last_confirmed_world=world_id or bel.last_confirmed_world,
        )
        ctx.selected_target = open_c
        ctx.target_confidence = bel.confidence
        ctx.originating_world = world_id or ctx.originating_world
    elif open_c and name and not _stem_match(open_c, name):
        # Positive contradiction: different conversation visible
        bel = ContextualBelief(
            value=False,
            confidence=0.85,
            observability=Observability.CONFIRMED_FALSE.value,
            last_confirmed_world=world_id or bel.last_confirmed_world,
        )
        ctx.selected_target = open_c
        ctx.target_confidence = 0.2
    elif not open_c and bel.effective:
        # Header gone — occluded, not falsified (unless surface leaves app context)
        bel = ContextualBelief(
            value=True,
            confidence=max(0.55, bel.confidence * 0.95),
            observability=Observability.NOT_CURRENTLY_OBSERVABLE.value,
            last_confirmed_world=bel.last_confirmed_world or world_id,
        )
    elif not open_c and not bel.effective:
        bel = ContextualBelief(
            value=False,
            confidence=0.3,
            observability=Observability.UNKNOWN.value,
            last_confirmed_world=bel.last_confirmed_world,
        )

    ctx.open_conversation = bel
    ctx.active_surface = surface
    if selected_label:
        observability = Observability.CONFIRMED_TRUE.value
        if selected_obs in {
            Observability.NOT_CURRENTLY_OBSERVABLE.value,
            Observability.UNKNOWN.value,
            Observability.STALE.value,
        }:
            observability = selected_obs
        elif selected_visible is False:
            observability = Observability.NOT_CURRENTLY_OBSERVABLE.value
        ctx.selected_object_label = selected_label
        ctx.selected_object = ContextualBelief(
            value=True,
            confidence=max(float(selected_conf or 0.0), 0.65 if observability != Observability.CONFIRMED_TRUE.value else 0.75),
            observability=observability,
            last_confirmed_world=world_id or ctx.selected_object.last_confirmed_world,
        )
    elif ctx.selected_object.effective:
        # Keep a latent selected-object belief alive through temporary occlusion.
        ctx.selected_object = ContextualBelief(
            value=True,
            confidence=max(0.55, ctx.selected_object.confidence * 0.95),
            observability=Observability.NOT_CURRENTLY_OBSERVABLE.value,
            last_confirmed_world=ctx.selected_object.last_confirmed_world or world_id,
        )
    if surface == "call_picker":
        ctx.reversible = True
    ctx.latent_affordances = latent
    return ctx


def latent_target_in_focus(ctx: Optional[InteractionContext], goal: Goal, view: Dict[str, Any]) -> float:
    """Score whether the goal target is still in focus, including occluded latent state."""
    open_c = str(view.get("open_conversation") or "")
    ref = goal.ensure_reference() if goal.contact else None
    name = (ref.active_name if ref else goal.contact) or ""
    if name and open_c and _stem_match(open_c, name):
        return 1.0
    if not name and open_c:
        return 0.8
    if ctx and ctx.open_conversation.effective:
        sel = ctx.selected_target or ""
        if name and (sel and _stem_match(sel, name)):
            return 0.85  # occluded but latent
        if ctx.open_conversation.observability == Observability.NOT_CURRENTLY_OBSERVABLE.value:
            if name and ctx.originating_world:
                return 0.8
    if ctx and ctx.selected_object.effective:
        sel_obj = ctx.selected_object_label or ""
        labels = " | ".join(_labels_from_view(view))
        if sel_obj and _stem_match(labels, sel_obj):
            return 0.85
        if ctx.selected_object.observability == Observability.NOT_CURRENTLY_OBSERVABLE.value:
            return 0.7
    # Visible labels may still mention target (call picker title)
    labels = " | ".join(_labels_from_view(view))
    if name and _stem_match(labels, name):
        return 0.75
    return 0.0


def contradiction_evidence(
    *,
    goal: Goal,
    before_view: Dict[str, Any],
    after_view: Dict[str, Any],
    ctx: Optional[InteractionContext] = None,
    features_after: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Positive evidence of a bad branch — not mere loss of familiar features."""
    evidence: List[str] = []
    features_after = features_after or {}
    ref = goal.ensure_reference() if goal.contact else None
    name = (ref.active_name if ref else goal.contact) or ""
    open_after = str(after_view.get("open_conversation") or "")
    open_before = str(before_view.get("open_conversation") or "")

    if name and open_after and not _stem_match(open_after, name):
        # Different named conversation confirmed open
        if len(_clean_label(open_after)) >= 2:
            evidence.append("wrong_target_visible")

    app_b = str(before_view.get("app") or before_view.get("active_app") or "")
    app_a = str(after_view.get("app") or after_view.get("active_app") or "")
    if app_b and app_a and app_b.lower() != app_a.lower():
        evidence.append("app_changed_unintentionally")

    # Explicit deselection: we had confirmed focus, now confirmed different/false with no new affordances
    if ctx and ctx.open_conversation.observability == Observability.CONFIRMED_FALSE.value:
        evidence.append("target_deselected")

    # Returned to empty list from conversation without gaining call affordances
    aff = detect_goal_affordances(goal, after_view)
    if (
        open_before
        and not open_after
        and not aff
        and str(after_view.get("screen") or "").upper() == "LIST"
        and str(before_view.get("screen") or "").upper() == "CONVERSATION"
        and not any(x in " | ".join(_labels_from_view(after_view)).lower() for x in ("voice", "video", "select people"))
    ):
        evidence.append("left_conversation_without_call_surface")

    if features_after.get("leftover_call") and goal.kind == "whatsapp_voice_call":
        # leftover alone is not regression into call_picker path
        pass

    return evidence
