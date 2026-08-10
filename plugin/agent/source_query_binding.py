"""High-precision source-object binding for link/query goals.

Candidate generation may be high-recall (any URL in Pallavi). Binding must be
high-precision: a YouTube URL must never satisfy ``source_query=zarooratwala``.

``matches_goal`` from perception is treated as a *candidate signal*, not identity.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import urlparse

_URL_RE = re.compile(r"https?://[^\s<>\"')\]]+|www\.[^\s<>\"')\]]+", re.I)

# Hosts that are never the brand/domain of a grocery/link query like zarooratwala.
_DISTRACTOR_HOSTS = frozenset(
    {
        "youtu.be",
        "youtube.com",
        "m.youtube.com",
        "instagram.com",
        "www.instagram.com",
        "facebook.com",
        "fb.com",
        "twitter.com",
        "x.com",
        "tiktok.com",
        "google.com",
        "maps.google.com",
        "wa.me",
        "chat.whatsapp.com",
    }
)


@dataclass
class GoalMatch:
    """Per-constraint match evidence for a candidate vs the forward goal."""

    container_match: bool = False
    object_type_match: bool = False
    semantic_query_match: bool = False
    identity_match: bool = False
    binding_eligible: bool = False
    evidence: List[str] = field(default_factory=list)
    contradictions: List[str] = field(default_factory=list)
    confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "container_match": self.container_match,
            "object_type_match": self.object_type_match,
            "semantic_query_match": self.semantic_query_match,
            "identity_match": self.identity_match,
            "binding_eligible": self.binding_eligible,
            "evidence": list(self.evidence)[:8],
            "contradictions": list(self.contradictions)[:8],
            "confidence": round(float(self.confidence), 3),
        }


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _query_tokens(query: str) -> List[str]:
    q = _norm(query)
    if not q:
        return []
    # Keep brand-like tokens; drop tiny noise.
    return [t for t in re.split(r"[^a-z0-9]+", q) if len(t) >= 3]


def extract_urls(text: str) -> List[str]:
    return [m.group(0).rstrip(".,);]") for m in _URL_RE.finditer(str(text or ""))]


def url_host(url: str) -> str:
    raw = str(url or "").strip()
    if not raw:
        return ""
    if not re.match(r"^[a-z][a-z0-9+.-]*://", raw, re.I):
        raw = "https://" + raw
    try:
        host = (urlparse(raw).netloc or "").lower()
    except Exception:
        return ""
    if host.startswith("www."):
        host = host[4:]
    return host


def query_supported_by_text(text: str, query: str) -> bool:
    """True when query tokens appear in text/URL (not merely 'has a URL')."""
    blob = _norm(text)
    tokens = _query_tokens(query)
    if not tokens or not blob:
        return False
    if _norm(query) and _norm(query) in blob:
        return True
    return all(tok in blob for tok in tokens)


def host_contradicts_query(text: str, query: str) -> bool:
    """URL present whose host/domain does not support the query brand/domain."""
    tokens = _query_tokens(query)
    if not tokens:
        return False
    urls = extract_urls(text)
    if not urls:
        return False
    q = _norm(query).replace(" ", "")
    for url in urls:
        host = url_host(url)
        if not host:
            continue
        # Explicit distractor platforms with no query token in host/path.
        path_blob = _norm(url)
        if host in _DISTRACTOR_HOSTS or any(
            host.endswith("." + d) for d in _DISTRACTOR_HOSTS if "." in d
        ):
            if not query_supported_by_text(path_blob, query):
                return True
        # Brand/domain query: host must contain the brand token.
        if q and ("." in q or len(tokens) == 1):
            brand = tokens[0]
            if brand not in host and brand not in path_blob:
                # Only contradict when this looks like a different site URL.
                if host and not any(tok in host for tok in tokens):
                    return True
    return False


def evaluate_source_object_match(
    *,
    text: str,
    kind: str = "",
    query: str = "",
    container_open: str = "",
    expected_container: str = "",
    perception_matches_goal: bool = False,
) -> GoalMatch:
    """High-precision eligibility for binding ``source_object``."""
    gm = GoalMatch()
    blob = str(text or "")
    kind_l = _norm(kind)
    q = _norm(query)

    # Container
    if expected_container:
        open_n = _norm(container_open)
        want = _norm(expected_container)
        gm.container_match = bool(want and open_n and (want in open_n or open_n in want))
        if gm.container_match:
            gm.evidence.append(f"container={container_open}")
        else:
            gm.contradictions.append("container_unmatched")

    # Object type: message / link / chat content (not bare chat_row preview alone
    # unless it carries the query).
    content_kinds = {
        "message",
        "message_bubble",
        "message_link_preview",
        "link",
        "attachment",
        "message_with_link",
        "message_cluster",
    }
    gm.object_type_match = kind_l in content_kinds or bool(extract_urls(blob))
    if gm.object_type_match:
        gm.evidence.append(f"kind={kind_l or 'url'}")
    else:
        gm.contradictions.append("not_content_object")

    # Semantic query
    if not q:
        gm.semantic_query_match = True  # no query constraint
    else:
        gm.semantic_query_match = query_supported_by_text(blob, query)
        if gm.semantic_query_match:
            gm.evidence.append(f"query_supported:{query}")
        else:
            gm.contradictions.append(f"query_absent:{query}")

    if q and host_contradicts_query(blob, query):
        gm.semantic_query_match = False
        gm.contradictions.append("url_host_contradicts_query")

    # Identity: query support + content object (+ container when known)
    gm.identity_match = bool(
        gm.semantic_query_match
        and gm.object_type_match
        and (gm.container_match or not expected_container)
    )

    # Perception bool is recall only — cannot override query contradiction.
    if perception_matches_goal and gm.semantic_query_match:
        gm.evidence.append("perception_matches_goal")
    elif perception_matches_goal and not gm.semantic_query_match:
        gm.contradictions.append("perception_matches_goal_ignored_query_fail")

    gm.binding_eligible = bool(gm.identity_match)
    if gm.binding_eligible:
        gm.confidence = 0.9 if gm.container_match else 0.75
    elif gm.object_type_match and gm.container_match and not gm.semantic_query_match:
        gm.confidence = 0.15  # distractor link in right chat
    else:
        gm.confidence = 0.05
    return gm


def scrub_matches_goal_flags(
    document: Optional[Dict[str, Any]],
    *,
    query: str,
    expected_container: str = "",
) -> Dict[str, Any]:
    """Downgrade opaque matches_goal when query evidence is absent/contradicted."""
    doc = dict(document) if isinstance(document, dict) else {}
    if not _norm(query):
        return doc
    objects = [dict(o) for o in (doc.get("objects") or []) if isinstance(o, dict)]
    open_c = str(doc.get("open_conversation") or "")
    changed = False
    for obj in objects:
        if not bool(obj.get("matches_goal")):
            continue
        text = str(obj.get("text") or obj.get("label") or "")
        kind = str(obj.get("kind") or "")
        gm = evaluate_source_object_match(
            text=text,
            kind=kind,
            query=query,
            container_open=open_c,
            expected_container=expected_container,
            perception_matches_goal=True,
        )
        obj["goal_match"] = gm.to_dict()
        if not gm.binding_eligible:
            obj["matches_goal"] = False
            obj["matches_goal_rejected"] = "source_query_not_supported"
            changed = True
    if changed or objects:
        doc["objects"] = objects
    return doc


def text_locates_source_query(text: str, query: str) -> bool:
    """For soft content_located: require query support, not host-contradicting URL."""
    if not _norm(query):
        return False
    if host_contradicts_query(text, query) and not query_supported_by_text(text, query):
        return False
    return query_supported_by_text(text, query)


def document_locates_source_query(document: Optional[Dict[str, Any]], query: str) -> bool:
    if not isinstance(document, dict) or not _norm(query):
        return False
    for obj in document.get("objects") or []:
        if not isinstance(obj, dict):
            continue
        text = str(obj.get("text") or obj.get("label") or "")
        if text_locates_source_query(text, query):
            return True
    return False


def source_object_unresolved(task_state: Any) -> bool:
    status = str(getattr(task_state, "referent_binding_status", "") or "").strip().lower()
    selected = bool(getattr(task_state, "referent_selected", False))
    if status in {"unresolved", "ambiguous", ""}:
        return True
    if status == "provisional" and not selected:
        return True
    return not selected and status != "confirmed"
