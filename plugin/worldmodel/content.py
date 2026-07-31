"""Generic content-object primitives for goal-conditioned object discovery.

This module stays app-agnostic. App adapters are responsible for turning
their visible surface into normalized content objects; the core uses those
objects to resolve what the user likely meant from the task goal.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
import re
from typing import Any, Dict, List, Optional, Protocol, Sequence, Tuple, runtime_checkable
from urllib.parse import parse_qsl, urlparse


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _tokenize(value: Any) -> List[str]:
    raw = _clean_text(value).lower()
    if not raw:
        return []
    return [tok for tok in re.split(r"[^a-z0-9]+", raw) if tok]


def _compact(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", _clean_text(value).lower())


def _looks_like_url(raw: str) -> bool:
    return bool(re.search(r"https?://|www\.", raw or "", re.I))


def _normalize_host(host: str) -> str:
    host = (host or "").strip().lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    if host.startswith("m.") and host.count(".") >= 2:
        host = host[2:]
    return host


def extract_url_identity(raw_url: str) -> Dict[str, Any]:
    """Parse a URL into stable comparison tokens."""
    raw = _clean_text(raw_url)
    if not raw:
        return {
            "raw_url": "",
            "scheme": "",
            "host": "",
            "registrable_domain": "",
            "host_tokens": [],
            "path_tokens": [],
            "query_tokens": [],
        }

    candidate = raw if re.match(r"^[a-z][a-z0-9+.-]*://", raw, re.I) else f"https://{raw}"
    parsed = urlparse(candidate)
    host = _normalize_host(parsed.netloc)
    host_parts = [part for part in host.split(".") if part]
    registrable = host
    if len(host_parts) >= 2 and not re.fullmatch(r"\d+(?:\.\d+){3}", host):
        registrable = ".".join(host_parts[-2:])

    path_tokens = [tok for segment in parsed.path.split("/") for tok in _tokenize(segment)]
    query_tokens: List[str] = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        query_tokens.extend(_tokenize(key))
        query_tokens.extend(_tokenize(value))

    host_tokens = _tokenize(host)
    return {
        "raw_url": raw,
        "scheme": parsed.scheme or "",
        "host": host,
        "registrable_domain": registrable,
        "host_tokens": host_tokens,
        "path_tokens": path_tokens,
        "query_tokens": query_tokens,
    }


@dataclass
class ContentObject:
    """Normalized, app-agnostic visible content item."""

    id: str
    object_type: str
    text: str | None = None
    title: str | None = None
    url: str | None = None
    filename: str | None = None
    sender: str | None = None
    recipients: List[str] = field(default_factory=list)
    timestamp: datetime | None = None
    container_id: str = ""
    container_type: str = ""
    parent_object_id: str | None = None
    attachments: List[str] = field(default_factory=list)
    source_app: str = ""
    source_entity_ids: List[int] = field(default_factory=list)
    visible: bool = True
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        if self.timestamp is not None:
            data["timestamp"] = self.timestamp.isoformat()
        return data

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ContentObject":
        timestamp = d.get("timestamp")
        if isinstance(timestamp, str) and timestamp:
            try:
                timestamp = datetime.fromisoformat(timestamp)
            except Exception:
                timestamp = None
        elif not isinstance(timestamp, datetime):
            timestamp = None
        return cls(
            id=str(d.get("id") or ""),
            object_type=str(d.get("object_type") or "unknown"),
            text=str(d.get("text") or "") or None,
            title=str(d.get("title") or "") or None,
            url=str(d.get("url") or "") or None,
            filename=str(d.get("filename") or "") or None,
            sender=str(d.get("sender") or "") or None,
            recipients=[str(x) for x in (d.get("recipients") or [])],
            timestamp=timestamp,
            container_id=str(d.get("container_id") or ""),
            container_type=str(d.get("container_type") or ""),
            parent_object_id=str(d.get("parent_object_id") or "") or None,
            attachments=[str(x) for x in (d.get("attachments") or [])],
            source_app=str(d.get("source_app") or ""),
            source_entity_ids=[int(x) for x in (d.get("source_entity_ids") or []) if str(x).strip()],
            visible=bool(d.get("visible", True)),
            confidence=float(d.get("confidence") if d.get("confidence") is not None else 1.0),
            metadata=dict(d.get("metadata") or {}),
        )

    @property
    def display_text(self) -> str:
        for candidate in (self.title, self.text, self.filename, self.url, self.sender):
            if candidate and _clean_text(candidate):
                return _clean_text(candidate)
        return self.id

    @property
    def url_identity(self) -> Dict[str, Any]:
        return extract_url_identity(self.url or "")

    def text_blob(self) -> str:
        pieces = [
            self.title or "",
            self.text or "",
            self.filename or "",
            self.sender or "",
            self.container_id or "",
            self.container_type or "",
            self.url or "",
            " ".join(str(x) for x in self.recipients),
            " ".join(str(x) for x in self.attachments),
        ]
        meta_bits: List[str] = []
        for key in ("description", "label", "context", "neighbor_text", "container_title"):
            value = self.metadata.get(key)
            if value:
                meta_bits.append(_clean_text(value))
        pieces.extend(meta_bits)
        return " ".join(p for p in pieces if p).strip()


@dataclass
class ContentQuery:
    """Goal-conditioned content query used by the discovery core."""

    raw: str = ""
    semantic_reference: str = ""
    target_types: List[str] = field(default_factory=list)
    source_container: str = ""
    source_container_type: str = ""
    desired_operation: str = ""
    destination: str = ""
    semantic_aliases: List[str] = field(default_factory=list)
    context_hypotheses: List[str] = field(default_factory=list)
    prompt: str = ""
    goal_kind: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DiscoveryContext:
    """Read-only context passed from the adapter boundary into the core."""

    source_app: str = ""
    container_id: str = ""
    container_type: str = ""
    window_name: str = ""
    conversation_window: int = 0
    retry_count: int = 0
    visible_object_count: int = 0
    notes: List[str] = field(default_factory=list)
    use_llm: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RankedContentObject:
    object_id: str
    score: float
    reasons: List[str] = field(default_factory=list)
    object: ContentObject | None = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["object"] = None if self.object is None else self.object.to_dict()
        return data


@dataclass
class ObjectResolution:
    status: str = "not_found"
    selected_object_id: str | None = None
    candidates: List[RankedContentObject] = field(default_factory=list)
    confidence: float = 0.0
    evidence: List[str] = field(default_factory=list)
    next_information_actions: List[str] = field(default_factory=list)
    selected_source_entity_ids: List[int] = field(default_factory=list)
    selected_object_text: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "selected_object_id": self.selected_object_id,
            "candidates": [c.to_dict() for c in self.candidates],
            "confidence": round(float(self.confidence or 0.0), 4),
            "evidence": list(self.evidence),
            "next_information_actions": list(self.next_information_actions),
            "selected_source_entity_ids": [int(x) for x in self.selected_source_entity_ids],
            "selected_object_text": self.selected_object_text,
            "raw": self.raw,
        }


@runtime_checkable
class ContentObjectAdapter(Protocol):
    """Adapter contract for app-specific extraction.

    Adapters expose visible objects as `ContentObject` instances only. They do
    not decide which object is relevant or which action should follow.
    """

    def list_visible_objects(self, *, world: Any, goal: Any = None) -> Sequence[ContentObject]:
        ...


def infer_content_object_type(row: Dict[str, Any], *, text_blob: str = "") -> str:
    explicit = _clean_text(row.get("object_type") or row.get("content_type") or "")
    if explicit:
        return explicit
    entity_type = _clean_text(row.get("entity_type") or row.get("role") or "").lower()
    if row.get("filename") or _clean_text(row.get("filename")):
        return "file"
    candidate_url = _clean_text(row.get("url") or "")
    if not candidate_url:
        match = re.search(r"https?://\S+|www\.\S+", text_blob or "", re.I)
        candidate_url = _clean_text(match.group(0)) if match else ""
    if candidate_url:
        if text_blob and text_blob.strip() and _clean_text(text_blob).strip() != candidate_url:
            return "message_with_link"
        return "link"
    if entity_type in {"link", "message_with_link"}:
        return entity_type
    if entity_type in {"textfield", "input"}:
        return "input"
    if entity_type in {"button", "cta"}:
        return "action"
    if entity_type in {"static", "text", "cell", "message"}:
        return "message"
    return entity_type or "unknown"


def content_object_from_row(
    row: Dict[str, Any],
    *,
    source_app: str = "",
    container_id: str = "",
    container_type: str = "conversation",
    parent_object_id: str | None = None,
) -> ContentObject:
    entity_id = row.get("entity_id")
    object_id = str(entity_id) if entity_id is not None else _clean_text(row.get("id") or row.get("object_id") or "")
    if not object_id:
        object_id = _clean_text(row.get("label") or row.get("text") or row.get("title") or "object")
    title = _clean_text(row.get("title") or row.get("label") or "")
    text = _clean_text(row.get("text") or row.get("description") or row.get("value") or "")
    filename = _clean_text(row.get("filename") or "")
    sender = _clean_text(row.get("sender") or row.get("author") or row.get("from") or "")
    url = _clean_text(row.get("url") or "")
    if not url:
        match = re.search(r"https?://\S+|www\.\S+", " ".join([title, text, filename, sender]), re.I)
        if match:
            url = _clean_text(match.group(0))
    recipients = [str(x).strip() for x in (row.get("recipients") or []) if str(x).strip()]
    attachments = [str(x).strip() for x in (row.get("attachments") or []) if str(x).strip()]
    text_blob = " ".join([title, text, filename, url, sender, " ".join(recipients), " ".join(attachments)])
    obj_type = infer_content_object_type({**row, "url": url, "filename": filename}, text_blob=text_blob)
    metadata = dict(row.get("metadata") or {})
    for key in ("description", "label", "role", "entity_type", "x", "y", "bounds"):
        value = row.get(key)
        if value not in {None, ""}:
            metadata.setdefault(key, value)
    if url:
        metadata.setdefault("url_identity", extract_url_identity(url))
    if text_blob:
        metadata.setdefault("blob", _clean_text(text_blob))
    return ContentObject(
        id=object_id,
        object_type=obj_type,
        text=text or None,
        title=title or None,
        url=url or None,
        filename=filename or None,
        sender=sender or None,
        recipients=recipients,
        timestamp=None,
        container_id=_clean_text(container_id or row.get("container_id") or ""),
        container_type=_clean_text(row.get("container_type") or container_type or ""),
        parent_object_id=parent_object_id,
        attachments=attachments,
        source_app=source_app,
        source_entity_ids=[int(entity_id)] if entity_id is not None and str(entity_id).strip() else [],
        visible=bool(row.get("visible", True)),
        confidence=float(row.get("confidence") if row.get("confidence") is not None else 1.0),
        metadata=metadata,
    )


def content_objects_from_rows(
    rows: Sequence[Dict[str, Any]],
    *,
    source_app: str = "",
    container_id: str = "",
    container_type: str = "conversation",
) -> List[ContentObject]:
    out: List[ContentObject] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        out.append(
            content_object_from_row(
                row,
                source_app=source_app,
                container_id=container_id,
                container_type=container_type,
            )
        )
    return out

