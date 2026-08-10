"""WhatsApp / messaging-UI evidence adapter.

Owns row/preview structure, AX+vision display-name inference, and
host-aware content matching. The generic IdentityResolver never sees
"chat row" or "contact-name extraction" — only typed IdentityEvidence.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from plugin.agent.role_binding import (
    EntityObservation,
    IdentityEvidence,
    register_evidence_provider,
)


_WHATSAPP_KINDS = {
    "chat_row",
    "conversation_row",
    "conversation",
    "chat",
    "search_result_row",
    "picker_row",
    "message",
    "message_bubble",
    "message_with_link",
    "link",
}


class WhatsAppUIEvidenceProvider:
    """Emit identity vs content evidence from WhatsApp-like UI candidates."""

    name = "whatsapp_ui"

    def can_handle(self, candidate: Dict[str, Any]) -> bool:
        if candidate.get("identity_evidence") or candidate.get("content_evidence"):
            # Already typed — leave to passthrough.
            return False
        if str(candidate.get("domain") or candidate.get("app") or "").lower() in {
            "whatsapp",
            "wa",
            "messaging",
        }:
            return True
        kind = str(
            candidate.get("entity_kind")
            or candidate.get("object_type")
            or candidate.get("kind")
            or candidate.get("type")
            or ""
        ).strip().lower()
        if kind in _WHATSAPP_KINDS:
            return True
        # Heuristic: flattened "Name - You: preview" / URL-in-label list rows.
        label = str(candidate.get("label") or candidate.get("text") or "")
        if " - " in label and (
            "http://" in label.lower()
            or "https://" in label.lower()
            or "you:" in label.lower()
        ):
            return True
        return False

    def observe(self, candidate: Dict[str, Any]) -> EntityObservation:
        eid = str(
            candidate.get("id")
            or candidate.get("entity_id")
            or candidate.get("object_id")
            or ""
        )
        raw_kind = str(
            candidate.get("entity_kind")
            or candidate.get("object_type")
            or candidate.get("kind")
            or candidate.get("type")
            or ""
        ).strip().lower()
        label = str(
            candidate.get("label")
            or candidate.get("title")
            or candidate.get("name")
            or candidate.get("text")
            or ""
        ).strip()

        # Map UI kinds → abstract entity kinds for the generic binder.
        if raw_kind in {
            "chat_row",
            "conversation_row",
            "chat",
            "search_result_row",
            "picker_row",
            "conversation",
        }:
            entity_kind = "conversation"
        elif raw_kind in {"message", "message_bubble", "message_with_link"}:
            entity_kind = "message" if "link" not in raw_kind else "link"
        elif raw_kind == "link":
            entity_kind = "link"
        else:
            entity_kind = raw_kind or "conversation"

        identity: List[IdentityEvidence] = []
        content: List[IdentityEvidence] = []
        text = str(candidate.get("text") or "")
        is_content_entity = entity_kind in {"message", "link", "content_item"}

        if is_content_entity:
            # Message/link bodies are content evidence — never conversation identity.
            body = text or label
            if body:
                content.append(
                    IdentityEvidence(
                        kind="content_text",
                        value=body,
                        subject=eid,
                        identity_bearing=False,
                        provenance="whatsapp_message",
                    )
                )
            display_name, preview = "", ""
        else:
            display_name, preview = _split_display_and_preview(label)
            if display_name:
                identity.append(
                    IdentityEvidence(
                        kind="display_name",
                        value=display_name,
                        subject=eid,
                        confidence=0.96,
                        provenance="whatsapp_ax+vision",
                    )
                )
            if preview:
                content.append(
                    IdentityEvidence(
                        kind="preview_text",
                        value=preview,
                        subject=eid,
                        identity_bearing=False,
                        provenance="whatsapp_row_preview",
                    )
                )
            if text and text.strip() != display_name:
                content.append(
                    IdentityEvidence(
                        kind="content_text",
                        value=text,
                        subject=eid,
                        identity_bearing=False,
                        provenance="whatsapp_text",
                    )
                )

        parts = candidate.get("participants") or candidate.get("participant_names")
        if isinstance(parts, (list, tuple)):
            for p in parts:
                if str(p or "").strip():
                    identity.append(
                        IdentityEvidence(
                            kind="participant",
                            value=p,
                            subject=eid,
                            confidence=0.99,
                            provenance="whatsapp_participants",
                        )
                    )
        for u in candidate.get("urls") or []:
            if u:
                content.append(
                    IdentityEvidence(
                        kind="url",
                        value=u,
                        subject=eid,
                        identity_bearing=False,
                        provenance="whatsapp_url",
                    )
                )
        # Host-aware query support as precomputed content_match when a query hint
        # is present on the candidate (binders may pass goal query through).
        query_hint = str(candidate.get("source_query") or candidate.get("query") or "")
        if query_hint and (preview or text or candidate.get("urls")):
            match = _content_supports_query(
                text=" ".join(
                    [
                        preview,
                        text,
                        " ".join(str(u) for u in (candidate.get("urls") or []) if u),
                    ]
                ),
                kind=raw_kind,
                query=query_hint,
                container=str(candidate.get("container") or ""),
            )
            content.append(
                IdentityEvidence(
                    kind="content_match",
                    value=bool(match),
                    subject=eid,
                    identity_bearing=False,
                    provenance="whatsapp_source_query_binding",
                    confidence=0.95 if match else 0.95,
                )
            )

        relations: Dict[str, Any] = {}
        for rk in ("container", "container_id", "open_conversation"):
            if candidate.get(rk) not in (None, ""):
                relations["container"] = candidate.get(rk)
                break

        return EntityObservation(
            entity_kind=entity_kind,
            entity_id=eid,
            label=display_name or label,
            identity_evidence=identity,
            content_evidence=content,
            relations=relations,
            raw=candidate,
        )


def _split_display_and_preview(label: str) -> tuple[str, str]:
    """Domain rule: preview/content must not redefine conversation identity.

    Uses the messaging-UI contact-head extractor when available; otherwise a
    conservative dash/URL cut. This logic stays in the adapter.
    """
    text = " ".join(str(label or "").strip().split())
    if not text:
        return "", ""
    try:
        from plugin.agent.capabilities.resolve_entity import _row_contact_name

        head = _row_contact_name(text)
    except Exception:
        head = text
        for sep in (" - ", " – ", " — "):
            if sep in text:
                head = text.split(sep, 1)[0].strip()
                break
        else:
            import re

            m = re.search(r"https?://", text, flags=re.I)
            if m and m.start() > 0:
                head = text[: m.start()].strip().rstrip(":").strip()
    head = head or text
    preview = ""
    if head and text.lower().startswith(head.lower()) and len(text) > len(head):
        preview = text[len(head) :].lstrip(" -–—:").strip()
    elif head != text:
        # Extractor shortened; remainder is preview-ish.
        preview = text[len(head) :].strip() if text.startswith(head) else text
    return head, preview


def _content_supports_query(
    *, text: str, kind: str, query: str, container: str
) -> bool:
    try:
        from plugin.agent.source_query_binding import (
            evaluate_source_object_match,
            query_supported_by_text,
        )

        gm = evaluate_source_object_match(
            text=text,
            kind=kind,
            query=query,
            container_open=container,
            expected_container=container,
        )
        return bool(gm.semantic_query_match or query_supported_by_text(text, query))
    except Exception:
        q = " ".join(str(query or "").strip().lower().split())
        return bool(q and q in " ".join(str(text or "").strip().lower().split()))


_REGISTERED = False


def ensure_whatsapp_provider_registered() -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    register_evidence_provider(WhatsAppUIEvidenceProvider())
    _REGISTERED = True


# Auto-register on import so WhatsApp runs pick up the adapter.
ensure_whatsapp_provider_registered()
