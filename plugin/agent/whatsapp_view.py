"""WhatsApp semantic overlay — deterministic view over generic WorldModel entities."""

from __future__ import annotations

import re
from functools import lru_cache
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from plugin.worldmodel.entities.entity import Entity
from plugin.worldmodel.entities.normalize import _clean_label
from plugin.worldmodel.model import WorldModel
from plugin.agent.system_signals import detect_system_warning_evidence

# Vision-derived entities are materialised above the AX id range so the two
# perception sources never collide. Kept in sync with unified_cognition's
# _VISION_ENTITY_ID_BASE; the ``source`` marker is the primary signal and the
# id range is the invariant fallback.
_VISION_ENTITY_ID_BASE = 900_000


def is_vision_entity(entity: Any) -> bool:
    """True when an entity was materialised from the perceptor's vision reading.

    Vision entities carry ``attributes["source"] == "vision"`` and live above
    the AX id range. Either signal alone identifies them; checking both keeps
    the predicate robust if one is ever dropped.
    """
    if entity is None:
        return False
    attrs = getattr(entity, "attributes", None)
    if isinstance(attrs, dict) and str(attrs.get("source") or "").strip().lower() == "vision":
        return True
    try:
        return int(getattr(entity, "id", 0) or 0) >= _VISION_ENTITY_ID_BASE
    except (TypeError, ValueError):
        return False

_DIALOG_HINTS = (
    "update available",
    "new version",
    "ok",
    "not now",
    "later",
    "permissions",
    "allow",
    "don't allow",
    "enable notifications",
)

_CHROME_NAMES = {
    "chats",
    "status",
    "calls",
    "settings",
    "new chat",
    "search",
    "file",
    "format",
    "edit",
    "view",
    "window",
    "help",
    "back",
    "updates",
    "archived",
    "starred",
    "search results",
    "list of chats",
    "main navigation",
    "whatsapp",
    "more",
    "clear text",
    "share media",
    "apple",
    "file",
    "edit",
    "chat",
    "call",
    "image",
    "photo",
    "view",
    "window",
    "help",
    "end-to-end encrypted",
}

_GENERIC_HEADER_CHIPS = {
    "all",
    "chats",
    "chat",
    "groups",
    "group",
    "calls",
    "call",
    "status",
    "updates",
    "archived",
    "starred",
    "favorites",
    "favourites",
    "media",
    "links",
    "photos",
    "videos",
    "messages",
    "message",
    "search",
}

_DATE_SEPARATORS = {
    "today",
    "yesterday",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
}

_DATE_FRAGMENT_PATTERNS = (
    # "Fri, 24 Jul", "Friday 24 Jul", "Sat, 30 May"
    r"^(?:mon|tue|wed|thu|fri|sat|sun)(?:day)?[, ]+\d{1,2}\s+[a-z]{3,9}\b",
    # "24 Jul", "30 July"
    r"^\d{1,2}\s+[a-z]{3,9}\b",
    # "Jul 24", "July 24"
    r"^[a-z]{3,9}\s+\d{1,2}\b",
    # Clock fragments that sometimes leak into header text.
    r"^\d{1,2}:\d{2}\s?(?:am|pm)\b",
)

_PREVIEW_MARKERS = (
    "message,",
    "created this group",
    "tap to",
    "voice message",
    "emoji",
    "photo from",
    "video from",
    "unread messages",
    "start video call",
    "start voice call",
    "personal messages are end-to-end",
)

_CALL_STATE_HINTS = {
    "calling",
    "ringing",
    "call in progress",
    "ongoing call",
    "incoming call",
    "connecting",
}

_CALL_WINDOW_HINTS = (
    "whatsapp voice call",
    "whatsapp video call",
    "voice call",
    "video call",
)

_OPEN_CONVERSATION_NOISE_PATTERNS = (
    r"\bmessage from\b",
    r"\breplying to\b",
    r"\bquoted message\b",
    r"\breceived in\b",
    r"\bsent to\b",
    r"\bplayed\b",
    r"\badded \+\b",
    r"\b\d{1,2}:\d{2}\s?(?:am|pm)\b",
    r"\b\d{1,2}\s?(?:am|pm)\b",
    r"\bunread message\b",
    r"\bunread messages\b",
    r"\bnew message\b",
    r"\bnew messages\b",
)

_SYSTEM_WARNING_PATTERNS = (
    r"\bstorage is too full\b",
    r"\bstorage full\b",
    r"\binsufficient storage\b",
    r"\bfree up space\b",
    r"\bout of space\b",
    r"\bdisk full\b",
    r"\bno space left on device\b",
)

_URL_PATTERN = re.compile(
    r"https?://[^\s<>()\"']+",
    re.IGNORECASE,
)


def _attr(e: Entity, *keys: str) -> str:
    for k in keys:
        v = e.attributes.get(k)
        if v is not None and str(v).strip():
            return _clean_label(str(v))
    return ""


def _extract_urls_from_text(*parts: str) -> List[str]:
    urls: List[str] = []
    seen = set()
    for part in parts:
        text = _clean_label(part or "")
        if not text:
            continue
        for raw in _URL_PATTERN.findall(text):
            cleaned = raw.rstrip(").,;:!?]")
            if not cleaned:
                continue
            low = cleaned.lower()
            if low in seen:
                continue
            seen.add(low)
            urls.append(cleaned)
    return urls


def _is_search_mirror(e: Entity) -> bool:
    """AXStaticText/button whose description is Search and title is the query."""
    desc = _attr(e, "description", "AXDescription").lower()
    if desc in {"search", "search or start new chat", "search…"}:
        return True
    return False


@lru_cache(maxsize=1)
def _conversation_context_window() -> int:
    """Max message rows to expose as conversation context."""
    try:
        from hermes_cli.config import load_config_readonly

        cfg = load_config_readonly() or {}
        agent_cfg = cfg.get("agent") if isinstance(cfg.get("agent"), dict) else {}
        raw = agent_cfg.get("conversation_context_window", 100)
        return max(1, min(500, int(raw)))
    except Exception:
        return 100


def _is_contact_name(name: str) -> bool:
    n = _clean_label(name)
    if not n or len(n) > 48:
        return False
    low = n.lower()
    # Sidebar Search chrome ("• Search|", "Q Search|") is never a contact.
    try:
        from plugin.agent.world_critic import is_search_field_echo
    except Exception:  # pragma: no cover
        is_search_field_echo = lambda _t: False  # type: ignore
    if is_search_field_echo(n):
        return False
    if any(re.search(pat, low, re.I) for pat in _SYSTEM_WARNING_PATTERNS):
        return False
    if any(re.search(pat, low, re.I) for pat in _OPEN_CONVERSATION_NOISE_PATTERNS):
        return False
    if low in {"whatsapp", "whatsapp for mac"} or (low.startswith("whatsapp ") and "for mac" in low):
        return False
    if low in _CHROME_NAMES:
        return False
    low_stripped = re.sub(r"^[•·▪●◦q]+\s*", "", low).rstrip("|").strip()
    if low_stripped in _CHROME_NAMES:
        return False
    if any(m in low for m in _PREVIEW_MARKERS):
        return False
    if any(k in low for k in ("unread message", "unread messages", "new message", "new messages")):
        return False
    if low in _DATE_SEPARATORS:
        return False
    if any(re.search(pat, low, re.I) for pat in _DATE_FRAGMENT_PATTERNS):
        return False
    if low.startswith("start ") and "call" in low:
        return False
    if "end-to-end encrypted" in low:
        return False
    if re.fullmatch(r"\d+\s+unread\s+messages?", low) or re.fullmatch(r"\d+\s+messages?", low):
        return False
    if not any(ch.isalpha() for ch in n):
        return False
    digit_count = sum(ch.isdigit() for ch in n)
    alpha_count = sum(ch.isalpha() for ch in n)
    if digit_count >= 3 and alpha_count < max(3, digit_count):
        return False
    return True


def _is_call_state_text(label: str, description: str = "") -> bool:
    """Return True only for explicit call-state chrome, not incidental text."""
    lab = _clean_label(label).lower()
    desc = _clean_label(description).lower()
    for blob in (lab, desc):
        if not blob:
            continue
        if blob in _CALL_STATE_HINTS:
            return True
        if any(blob.startswith(f"{hint} ") for hint in _CALL_STATE_HINTS):
            return True
    return False


def _normalize_open_conversation_text(raw: str) -> str:
    """Extract the chat title from noisy header text.

    Generic rule: prefer a compact contact-like title over duplicated
    timeline/reply text. This keeps open-conversation belief grounded in the
    visible header while ignoring blended list or reply previews.
    """
    text = _clean_label(raw or "")
    if not text:
        return ""
    low = text.lower()
    if _is_contact_name(text) is False and any(
        re.search(pat, low, re.I) for pat in _DATE_FRAGMENT_PATTERNS
    ):
        return ""
    if "messages in chat with" in low:
        parts = re.split(r"messages in chat with", text, flags=re.I)
        candidates: List[str] = []
        prefix = _clean_label(parts[0] if parts else "")
        if _is_contact_name(prefix):
            candidates.append(prefix)
        for part in parts[1:]:
            chunk = _clean_label(part)
            chunk = re.split(r"\s+-\s+|\s+\|\s+|,|:|\n", chunk, maxsplit=1)[0].strip()
            if _is_contact_name(chunk):
                candidates.append(chunk)
        if candidates:
            # Keep the most compact stable title.
            candidates.sort(key=lambda s: (len(_clean_label(s)), s.lower()))
            return candidates[0]
    if _is_contact_name(text):
        return text
    return ""


def _header_conversation_text(e: Entity) -> str:
    """Extract an explicit chat title from a header entity only.

    Keep this narrow: only parse actual header text, not a joined blob of nearby
    timeline rows. That lets nickname-only headers survive without letting list
    rows or reply previews claim the open conversation.
    """
    lab = _clean_label(e.label or "")
    sem = _clean_label(e.semantic_role or "")
    desc = _attr(e, "description", "AXDescription")
    etype = (e.entity_type or "").lower()
    role = _clean_label(getattr(e, "role", "") or "").lower()
    if etype in {"image", "photo"} or role == "aximage":
        return ""
    if _clean_label(lab).lower() in {"image", "photo", "camera"}:
        return ""
    if etype in {"button", "menu", "menubar", "toolbar"}:
        return ""
    from plugin.worldmodel.pragmatic_role import (
        UiPragmaticRole,
        get_pragmatic_role,
        infer_pragmatic_role_stage2,
    )

    if get_pragmatic_role(e) == UiPragmaticRole.UNKNOWN:
        infer_pragmatic_role_stage2(e)
    if any(token in f"{lab} {sem} {desc}".lower() for token in ("voice call", "audio call", "video call", "call", "more options", "info")):
        return ""
    if any(re.search(pat, f"{lab} {sem} {desc}".lower(), re.I) for pat in _DATE_FRAGMENT_PATTERNS):
        return ""
    for source in (lab, sem, desc):
        if not source:
            continue
        low = source.lower()
        if "messages in chat with" in low:
            cleaned = _normalize_open_conversation_text(source)
            if cleaned:
                return cleaned
    if get_pragmatic_role(e) in {
        UiPragmaticRole.NAV_CHROME,
        UiPragmaticRole.CTA,
        UiPragmaticRole.INPUT,
        UiPragmaticRole.DECORATIVE,
    }:
        return ""
    if _is_contact_name(lab):
        if lab.lower() in _GENERIC_HEADER_CHIPS:
            return ""
        return lab
    if _is_contact_name(desc):
        if desc.lower() in _GENERIC_HEADER_CHIPS:
            return ""
        return desc
    return ""


def contact_names_from_entity(
    e: Entity,
    *,
    entities: Optional[Sequence[Entity]] = None,
    scene_graph: Optional[dict] = None,
) -> List[str]:
    """Prefer short AXDescription over long AXTitle message previews."""
    if not e.visible:
        return []
    etype = (e.entity_type or "").lower()
    role = _clean_label(getattr(e, "role", "") or "").lower()
    if etype in {"image", "photo"} or role == "aximage":
        return []
    if etype in {"menu", "menubar"} or role in {"axmenuitem", "axmenubar"}:
        return []
    # Never treat the Electron search-query mirror as a contact row
    if _is_search_mirror(e):
        return []
    lab = _clean_label(e.label or "")
    desc = _attr(e, "description", "AXDescription")
    blob = f"{lab} {desc}".lower()
    is_chat_row_static = (
        e.entity_type == "static"
        and ("messages in chat with" in blob or "sent to" in blob or "received from" in blob)
    )
    if e.entity_type == "static":
        # Conversation rows in WhatsApp Desktop often surface as static text.
        # Keep these if they clearly look like a chat row, but continue to drop
        # generic chrome/status strings.
        if not is_chat_row_static:
            return []
    from plugin.worldmodel.pragmatic_role import (
        UiPragmaticRole,
        get_pragmatic_role,
        infer_pragmatic_role_stage2,
    )

    if get_pragmatic_role(e) == UiPragmaticRole.UNKNOWN:
        infer_pragmatic_role_stage2(e)
    pragmatic_role = get_pragmatic_role(e)
    if pragmatic_role in {
        UiPragmaticRole.CTA,
        UiPragmaticRole.NAV_CHROME,
        UiPragmaticRole.STATUS,
        UiPragmaticRole.INPUT,
        UiPragmaticRole.DECORATIVE,
    } and not is_chat_row_static:
        # Electron/AX often marks result rows as CTA. Keep them if the
        # description itself looks like a contact, because those are still
        # actionable source rows rather than chrome.
        if not (_is_contact_name(desc) or _is_contact_name(lab)):
            return []
    if any(re.search(pat, f"{lab} {desc}".lower(), re.I) for pat in _SYSTEM_WARNING_PATTERNS):
        return []
    out: List[str] = []
    if e.entity_type in {"button", "link", "cell", "unknown"}:
        if scene_graph is not None:
            from plugin.agent.apps.whatsapp_targets import in_sidebar_band

            if not in_sidebar_band(e, list(entities or []), scene_graph=scene_graph):
                return []
        if _is_contact_name(desc):
            out.append(desc)
        if _is_contact_name(lab) and lab.lower() not in {x.lower() for x in out}:
            if any(m in lab.lower() for m in _PREVIEW_MARKERS):
                pass
            else:
                out.append(lab)
    elif is_chat_row_static:
        chat_title = _normalize_open_conversation_text(lab or desc)
        if chat_title and _is_contact_name(chat_title):
            out.append(chat_title)
    return out


def _looks_like_message_row(e: Entity, entities: List[Entity], *, scene_graph: Optional[dict] = None) -> bool:
    from plugin.agent.apps.whatsapp_targets import in_sidebar_band
    from plugin.worldmodel.pragmatic_role import (
        UiPragmaticRole,
        get_pragmatic_role,
        infer_pragmatic_role_stage2,
    )
    if not e.visible:
        return False
    etype = (e.entity_type or "").lower()
    role = _clean_label(getattr(e, "role", "") or "").lower()
    if etype in {"window", "menu", "menubar"} or role in {"axmenuitem", "axmenubar"}:
        return False
    if _is_search_mirror(e):
        return False
    label = _clean_label(e.label or "")
    desc = _attr(e, "description", "AXDescription")
    value = _attr(e, "value", "AXValue")
    blob = f"{label} {desc} {value}".strip()
    low = blob.lower()
    if not blob or any(re.search(pat, low, re.I) for pat in _SYSTEM_WARNING_PATTERNS):
        return False
    region_kind = ""
    if scene_graph:
        for region in scene_graph.get("regions") or []:
            if not isinstance(region, dict):
                continue
            ids = region.get("entity_ids") or []
            if e.id in ids:
                region_kind = str(region.get("kind") or "").lower()
                break
    if region_kind and region_kind not in {"conversation", "timeline", "unknown"}:
        return False
    # No scene region: geometric left-rail chat-list previews ("Voice message",
    # last-message snippets) must not count as the open-conversation timeline.
    # Live 092106 classified the chat list as CONVERSATION off a sidebar
    # "Voice message" row with empty open_conversation — freezing OPEN_SOURCE.
    if not region_kind:
        try:
            if in_sidebar_band(e, list(entities or []), scene_graph=None):
                return False
        except Exception:
            pass
    if get_pragmatic_role(e) == UiPragmaticRole.UNKNOWN:
        infer_pragmatic_role_stage2(e)
    pragmatic_role = get_pragmatic_role(e)
    is_message_content = any(
        tok in low
        for tok in (
            "message",
            "link",
            "photo",
            "video",
            "reply",
            "sent to",
            "received from",
            "http://",
            "https://",
            "your message",
        )
    )
    if pragmatic_role in {
        UiPragmaticRole.CTA,
        UiPragmaticRole.NAV_CHROME,
        UiPragmaticRole.INPUT,
        UiPragmaticRole.DECORATIVE,
    } and not (
        is_message_content and etype in {"link", "static", "cell", "unknown", "button"}
    ):
        return False
    if etype in {"static", "link", "cell", "button", "unknown", "textfield"}:
        if any(tok in low for tok in ("messages in chat with", "sent to", "received from")):
            return True
        if is_message_content and len(blob) >= 3:
            return True
    return False


def conversation_message_rows_from_entities(
    entities: List[Entity],
    *,
    max_messages: Optional[int] = None,
    scene_graph: Optional[dict] = None,
) -> List[Dict[str, Any]]:
    """Return the last N timeline rows that look like in-conversation messages."""
    ents = [e for e in entities if getattr(e, "visible", False)]
    if not ents:
        return []
    window = max_messages if max_messages is not None else _conversation_context_window()
    window = max(1, min(500, int(window)))
    records: List[Dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for e in sorted(
        ents,
        key=lambda ent: (
            float((ent.bounds or (0, 0, 0, 0))[1]) if len(ent.bounds or ()) >= 2 else 0.0,
            float((ent.bounds or (0, 0, 0, 0))[0]) if len(ent.bounds or ()) >= 1 else 0.0,
            int(getattr(ent, "id", 0) or 0),
        ),
    ):
        if not _looks_like_message_row(e, ents, scene_graph=scene_graph):
            continue
        label = _clean_label(e.label or "")
        desc = _attr(e, "description", "AXDescription")
        value = _attr(e, "value", "AXValue")
        text = _clean_label(" ".join(part for part in (label, desc, value) if part))
        if not text:
            continue
        key = (text.lower(), str(getattr(e, "id", "")))
        if key in seen:
            continue
        seen.add(key)
        b = e.bounds or (0, 0, 0, 0)
        records.append(
            {
                "entity_id": int(getattr(e, "id", 0) or 0),
                "label": label,
                "description": desc,
                "value": value,
                "entity_type": e.entity_type,
                "role": e.role,
                "text": text,
                "y": float(b[1]) if len(b) >= 2 else 0.0,
                "x": float(b[0]) if len(b) >= 1 else 0.0,
            }
        )
    if len(records) <= window:
        if records:
            return records
        records = _fallback_message_rows_from_entities(
            entities, max_messages=max_messages, scene_graph=scene_graph
        )
        if len(records) <= window:
            return records
    return records[-window:]


def _fallback_message_rows_from_entities(
    entities: List[Entity],
    *,
    max_messages: Optional[int] = None,
    scene_graph: Optional[dict] = None,
) -> List[Dict[str, Any]]:
    """Best-effort recovery when scene-region or role signals hide chat rows.

    Some WhatsApp desktop surfaces expose real message content as static text or
    link/button hybrids, but the surrounding scene graph can still tag those
    nodes as sidebar/header chrome. When the strict row detector returns
    nothing, fall back to message-shaped text so downstream reasoning still sees
    the timeline instead of an empty prompt.

    When there is no scene graph, skip geometric left-rail previews so a chat
    list cannot be mistaken for an open conversation (live 092106).
    """
    from plugin.agent.apps.whatsapp_targets import in_sidebar_band

    ents = [e for e in entities if getattr(e, "visible", False)]
    if not ents:
        return []
    window = max_messages if max_messages is not None else _conversation_context_window()
    window = max(1, min(500, int(window)))
    records: List[Dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    use_geo_sidebar_filter = not bool(scene_graph and (scene_graph.get("regions") or []))
    for e in sorted(
        ents,
        key=lambda ent: (
            float((ent.bounds or (0, 0, 0, 0))[1]) if len(ent.bounds or ()) >= 2 else 0.0,
            float((ent.bounds or (0, 0, 0, 0))[0]) if len(ent.bounds or ()) >= 1 else 0.0,
            int(getattr(ent, "id", 0) or 0),
        ),
    ):
        etype = (e.entity_type or "").lower()
        if etype not in {"static", "link", "cell", "button", "unknown", "textfield"}:
            continue
        if use_geo_sidebar_filter:
            try:
                if in_sidebar_band(e, ents, scene_graph=None):
                    continue
            except Exception:
                pass
        label = _clean_label(e.label or "")
        desc = _attr(e, "description", "AXDescription")
        value = _attr(e, "value", "AXValue")
        text = _clean_label(" ".join(part for part in (label, desc, value) if part))
        low = text.lower()
        if not text or any(re.search(pat, low, re.I) for pat in _SYSTEM_WARNING_PATTERNS):
            continue
        if _is_search_mirror(e):
            continue
        if not any(
            tok in low
            for tok in (
                "message",
                "link",
                "photo",
                "video",
                "reply",
                "sent to",
                "received from",
                "http://",
                "https://",
                "your message",
            )
        ):
            continue
        key = (text.lower(), str(getattr(e, "id", "")))
        if key in seen:
            continue
        seen.add(key)
        b = e.bounds or (0, 0, 0, 0)
        records.append(
            {
                "entity_id": int(getattr(e, "id", 0) or 0),
                "label": label,
                "description": desc,
                "value": value,
                "entity_type": e.entity_type,
                "role": e.role,
                "text": text,
                "y": float(b[1]) if len(b) >= 2 else 0.0,
                "x": float(b[0]) if len(b) >= 1 else 0.0,
            }
        )
    if len(records) <= window:
        return records
    return records[-window:]


def conversation_timeline_clusters_from_entities(
    entities: List[Entity],
    *,
    max_messages: Optional[int] = None,
    scene_graph: Optional[dict] = None,
) -> List[Dict[str, Any]]:
    """Group visible timeline rows into compact message clusters.

    The raw message rows remain available for binding and diagnostics, but the
    clustered timeline is the payload we want to hand to downstream reasoning:
    it carries visible text and URLs without dragging in unrelated chrome.
    """
    rows = conversation_message_rows_from_entities(
        entities,
        max_messages=max_messages,
        scene_graph=scene_graph,
    )
    if not rows:
        rows = _fallback_message_rows_from_entities(
            entities, max_messages=max_messages, scene_graph=scene_graph
        )
    if not rows:
        return []

    sorted_rows = sorted(
        rows,
        key=lambda row: (
            float(row.get("y") or 0.0),
            float(row.get("x") or 0.0),
            int(row.get("entity_id") or 0),
        ),
    )
    clusters: List[Dict[str, Any]] = []
    current: Dict[str, Any] = {}
    gap_threshold = 84.0

    def _flush_cluster() -> None:
        nonlocal current
        if not current:
            return
        texts = [str(x) for x in current.get("texts") or [] if str(x).strip()]
        urls = list(dict.fromkeys([str(x) for x in current.get("urls") or [] if str(x).strip()]))
        message_ids = [int(x) for x in current.get("message_ids") or [] if str(x).strip()]
        joined_text = _clean_label(" ".join(texts))
        clusters.append(
            {
                "message_ids": message_ids,
                "entity_ids": list(message_ids),
                "row_count": len(message_ids),
                "texts": texts,
                "text": joined_text,
                "urls": urls,
                "top_y": float(current.get("top_y") or 0.0),
                "bottom_y": float(current.get("bottom_y") or 0.0),
                "x": float(current.get("x") or 0.0),
                "kind": "message_cluster",
            }
        )
        current = {}

    for row in sorted_rows:
        row_y = float(row.get("y") or 0.0)
        row_x = float(row.get("x") or 0.0)
        row_text = _clean_label(row.get("text") or row.get("label") or row.get("description") or "")
        row_urls = _extract_urls_from_text(
            row.get("text") or "",
            row.get("label") or "",
            row.get("description") or "",
            row.get("value") or "",
        )
        if not row_text and not row_urls:
            continue
        if current and row_y - float(current.get("bottom_y") or 0.0) > gap_threshold:
            _flush_cluster()
        if not current:
            current = {
                "message_ids": [],
                "texts": [],
                "urls": [],
                "top_y": row_y,
                "bottom_y": row_y,
                "x": row_x,
            }
        current["message_ids"].append(int(row.get("entity_id") or 0))
        if row_text:
            current["texts"].append(row_text)
        for url in row_urls:
            if url.lower() not in {u.lower() for u in current["urls"]}:
                current["urls"].append(url)
        current["top_y"] = min(float(current.get("top_y") or row_y), row_y)
        current["bottom_y"] = max(float(current.get("bottom_y") or row_y), row_y)
        current["x"] = min(float(current.get("x") or row_x), row_x)
    _flush_cluster()
    return clusters


def _name_match_score(candidate: str, needle: str) -> float:
    """Score how well a contact label matches the requested name (0..1)."""
    c = _clean_label(candidate).lower()
    n = _clean_label(needle).lower()
    if not c or not n:
        return 0.0
    if c == n:
        return 1.0
    tokens = [t for t in n.split() if t]
    c_tokens = [t.strip(",.<>()") for t in c.replace(",", " ").split() if t.strip(",.<>()")]
    if tokens and all(t in c_tokens for t in tokens):
        # All query tokens appear as whole tokens (works for chat headers too)
        if len(tokens) == len(c_tokens):
            return 0.95
        return 0.88
    if tokens and all(t in c for t in tokens):
        return 0.72
    if c.startswith(n + " ") or c.startswith(n + ",") or c.startswith(n + "<"):
        return 0.75
    if n in c and len(c) <= len(n) + 24:
        return 0.55
    if len(n) >= 4 and n in c:
        return 0.35
    return 0.0


def contact_matches(haystack: str, needle: str, *, min_score: float = 0.75) -> bool:
    return _name_match_score(haystack or "", needle or "") >= min_score


def _content_words(text: str) -> List[str]:
    """Words in ``text``, minus the single characters OCR makes out of icons.

    The magnifier glyph beside the search field has no text, so the reader
    renders it as whatever letter it resembles -- 'Q', 'a' and 'cK' have all
    been seen on this one field. That stray token adds a word, which is enough
    to make a title that is purely an echo of the query look like a two-word
    chat name and slip past a word-count comparison: a live run reached the
    forward phase believing the open chat was 'Q Kulvinder'. No WhatsApp
    contact is addressed by a single letter, so dropping them costs nothing.
    """
    return [w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(w) > 1]


def _echoes_search_query(title: str, query: str) -> bool:
    """Is this supposed chat title just the search box reading itself back?

    An echo is the typed string itself, so it carries the same word count; the
    OCR damage seen live lands inside a word rather than adding one
    ('Kulvinderr', 'Kulvinder]', 'Kulvinderng' against a typed 'Kulvinder').
    A real chat title that merely starts the same way adds a word -- and the
    case that matters is 'Kulvinder Ji', the actual target of this task, which a
    plain prefix test would erase the moment the chat finally opened. So compare
    word counts first, then prefix-match the stems for the OCR slack.
    """
    title_words = _content_words(title)
    query_words = _content_words(query)
    if not title_words or not query_words:
        return False
    # The search field's own placeholder, with the query not yet typed or not
    # yet read. It is the field, so it is never a chat, whatever the query is.
    if title_words == ["search"]:
        return True
    if len(title_words) != len(query_words):
        return False
    if sum(len(w) for w in query_words) < 4:
        return False
    # Word by word rather than on the concatenation. OCR damage lands *inside* a
    # word ('zaroratwala' for 'zarooratwala'), and a joined stem carries that
    # divergence into every character after it, so a comparison on the whole
    # string stops matching at the first damaged letter and the echo is missed.
    return all(_same_word(a, b) for a, b in zip(title_words, query_words))


def _same_word(read: str, typed: str) -> bool:
    """One OCR-damaged word against the word that was actually typed.

    Kept loose on purpose: this only ever compares a candidate chat title
    against the query the agent typed a moment earlier, position for position,
    so the alternative to a near match is not a different contact but the same
    string misread. Exact, either-way prefix, or one edit of any kind — the
    damage seen live includes a dropped letter ('zaroratwala') as well as a
    substituted one, and a same-length test only catches the second.
    """
    if read == typed:
        return True
    shorter, longer = sorted((read, typed), key=len)
    if len(shorter) >= 4 and longer.startswith(shorter):
        return True
    return len(longer) - len(shorter) <= 1 and _within_one_edit(shorter, longer)


def _within_one_edit(shorter: str, longer: str) -> bool:
    """One substitution, insertion or deletion apart, at most."""
    if len(shorter) == len(longer):
        return sum(1 for a, b in zip(shorter, longer) if a != b) <= 1
    for i, (a, b) in enumerate(zip(shorter, longer)):
        if a != b:
            return shorter[i:] == longer[i + 1 :]
    return True


def resolve_contact_entity(
    world: WorldModel,
    contact: str,
    *,
    require_clear_winner: bool = True,
    clear_margin: float = 0.12,
) -> Optional[Entity]:
    """Pick best clickable entity via Reference Resolver confidence policy."""
    from plugin.agent.resolver import get_reference_resolver

    _ = clear_margin  # legacy API; confidence policy replaces margin thresholds
    res = get_reference_resolver().resolve(world, contact)
    if res.winner is not None:
        return res.winner
    if not require_clear_winner and res.candidates:
        # Soft: return top entity even in observe/ask (callers that opt in)
        ent = res.candidates[0].entity
        if ent is not None:
            return ent
        eid = res.candidates[0].entity_id
        return None if eid is None else world.entities.get(eid)
    return None


def rank_contact_candidates(
    world: WorldModel,
    contact: str,
    *,
    min_score: float = 0.35,
    limit: int = 8,
) -> List[Dict[str, Any]]:
    """Rank clickable contact rows — confidence-based (compat shape)."""
    from plugin.agent.resolver import get_reference_resolver

    res = get_reference_resolver().resolve(world, contact, limit=limit)
    out: List[Dict[str, Any]] = []
    for c in res.candidates:
        if c.confidence < min_score and c.name_similarity < min_score:
            continue
        y = 0.0
        if c.entity is not None and c.entity.bounds and len(c.entity.bounds) >= 2:
            y = float(c.entity.bounds[1])
        out.append(
            {
                "name": c.name,
                "entity_id": c.entity_id,
                "score": round(c.confidence, 3),
                "name_similarity": round(c.name_similarity, 3),
                "y": y,
                "label": None if c.entity is None else c.entity.label,
                "description": None
                if c.entity is None
                else _attr(c.entity, "description"),
            }
        )
    return out[:limit]


@dataclass
class WhatsAppWorldView:
    app_active: bool = False
    screen: str = "UNKNOWN"  # LIST | SEARCH | SEARCH_RESULTS | CONVERSATION | CALLING | DIALOG | UNKNOWN
    search_visible: bool = False
    search_focused: bool = False
    search_query: str = ""
    window_name: str = ""
    visible_contacts: List[str] = field(default_factory=list)
    conversation_messages: List[Dict[str, Any]] = field(default_factory=list)
    conversation_timeline: List[Dict[str, Any]] = field(default_factory=list)
    open_conversation: Optional[str] = None
    voice_call_available: bool = False
    call_state: Optional[str] = None  # ringing | idle | None
    composer_visible: bool = False
    unexpected_dialogs: List[str] = field(default_factory=list)
    system_warnings: List[str] = field(default_factory=list)
    blocking_overlay: bool = False
    focused_entity_id: Optional[int] = None
    world_signature: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_world_model_raw(
        cls,
        world: WorldModel,
        *,
        search_query_hint: str = "",
    ) -> "WhatsAppWorldView":
        app_active = "whatsapp" in _clean_label(world.active_app).lower()
        window_name = _clean_label(getattr(world, "last_window_name", "") or "")
        # Vision-materialised entities are the perceptor's reading, not AX nodes.
        # They must never run through the label/geometry heuristics below (which
        # would, e.g., mistake a message body for a conversation header); the
        # synthesized ``from_world_model`` folds them in through the reading.
        visible_entities = [
            e for e in world.entities.values() if e.visible and not is_vision_entity(e)
        ]
        scene_graph = getattr(world, "last_scene_graph", None) or {}
        scene_region_kinds = {
            str(r.get("kind") or "").lower()
            for r in (scene_graph.get("regions") or [])
            if isinstance(r, dict)
        }
        search_visible = False
        search_focused = False
        search_query = ""
        focused_id: Optional[int] = None
        composer_visible = False
        voice_call_available = False
        call_state: Optional[str] = None
        call_state_hint = False
        maybe_end_call_hint = False
        call_window_visible = bool(window_name) and any(
            hint in window_name.lower() for hint in _CALL_WINDOW_HINTS
        )
        open_conversation: Optional[str] = None
        contacts: List[str] = []
        dialogs: List[str] = []
        system_warning_evidence: List[str] = []

        for e in visible_entities:
            lab = _clean_label(e.label or "")
            sem = _clean_label(e.semantic_role or "")
            desc = _attr(e, "description", "AXDescription")
            placeholder = _attr(e, "placeholder", "AXPlaceholderValue", "placeholder_value")
            value = _attr(e, "value", "AXValue")
            blob = f"{lab} {sem} {desc} {placeholder} {value}".lower()
            et = e.entity_type
            focused = bool(e.attributes.get("focused") or e.attributes.get("AXFocused"))
            role_l = (e.role or "").lower()

            is_search_field = et == "textfield" and (
                "search" in blob or "search" in role_l or "searchfield" in role_l
            )
            # Electron: AXStaticText title=query, description=Search
            is_search_mirror = (
                et in {"static", "button"}
                and desc.lower() in {"search", "search or start new chat", "search…"}
                and lab
                and lab.lower() not in {"search", "search results"}
                and len(lab) < 80
            )
            if is_search_field:
                search_visible = True
                if focused:
                    search_focused = True
                    focused_id = e.id
                if value and "compose" not in blob and len(value) < 80:
                    search_query = value
                elif (
                    lab
                    and lab.lower() not in {"search", "search or start new chat"}
                    and "search" in f"{sem} {desc}".lower()
                ):
                    if lab.lower() != "search":
                        search_query = search_query or lab
            if is_search_mirror:
                search_visible = True
                search_query = search_query or lab
                if focused:
                    search_focused = True
                    focused_id = e.id

            if et in {"button", "static"} and lab.lower() == "search":
                search_visible = True

            if "compose" in blob or "type a message" in blob:
                composer_visible = True

            # Call chrome: gated by pragmatic role + geometry
            from plugin.worldmodel.pragmatic_role import (
                UiPragmaticRole,
                get_pragmatic_role,
                infer_pragmatic_role_stage2,
                is_active_call_evidence,
            )

            if get_pragmatic_role(e) == UiPragmaticRole.UNKNOWN:
                infer_pragmatic_role_stage2(e)
            role = get_pragmatic_role(e)
            lab_l = lab.lower()
            desc_l = desc.lower()
            b = e.bounds or (0, 0, 0, 0)
            area = max(0.0, float(b[2])) * max(0.0, float(b[3])) if len(b) >= 4 else 0.0
            has_geom = area >= 16.0

            if role == UiPragmaticRole.NAV_CHROME:
                pass  # Calls/Chats tabs are never active-call or start_call
            elif lab_l in {"voice message", "send voice message"} or desc_l in {
                "voice message",
                "send voice message",
            }:
                pass  # composer mic — never voice_call_available
            elif (
                role == UiPragmaticRole.CTA
                and et == "button"
                and lab_l in {"voice", "voice call", "audio call"}
                and has_geom
            ):
                voice_call_available = True
            elif (
                role == UiPragmaticRole.CTA
                and et == "button"
                and lab_l in {"call", "phone"}
                and "end" not in lab_l
                and has_geom
            ):
                voice_call_available = True
            elif "open call dropdown" in blob and has_geom and role != UiPragmaticRole.NAV_CHROME:
                voice_call_available = True

            if is_active_call_evidence(e):
                if lab_l in {"end call", "decline"} or "end call" in blob:
                    maybe_end_call_hint = True
                else:
                    call_state_hint = True

            for name in contact_names_from_entity(
                e,
                entities=visible_entities,
                scene_graph=getattr(world, "last_scene_graph", None) or {},
            ):
                contacts.append(name)

            if open_conversation is None:
                from plugin.agent.apps.whatsapp_targets import in_header_band, in_sidebar_band

                header_text = _header_conversation_text(e)
                explicit_header = "messages in chat with" in f"{lab} {sem} {desc}".lower()
                if header_text:
                    if explicit_header:
                        open_conversation = header_text
                    elif in_header_band(
                        e,
                        visible_entities,
                        scene_graph=getattr(world, "last_scene_graph", None) or {},
                    ):
                        open_conversation = header_text
                    elif in_sidebar_band(
                        e,
                        visible_entities,
                        scene_graph=getattr(world, "last_scene_graph", None) or {},
                    ):
                        pass

            for hint in _DIALOG_HINTS:
                if hint in blob and et in {"button", "static", "dialog", "window", "unknown"}:
                    if hint in {"ok", "allow", "later", "not now"} and len(lab) < 24:
                        b = e.bounds or (0, 0, 0, 0)
                        area = max(0.0, float(b[2])) * max(0.0, float(b[3])) if len(b) >= 4 else 0.0
                        if area >= 16.0 or et == "button":
                            dialogs.append(lab or hint)
            if detect_system_warning_evidence(blob):
                system_warning_evidence.append(lab or desc or blob)

        open_conversation = _normalize_open_conversation_text(open_conversation or "")
        if open_conversation:
            open_l = open_conversation.lower()
            window_l = window_name.lower()
            if open_l == window_l or "whatsapp" in open_l and open_l in {"whatsapp", "whatsapp for mac"}:
                open_conversation = ""
        # AX sidebar Search ("• Search|") is never an open chat title.
        try:
            from plugin.agent.world_critic import is_search_field_echo
        except Exception:  # pragma: no cover
            is_search_field_echo = lambda _t: False  # type: ignore
        if open_conversation and is_search_field_echo(open_conversation):
            open_conversation = ""
        # Against the remembered query, not only this frame's. Recognising the
        # field's text masquerading as a chat title requires knowing what was
        # typed, and the frames where that confusion happens are exactly the
        # frames where the query was consumed as the title and so cannot be
        # read here: a run reached the forward phase believing the open chat
        # was 'Q zarooratwala Kulvinder' with search_query empty beside it.
        #
        # Not on a conversation surface, though. Searching a contact by name
        # and opening them leaves a chat whose title is the query, character
        # for character -- the ordinary case, not a misread -- so a string test
        # cannot separate the two and the surface has to. A composer on screen
        # means a chat is genuinely open; erasing it there cost the voice-call
        # path its success and left it re-opening the same contact until the
        # step budget ran out.
        if search_query:
            world.last_search_query = search_query
        remembered_query = search_query or str(getattr(world, "last_search_query", "") or "")
        if (
            open_conversation
            and not composer_visible
            and _echoes_search_query(open_conversation, remembered_query)
        ):
            # The search field lives in the header band, so on this app its text
            # is a header static node like any other and gets read as the chat
            # title -- except the title it yields is the query the agent typed a
            # moment ago, echoed back. Three live runs believed the open chat was
            # 'Kulvinderr', 'Kulvinder]' and 'Kulvinderng': OCR readings of their
            # own query. Each confirmed source_conversation at 0.95 off it, jumped
            # the phase past the step that actually opens the chat, and then hunted
            # a forward affordance on a search screen until the clock ran out.
            open_conversation = ""
        if system_warning_evidence:
            system_warning_evidence = list(dict.fromkeys(system_warning_evidence))
        # Keep open_conversation conservative: only an explicit header marker
        # should claim that a chat is open. Generic contact rows remain list
        # evidence and are not promoted to header context.

        # Storage pressure and other warnings should be surfaced as recovery
        # signals, not treated as a generic modal unless the scene actually
        # looks modal/floating. This prevents a timeline warning row from
        # collapsing the whole screen into a false DIALOG state.
        blocking_overlay = bool(system_warning_evidence and scene_region_kinds & {"modal", "floating_menu"})

        # voice_call_available only if exact call chrome sits in the header band
        if voice_call_available:
            vis = [e for e in visible_entities if len(e.bounds or ()) >= 4]
            ys = [float(e.bounds[1]) for e in vis if float(e.bounds[3]) > 0]
            bottoms = [
                float(e.bounds[1]) + float(e.bounds[3])
                for e in vis
                if float(e.bounds[3]) > 0
            ]
            if ys and bottoms:
                y0, H = min(ys), max(bottoms) - min(ys)
                header_cut = y0 + 0.18 * max(H, 1.0)
                composer_cut = y0 + 0.72 * max(H, 1.0)
                still = False
                for e in vis:
                    lab_l = _clean_label(e.label or "").lower()
                    desc_l = _attr(e, "description", "AXDescription").lower()
                    blob = f"{lab_l} {desc_l}"
                    cy = float(e.bounds[1]) + float(e.bounds[3]) / 2.0
                    if cy >= composer_cut:
                        continue
                    if lab_l in {"voice message", "send voice message"}:
                        continue
                    if lab_l in {"voice", "voice call", "audio call", "call", "phone"} and cy <= header_cut:
                        still = True
                        break
                    if "open call dropdown" in blob:
                        still = True
                        break
                voice_call_available = still

        hint = _clean_label(search_query_hint)
        if hint and not search_query:
            search_query = hint
            search_visible = True
        if search_query:
            world.last_search_query = search_query

        has_search_field = any(
            e.visible
            and e.entity_type == "textfield"
            and "search"
            in f"{e.label} {e.semantic_role} {_attr(e, 'description')} {_attr(e, 'placeholder')}".lower()
            for e in world.entities.values()
        ) or bool(search_query)
        has_chat_list = any(
            e.visible and "list of chats" in f"{e.label} {e.semantic_role}".lower()
            for e in world.entities.values()
        ) or any(
            e.visible and _clean_label(e.semantic_role or "").lower() == "chats"
            for e in world.entities.values()
        )
        has_layout_context = bool(scene_region_kinds & {"sidebar", "navigation", "timeline", "header", "toolbar"})
        has_list_context = has_search_field or has_chat_list or search_visible or search_query or has_layout_context
        # Explicit active-call evidence should win over list chrome, but only
        # when it is backed by a real call surface signal. This keeps stale
        # "ringing" / "calling" text from a previous state from turning a
        # contact-info dialog or chat list into a phantom call screen.
        has_call_surface = bool(call_window_visible or maybe_end_call_hint)
        if call_state_hint and (has_call_surface or not has_list_context):
            call_state = "ringing"
            voice_call_available = False
        elif maybe_end_call_hint and not has_list_context:
            call_state = "ringing"

        window_l = window_name.lower()
        call_window_visible = call_window_visible or (bool(window_l) and any(hint in window_l for hint in _CALL_WINDOW_HINTS))
        if call_window_visible:
            call_state = "ringing"

        # Build conversation evidence before screen classification. On WA Mac the
        # sidebar Search field stays visible while a chat is open; preferring
        # SEARCH over that evidence made AX settle report LIST/Search forever
        # and poisoned executive belief (screenshot VLM is SoT).
        conversation_messages = conversation_message_rows_from_entities(
            visible_entities,
            max_messages=_conversation_context_window(),
            scene_graph=scene_graph,
        )
        conversation_timeline = conversation_timeline_clusters_from_entities(
            visible_entities,
            max_messages=_conversation_context_window(),
            scene_graph=scene_graph,
        )
        def _is_placeholder_timeline(items: Any) -> bool:
            """E2E-encryption / empty-pane notices are not a real conversation."""
            if not items:
                return True
            blob = " ".join(str(x) for x in items[:6]).lower()
            markers = (
                "end-to-end encrypted",
                "end to end encrypted",
                "messages and calls are",
                "whatsapp for mac",
            )
            return any(m in blob for m in markers) and not open_conversation

        timeline_is_placeholder = _is_placeholder_timeline(conversation_timeline)
        messages_are_placeholder = _is_placeholder_timeline(conversation_messages)
        real_conversation_body = bool(
            (conversation_messages and not messages_are_placeholder)
            or (conversation_timeline and not timeline_is_placeholder)
        )
        conversation_evidence = bool(
            composer_visible
            or open_conversation
            or real_conversation_body
        )

        screen = "UNKNOWN"
        if call_state == "ringing":
            screen = "CALLING"
        elif dialogs and not composer_visible and not search_query and (
            blocking_overlay or not has_list_context
        ):
            screen = "DIALOG"
        elif search_query or (search_focused and not conversation_evidence):
            # Active typed query / focused empty search without chat evidence.
            screen = "SEARCH_RESULTS" if (search_query or contacts) else "SEARCH"
        elif conversation_evidence:
            # Idle sidebar Search chrome coexists with an open chat on WA Mac —
            # do not prefer SEARCH over header/messages/composer (screenshot SoT).
            screen = "CONVERSATION"
        elif has_search_field and search_visible:
            screen = "SEARCH"
        elif contacts or has_chat_list or has_layout_context:
            screen = "LIST"
        elif search_visible:
            screen = "LIST"
        # Chat-list + empty right pane ("WhatsApp for Mac") is LIST, not a
        # conversation — even if an E2E notice looks message-shaped.
        if (
            screen == "CONVERSATION"
            and not composer_visible
            and not open_conversation
            and (has_chat_list or has_search_field or bool(contacts))
            and not real_conversation_body
        ):
            screen = "LIST"
        if timeline_is_placeholder:
            conversation_timeline = []
        if messages_are_placeholder:
            conversation_messages = []
        if blocking_overlay and screen not in {"CALLING"}:
            screen = "DIALOG"

        seen = set()
        uniq: List[str] = []
        for c in contacts:
            k = c.lower()
            if k not in seen:
                seen.add(k)
                uniq.append(c)

        sig_parts = [
            screen,
            search_query,
            ",".join(uniq[:12]),
            open_conversation or "",
            window_name,
            call_state or "",
            str(composer_visible),
            str(voice_call_available),
            "|".join(dialogs[:4]),
        ]
        world_signature = "||".join(sig_parts)

        return cls(
            app_active=app_active,
            screen=screen,
            search_visible=search_visible or bool(search_query),
            search_focused=search_focused or bool(search_query),
            search_query=search_query,
            window_name=window_name,
            visible_contacts=uniq,
            conversation_messages=conversation_messages,
            conversation_timeline=conversation_timeline,
            open_conversation=open_conversation,
            voice_call_available=voice_call_available,
            call_state=call_state,
            composer_visible=composer_visible,
            unexpected_dialogs=list(dict.fromkeys(dialogs)),
            system_warnings=system_warning_evidence,
            blocking_overlay=blocking_overlay,
            focused_entity_id=focused_id,
            world_signature=world_signature,
        )

    @classmethod
    def from_world_model(
        cls,
        world: WorldModel,
        *,
        search_query_hint: str = "",
    ) -> "WhatsAppWorldView":
        """Return the interpreted WA view.

        The raw AX view is still available via ``from_world_model_raw`` for
        prompt construction. This method optionally folds in the latest cached
        perception synthesis so downstream callers use the smarter interpretation
        instead of re-deriving meaning from labels.
        """
        view = cls.from_world_model_raw(world, search_query_hint=search_query_hint)
        summary = getattr(world, "last_perception_synthesis", None) or {}
        raw = summary.get("summary") if isinstance(summary, dict) else None
        if isinstance(raw, dict):
            screen_type = _clean_label(str(raw.get("screen_type") or "")).lower()
            active_surface = _clean_label(str(raw.get("active_surface") or "")).lower()
            likely_family = _clean_label(str(raw.get("likely_next_family") or "")).lower()
            likely_target = _clean_label(str(raw.get("likely_next_target") or "")).strip()
            if screen_type:
                if screen_type in {"list", "search", "conversation", "dialog", "call_picker"}:
                    if screen_type == "call_picker" and view.screen not in {"CALLING", "DIALOG"}:
                        view.screen = "DIALOG"
                    elif screen_type == "search":
                        view.screen = "SEARCH_RESULTS" if view.visible_contacts else "SEARCH"
                    elif screen_type == "conversation" and (
                        view.composer_visible
                        or raw.get("open_conversation")
                        or raw.get("visible_objects")
                    ):
                        # The reading is authoritative for the conversation
                        # surface. On apps whose AX tree is window chrome only
                        # (WhatsApp) there is no composer entity to key off, so
                        # the perceptor's open_conversation / visible messages are
                        # the only evidence — and they are enough.
                        view.screen = "CONVERSATION"
                    elif screen_type == "dialog":
                        # Do not let a weak synthesized dialog override a strong
                        # raw conversation/composer state unless we actually have
                        # overlay evidence or a genuinely empty, modal-looking
                        # surface. This keeps ordinary chat content from
                        # collapsing into a false preclear branch.
                        if view.blocking_overlay or (
                            view.unexpected_dialogs
                            and not (view.composer_visible or view.open_conversation)
                            and not (view.visible_contacts or view.search_visible or view.search_query)
                        ):
                            view.screen = "DIALOG"
                    elif screen_type == "list" and view.screen == "UNKNOWN":
                        view.screen = "LIST"
            if active_surface == "call_picker":
                view.voice_call_available = True
            if likely_family in {"open_search", "type_query"} and view.search_visible:
                view.search_focused = True
            # The recommendation is deliberately NOT folded into the open-chat
            # belief here. likely_next_target names the chat the perceptor wants
            # to open; treating it as the chat that *is* open turns an intention
            # into an accomplished state, and the screen_type guard let it happen
            # on the search surface, which is exactly where the target is only
            # ever a proposal. Live runs then confirmed source_conversation at
            # 0.95 off a search-result row the agent had not clicked, skipped the
            # open step, and hunted a forward affordance that was not on screen:
            # 31 iterations believing the open chat was 'Cmd+F search shortcut'
            # in one run, 10 believing it was an OCR misread in another. What the
            # perceptor actually observed is read below, from open_conversation.

            # The reading names the open conversation directly and lists the
            # messages it saw. Fold both in — this is the vision bridge that lets
            # a chrome-only AX tree still see which chat is open and what it holds.
            syn_open = _clean_label(str(raw.get("open_conversation") or "")).strip()
            if syn_open and _is_contact_name(syn_open):
                view.open_conversation = syn_open
            syn_objects = raw.get("visible_objects")
            if isinstance(syn_objects, list) and syn_objects and not view.conversation_messages:
                rows: List[Dict[str, Any]] = []
                for obj in syn_objects:
                    if not isinstance(obj, dict):
                        continue
                    text = str(obj.get("text") or obj.get("label") or "").strip()
                    if not text:
                        continue
                    rows.append({"text": text, "matches_goal": bool(obj.get("matches_goal"))})
                if rows:
                    view.conversation_messages = rows
        if view.open_conversation and not _is_contact_name(view.open_conversation):
            view.open_conversation = None
        # The same echo has to be caught again here, not only in the raw view:
        # the perceptor reports an open_conversation of its own and it is applied
        # above, so a model that reads the search box as a chat header reinstates
        # exactly the belief the raw guard just cleared. It does -- a live run
        # reached OPEN_FORWARD with open_conversation='Kulvinder', the query it
        # had typed one action earlier and had not yet clicked a result for.
        if (
            view.open_conversation
            and view.screen != "CONVERSATION"
            and not view.composer_visible
            and _echoes_search_query(
                view.open_conversation,
                view.search_query or str(getattr(world, "last_search_query", "") or ""),
            )
        ):
            view.open_conversation = None
        return view


def entities_matching(world: WorldModel, needle: str, *, limit: int = 20) -> List[Dict[str, Any]]:
    """Debug helper: entities whose label/desc/value contain needle."""
    n = _clean_label(needle).lower()
    hits: List[Dict[str, Any]] = []
    if not n:
        return hits
    for e in world.entities.values():
        if not e.visible:
            continue
        desc = _attr(e, "description")
        val = _attr(e, "value")
        blob = f"{e.label} {e.semantic_role} {desc} {val}".lower()
        if n in blob:
            hits.append(
                {
                    "id": e.id,
                    "type": e.entity_type,
                    "label": e.label,
                    "semantic": e.semantic_role,
                    "description": desc,
                    "value": val,
                }
            )
            if len(hits) >= limit:
                break
    return hits
