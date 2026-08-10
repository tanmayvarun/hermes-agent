"""WhatsApp app overlay — semantic view + progress signals (not a planner)."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence

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
from plugin.agent.capabilities.locate_content import MACOS_FIND as _MACOS_FIND
from plugin.perception.representation import build_perception_result, structured_perception_bridge
from plugin.worldmodel.entities.entity import Entity
from plugin.worldmodel.entities.normalize import _clean_label
from plugin.worldmodel.model import WorldModel
from plugin.worldmodel.scene.focus import attach_active_cognitive_subgraph

# Host observation: WhatsApp search segments that restrict the result space to
# media-only grids (tag as filter_chip+restricts=media). Not a recovery rule.
_MEDIA_RESTRICT_FILTERS = frozenset(
    {
        "videos",
        "photos",
        "gifs",
        "audio",
        "voice",
        "documents",
        "stickers",
        "gifs & stickers",
        "image",
    }
)

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

# Result-scope filter chips (Links / Messages / All …) — distinct from the
# Search field chrome label, which must not be typed as an active filter.
_RESULT_SCOPE_FILTERS = frozenset(
    {
        "messages",
        "links",
        "all",
        "chats",
        "groups",
        "unread",
        "favourites",
        "favorites",
        "archived",
    }
)

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
    if not _conversation_surface_observed(view):
        return []
    rows = list(getattr(view, "conversation_messages", None) or [])
    if not rows:
        clusters = list(getattr(view, "conversation_timeline", None) or [])
        for cluster in clusters:
            if not isinstance(cluster, dict):
                continue
            text = _clean_label(str(cluster.get("text") or ""))
            urls = [str(u) for u in (cluster.get("urls") or []) if str(u).strip()]
            if not text and not urls:
                continue
            ids = [
                int(x)
                for x in (cluster.get("entity_ids") or cluster.get("message_ids") or [])
                if str(x).strip().isdigit()
            ]
            rows.append(
                {
                    "entity_id": ids[0] if ids else None,
                    "text": text or " ".join(urls),
                    "label": _clean_label(str(cluster.get("label") or "")),
                    "description": _clean_label(str(cluster.get("description") or "")),
                    "entity_type": "conversation_cluster",
                    "role": "conversation_cluster",
                    "y": cluster.get("top_y"),
                    "x": cluster.get("x"),
                    "entity_ids": ids,
                }
            )
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


def _sidebar_filtered_entity_ids(
    hit_ids: Sequence[int],
    world: WorldModel,
    ents: Sequence[Any],
    *,
    in_sidebar_fn: Any,
) -> List[int]:
    """Keep conversation-pane content ids; drop left-rail chat-list echoes.

    Timeline matching historically accepted sidebar preview rows that contain
    the query ("J/ zarooratwala Pallavi|"), which then became provisional
    source_object and sent RevealActions to ~(360,151) forever.
    """
    scene = getattr(world, "last_scene_graph", None) or {}
    kept: List[int] = []
    for eid in hit_ids:
        try:
            eid_i = int(eid)
        except (TypeError, ValueError):
            continue
        e = world.entities.get(eid_i)
        if e is None or not getattr(e, "visible", True):
            continue
        try:
            if in_sidebar_fn(e, ents, scene_graph=scene):
                continue
        except TypeError:
            try:
                if in_sidebar_fn(e, ents):
                    continue
            except Exception:
                pass
        except Exception:
            pass
        kept.append(eid_i)
    return list(dict.fromkeys(kept))


def _entity_blob_has_url(blob: str) -> bool:
    b = str(blob or "").lower()
    return (
        "http://" in b
        or "https://" in b
        or ".goo." in b
        or ".com/" in b
        or ".com?" in b
        or b.rstrip(".").endswith(".com")
    )


def _entity_query_blob(world: WorldModel, eid: int) -> str:
    e = world.entities.get(int(eid))
    if e is None:
        return ""
    return (
        f"{e.label or ''} {e.semantic_role or ''} "
        f"{(e.attributes or {}).get('description', '')}"
    )


def _entity_supports_source_query(world: WorldModel, eid: int, query: str) -> bool:
    from plugin.agent.source_query_binding import text_locates_source_query

    return text_locates_source_query(_entity_query_blob(world, eid), query)


def _entity_sender_for_binding(
    world: WorldModel,
    eid: int,
    *,
    peer: str = "",
) -> str:
    """Resolve message authorship for binding.

    Explicit ``You:`` / sender attrs win. Otherwise, unlabeled bubbles in an
    open peer conversation are treated as inbound from that peer (WhatsApp
    timeline convention) — container membership alone never invents authorship
    when the UI marks the message as outgoing.
    """
    from plugin.agent.source_query_binding import infer_message_originator

    e = world.entities.get(int(eid))
    if e is None:
        return ""
    attrs = e.attributes or {}
    text = _entity_query_blob(world, eid)
    explicit = infer_message_originator(
        text,
        sender=attrs.get("sender") or attrs.get("originator"),
    )
    if explicit:
        return explicit
    peer_n = str(peer or "").strip()
    if peer_n:
        return peer_n
    return ""


def _entity_binding_eligible(
    world: WorldModel,
    eid: int,
    *,
    query: str,
    expected_container: str = "",
    expected_originator: str = "",
) -> bool:
    """Overlay bind gate: query identity + originator (not opaque matches_goal).

    AX timeline nodes are often ``static``; object-kind is enforced at RoleBinder
    ACT time. Here we only refuse host-contradicting / wrong-author candidates.
    """
    from plugin.agent.source_query_binding import (
        evaluate_source_object_match,
        host_contradicts_query,
        query_supported_by_text,
    )

    e = world.entities.get(int(eid))
    if e is None:
        return False
    text = _entity_query_blob(world, eid)
    if query:
        if host_contradicts_query(text, query) and not query_supported_by_text(
            text, query
        ):
            return False
        if not query_supported_by_text(text, query):
            return False
    if not expected_originator:
        return True
    open_c = str(
        getattr(world, "open_conversation", "")
        or (getattr(world, "overlay_hints", None) or {}).get("open_conversation")
        or ""
    )
    peer = expected_container or open_c
    # Treat URL-bearing / query-bearing AX nodes as content for originator check.
    gm = evaluate_source_object_match(
        text=text,
        kind="message_with_link" if _entity_blob_has_url(text.lower()) else "message",
        query="",  # query already checked above (host may distract while text matches)
        container_open=open_c,
        expected_container="",  # container gated separately via on_source
        expected_originator=expected_originator,
        sender=_entity_sender_for_binding(world, eid, peer=peer),
    )
    return bool(gm.originator_match)


def _rank_source_object_hits(
    hit_ids: Sequence[int],
    world: WorldModel,
    *,
    query: str = "",
) -> List[int]:
    """Prefer URL/message content farther right (conversation pane) over list echoes.

    When any URL-bearing hit exists, drop plain-text substring matches so an
    outgoing caption like "zarooratwala Pallavi" cannot outrank
    https://www.zarooratwala.com (live 024851).

    ``matches_goal`` is recall-only — query identity outranks an opaque bool
    (live 214025: YouTube matches_goal must lose to zarooratwala).
    """

    def _blob(eid: int) -> str:
        return _entity_query_blob(world, eid).lower()

    ids = [int(x) for x in hit_ids]
    q = str(query or "").strip()
    if q:
        # Drop host-contradicting distractors before ranking.
        from plugin.agent.source_query_binding import host_contradicts_query, query_supported_by_text

        kept: List[int] = []
        for eid in ids:
            blob = _entity_query_blob(world, eid)
            if host_contradicts_query(blob, q) and not query_supported_by_text(blob, q):
                continue
            kept.append(eid)
        # If everything was a distractor, keep empty — do not bind YouTube.
        ids = kept

    url_ids = [eid for eid in ids if _entity_blob_has_url(_blob(eid))]
    if url_ids:
        ids = url_ids

    def _score(eid: int) -> tuple:
        e = world.entities.get(int(eid))
        if e is None:
            return (0, 0, 0, 0.0, 0.0, int(eid))
        blob = _blob(eid)
        has_url = 1 if _entity_blob_has_url(blob) else 0
        query_ok = 1 if (q and _entity_supports_source_query(world, eid, q)) else (0 if q else 1)
        # Opaque perception bool only helps among query-eligible hits.
        matches_goal = (
            1
            if query_ok and (e.attributes or {}).get("matches_goal")
            else 0
        )
        b = e.bounds or (0, 0, 0, 0)
        x = float(b[0]) if len(b) >= 1 else 0.0
        y = float(b[1]) if len(b) >= 2 else 0.0
        return (query_ok, has_url, matches_goal, x, -y, int(eid))

    return sorted(ids, key=_score, reverse=True)


def _conversation_timeline_rows(view: WhatsAppWorldView) -> List[Dict[str, Any]]:
    if not _conversation_surface_observed(view):
        return []
    clusters = list(getattr(view, "conversation_timeline", None) or [])
    out: List[Dict[str, Any]] = []
    seen = set()
    for cluster in clusters:
        if not isinstance(cluster, dict):
            continue
        text = _clean_label(str(cluster.get("text") or ""))
        urls = [str(u) for u in (cluster.get("urls") or []) if str(u).strip()]
        if not text and not urls:
            continue
        key = (
            text.lower(),
            tuple(u.lower() for u in urls),
            tuple(int(x) for x in (cluster.get("message_ids") or []) if str(x).strip().isdigit()),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "entity_id": (cluster.get("message_ids") or [None])[0],
                "message_ids": list(cluster.get("message_ids") or []),
                "entity_ids": list(cluster.get("entity_ids") or cluster.get("message_ids") or []),
                "text": text,
                "label": _clean_label(str(cluster.get("label") or "")),
                "description": _clean_label(str(cluster.get("description") or "")),
                "entity_type": "conversation_cluster",
                "role": "conversation_cluster",
                "urls": urls,
                "row_count": cluster.get("row_count"),
                "y": cluster.get("top_y"),
                "x": cluster.get("x"),
            }
        )
    return out


def _conversation_surface_observed(view: WhatsAppWorldView) -> bool:
    screen = str(getattr(view, "screen", "") or "").strip().upper()
    open_c = _clean_label(getattr(view, "open_conversation", "") or "")
    if not open_c:
        return False
    if screen not in {"LIST", "SEARCH", "SEARCH_RESULTS"}:
        return True
    # The sidebar can stay in SEARCH_RESULTS while the main pane already shows
    # the active conversation. When that happens, the timeline rows are still
    # usable and should not be dropped from forward binding.
    return bool(getattr(view, "conversation_messages", None) or getattr(view, "conversation_timeline", None))


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
    observed_conversation = _conversation_surface_observed(view)
    timeline_rows = _conversation_timeline_rows(view) if observed_conversation else []

    # Source chat is open — drop open-click repair so we don't keep escalating.
    if on_source:
        hints = getattr(world, "overlay_hints", None)
        if isinstance(hints, dict) and hints.get("open_repair"):
            hints.pop("open_repair", None)

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
    originator = str(
        getattr(goal, "originator", None)
        or getattr(goal, "contact", None)
        or source
        or ""
    ).strip()
    obj_b.constraints = {
        "content_tokens": [query] if query else [],
        "types": ["link", "message"],
        "container_binding": "source_conversation",
        "originator": originator,
    }
    hits = []
    timeline_hit_ids: List[int] = []
    if observed_conversation and query and timeline_rows:
        q_low = query.lower().strip()
        compact_q = re.sub(r"[^a-z0-9]+", "", q_low)
        for row in timeline_rows:
            blob = " ".join(
                [
                    str(row.get("text") or ""),
                    str(row.get("label") or ""),
                    str(row.get("description") or ""),
                    " ".join(str(u) for u in row.get("urls") or []),
                ]
            ).lower()
            compact_blob = re.sub(r"[^a-z0-9]+", "", blob)
            if q_low in blob or (compact_q and compact_q in compact_blob):
                ids = [
                    int(x)
                    for x in (row.get("entity_ids") or row.get("message_ids") or [])
                    if str(x).strip().isdigit()
                ]
                if not ids and row.get("entity_id") is not None and str(row.get("entity_id")).strip().isdigit():
                    ids = [int(row.get("entity_id"))]
                for eid in ids:
                    # Drop left-rail preview echoes before they own source_object.
                    e_hit = world.entities.get(int(eid))
                    if e_hit is not None:
                        try:
                            if in_sidebar_band(
                                e_hit,
                                ents,
                                scene_graph=getattr(world, "last_scene_graph", None) or {},
                            ):
                                continue
                        except Exception:
                            pass
                    if eid not in hits:
                        hits.append(eid)
                    if eid not in timeline_hit_ids:
                        timeline_hit_ids.append(eid)
    generic_hits = (
        find_query_entities(ents, query, in_sidebar_fn=in_sidebar_band)
        if (query and observed_conversation)
        else []
    )
    # Prefer message/link content over decorative/profile chrome.
    hit_ids = list(hits)
    for e in generic_hits:
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
    if hit_ids:
        hit_ids = list(dict.fromkeys(hit_ids))
    # Hard gate: never bind select→forward geometry to sidebar chat-list echoes.
    hit_ids = _sidebar_filtered_entity_ids(hit_ids, world, ents, in_sidebar_fn=in_sidebar_band)
    timeline_hit_ids = [eid for eid in timeline_hit_ids if eid in set(hit_ids)]
    hit_ids = _rank_source_object_hits(hit_ids, world, query=query)
    # Drop a prior bind only when that entity is still visible *and* is a
    # left-rail echo. Occluded content (missing from the tree) must keep its
    # latent selection so OPEN_FORWARD can invoke Forward.
    prior_resolved = obj_b.resolved_entity_id
    if prior_resolved is not None:
        try:
            prior_resolved = int(prior_resolved)
        except (TypeError, ValueError):
            prior_resolved = None
        if prior_resolved is not None and prior_resolved not in hit_ids:
            pe = world.entities.get(prior_resolved)
            if pe is not None and getattr(pe, "visible", True):
                try:
                    sidebar_prior = bool(
                        in_sidebar_band(
                            pe,
                            ents,
                            scene_graph=getattr(world, "last_scene_graph", None) or {},
                        )
                    )
                except Exception:
                    sidebar_prior = False
                if sidebar_prior:
                    obj_b.resolved_entity_id = None
                    if obj_b.status in {"provisional", "ambiguous", "confirmed"}:
                        obj_b.status = "unresolved"
    obj_b.candidate_entity_ids = hit_ids[:12]
    source_hits = (
        find_query_entities(ents, source, in_sidebar_fn=in_sidebar_band)
        if (source and observed_conversation)
        else []
    )
    source_hit_ids: List[int] = []
    source_timeline_hit_ids: List[int] = []
    if observed_conversation and source and timeline_rows:
        source_low = source.lower().strip()
        source_compact = re.sub(r"[^a-z0-9]+", "", source_low)
        for row in timeline_rows:
            blob = " ".join(
                [
                    str(row.get("text") or ""),
                    str(row.get("label") or ""),
                    str(row.get("description") or ""),
                    " ".join(str(u) for u in row.get("urls") or []),
                ]
            ).lower()
            compact_blob = re.sub(r"[^a-z0-9]+", "", blob)
            if source_low in blob or (source_compact and source_compact in compact_blob):
                ids = [
                    int(x)
                    for x in (row.get("entity_ids") or row.get("message_ids") or [])
                    if str(x).strip().isdigit()
                ]
                if not ids and row.get("entity_id") is not None and str(row.get("entity_id")).strip().isdigit():
                    ids = [int(row.get("entity_id"))]
                for eid in ids:
                    if eid not in source_hit_ids:
                        source_hit_ids.append(eid)
                    if eid not in source_timeline_hit_ids:
                        source_timeline_hit_ids.append(eid)
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
    if source_hit_ids:
        source_hit_ids = list(dict.fromkeys(source_hit_ids))
    if not on_source and not source_hit_ids and source:
        # List/search OR open-conversation without a resolved header: scan the
        # left rail for the goal contact. Previously this only ran when a
        # conversation surface was already observed, so a chat-list frame with
        # Pallavi visible kept source_conversation_visible=False forever
        # (live 092106).
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
    if observed_conversation and isinstance(conversation_relevance, dict):
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
            llm_ranked_ids = _sidebar_filtered_entity_ids(
                llm_ranked_ids, world, ents, in_sidebar_fn=in_sidebar_band
            )
            # Candidate recall may include any link; binding requires full role
            # constraints (query + originator). Relevance scores never write
            # Binding.resolved_entity_id by themselves.
            if query or originator:
                llm_ranked_ids = [
                    eid
                    for eid in llm_ranked_ids
                    if _entity_binding_eligible(
                        world,
                        eid,
                        query=query,
                        expected_container=source if on_source else "",
                        expected_originator=originator,
                    )
                    or (
                        # Keep high-recall candidates that only fail originator
                        # evidence when sender is unknown — still not bindable.
                        _entity_supports_source_query(world, eid, query)
                        if query
                        else True
                    )
                ]
            for eid in reversed(llm_ranked_ids[:6]):
                if eid not in hit_ids:
                    hit_ids.insert(0, eid)
            hit_ids = _rank_source_object_hits(hit_ids, world, query=query)
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
        # Sidebar latch is not a content selection.
        sidebar_selected = False
        try:
            sidebar_selected = bool(
                in_sidebar_band(
                    se,
                    ents,
                    scene_graph=getattr(world, "last_scene_graph", None) or {},
                )
            )
        except Exception:
            sidebar_selected = False
        if sidebar_selected:
            selected_id = None
            hints.pop("source_object_entity_id", None)
        elif se.visible and selected_id in hit_ids:
            selected_ok = True
        elif se.visible and query and query.lower() in (
            f"{se.label} {se.semantic_role} {(se.attributes or {}).get('description', '')}"
        ).lower():
            # Only accept query-text latch when not a left-rail echo.
            selected_ok = True
            if selected_id not in hit_ids:
                hit_ids.insert(0, selected_id)
                hit_ids = _rank_source_object_hits(hit_ids, world, query=query)
                obj_b.candidate_entity_ids = hit_ids[:12]

    if selected_id is not None and not on_source:
        obj_b.status = "provisional" if source_hit_ids else "unresolved"
        obj_b.resolved_entity_id = source_hit_ids[0] if source_hit_ids else None
        obj_b.confidence = 0.45 if source_hit_ids else 0.0
        obj_b.evidence = (
            [f"source timeline match entity_id={source_hit_ids[0]}"]
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
        obj_b.evidence = [
            f"source timeline match entity_id={hit_ids[0]}"
            if hit_ids[0] in timeline_hit_ids
            else f"unique match entity_id={hit_ids[0]}"
        ]
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

    # Hard binding validator: RoleBinder owns resolved identity. Query match
    # and opaque conversation_message_relevance scores are candidate signals
    # only — originator + query must both clear before resolved_entity_id sticks.
    # Skip when the resolved entity is temporarily occluded (latent selection).
    if obj_b.resolved_entity_id is not None and (query or originator):
        resolved_eid = int(obj_b.resolved_entity_id)
        entity_present = resolved_eid in world.entities
        if entity_present and not _entity_binding_eligible(
            world,
            resolved_eid,
            query=query,
            expected_container=source if on_source else "",
            expected_originator=originator,
        ):
            obj_b.evidence = list(obj_b.evidence or []) + [
                f"binding_rejected: entity_id={obj_b.resolved_entity_id} "
                f"fails role constraints query={query!r} originator={originator!r}"
            ]
            obj_b.resolved_entity_id = None
            if obj_b.status in {"confirmed", "provisional"}:
                obj_b.status = "ambiguous" if (obj_b.candidate_entity_ids or hit_ids) else "unresolved"
            obj_b.confidence = min(float(obj_b.confidence or 0.0), 0.45)
            p_tmp = state.predicates
            p_tmp.source_object_selected = False
            # Candidates may still be query-relevant; eligibility filters binds.
            if query:
                obj_b.candidate_entity_ids = [
                    eid
                    for eid in (obj_b.candidate_entity_ids or [])
                    if int(eid) in world.entities
                    and _entity_supports_source_query(world, int(eid), query)
                ]
                hit_ids = list(obj_b.candidate_entity_ids)

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
    # Destination selected = a recipient matching the goal dest is chosen
    # *inside the picker*. Open conversation title == dest is not enough
    # (and must not conflate background source-selection chrome).
    dest_row_selected = False
    if picker_only and dest:
        for e in ents:
            if not getattr(e, "visible", True):
                continue
            lab = entity_display_text(e).strip()
            if not lab:
                continue
            if not contact_matches(lab, dest, min_score=0.7):
                continue
            attrs = getattr(e, "attributes", None) or {}
            if bool(attrs.get("selected")) or bool(getattr(e, "selected", False)):
                dest_row_selected = True
                break
    p.destination_selected = bool(picker_only and dest_row_selected)
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
    # WhatsApp exposes the standard macOS find chord for in-conversation search;
    # declaring it (rather than scripting a search) lets locate_content pick the
    # native find realization before falling back to a scroll scan.
    find_affordance = _MACOS_FIND

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

    # Phases in which the source object is still being hunted: an unresolved
    # source binding here is a genuine blocking uncertainty. Once past them
    # (destination picking, done) the source object no longer gates progress.
    _SOURCE_HUNT_PHASES = {"FIND_LINK", "OPEN_FORWARD"}

    def enrich_world_document(self, document: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Tag WhatsApp search filter chips as typed observations (not recovery).

        Core branch fitness only reads ``kind=filter_chip`` / ``restricts``;
        this overlay owns host-specific label recognition.
        """
        doc = dict(document) if isinstance(document, dict) else {}
        objects = [dict(o) for o in (doc.get("objects") or []) if isinstance(o, dict)]
        tagged = False

        def _chip_label(raw: str) -> str:
            return re.sub(r"^[\s•·]+", "", str(raw or "")).strip()

        active_filter = ""
        for obj in objects:
            text = _chip_label(str(obj.get("text") or obj.get("label") or ""))
            token = text.split()[0].lower() if text else ""
            kind = str(obj.get("kind") or "").strip().lower()
            if token in _MEDIA_RESTRICT_FILTERS or text.lower() in _MEDIA_RESTRICT_FILTERS:
                obj["kind"] = "filter_chip"
                obj["restricts"] = "media"
                if text:
                    obj["text"] = text.split()[0] if text.split() else text
                active_filter = active_filter or token
                tagged = True
            elif token in _RESULT_SCOPE_FILTERS or (
                kind in {"chip", "tab", "segment"} and token in _RESULT_SCOPE_FILTERS
            ):
                # Links / Messages / All / Chats are real search-result filters —
                # not conversation chrome. Tag so the critic can refuse a
                # conversation patch while this surface remains active.
                obj["kind"] = "filter_chip"
                obj["restricts"] = "result_scope"
                obj["active_filter"] = token
                if text:
                    obj["text"] = text.split()[0] if text.split() else text
                active_filter = active_filter or token
                tagged = True
            elif kind in {"chip", "tab", "segment"} and token in _RESULT_CHROME:
                # Other result chrome (e.g. media) already handled above; keep
                # typed chip kind for non-scope leftovers without inventing scope.
                if token in _MEDIA_RESTRICT_FILTERS:
                    obj["kind"] = "filter_chip"
                    obj["restricts"] = "media"
                    tagged = True

        open_c = _chip_label(str(doc.get("open_conversation") or ""))
        open_tok = open_c.split()[0].lower() if open_c else ""
        if open_tok in _MEDIA_RESTRICT_FILTERS and not any(
            str(o.get("kind") or "").lower() == "filter_chip" for o in objects
        ):
            objects.insert(
                0,
                {
                    "id": "filter_chip_ax",
                    "kind": "filter_chip",
                    "text": open_c.split()[0] if open_c.split() else open_c,
                    "restricts": "media",
                    "matches_goal": False,
                },
            )
            active_filter = active_filter or open_tok
            tagged = True
        elif open_tok in _RESULT_SCOPE_FILTERS and not any(
            str(o.get("kind") or "").lower() == "filter_chip" for o in objects
        ):
            objects.insert(
                0,
                {
                    "id": "filter_chip_ax",
                    "kind": "filter_chip",
                    "text": open_c.split()[0] if open_c.split() else open_c,
                    "restricts": "result_scope",
                    "active_filter": open_tok,
                    "matches_goal": False,
                },
            )
            active_filter = active_filter or open_tok
            tagged = True

        if tagged or objects != list(doc.get("objects") or []):
            doc["objects"] = objects
        if active_filter:
            doc["active_filter"] = active_filter
            # Filtered Links/Messages results are still search_results scope.
            surf = str(doc.get("surface") or "").strip().lower()
            if surf in {"", "conversation", "search_results", "search"}:
                # Do not upgrade conversation here — critic owns surface authority.
                # Only annotate when already search-like or blank.
                if surf in {"", "search", "search_results"}:
                    doc["primary_surface"] = "search_results"
                    doc["search_scope"] = "filtered" if active_filter else "global"
        return doc

    def affordance_priors(self, surface: str) -> List[Dict[str, Any]]:
        """Latent actions the app knows exist on a surface before any object proves it.

        A declaration, not a code path: the affordance frontier turns these into
        latent actions the model can plan toward, and the core never learns
        WhatsApp's menu tree. The forward picker's Send is the canonical case —
        it only appears once a recipient is chosen, so no object prior on the
        empty picker could know it, yet the model must be able to say it before
        it does. It is irreversible and gated behind resolving the recipient.
        """
        s = str(surface or "").strip().lower()
        if s == "forward_picker":
            return [
                {
                    "id": "picker_send",
                    "label": "Send",
                    "family": "commit_irreversible",
                    "available_after": "resolve_entity",
                    "probability": 0.9,
                    "basis": "the forward picker's Send commits once a recipient is chosen",
                }
            ]
        return []

    def observe_blocking_uncertainties(self, forward_task: Optional[Dict[str, Any]]) -> List[str]:
        """Domain-general blocking uncertainty distilled from the forward task.

        The controller no longer reads WhatsApp phase names or binding shapes to
        decide whether the source object is still being hunted; it asks the
        overlay, which returns a small, app-neutral vocabulary the executive's
        sufficiency judgement consumes. The forward phase machine is thus demoted
        to an overlay *hint*, not a control-flow authority.
        """
        if not isinstance(forward_task, dict) or not forward_task:
            return []
        out: List[str] = []
        preds = forward_task.get("predicates")
        if not isinstance(preds, dict):
            preds = {}
        # Destination picker open but recipient not chosen → executive SEARCH
        # question (live 184742). Distinct from source-object hunt.
        if bool(preds.get("destination_picker_visible")) and not bool(
            preds.get("destination_selected")
        ):
            out.append("destination_contact_unresolved")
        phase = str(forward_task.get("derived_phase") or "").strip().upper()
        if phase in self._SOURCE_HUNT_PHASES:
            bindings = forward_task.get("bindings")
            src = bindings.get("source_object") if isinstance(bindings, dict) else None
            status = (
                str((src or {}).get("status") or "").strip().lower()
                if isinstance(src, dict)
                else ""
            )
            if status in {"unresolved", "ambiguous"}:
                out.append("source_object_unresolved")
        return out

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
        timeline_rows = _conversation_timeline_rows(view)

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
        # Empty-hit + garbled field (live 202832: Pallavipo / No results) must
        # reach compose as search_empty so the dead query is not retyped.
        from plugin.agent.capabilities.compose_search_query import (
            goal_evidence_tokens,
            query_looks_corrupted,
            ui_shows_no_search_results,
        )

        visible_labels = [
            _clean_label(getattr(e, "label", "") or getattr(e, "semantic_role", "") or "")
            for e in ents
            if getattr(e, "visible", True)
        ][:24]
        no_results_chrome = ui_shows_no_search_results(
            view.open_conversation,
            *visible_labels,
            *list(view.visible_contacts or [])[:8],
        )
        evidence_tokens = goal_evidence_tokens(goal)
        field_corrupted = bool(q) and query_looks_corrupted(q, evidence_tokens)
        if not field_corrupted and view.open_conversation:
            field_corrupted = query_looks_corrupted(
                str(view.open_conversation), evidence_tokens
            )
        search_empty = bool(
            no_results_chrome
            or (
                bool(q)
                and bool(view.search_visible or view.search_focused)
                and not search_result_rows
                and not view.visible_contacts
                and not source_contact_rows
            )
            or field_corrupted
        )
        open_c = view.open_conversation or ""
        try:
            from plugin.agent.world_critic import is_search_field_echo
        except Exception:  # pragma: no cover
            is_search_field_echo = lambda _t: False  # type: ignore
        # AX search chrome ("Q Search|") is not an open chat title.
        if open_c and is_search_field_echo(open_c):
            open_c = ""
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
                "search_empty": search_empty,
                "search_field_corrupted": field_corrupted,
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
                "conversation_timeline": timeline_rows[:_conversation_context_window()],
                "conversation_timeline_text": [
                    row.get("text") for row in timeline_rows[:_conversation_context_window()]
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
                "open_repair": dict((world.overlay_hints or {}).get("open_repair") or {}),
                "capture_frame": dict(getattr(world, "last_capture_frame", None) or {}),
                **selected_object_meta,
                "end_call_fail_streak": int((world.overlay_hints or {}).get("end_call_fail_streak") or 0),
            },
        )
        try:
            from plugin.perception.display_topology import build_task_surface

            ts = build_task_surface(
                str(world.active_app or "WhatsApp"),
                capture_frame=getattr(world, "last_capture_frame", None),
            )
            feats.extras["task_surface"] = ts.to_dict()
            world.overlay_hints = dict(world.overlay_hints or {})
            world.overlay_hints["task_surface"] = ts.to_dict()
        except Exception:
            feats.extras["task_surface"] = dict(
                (world.overlay_hints or {}).get("task_surface") or {}
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
            scene_graph = attach_active_cognitive_subgraph(
                scene_graph,
                list(world.entities.values()),
                goal=goal,
                view=view.to_dict() if hasattr(view, "to_dict") else dict(view or {}),
                world_id=str(getattr(world.current_screen, "id", "") or getattr(world.current_screen, "signature", "") or ""),
                cap_graph=cap_graph,
            )
            scene = scene_graph.to_dict()
            feats.extras["capability_graph"] = cap_graph.to_dict()
            feats.extras["goal_capability_types"] = goal_capability_types(goal)
            feats.extras["goal_capability_ids"] = list(cap_graph.goal_capability_ids)
            feats.extras["capability_frontier"] = [node.to_dict() for node in cap_graph.frontier]
            selected = cap_graph.select_for_goal(goal)
            feats.extras["selected_capability"] = "" if selected is None else selected.capability_id
            feats.extras["active_cognitive_subgraph"] = (
                None if scene_graph.active_subgraph is None else scene_graph.active_subgraph.to_dict()
            )
            feats.extras["surface_state"] = (
                None if getattr(scene_graph, "surface_state", None) is None else scene_graph.surface_state.to_dict()
            )
            feats.extras["scene_attention_regions"] = (
                [] if scene_graph.attention is None else list(scene_graph.attention.region_ids)
            )
            feats.extras["scene_attention_entity_ids"] = (
                [] if scene_graph.attention is None else list(scene_graph.attention.entity_ids)
            )
            world.last_capability_graph = cap_graph.to_dict()
            world.last_active_subgraph = {} if scene_graph.active_subgraph is None else scene_graph.active_subgraph.to_dict()
            world.last_surface_state = (
                {} if getattr(scene_graph, "surface_state", None) is None else scene_graph.surface_state.to_dict()
            )
            world.last_scene_graph = scene
        except Exception:
            pass

        try:
            perception_result = build_perception_result(
                world,
                view.to_dict() if hasattr(view, "to_dict") else dict(view or {}),
                feats,
                goal=goal,
            )
            feats.extras["perception_result"] = perception_result.to_dict()
            feats.extras["perception_narrative"] = perception_result.narrative
            feats.extras["perception_summary"] = structured_perception_bridge(
                perception_result.to_dict(),
                features=feats,
                world=world,
            )
            if world.last_perception_synthesis is None:
                world.last_perception_synthesis = {}
            if isinstance(world.last_perception_synthesis, dict):
                world.last_perception_synthesis["structured_perception"] = perception_result.to_dict()
                world.last_perception_synthesis["structured_perception_narrative"] = perception_result.narrative
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
