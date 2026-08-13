"""High-precision source-object binding for link/query goals.

Candidate generation may be high-recall (any URL in Pallavi). Binding must be
high-precision: a YouTube URL must never satisfy ``source_query=zarooratwala``,
and an outgoing ``You:`` message must never satisfy ``originator=Pallavi``.

``matches_goal`` from perception is treated as a *candidate signal*, not identity.
Authoritative binding uses constraint-level evidence (``GoalMatch`` /
``ConstraintMatch``) and ``binding_eligible``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import urlparse

_URL_RE = re.compile(r"https?://[^\s<>\"')\]]+|www\.[^\s<>\"')\]]+", re.I)
_YOU_SENDER_RE = re.compile(
    r"(?:^|[\s\-–—:])you\s*:",
    re.I,
)

_SELF_ORIGINATORS = frozenset({"self", "me", "i", "you", "myself"})


@dataclass
class ConstraintMatch:
    """One required/optional role constraint vs a candidate."""

    name: str
    required: bool = True
    status: str = "unknown"  # match | mismatch | missing | unknown
    evidence: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "required": self.required,
            "status": self.status,
            "evidence": self.evidence[:160],
        }


# Roles / kinds that may show query text but are never content patients.
_INPUT_EDITOR_KINDS = frozenset(
    {
        "draft",
        "composer",
        "composer_draft",
        "message_composer",
        "text_field",
        "search_field",
        "search_input",
        "search_bar",
        "input",
        "edit_field",
        "filter_field",
        "typeahead",
    }
)
_INPUT_EDITOR_ROLES = frozenset(
    {
        "composer",
        "draft",
        "message_composer",
        "input",
        "filter",
        "filter_field",
        "search_field",
        "type_field",
        "editor",
    }
)


@dataclass
class GoalMatch:
    """Per-constraint match evidence for a candidate vs the forward goal.

    ``task_relevance`` / perception recall may be high while ``binding_eligible``
    stays false (e.g. content+container match, originator mismatch).

    Typed claims (binding path):
    - ``query_match`` — query identity in text (alias of semantic_query_match)
    - ``role_compatible`` — content-patient role (not composer/draft/input)
    - ``binding_eligible`` — query_match ∧ role ∧ container ∧ originator
    """

    container_match: bool = False
    object_type_match: bool = False
    semantic_query_match: bool = False
    query_match: bool = False
    role_compatible: bool = True
    originator_match: bool = False
    identity_match: bool = False
    binding_eligible: bool = False
    constraints: List[ConstraintMatch] = field(default_factory=list)
    evidence: List[str] = field(default_factory=list)
    contradictions: List[str] = field(default_factory=list)
    confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "container_match": self.container_match,
            "object_type_match": self.object_type_match,
            "semantic_query_match": self.semantic_query_match,
            "query_match": self.query_match,
            "role_compatible": self.role_compatible,
            "originator_match": self.originator_match,
            "identity_match": self.identity_match,
            "binding_eligible": self.binding_eligible,
            "constraints": [c.to_dict() for c in self.constraints[:12]],
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
        path_blob = _norm(url)
        # Brand/domain query: host or path must support the brand token.
        # Platform hosts are not a global denylist — Instagram/YouTube/etc.
        # can be the sought object when the goal names them; when the brand
        # appears only in a path, ranking (not this hard reject) separates
        # direct brand hosts from related platform accounts.
        if q and ("." in q or len(tokens) == 1):
            brand = tokens[0]
            if brand not in host and brand not in path_blob:
                # Only contradict when this looks like a different site URL.
                if host and not any(tok in host for tok in tokens):
                    return True
    return False


def infer_message_originator(
    text: str,
    *,
    sender: Any = None,
    kind: str = "",
) -> str:
    """Best-effort sender label: ``self``, a contact name, or empty if unknown."""
    if sender not in (None, ""):
        s = _norm(sender)
        if s in _SELF_ORIGINATORS or s in {"outgoing", "mine"}:
            return "self"
        return str(sender).strip()
    blob = str(text or "")
    if _YOU_SENDER_RE.search(blob):
        return "self"
    # Explicit "Name: …" prefix (inbound attributed search rows).
    m = re.match(
        r"^([A-Z][\w .'-]{1,60}?)\s*:\s+\S",
        blob.strip(),
    )
    if m:
        name = m.group(1).strip()
        if _norm(name) not in _SELF_ORIGINATORS:
            return name
    return ""


def originator_matches(observed: str, expected: str) -> bool:
    """Identity equivalence via IdentityResolver — no substring matching."""
    want = _norm(expected)
    got = _norm(observed)
    if not want:
        return True
    if not got:
        return False
    want_self = want in _SELF_ORIGINATORS
    got_self = got in _SELF_ORIGINATORS
    if want_self:
        return got_self
    if got_self:
        return False
    from plugin.agent.role_binding import IdentityResolver

    return IdentityResolver.values_same_identity(observed, expected)


def evaluate_source_object_match(
    *,
    text: str,
    kind: str = "",
    query: str = "",
    container_open: str = "",
    expected_container: str = "",
    expected_originator: str = "",
    sender: Any = None,
    perception_matches_goal: bool = False,
    role: str = "",
) -> GoalMatch:
    """High-precision eligibility for binding ``source_object``."""
    gm = GoalMatch()
    blob = str(text or "")
    kind_l = _norm(kind)
    role_l = _norm(role)
    q = _norm(query)
    want_origin = str(expected_originator or "").strip()

    # Role: content patient vs input/editor (draft may carry query text).
    gm.role_compatible = not (
        kind_l in _INPUT_EDITOR_KINDS
        or role_l in _INPUT_EDITOR_ROLES
        or any(tok in kind_l for tok in ("composer", "draft", "input"))
        or any(tok in role_l for tok in ("composer", "draft", "input", "filter"))
    )
    gm.constraints.append(
        ConstraintMatch(
            name="role",
            required=True,
            status="match" if gm.role_compatible else "mismatch",
            evidence=f"kind={kind_l or '-'} role={role_l or '-'}",
        )
    )
    if not gm.role_compatible:
        gm.contradictions.append("role_incompatible_input_editor")

    # Container
    if expected_container:
        open_n = _norm(container_open)
        want = _norm(expected_container)
        gm.container_match = bool(want and open_n and (want in open_n or open_n in want))
        gm.constraints.append(
            ConstraintMatch(
                name="container",
                required=True,
                status="match" if gm.container_match else "mismatch",
                evidence=f"open={container_open!r} want={expected_container!r}",
            )
        )
        if gm.container_match:
            gm.evidence.append(f"container={container_open}")
        else:
            gm.contradictions.append("container_unmatched")
    else:
        gm.container_match = True
        gm.constraints.append(
            ConstraintMatch(
                name="container",
                required=False,
                status="unknown",
                evidence="no expected_container",
            )
        )

    # Object type: message / link / chat content (not bare chat_row preview alone
    # unless it carries the query). Input/editor kinds are never content objects.
    content_kinds = {
        "message",
        "message_bubble",
        "message_link_preview",
        "link",
        "attachment",
        "message_with_link",
        "message_cluster",
    }
    gm.object_type_match = (
        gm.role_compatible
        and (kind_l in content_kinds or bool(extract_urls(blob)))
    )
    gm.constraints.append(
        ConstraintMatch(
            name="object_type",
            required=True,
            status="match" if gm.object_type_match else "mismatch",
            evidence=f"kind={kind_l or 'url'}",
        )
    )
    if gm.object_type_match:
        gm.evidence.append(f"kind={kind_l or 'url'}")
    else:
        gm.contradictions.append("not_content_object")

    # Semantic query / typed query_match claim
    if not q:
        gm.semantic_query_match = True  # no query constraint
        gm.query_match = True
        gm.constraints.append(
            ConstraintMatch(
                name="content",
                required=False,
                status="match",
                evidence="no query constraint",
            )
        )
    else:
        gm.semantic_query_match = query_supported_by_text(blob, query)
        gm.query_match = bool(gm.semantic_query_match)
        if gm.semantic_query_match:
            gm.evidence.append(f"query_supported:{query}")
        else:
            gm.contradictions.append(f"query_absent:{query}")
        gm.constraints.append(
            ConstraintMatch(
                name="content",
                required=True,
                status="match" if gm.semantic_query_match else "mismatch",
                evidence=f"query={query!r}",
            )
        )

    if q and host_contradicts_query(blob, query):
        gm.semantic_query_match = False
        gm.query_match = False
        gm.contradictions.append("url_host_contradicts_query")
        for c in gm.constraints:
            if c.name == "content":
                c.status = "mismatch"
                c.evidence = "url_host_contradicts_query"

    # Originator / sender (container membership is not authorship)
    observed_origin = infer_message_originator(blob, sender=sender, kind=kind)
    if want_origin:
        gm.originator_match = originator_matches(observed_origin, want_origin)
        if not observed_origin:
            gm.originator_match = False
            gm.constraints.append(
                ConstraintMatch(
                    name="originator",
                    required=True,
                    status="missing",
                    evidence=f"want={want_origin!r}; no sender evidence",
                )
            )
            gm.contradictions.append("originator_missing")
        elif gm.originator_match:
            gm.constraints.append(
                ConstraintMatch(
                    name="originator",
                    required=True,
                    status="match",
                    evidence=f"sender={observed_origin!r}",
                )
            )
            gm.evidence.append(f"originator={observed_origin}")
        else:
            gm.constraints.append(
                ConstraintMatch(
                    name="originator",
                    required=True,
                    status="mismatch",
                    evidence=f"UI sender={observed_origin!r} want={want_origin!r}",
                )
            )
            gm.contradictions.append(
                f"originator_mismatch:{observed_origin!r}!={want_origin!r}"
            )
    else:
        gm.originator_match = True
        gm.constraints.append(
            ConstraintMatch(
                name="originator",
                required=False,
                status="unknown",
                evidence="no expected_originator",
            )
        )

    # Identity: query + content-patient role + container (when known) + originator
    gm.identity_match = bool(
        gm.query_match
        and gm.role_compatible
        and gm.object_type_match
        and (gm.container_match or not expected_container)
        and gm.originator_match
    )

    # Perception bool is recall only — cannot override query/originator/role fail.
    if perception_matches_goal and gm.query_match:
        gm.evidence.append("perception_matches_goal_recall_only")
    elif perception_matches_goal and not gm.query_match:
        gm.contradictions.append("perception_matches_goal_ignored_query_fail")
    if perception_matches_goal and want_origin and not gm.originator_match:
        gm.contradictions.append("perception_matches_goal_ignored_originator_fail")
    if perception_matches_goal and not gm.role_compatible:
        gm.contradictions.append("perception_matches_goal_ignored_role_fail")

    # Binding path: relevance ≠ bind. Require typed query_match + role.
    gm.binding_eligible = bool(gm.identity_match)
    if gm.binding_eligible:
        gm.confidence = 0.9 if gm.container_match else 0.75
    elif (
        gm.object_type_match
        and gm.container_match
        and gm.semantic_query_match
        and want_origin
        and not gm.originator_match
    ):
        gm.confidence = 0.35  # high relevance, wrong author
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
    expected_originator: str = "",
) -> Dict[str, Any]:
    """Downgrade opaque matches_goal when query/originator evidence fails."""
    doc = dict(document) if isinstance(document, dict) else {}
    if not _norm(query) and not _norm(expected_originator):
        return doc
    objects = [dict(o) for o in (doc.get("objects") or []) if isinstance(o, dict)]
    open_c = str(doc.get("open_conversation") or "")
    changed = False
    for obj in objects:
        if not bool(obj.get("matches_goal")):
            continue
        text = str(obj.get("text") or obj.get("label") or "")
        kind = str(obj.get("kind") or "")
        sender = obj.get("sender") or obj.get("originator")
        gm = evaluate_source_object_match(
            text=text,
            kind=kind,
            query=query,
            container_open=open_c,
            expected_container=expected_container,
            expected_originator=expected_originator,
            sender=sender,
            perception_matches_goal=True,
            role=str(obj.get("role") or obj.get("field_role") or ""),
        )
        obj["goal_match"] = gm.to_dict()
        # Keep matches_goal for display/recall when query_match holds but role
        # forbids bind (draft). Clear when query identity / distractor fails.
        if not gm.binding_eligible:
            if not gm.query_match or "url_host_contradicts_query" in gm.contradictions:
                obj["matches_goal"] = False
                obj["matches_goal_rejected"] = "role_constraints_unsatisfied"
                changed = True
            else:
                obj["binding_eligible"] = False
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
