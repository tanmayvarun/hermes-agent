"""WhatsApp app overlay — semantic view + progress signals (not a planner)."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from plugin.agent.features import StateFeatures
from plugin.agent.goal import Goal, GoalStatus
from plugin.agent.predicates import CallStateIs
from plugin.agent.whatsapp_view import (
    WhatsAppWorldView,
    _conversation_context_window,
    _is_contact_name,
    contact_matches,
    resolve_contact_entity,
)
from plugin.agent.conversation_reasoning import rank_conversation_messages
from plugin.worldmodel.entities.entity import Entity
from plugin.worldmodel.entities.normalize import _clean_label
from plugin.worldmodel.model import WorldModel

_RESULT_CHROME = {
    "search",
    "search results",
    "messages",
    "photos",
    "videos",
    "links",
    "image",
    "all",
    "groups",
    "unread",
    "favourites",
    "favorites",
    "archived",
    "chat",
    "chats",
}

_SOURCE_ROW_ACTION_CHROME = (
    "start voice call",
    "start video call",
    "voice call with",
    "video call with",
    "audio call with",
    "open call dropdown",
    "more options",
    "chat info",
    "view contact",
)

_CALL_WINDOW_HINTS = (
    "whatsapp voice call",
    "whatsapp video call",
    "voice call",
    "video call",
)


def _get_reference_resolver():
    from plugin.agent.resolver import get_reference_resolver

    return get_reference_resolver()


def _looks_like_result_row(name: str) -> bool:
    label = _clean_label(name)
    if not label or len(label) > 80:
        return False
    low = label.lower()
    if low in _RESULT_CHROME:
        return False
    if any(token in low for token in ("message", "photo", "video", "link", "image")) and " " not in low:
        return False
    return True


def _search_result_rows(view: WhatsAppWorldView, goal: Goal, ref) -> List[str]:
    """Rows that look actionable on a search/results surface."""
    needles = []
    for candidate in (goal.contact or "", getattr(ref, "name", "") or ""):
        candidate = _clean_label(candidate)
        if candidate:
            needles.append(candidate)
    for hyp in getattr(ref, "search_hypotheses", None) or []:
        hyp = _clean_label(hyp)
        if hyp:
            needles.append(hyp)

    out: List[str] = []
    seen = set()
    for label in view.visible_contacts:
        cleaned = _clean_label(label)
        low = cleaned.lower()
        if not _looks_like_result_row(cleaned):
            continue
        if needles and not any(contact_matches(cleaned, needle, min_score=0.55) for needle in needles):
            stem = low.rstrip("….").split()[0] if low else ""
            if not stem or not any(
                stem in _clean_label(needle).lower().split()[0]
                for needle in needles
                if needle
            ):
                continue
        if low not in seen:
            seen.add(low)
            out.append(cleaned)
    return out


def _conversation_context_rows(view: WhatsAppWorldView) -> List[Dict[str, Any]]:
    rows = list(getattr(view, "conversation_messages", None) or [])
    out: List[Dict[str, Any]] = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        text = _clean_label(str(row.get("text") or row.get("label") or ""))
        if not text:
            continue
        key = (text.lower(), str(row.get("entity_id") or ""))
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "entity_id": row.get("entity_id"),
                "text": text,
                "label": _clean_label(str(row.get("label") or "")),
                "description": _clean_label(str(row.get("description") or "")),
                "entity_type": str(row.get("entity_type") or ""),
                "role": str(row.get("role") or ""),
                "y": row.get("y"),
                "x": row.get("x"),
            }
        )
    return out


def _looks_like_source_row_chrome(label: str) -> bool:
    low = _clean_label(label).lower()
    if not low:
        return False
    if any(pat in low for pat in _SOURCE_ROW_ACTION_CHROME):
        return True
    if low.startswith("start ") and "call" in low:
        return True
    return False


def _looks_like_call_window(window_name: str) -> bool:
    low = _clean_label(window_name).lower()
    if not low:
        return False
    return any(hint in low for hint in _CALL_WINDOW_HINTS)

def _call_mentions_contact(view: WhatsAppWorldView, world: WorldModel, contact: str) -> bool:
    needle = (contact or "").strip().lower()
    if not needle:
        return True
    # Prefer interpreted reference name (e.g. "Now" from "now group")
    names = [needle]
    try:
        from plugin.agent.reference import interpret_reference

        ref = interpret_reference(contact)
        if ref.name:
            names.append(ref.name.lower())
        for h in ref.search_hypotheses or []:
            if h:
                names.append(h.lower())
    except Exception:
        pass
    blobs = [
        view.open_conversation or "",
        view.search_query or "",
        " ".join(view.visible_contacts[:20]),
    ]
    for e in world.entities.values():
        if not e.visible:
            continue
        blobs.append(e.label or "")
        blobs.append(e.semantic_role or "")
        blobs.append(str(e.attributes.get("description") or ""))
    blob = " ".join(blobs).lower()
    for n in names:
        n = n.strip()
        if not n:
            continue
        if n in blob:
            return True
        # Stem against truncated headers
        stem = n.rstrip("….").split()[0] if n else ""
        if len(stem) >= 2 and stem in blob:
            return True
    # Nickname / soft match against open conversation header
    open_c = view.open_conversation or ""
    if open_c and any(stem and stem in open_c.lower() for stem in (n.split()[0] for n in names if n)):
        return True
    if open_c and contact_matches(open_c, contact, min_score=0.55):
        return True
    return False


def _on_named_conversation(open_c: str, name: str) -> bool:
    open_l = (open_c or "").lower()
    needle = (name or "").strip().lower()
    if not needle or not open_l:
        return False
    if needle in open_l:
        return True
    return any(tok in open_l for tok in needle.split() if len(tok) > 2)


def _query_in_conversation_timeline(world: WorldModel, query: str) -> bool:
    """True if query text is visible in the chat pane (not sidebar list rows)."""
    from plugin.agent.apps.whatsapp_targets import in_sidebar_band

    q = (query or "").strip().lower()
    if not q:
        return False
    compact_q = re.sub(r"[^a-z0-9]+", "", q)
    ents = [e for e in world.entities.values() if e.visible]
    for e in ents:
        if in_sidebar_band(e, ents):
            continue
        blob = f"{e.label} {e.semantic_role} {e.attributes.get('description', '')}".lower()
        compact_blob = re.sub(r"[^a-z0-9]+", "", blob)
        if q in blob or (compact_q and compact_q in compact_blob):
            return True
    return False


def _forward_chrome_visible(world: WorldModel) -> bool:
    """True only for Forward *picker* chrome — not 'Forwarded' status / message text."""
    from plugin.worldmodel.pragmatic_role import (
        UiPragmaticRole,
        get_pragmatic_role,
        has_clickable_geometry,
        infer_pragmatic_role_stage2,
    )

    chrome_exact = {
        "forward",
        "forward message",
        "forward messages",
        "send to",
        "select chats",
        "select chat",
    }
    for e in world.entities.values():
        if not e.visible:
            continue
        if get_pragmatic_role(e) == UiPragmaticRole.UNKNOWN:
            infer_pragmatic_role_stage2(e)
        role = get_pragmatic_role(e)
        # Status/content ("Forwarded") and nav must never look like forward chrome
        if role in {
            UiPragmaticRole.STATUS,
            UiPragmaticRole.CONTENT,
            UiPragmaticRole.NAV_CHROME,
            UiPragmaticRole.DECORATIVE,
            UiPragmaticRole.INPUT,
        }:
            continue
        lab = (e.label or e.semantic_role or "").strip().lower()
        if lab in {"forwarded", "forwarded message"}:
            continue
        if lab in chrome_exact and (
            role == UiPragmaticRole.CTA or has_clickable_geometry(e)
        ):
            return True
        desc = str((e.attributes or {}).get("description") or "").strip().lower()
        if desc in chrome_exact and role == UiPragmaticRole.CTA and has_clickable_geometry(e):
            return True
    return False


def build_forward_task_state(
    goal: Goal,
    world: WorldModel,
    view: Any,
    *,
    leftover: bool,
    prior: Optional[Dict[str, Any]] = None,
) -> "ForwardTaskState":
    """Evidence-driven bindings + predicates; phase is a derived view only."""
    from plugin.agent.apps.whatsapp_targets import in_sidebar_band
    from plugin.agent.task_binding import (
        ForwardTaskState,
        find_query_entities,
        picker_chrome_visible,
        source_object_latently_selected,
    )
    from plugin.worldmodel.pragmatic_role import (
        UiPragmaticRole,
        get_pragmatic_role,
        infer_pragmatic_role_stage2,
    )

    state = ForwardTaskState.from_dict(prior)
    source = (goal.contact or "").strip()
    dest = (goal.target_contact or "").strip()
    query = (goal.link_query or "").strip()
    open_c = view.open_conversation or ""
    on_source = _on_named_conversation(open_c, source)
    on_dest = _on_named_conversation(open_c, dest)
    ents = list(world.entities.values())

    # --- source_conversation ---
    conv_b = state.binding("source_conversation")
    conv_b.constraints = {"name": source}
    if on_source:
        conv_b.status = "confirmed"
        conv_b.confidence = 0.95
        conv_b.evidence = [f"open_conversation={open_c!r}"]
    elif conv_b.status == "confirmed":
        conv_b.status = "invalidated"
        state.invalidate_downstream_of("source_conversation")
    else:
        conv_b.status = "unresolved"
        conv_b.confidence = 0.0

    # --- source_object (message/link matching query) ---
    obj_b = state.binding("source_object")
    obj_b.constraints = {
        "content_tokens": [query] if query else [],
        "types": ["link", "message"],
        "container_binding": "source_conversation",
    }
    hits = find_query_entities(ents, query, in_sidebar_fn=in_sidebar_band) if query else []
    # Prefer message/link content over decorative/profile chrome.
    hit_ids = []
    for e in hits:
        if e.entity_type in {"window", "group", "scroll", "image", "photo"}:
            continue
        if get_pragmatic_role(e) == UiPragmaticRole.UNKNOWN:
            infer_pragmatic_role_stage2(e)
        role = get_pragmatic_role(e)
        if role in {
            UiPragmaticRole.STATUS,
            UiPragmaticRole.NAV_CHROME,
            UiPragmaticRole.DECORATIVE,
            UiPragmaticRole.INPUT,
        }:
            # Keep text-like timeline rows that contain the query; drop chrome
            # such as profile/photo/info panels and generic status rows.
            blob = f"{e.label or ''} {e.semantic_role or ''} {(e.attributes or {}).get('description', '')}".lower()
            if e.entity_type in {"static", "link", "message", "cell", "unknown"} and (
                query.lower() in blob or "http://" in blob or "https://" in blob or "link" in blob
            ):
                if "photo" not in (e.label or "").lower() and "image" not in (e.label or "").lower():
                    hit_ids.append(int(e.id))
            continue
        if role == UiPragmaticRole.CTA and e.entity_type not in {"link", "message"}:
            continue
        hit_ids.append(int(e.id))
    obj_b.candidate_entity_ids = hit_ids[:12]
    source_hits = find_query_entities(ents, source, in_sidebar_fn=in_sidebar_band) if source else []
    source_hit_ids: List[int] = []
    for e in source_hits:
        if e.entity_type in {"window", "group", "scroll", "image", "photo"}:
            continue
        if get_pragmatic_role(e) == UiPragmaticRole.UNKNOWN:
            infer_pragmatic_role_stage2(e)
        role = get_pragmatic_role(e)
        if role in {
            UiPragmaticRole.STATUS,
            UiPragmaticRole.NAV_CHROME,
            UiPragmaticRole.DECORATIVE,
            UiPragmaticRole.INPUT,
        }:
            continue
        source_hit_ids.append(int(e.id))
    if not source_hit_ids and source:
        # Fallback: scan raw sidebar entities directly. Some AX trees expose
        # contact rows as static/button hybrids that the generic resolver
        # can miss until the header is corrected.
        for e in ents:
            if not e.visible or not in_sidebar_band(e, ents, scene_graph=getattr(world, "last_scene_graph", None) or {}):
                continue
            if get_pragmatic_role(e) == UiPragmaticRole.UNKNOWN:
                infer_pragmatic_role_stage2(e)
            role = get_pragmatic_role(e)
            blob = f"{_clean_label(e.label or '')} {_clean_label(e.semantic_role or '')} {_clean_label((e.attributes or {}).get('description', ''))}"
            if contact_matches(blob, source, min_score=0.75):
                source_hit_ids.append(int(e.id))
                continue
            if role in {
                UiPragmaticRole.STATUS,
                UiPragmaticRole.NAV_CHROME,
                UiPragmaticRole.DECORATIVE,
                UiPragmaticRole.INPUT,
            }:
                continue
        if source_hit_ids:
            source_hit_ids = list(dict.fromkeys(source_hit_ids))
    llm_ranked_ids: List[int] = []
    llm_ranked_text = ""
    conversation_relevance = (getattr(world, "overlay_hints", None) or {}).get("conversation_message_relevance")
    if isinstance(conversation_relevance, dict):
        raw_ranked = conversation_relevance.get("ranked_messages") or []
        if isinstance(raw_ranked, list):
            for item in raw_ranked:
                if not isinstance(item, dict):
                    continue
                try:
                    eid = int(item.get("entity_id") or item.get("id"))
                except (TypeError, ValueError):
                    continue
                if eid in llm_ranked_ids:
                    continue
                if eid in world.entities and world.entities[eid].visible:
                    llm_ranked_ids.append(eid)
        raw_ids = conversation_relevance.get("likely_source_message_ids") or []
        if isinstance(raw_ids, list):
            for item in raw_ids:
                try:
                    eid = int(item)
                except (TypeError, ValueError):
                    continue
                if eid not in llm_ranked_ids and eid in world.entities and world.entities[eid].visible:
                    llm_ranked_ids.append(eid)
        llm_ranked_text = str(conversation_relevance.get("likely_source_message_text") or "").strip()
        if llm_ranked_ids:
            for eid in reversed(llm_ranked_ids[:6]):
                if eid not in hit_ids:
                    hit_ids.insert(0, eid)
            if not source_hit_ids:
                source_hit_ids = list(dict.fromkeys(llm_ranked_ids[:6]))
    hints = getattr(world, "overlay_hints", None) or {}
    selected_id = hints.get("source_object_entity_id")
    selected_ok = False
    prior_selected = source_object_latently_selected(state)
    if selected_id is not None:
        try:
            selected_id = int(selected_id)
        except (TypeError, ValueError):
            selected_id = None
        if selected_id is not None and selected_id in world.entities:
            se = world.entities[selected_id]
            if se.visible and selected_id in hit_ids:
                selected_ok = True
            elif se.visible and query and query.lower() in (
                f"{se.label} {se.semantic_role} {(se.attributes or {}).get('description', '')}"
            ).lower():
                selected_ok = True
                if selected_id not in hit_ids:
                    hit_ids.insert(0, selected_id)
                    obj_b.candidate_entity_ids = hit_ids[:12]

        if not on_source:
            obj_b.status = "provisional" if source_hit_ids else "unresolved"
        obj_b.resolved_entity_id = source_hit_ids[0] if source_hit_ids else None
        obj_b.confidence = 0.45 if source_hit_ids else 0.0
        obj_b.evidence = (
            [f"source conversation visible entity_id={source_hit_ids[0]}"]
            if source_hit_ids
            else ["source conversation not open"]
        )
    elif len(hit_ids) == 0:
        if prior_selected and obj_b.resolved_entity_id is not None:
            obj_b.status = "confirmed"
            obj_b.confidence = max(obj_b.confidence, 0.7)
            obj_b.evidence = [f"latently selected entity_id={obj_b.resolved_entity_id}"]
        elif llm_ranked_ids:
            obj_b.status = "provisional"
            obj_b.resolved_entity_id = llm_ranked_ids[0]
            obj_b.confidence = 0.66
            obj_b.evidence = [
                f"llm_ranked entity_id={llm_ranked_ids[0]}",
                *( [f"llm_text={llm_ranked_text!r}"] if llm_ranked_text else [] ),
            ]
        else:
            obj_b.status = "unresolved"
            obj_b.resolved_entity_id = None
            obj_b.confidence = 0.0
            obj_b.evidence = [f"no timeline match for {query!r}"]
    elif len(hit_ids) == 1:
        obj_b.resolved_entity_id = hit_ids[0]
        obj_b.confidence = 0.85
        obj_b.status = "confirmed" if (selected_ok or prior_selected) else "provisional"
        obj_b.evidence = [f"unique match entity_id={hit_ids[0]}"]
        if llm_ranked_ids and hit_ids[0] in llm_ranked_ids:
            obj_b.evidence.insert(0, f"llm_ranked entity_id={hit_ids[0]}")
            if llm_ranked_text:
                obj_b.evidence.insert(1, f"llm_text={llm_ranked_text!r}")
    else:
        # Ambiguous until selection; keep prior resolved id if still a candidate
        prior_id = obj_b.resolved_entity_id
        if (selected_ok or prior_selected) and selected_id in hit_ids:
            obj_b.resolved_entity_id = selected_id
            obj_b.status = "confirmed"
            obj_b.confidence = 0.92
            obj_b.evidence = [f"selected entity_id={selected_id}"]
        elif (prior_id in hit_ids and obj_b.status in {"provisional", "confirmed"}) or prior_selected:
            obj_b.resolved_entity_id = prior_id
            obj_b.status = "confirmed" if prior_selected else "provisional"
            obj_b.confidence = 0.75 if prior_selected else 0.6
            obj_b.evidence = [
                f"prior entity_id={prior_id} still visible among {len(hit_ids)}"
                if prior_id in hit_ids
                else f"latently selected entity_id={prior_id}"
            ]
        else:
            obj_b.resolved_entity_id = hit_ids[0]
            obj_b.status = "ambiguous"
            obj_b.confidence = 0.45
            obj_b.evidence = [f"{len(hit_ids)} matches; need select_content"]

    if (selected_ok or prior_selected) and obj_b.resolved_entity_id is not None:
        obj_b.status = "confirmed"
        obj_b.confidence = max(obj_b.confidence, 0.9 if selected_ok else 0.75)

    # --- destination ---
    dest_b = state.binding("destination")
    dest_b.constraints = {"name": dest}
    if on_dest:
        dest_b.status = "confirmed"
        dest_b.confidence = 0.9
        dest_b.evidence = [f"open_conversation={open_c!r}"]
    else:
        dest_b.status = "unresolved"
        dest_b.confidence = 0.0

    # --- predicates (world evidence only) ---
    picker_only = picker_chrome_visible(ents)
    from plugin.worldmodel.pragmatic_role import entity_display_text, get_pragmatic_role, UiPragmaticRole

    has_forward_verb = False
    for e in ents:
        if not e.visible:
            continue
        lab = entity_display_text(e).lower().strip()
        if lab in {"forward", "forward message", "forward messages", "share"}:
            role = get_pragmatic_role(e)
            if role in {UiPragmaticRole.STATUS, UiPragmaticRole.CONTENT, UiPragmaticRole.NAV_CHROME}:
                continue
            has_forward_verb = True
            break

    p = state.predicates
    p.source_conversation_open = on_source
    p.source_conversation_visible = bool(source_hit_ids) and not on_source
    p.source_object_visible = bool(hit_ids) and on_source
    p.source_object_selected = bool((selected_ok or prior_selected) and on_source)
    # Forward CTA ≠ destination picker
    p.forward_surface_open = bool(has_forward_verb and not picker_only)
    p.destination_picker_visible = bool(picker_only)
    p.destination_selected = bool(on_dest and picker_only)
    p.forward_completed = bool(
        on_dest
        and not on_source
        and not picker_only
        and bool(query)
        and _query_in_conversation_timeline(world, query)
        and bool(hints.get("forward_commit_started") or selected_ok)
    )

    state.derive_phase(leftover=leftover)
    state.consistency_rollback()
    state.derive_phase(leftover=leftover)
    return state


def _infer_forward_phase(
    goal: Goal,
    world: WorldModel,
    view: Any,
    *,
    leftover: bool,
) -> str:
    """Derived view of ForwardTaskState predicates (compat for candidates/value)."""
    prior = (getattr(world, "overlay_hints", None) or {}).get("forward_task")
    state = build_forward_task_state(goal, world, view, leftover=leftover, prior=prior)
    return state.derived_phase


class WhatsAppOverlay:
    app_names: List[str] = ["whatsapp", "WhatsApp"]

    def _view(self, world: WorldModel) -> WhatsAppWorldView:
        hint = str((getattr(world, "overlay_hints", None) or {}).get("search_query") or "")
        return WhatsAppWorldView.from_world_model(world, search_query_hint=hint)

    def raw_view(self, world: WorldModel) -> WhatsAppWorldView:
        hint = str((getattr(world, "overlay_hints", None) or {}).get("search_query") or "")
        return WhatsAppWorldView.from_world_model_raw(world, search_query_hint=hint)

    def view_dict(self, world: WorldModel) -> Dict[str, Any]:
        return self._view(world).to_dict()

    def raw_view_dict(self, world: WorldModel) -> Dict[str, Any]:
        return self.raw_view(world).to_dict()

    def capability_hints(self, goal: Goal) -> Dict[str, Any]:
        goal_kind = str(getattr(goal, "kind", "") or "")
        return {
            "goal_capability_types": {
                goal_kind: [
                    "InitiateVoiceCall",
                    "RevealCommunicationOptions",
                    "InitiateVideoCall",
                    "SelectParticipants",
                    "OpenMenu",
                    "OpenConversation",
                ]
            },
            "label_capability_regions": {
                "voice": ["floating_menu", "header", "toolbar", "modal"],
                "voice call": ["floating_menu", "header", "toolbar", "modal"],
                "audio call": ["floating_menu", "header", "toolbar", "modal"],
                "call": ["floating_menu", "header", "toolbar", "modal"],
                "video": ["floating_menu", "header", "toolbar", "modal"],
                "select people": ["floating_menu", "header", "toolbar", "modal"],
                "add people": ["floating_menu", "header", "toolbar", "modal"],
                "participants": ["floating_menu", "header", "toolbar", "modal"],
                "participant": ["floating_menu", "header", "toolbar", "modal"],
                "call dropdown": ["floating_menu", "header", "toolbar", "modal"],
                "call menu": ["floating_menu", "header", "toolbar", "modal"],
                "more options": ["floating_menu", "header", "toolbar", "modal"],
                "open call dropdown": ["floating_menu", "header", "toolbar", "modal"],
                "open call menu": ["floating_menu", "header", "toolbar", "modal"],
                "end call": ["floating_menu", "header", "toolbar", "modal"],
                "end": ["floating_menu", "header", "toolbar", "modal"],
                "decline": ["floating_menu", "header", "toolbar", "modal"],
            },
            "label_capability_types": {
                "voice": ["InitiateVoiceCall"],
                "voice call": ["InitiateVoiceCall"],
                "audio call": ["InitiateVoiceCall"],
                "call": ["InitiateVoiceCall"],
                "video": ["InitiateVideoCall"],
                "select people": ["SelectParticipants"],
                "add people": ["SelectParticipants"],
                "participants": ["SelectParticipants"],
                "participant": ["SelectParticipants"],
                "call dropdown": ["RevealCommunicationOptions"],
                "call menu": ["RevealCommunicationOptions"],
                "more options": ["RevealCommunicationOptions"],
                "open call dropdown": ["RevealCommunicationOptions"],
                "open call menu": ["RevealCommunicationOptions"],
                "end call": ["DismissOverlay"],
                "end": ["DismissOverlay"],
                "decline": ["DismissOverlay"],
            },
        }

    def features(self, world: WorldModel, goal: Goal, *, worldview_score: float = 1.0) -> StateFeatures:
        from plugin.agent.apps.whatsapp_semantics import apply_semantic_types

        apply_semantic_types(world)
        view = self._view(world)
        ents = list(world.entities.values())
        contact = (goal.contact or "").strip()
        ref = goal.ensure_reference() if contact else None
        resolve_name = (ref.active_name if ref else contact) or contact
        needle = contact.lower()
        name_needle = resolve_name.lower()
        q = (view.search_query or "").strip()
        # Query matches raw or any search hypothesis
        hyps = list((ref.search_hypotheses if ref else None) or [resolve_name, contact])
        query_matches = bool(q) and any(
            q.lower() == h.lower() or contact_matches(q, h, min_score=0.55) for h in hyps if h
        )

        resolution = (
            _get_reference_resolver().resolve(
                world,
                contact,
                goal_kind=goal.kind,
                reference=ref,
            )
            if contact
            else None
        )
        ranked = [] if resolution is None else [c.to_dict() for c in resolution.candidates]
        policy = "ask" if resolution is None else resolution.policy
        conf = 0.0 if resolution is None else float(resolution.confidence)
        named = policy == "auto" and resolution is not None and resolution.winner is not None
        if not named and resolve_name:
            named = any(contact_matches(c, resolve_name, min_score=0.9) for c in view.visible_contacts)

        low_confidence = bool(contact) and policy in {"observe", "ask"} and bool(ranked)
        needs_confirmation = policy == "ask" and bool(ranked)
        search_result_rows = _search_result_rows(view, goal, ref)
        result_surface_visible = bool(q) and bool(search_result_rows or view.visible_contacts)
        conversation_context_rows = _conversation_context_rows(view)
        storage_pressure = bool(view.system_warnings)
        # Storage pressure is a recovery signal, not a generic dialog. Keep it
        # separate so the policy layer can trigger cleanup instead of blindly
        # emitting dismiss actions.
        blocking_overlay = bool(getattr(view, "blocking_overlay", False) and not storage_pressure)
        source_contact_rows = [
            label
            for label in view.visible_contacts
            if contact_matches(label, resolve_name, min_score=0.75)
            or contact_matches(label, contact, min_score=0.75)
        ]
        if not source_contact_rows:
            from plugin.agent.apps.whatsapp_targets import in_sidebar_band

            for cand in ranked:
                cand_name = _clean_label(str(cand.get("name") or ""))
                if not cand_name:
                    continue
                if not _is_contact_name(cand_name):
                    continue
                if _looks_like_source_row_chrome(cand_name):
                    continue
                cand_ent = None
                cand_eid = cand.get("entity_id")
                if cand_eid is not None:
                    cand_ent = world.entities.get(int(cand_eid))
                if cand_ent is None or not cand_ent.visible:
                    continue
                if not in_sidebar_band(
                    cand_ent,
                    ents,
                    scene_graph=getattr(world, "last_scene_graph", None) or {},
                ):
                    continue
                if contact_matches(cand_name, resolve_name, min_score=0.75) or contact_matches(
                    cand_name, contact, min_score=0.75
                ):
                    source_contact_rows.append(cand_name)
        if not source_contact_rows and contact:
            # Generic fallback: if the semantic contact row is visible in the raw
            # sidebar entity set but was not promoted into `visible_contacts`,
            # still treat it as visible source evidence. This keeps forward
            # binding from getting stuck on list-item normalization details.
            from plugin.agent.apps.whatsapp_targets import in_sidebar_band
            from plugin.worldmodel.pragmatic_role import (
                UiPragmaticRole,
                get_pragmatic_role,
                infer_pragmatic_role_stage2,
            )

            for e in ents:
                if not e.visible or not in_sidebar_band(
                    e,
                    ents,
                    scene_graph=getattr(world, "last_scene_graph", None) or {},
                ):
                    continue
                if _looks_like_source_row_chrome(_clean_label(e.label or "") or _clean_label(e.semantic_role or "")):
                    continue
                if get_pragmatic_role(e) == UiPragmaticRole.UNKNOWN:
                    infer_pragmatic_role_stage2(e)
                if get_pragmatic_role(e) in {
                    UiPragmaticRole.CTA,
                    UiPragmaticRole.NAV_CHROME,
                    UiPragmaticRole.STATUS,
                    UiPragmaticRole.INPUT,
                    UiPragmaticRole.DECORATIVE,
                }:
                    continue
                blob = f"{_clean_label(e.label or '')} {_clean_label(e.semantic_role or '')} {_clean_label((e.attributes or {}).get('description', ''))}"
                if contact_matches(blob, resolve_name, min_score=0.75) or contact_matches(
                    blob, contact, min_score=0.75
                ):
                    name = _clean_label(e.label or e.semantic_role or "")
                    if name and _is_contact_name(name) and len(_clean_label(name)) <= 48:
                        source_contact_rows.append(name)
            if source_contact_rows:
                source_contact_rows = list(dict.fromkeys(source_contact_rows))
        open_c = view.open_conversation or ""
        winner_name = None if resolution is None else resolution.winner_name
        conv_match = bool(name_needle or needle) and (
            contact_matches(open_c, resolve_name, min_score=0.55)
            or contact_matches(open_c, contact, min_score=0.55)
            or (
                bool(winner_name)
                and contact_matches(open_c, winner_name, min_score=0.75)
            )
        )
        conv = conv_match and (
            view.screen == "CONVERSATION"
            or (view.composer_visible and not view.search_visible and not q)
        )
        source_conversation_visible = bool(source_contact_rows) and not conv
        from plugin.agent.apps.whatsapp_targets import (
            composer_mic_visible,
            end_call_clickable,
            end_call_visible,
            exact_label_visible,
            voice_call_chrome_visible,
        )

        end_visible = end_call_visible(world)
        end_clickable = end_call_clickable(world)
        call_window_visible = _looks_like_call_window(getattr(view, "window_name", "") or "")
        has_list_context = bool(
            view.screen in {"LIST", "SEARCH", "SEARCH_RESULTS"}
            or view.search_visible
            or view.search_query
            or view.visible_contacts
        )
        if goal.kind == "whatsapp_forward_message":
            # Only real hangup chrome — ghost ringing without End Call must not lock PRECLEAR
            leftover = bool(end_clickable or end_visible or call_window_visible or view.screen == "CALLING")
            fail_streak = int((world.overlay_hints or {}).get("end_call_fail_streak") or 0)
            # After repeated failed hangups with no clickable control, leave PRECLEAR
            if leftover and not end_clickable and fail_streak >= 3:
                leftover = False
        else:
            leftover = (
                ((end_clickable or end_visible) and not has_list_context)
                or view.call_state in {"ringing", "maybe_end_call"}
            )
            if call_window_visible or view.screen == "CALLING":
                leftover = True
            if leftover and (resolve_name or contact):
                # Active call to the goal contact is success chrome, not leftover
                leftover = not _call_mentions_contact(view, world, resolve_name or contact)
        call_available = voice_call_chrome_visible(world) or (
            bool(view.voice_call_available) and not leftover
        )
        mic_visible = composer_mic_visible(world)
        screen_map = {
            "LIST": "list",
            "SEARCH": "search",
            "SEARCH_RESULTS": "search",
            "CONVERSATION": "conversation",
            "CALLING": "calling",
            "DIALOG": "dialog",
        }
        screen_bucket = screen_map.get(view.screen, "unknown")
        screen_kind = str(getattr(getattr(world, "current_screen", None), "kind", "") or screen_bucket or "unknown").lower()
        if blocking_overlay:
            screen_bucket = "dialog"
            screen_kind = "dialog"
        progress = 0.0
        if query_matches:
            progress = max(progress, 0.25)
        if result_surface_visible and query_matches:
            progress = max(progress, 0.35)
        if named and query_matches:
            progress = max(progress, 0.45)
        elif policy == "observe" and query_matches:
            progress = max(progress, 0.35)
        if conv:
            progress = max(progress, 0.7)
        if call_available and conv:
            progress = max(progress, 0.85)
        if view.call_state == "ringing" and not leftover:
            progress = 1.0

        # Dialogs: only real dialog button labels with non-zero bounds
        _DIALOG_OK = {
            "not now",
            "later",
            "cancel",
            "ok",
            "close",
            "don't allow",
            "dont allow",
            "allow",
        }
        real_dialogs = []
        for d in view.unexpected_dialogs or []:
            lab = _clean_label(d)
            if not lab or lab.lower() not in _DIALOG_OK:
                continue
            if exact_label_visible(world, lab):
                real_dialogs.append(lab)

        forward_phase = ""
        forward_task_dict: Dict[str, Any] = {}
        selected_object_meta: Dict[str, Any] = {}
        if goal.kind == "whatsapp_forward_message":
            prior_ft = (world.overlay_hints or {}).get("forward_task")
            ft = build_forward_task_state(
                goal, world, view, leftover=leftover, prior=prior_ft if isinstance(prior_ft, dict) else None
            )
            # Carry controller suppress/repair flags from prior
            if isinstance(prior_ft, dict):
                ft.suppress_observe = bool(prior_ft.get("suppress_observe"))
                if prior_ft.get("binding_repair"):
                    ft.binding_repair = True
            forward_phase = ft.derived_phase
            forward_task_dict = ft.to_dict()
            if world.overlay_hints is None:
                world.overlay_hints = {}
            world.overlay_hints["forward_task"] = forward_task_dict
            src_binding = ft.binding("source_object")
            if src_binding.is_grounded:
                selected_ent = world.entities.get(int(src_binding.resolved_entity_id)) if src_binding.resolved_entity_id is not None else None
                selected_object_meta = {
                    "selected_object_label": _clean_label(
                        "" if selected_ent is None else (selected_ent.label or selected_ent.semantic_role or "")
                    ),
                    "selected_object_confidence": float(src_binding.confidence or 0.0),
                    "selected_object_visible": bool(selected_ent.visible) if selected_ent is not None else False,
                    "selected_object_observability": (
                        "confirmed_true"
                        if selected_ent is not None and selected_ent.visible
                        else "not_currently_observable"
                    ),
                }


        feats = StateFeatures(
            app=world.active_app or goal.app,
            screen_kind=screen_kind,
            screen_bucket=screen_bucket,
            has_dialog=bool(real_dialogs or blocking_overlay),
            has_text_query=bool(q),
            query_matches_goal=query_matches,
            has_named_entity=named,
            conversation_open=conv,
            call_available=bool(call_available),
            call_ringing=view.call_state == "ringing" and not leftover,
            leftover_call=leftover,
            search_focused=bool(view.search_focused),
            goal_progress=progress,
            worldview_score=worldview_score,
            mean_belief=round(
                (
                    sum(float(getattr(e, "confidence", 1.0) or 1.0) for e in world.entities.values() if e.visible)
                    / max(1, sum(1 for e in world.entities.values() if e.visible))
                )
                if any(e.visible for e in world.entities.values())
                else float(worldview_score),
                4,
            ),
            needs_reobserve=bool((world.last_worldview_score or {}).get("needs_reobserve")),
            extras={
                "search_query": q,
                "search_visible": bool(view.search_visible),
                "visible_contacts": view.visible_contacts[:12],
                "open_conversation": view.open_conversation,
                "dialogs": real_dialogs[:4],
                "system_warnings": list(view.system_warnings[:4]),
                "storage_pressure": storage_pressure,
                "blocking_overlay": blocking_overlay,
                "screen_kind": screen_kind,
                "wa_screen": view.screen,
                "window_name": getattr(view, "window_name", ""),
                "contact_candidates": ranked[:6],
                # Back-compat: "ambiguous" means low confidence (not auto)
                "ambiguous_contacts": low_confidence and not named,
                "needs_confirmation": needs_confirmation,
                "resolution_policy": policy,
                "resolution_confidence": round(conf, 4),
                "resolved_contact": (
                    resolution.winner_name
                    if resolution is not None and policy == "auto"
                    else None
                ),
                "preferred_contact": (
                    None if resolution is None else resolution.winner_name
                ),
                "resolution": None if resolution is None else resolution.to_dict(),
                "search_result_rows": search_result_rows,
                "result_surface_visible": result_surface_visible,
                "conversation_context_rows": conversation_context_rows,
                "conversation_context_text": [
                    row.get("text") for row in conversation_context_rows[:_conversation_context_window()]
                ],
                "conversation_context_window": _conversation_context_window(),
                "source_conversation_visible": source_conversation_visible,
                "source_conversation_rows": source_contact_rows[:6],
                "resolution_settled": resolution is not None,
                "perception_incomplete": False,
                "fusion_conflicts": list(world.last_conflicts or [])[:8],
                "mean_belief": round(
                    float((world.last_worldview_score or {}).get("mean_belief") or worldview_score),
                    4,
                ),
                "needs_reobserve": bool((world.last_worldview_score or {}).get("needs_reobserve")),
                "reference": None if ref is None else ref.to_dict(),
                "entity_type_filter": None if ref is None else ref.kind,
                "resolve_name": resolve_name,
                "end_call_visible": end_visible,
                "end_call_clickable": end_clickable,
                "composer_mic_visible": mic_visible,
                "forward_phase": forward_phase,
                "forward_task": forward_task_dict,
                **selected_object_meta,
                "end_call_fail_streak": int((world.overlay_hints or {}).get("end_call_fail_streak") or 0),
            },
        )
        conversation_relevance = None
        if goal.kind == "whatsapp_forward_message" and conversation_context_rows:
            try:
                conversation_relevance = rank_conversation_messages(
                    goal,
                    {
                        "screen": view.screen,
                        "open_conversation": view.open_conversation,
                        "search_query": view.search_query,
                        "conversation_context_window": _conversation_context_window(),
                    },
                    conversation_context_rows,
                    world=world,
                )
            except Exception:
                # Fail hard in the helper path if it is explicitly required; if
                # we reach here, leave the previous deterministic view intact so
                # the caller can surface the error at the live run boundary.
                raise
        if conversation_relevance is not None:
            conv_rel_dict = conversation_relevance.to_dict()
            feats.extras["conversation_message_relevance"] = conv_rel_dict
            feats.extras["ranked_conversation_messages"] = conv_rel_dict.get("ranked_messages", [])
            feats.extras["likely_source_message_ids"] = list(conv_rel_dict.get("likely_source_message_ids") or [])
            feats.extras["likely_source_message_text"] = conv_rel_dict.get("likely_source_message_text", "")
            if world.overlay_hints is None:
                world.overlay_hints = {}
            world.overlay_hints["conversation_message_relevance"] = conv_rel_dict
        try:
            from plugin.worldmodel.capability import build_capability_graph, goal_capability_types
            from plugin.worldmodel.scene.types import WorldGraph

            raw_scene = getattr(world, "last_scene_graph", None) or {}
            scene_graph = WorldGraph.from_dict(raw_scene) if isinstance(raw_scene, dict) and raw_scene else WorldGraph()
            cap_graph = build_capability_graph(
                scene_graph,
                list(world.entities.values()),
                goal=goal,
                capability_hints=self.capability_hints(goal),
            )
            feats.extras["capability_graph"] = cap_graph.to_dict()
            feats.extras["goal_capability_types"] = goal_capability_types(goal)
            feats.extras["goal_capability_ids"] = list(cap_graph.goal_capability_ids)
            feats.extras["capability_frontier"] = [node.to_dict() for node in cap_graph.frontier]
            selected = cap_graph.select_for_goal(goal)
            feats.extras["selected_capability"] = "" if selected is None else selected.capability_id
            world.last_capability_graph = cap_graph.to_dict()
        except Exception:
            pass
        return feats

    def goal_progress(self, world: WorldModel, goal: Goal) -> Dict[str, Any]:
        f = self.features(world, goal)
        return {
            "progress": f.goal_progress,
            "bits": {
                "query_matches": f.query_matches_goal,
                "contact_visible": f.has_named_entity,
                "conversation_open": f.conversation_open,
                "call_available": f.call_available,
                "ringing": f.call_ringing,
            },
            "features": f.to_dict(),
        }

    def evaluate_goal(self, goal: Goal, world: WorldModel) -> GoalStatus:
        view = self._view(world)
        if goal.kind == "whatsapp_forward_message":
            return self._evaluate_forward(goal, world, view)
        if goal.kind != "whatsapp_voice_call":
            return GoalStatus(impossible=True, reason=f"unknown goal kind {goal.kind}")
        ringing = CallStateIs("ringing").evaluate(world)
        if ringing.passed:
            if goal.require_contact_in_call and not _call_mentions_contact(view, world, goal.contact):
                return GoalStatus(
                    succeeded=False,
                    reason=f"call UI present but contact {goal.contact!r} not in call evidence — end leftover call",
                    evidence=view.to_dict(),
                )
            if goal.require_agent_initiated_call:
                started = int((world.overlay_hints or {}).get("start_call_count") or 0)
                if started < 1:
                    return GoalStatus(
                        succeeded=False,
                        reason="ringing UI present but no agent start_call this session (stale leftover)",
                        evidence={**view.to_dict(), "start_call_count": started},
                    )
            return GoalStatus(succeeded=True, reason="call ringing", evidence=view.to_dict())
        if not view.app_active and not world.entities:
            return GoalStatus(impossible=True, reason="WhatsApp world empty / inactive")
        return GoalStatus(succeeded=False, reason="call not ringing yet", evidence=view.to_dict())

    def _evaluate_forward(self, goal: Goal, world: WorldModel, view: Any) -> GoalStatus:
        """Success requires destination open AND query/link evidence (no soft skip)."""
        if not view.app_active and not world.entities:
            return GoalStatus(
                impossible=True,
                reason="WhatsApp world empty / inactive",
                evidence=view.to_dict(),
            )
        target = (goal.target_contact or "").strip().lower()
        query = (goal.link_query or "").strip().lower()
        open_c = (view.open_conversation or "").lower()
        on_target = _on_named_conversation(open_c, target)
        has_query = _query_in_conversation_timeline(world, query) if query else False
        # Also accept query anywhere if already forwarded into dest chat
        if query and not has_query:
            blob = " ".join(
                f"{e.label} {e.semantic_role}" for e in world.entities.values() if e.visible
            ).lower()
            has_query = query in blob
        forward_chrome = _forward_chrome_visible(world)
        if on_target and has_query:
            return GoalStatus(
                succeeded=True,
                reason="destination open with query evidence",
                evidence={
                    **view.to_dict(),
                    "has_query": has_query,
                    "forward_chrome": forward_chrome,
                },
            )
        return GoalStatus(
            succeeded=False,
            reason=(
                f"forward pending source={goal.contact!r} query={goal.link_query!r} "
                f"target={goal.target_contact!r} open={view.open_conversation!r} "
                f"has_query={has_query}"
            ),
            evidence=view.to_dict(),
        )

    def resolve_target(self, world: WorldModel, semantic: str, action: str) -> Optional[Entity]:
        from plugin.agent.apps.whatsapp_targets import resolve_whatsapp_target

        return resolve_whatsapp_target(world, semantic, action=action)
