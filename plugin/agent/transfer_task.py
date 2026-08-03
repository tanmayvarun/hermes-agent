"""App-general model of an "act on / transfer an object" task.

The WhatsApp overlay grew a bespoke ``WhatsAppWorldView`` plus a ~900-line
accessibility binder to answer three questions: is the container open, is the
target object present/selected, and is the action/destination surface up. Those
questions are not WhatsApp-specific -- forwarding a WhatsApp message, forwarding
a Slack message, moving a Finder file and sharing a YouTube video are the same
task *shape*. Only the surface vocabulary differs.

This module derives the task's predicates from the **unified world document**
(``{surface, open_conversation, objects:[{kind,text,matches_goal}]}``) that the
multimodal perceptor already emits for every app, rather than from per-app AX
heuristics. It reuses the existing :class:`ForwardTaskState` schema so the phase
ladder, policy and evals keep working unchanged while the input becomes general.

The mapping from a concrete app's surface names to the general roles is the only
app-aware part, and it lives in :data:`SURFACE_ROLES` as plain data an overlay
can extend -- not as branching logic.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from plugin.agent.goal import Goal
from plugin.agent.task_binding import ForwardTaskState

# The general surface-role table now lives in scene_layers (single source of
# truth shared with the layered perceptor). Re-exported here so existing callers
# and tests keep importing ``surface_role`` / ``SURFACE_ROLES`` from this module.
from plugin.agent.scene_layers import (  # noqa: F401  (re-export)
    SURFACE_ROLES,
    Layer,
    container_layer as _container_layer,
    find_layer as _find_layer,
    normalize_layers,
    surface_role,
)


def _objects(document: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [o for o in (document.get("objects") or []) if isinstance(o, dict)]


def _text_of(obj: Dict[str, Any]) -> str:
    return str(obj.get("text") or obj.get("label") or "").strip()


def _matches_query(obj: Dict[str, Any], query: str) -> bool:
    """A document object is the goal object if the model flagged it or its text
    carries the query token. Kept lexical + explicit so it transfers across apps;
    genuinely hard disambiguation is the resolver's job, not the binder's."""
    if bool(obj.get("matches_goal")):
        return True
    q = (query or "").strip().lower()
    if not q:
        return False
    blob = _text_of(obj).lower()
    if q in blob:
        return True
    compact_q = "".join(ch for ch in q if ch.isalnum())
    compact_blob = "".join(ch for ch in blob if ch.isalnum())
    return bool(compact_q) and compact_q in compact_blob


def _name_matches(observed: str, wanted: str) -> bool:
    obs = str(observed or "").strip().lower()
    want = str(wanted or "").strip().lower()
    if not want:
        return bool(obs)  # no specific container required: any open one counts
    if not obs:
        return False
    return want in obs or obs in want


def build_transfer_state(
    goal: Goal,
    document: Dict[str, Any],
    *,
    prior: Optional[Dict[str, Any]] = None,
    entity_id_for_text: Optional[Any] = None,
    leftover: bool = False,
) -> ForwardTaskState:
    """Derive transfer predicates + phase from the unified world document.

    Pure over ``(goal, document, prior)`` so it is unit-testable without a live
    ``WorldModel``. ``entity_id_for_text`` is an optional callable ``str -> int``
    used to bind the goal object to a clickable entity when available; predicates
    and phase never depend on it.
    """
    state = ForwardTaskState.from_dict(prior)
    document = document if isinstance(document, dict) else {}

    # Preferred path: the perceptor gave us a layer stack, so object permanence
    # is already in the representation (the container stays present, occluded,
    # beneath any overlay). Read the stack directly -- no prior-state stickiness.
    raw_layers = document.get("layers")
    if raw_layers:
        return _build_from_layers(
            goal,
            normalize_layers(raw_layers),
            state,
            entity_id_for_text=entity_id_for_text,
            leftover=leftover,
        )

    # ---- bridge (flat single-surface reading) --------------------------------
    # Kept only until layered perception is the default. Here permanence has to
    # be reconstructed from prior task state, because the flat reading erases the
    # container the moment an overlay appears. This block is the "sticky belief"
    # patch; it disappears when ``layers`` is always present.
    # Beliefs that persist behind an overlay. When an action menu, destination
    # picker or dialog is on top, the container and its object are still open
    # underneath -- the reading just describes the overlay. Recomputing them to
    # False here would regress the phase to OPEN_SOURCE the instant the Forward
    # menu appears (observed live), so carry the prior truth across overlays.
    prior_container_open = bool(state.predicates.source_conversation_open)
    prior_object_visible = bool(state.predicates.source_object_visible)

    role = surface_role(document.get("surface", ""))
    overlay_role = role in {"action_menu", "destination", "dialog"}
    container_name = str(document.get("open_conversation") or document.get("container") or "").strip()
    source = (goal.contact or "").strip()
    dest = (goal.target_contact or "").strip()
    query = (goal.link_query or "").strip()
    objects = _objects(document)

    container_open = (role == "container" and _name_matches(container_name, source)) or (
        overlay_role and prior_container_open
    )

    # --- container (source_conversation) ---
    conv_b = state.binding("source_conversation")
    conv_b.constraints = {"name": source}
    if container_open:
        conv_b.status = "confirmed"
        conv_b.confidence = 0.95
        conv_b.evidence = [f"container={container_name!r}"]
    elif conv_b.status == "confirmed":
        conv_b.status = "invalidated"
        state.invalidate_downstream_of("source_conversation")
    else:
        conv_b.status = "unresolved"
        conv_b.confidence = 0.0

    # --- target object (source_object) ---
    obj_b = state.binding("source_object")
    obj_b.constraints = {"content_tokens": [query] if query else [], "container_binding": "source_conversation"}
    goal_objects = [o for o in objects if _matches_query(o, query)] if container_open else []
    object_present = bool(goal_objects)
    if object_present:
        ids: List[int] = []
        if callable(entity_id_for_text):
            for obj in goal_objects:
                try:
                    eid = entity_id_for_text(_text_of(obj))
                except Exception:
                    eid = None
                if eid is not None:
                    ids.append(int(eid))
        obj_b.candidate_entity_ids = list(dict.fromkeys(ids))[:12]
        if obj_b.status not in {"provisional", "confirmed"}:
            obj_b.status = "ambiguous" if len(goal_objects) > 1 else "provisional"
        if obj_b.candidate_entity_ids and obj_b.resolved_entity_id is None and len(obj_b.candidate_entity_ids) == 1:
            obj_b.resolved_entity_id = obj_b.candidate_entity_ids[0]
        obj_b.confidence = max(obj_b.confidence, 0.7 if len(goal_objects) == 1 else 0.4)
        obj_b.evidence = [f"object={_text_of(goal_objects[0])[:60]!r}"]
    elif container_open and not overlay_role and obj_b.status == "confirmed":
        # Container still open (no overlay) but the object dropped from view ->
        # keep a grounded selection alive (occlusion), otherwise demote.
        if obj_b.resolved_entity_id is None:
            obj_b.status = "unresolved"

    # --- action/destination surfaces from the general surface role ---
    action_menu_open = role == "action_menu"
    destination_visible = role == "destination"
    # Destination chosen: on the destination surface an object matching the
    # destination name is flagged selected/matches_goal.
    destination_chosen = destination_visible and any(
        _name_matches(_text_of(o), dest) and (bool(o.get("selected")) or bool(o.get("matches_goal")))
        for o in objects
    )

    p = state.predicates
    p.source_conversation_open = container_open
    p.source_conversation_visible = p.source_conversation_visible or container_open or role in {"list", "search"}
    p.source_object_visible = object_present or (overlay_role and prior_object_visible)
    # selection is an action effect, not a reading; preserve prior unless the
    # object left view while ungrounded.
    if object_present and obj_b.is_grounded:
        p.source_object_selected = p.source_object_selected or False
    p.forward_surface_open = action_menu_open
    p.destination_picker_visible = destination_visible
    if destination_chosen:
        p.destination_selected = True

    state.derive_phase(leftover=leftover)
    return state


def _build_from_layers(
    goal: Goal,
    layers: Sequence["Layer"],
    state: ForwardTaskState,
    *,
    entity_id_for_text: Optional[Any] = None,
    leftover: bool = False,
) -> ForwardTaskState:
    """Derive transfer predicates from a layer stack.

    Object permanence is a property of the stack (the container layer persists,
    occluded, beneath any overlay, carrying its objects), so this reads the
    layers as-is with no prior-state carry: ``source_conversation_open`` is true
    whenever a container layer exists in the stack, whether active or occluded.
    """
    source = (goal.contact or "").strip()
    dest = (goal.target_contact or "").strip()
    query = (goal.link_query or "").strip()

    container = _container_layer(layers)
    action_menu = _find_layer(layers, "action_menu")
    destination = _find_layer(layers, "destination")

    container_name = container.name if container is not None else ""
    container_present = container is not None
    container_open = container_present and _name_matches(container_name, source)
    container_objects = list(container.objects) if container is not None else []

    # --- container (source_conversation) ---
    conv_b = state.binding("source_conversation")
    conv_b.constraints = {"name": source}
    if container_open:
        occ = " (occluded)" if container is not None and container.occluded else ""
        conv_b.status = "confirmed"
        conv_b.confidence = 0.95
        conv_b.evidence = [f"container={container_name!r}{occ}"]
    elif conv_b.status == "confirmed":
        conv_b.status = "invalidated"
        state.invalidate_downstream_of("source_conversation")
    else:
        conv_b.status = "unresolved"
        conv_b.confidence = 0.0

    # --- target object (source_object) ---
    obj_b = state.binding("source_object")
    obj_b.constraints = {
        "content_tokens": [query] if query else [],
        "container_binding": "source_conversation",
    }
    goal_objects = (
        [o for o in container_objects if _matches_query(o, query)] if container_open else []
    )
    object_present = bool(goal_objects)
    if object_present:
        ids: List[int] = []
        if callable(entity_id_for_text):
            for obj in goal_objects:
                try:
                    eid = entity_id_for_text(_text_of(obj))
                except Exception:
                    eid = None
                if eid is not None:
                    ids.append(int(eid))
        obj_b.candidate_entity_ids = list(dict.fromkeys(ids))[:12]
        if obj_b.status not in {"provisional", "confirmed"}:
            obj_b.status = "ambiguous" if len(goal_objects) > 1 else "provisional"
        if (
            obj_b.candidate_entity_ids
            and obj_b.resolved_entity_id is None
            and len(obj_b.candidate_entity_ids) == 1
        ):
            obj_b.resolved_entity_id = obj_b.candidate_entity_ids[0]
        obj_b.confidence = max(obj_b.confidence, 0.7 if len(goal_objects) == 1 else 0.4)
        obj_b.evidence = [f"object={_text_of(goal_objects[0])[:60]!r}"]
    elif container_open and obj_b.status == "confirmed" and obj_b.resolved_entity_id is None:
        obj_b.status = "unresolved"

    # --- action / destination surfaces from the stack ---
    action_menu_open = action_menu is not None
    destination_visible = destination is not None
    dest_objects = list(destination.objects) if destination is not None else []
    destination_chosen = destination_visible and any(
        _name_matches(_text_of(o), dest) and (bool(o.get("selected")) or bool(o.get("matches_goal")))
        for o in dest_objects
    )

    p = state.predicates
    p.source_conversation_open = container_open
    p.source_conversation_visible = (
        p.source_conversation_visible
        or container_open
        or _find_layer(layers, "list") is not None
        or _find_layer(layers, "search") is not None
    )
    p.source_object_visible = object_present
    if object_present and obj_b.is_grounded:
        p.source_object_selected = p.source_object_selected or False
    p.forward_surface_open = action_menu_open
    p.destination_picker_visible = destination_visible
    if destination_chosen:
        p.destination_selected = True

    state.derive_phase(leftover=leftover)
    return state
