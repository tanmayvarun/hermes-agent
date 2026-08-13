"""Generic typed role-binding: policy + evidence + resolver.

Layering (do not collapse):

1. **RoleBindingPolicy** — what identity relationship a role requires.
2. **IdentityEvidenceProvider** (domain adapters) — emit typed evidence.
3. **IdentityResolver** — whether available evidence satisfies the contract.

Core must not know UI rows, chat previews, contact-name extraction, or app
names. Descendants' content must not redefine a container's identity unless
that property is explicitly identity-bearing.

Relevance proposes candidates. Required identity relations are hard gates.
Binding owns semantic identity; ACT consumes ``binding.is_valid()``; VERIFY
may invalidate via contradictory evidence (``REFERENT_MISMATCH``).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Protocol, Sequence, Set


# ---------------------------------------------------------------------------
# Typed evidence / observations
# ---------------------------------------------------------------------------


@dataclass
class IdentityEvidence:
    """One typed fact about an entity. Produced by domain adapters only."""

    kind: str  # display_name | participant | stable_id | alias | container | …
    value: Any = None
    subject: str = ""
    confidence: float = 1.0
    provenance: str = ""
    # True → may establish identity; False → relevance/content only.
    identity_bearing: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EntityObservation:
    """Environment-neutral view of a candidate entity.

    ``entity_kind`` is a resolved domain kind when known. Ambiguous UI widgets
    leave it empty and populate ``candidate_entity_kinds`` + ``ui_role`` instead.
    """

    entity_kind: str = ""
    entity_id: str = ""
    label: str = ""
    ui_role: str = ""  # presentation widget — not a domain entity type
    candidate_entity_kinds: Set[str] = field(default_factory=set)
    identity_evidence: List[IdentityEvidence] = field(default_factory=list)
    content_evidence: List[IdentityEvidence] = field(default_factory=list)
    relations: Dict[str, Any] = field(default_factory=dict)  # e.g. container → id/label
    raw: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_kind": self.entity_kind,
            "entity_id": self.entity_id,
            "label": self.label,
            "ui_role": self.ui_role,
            "candidate_entity_kinds": sorted(self.candidate_entity_kinds),
            "identity_evidence": [e.to_dict() for e in self.identity_evidence[:12]],
            "content_evidence": [e.to_dict() for e in self.content_evidence[:12]],
            "relations": dict(self.relations or {}),
        }


# DELETE_TICKET(forward_shims): remove after callers import procedures.forward_message.
# Gate: no NEW call sites may use these shims (see contract_hardening_gate).
def forward_role_specs(goal: Any) -> Dict[str, RoleBindingSpec]:
    """DEPRECATED shim — import from procedures.forward_message instead."""
    from plugin.agent.procedures.forward_message import forward_role_specs as _specs

    return _specs(goal)


@dataclass
class Constraint:
    """One required relation in a role identity contract."""

    relation: str  # same_identity | same_content_referent | equals_binding | …
    referent_source: str = ""  # goal path or binding name
    value: Any = None
    required: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RoleBindingSpec:
    """Policy: what identity a typed role must refer to."""

    role: str
    expected_entity_kinds: Set[str] = field(default_factory=set)
    identity_constraints: List[Constraint] = field(default_factory=list)
    evidence_threshold: float = 0.85

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "expected_entity_kinds": sorted(self.expected_entity_kinds),
            "identity_constraints": [c.to_dict() for c in self.identity_constraints],
            "evidence_threshold": self.evidence_threshold,
        }


@dataclass
class EvidenceNote:
    kind: str
    value: Any = None
    detail: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"kind": self.kind, "value": self.value, "detail": self.detail}


@dataclass
class CandidateAssessment:
    """Keep task relevance and role identity completely separate."""

    task_relevance: float = 0.0
    role_identity_confidence: float = 0.0
    binding_eligible: bool = False
    supporting: List[EvidenceNote] = field(default_factory=list)
    contradicting: List[EvidenceNote] = field(default_factory=list)
    missing_required: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_relevance": round(float(self.task_relevance), 3),
            "role_identity_confidence": round(float(self.role_identity_confidence), 3),
            "binding_eligible": bool(self.binding_eligible),
            "supporting": [e.to_dict() for e in self.supporting[:8]],
            "contradicting": [e.to_dict() for e in self.contradicting[:8]],
            "missing_required": list(self.missing_required)[:8],
        }


@dataclass
class BindingProposal:
    """Explicit binding transition — never a side effect of ranking."""

    role: str
    candidate_id: str = ""
    candidate_label: str = ""
    supporting_evidence: List[EvidenceNote] = field(default_factory=list)
    contradicting_evidence: List[EvidenceNote] = field(default_factory=list)
    required_constraints_satisfied: bool = False
    confidence: float = 0.0
    task_relevance: float = 0.0
    assessment: Optional[CandidateAssessment] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "candidate_id": self.candidate_id,
            "candidate_label": self.candidate_label,
            "supporting_evidence": [e.to_dict() for e in self.supporting_evidence[:8]],
            "contradicting_evidence": [e.to_dict() for e in self.contradicting_evidence[:8]],
            "required_constraints_satisfied": bool(self.required_constraints_satisfied),
            "confidence": round(float(self.confidence), 3),
            "task_relevance": round(float(self.task_relevance), 3),
            "assessment": self.assessment.to_dict() if self.assessment else None,
        }


@dataclass
class BindingRecord:
    """Authoritative bound role. ACT asks ``is_valid()``, does not re-resolve."""

    role: str
    entity_id: str = ""
    label: str = ""
    status: str = "unresolved"  # provisional | confirmed | invalidated
    confidence: float = 0.0
    evidence: List[str] = field(default_factory=list)

    def is_valid(self) -> bool:
        return self.status in {"provisional", "confirmed"} and bool(
            self.entity_id or self.label
        )

    def matches_target(self, target: str) -> bool:
        t = _norm(target)
        if not t:
            return False
        if self.entity_id and _norm(self.entity_id) == t:
            return True
        if self.label and _norm(self.label) == t:
            return True
        # Allow target that is the identity head of a longer actuator string.
        if self.label and t.startswith(_norm(self.label)):
            return True
        return False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "entity_id": self.entity_id,
            "label": self.label,
            "status": self.status,
            "confidence": round(float(self.confidence), 3),
            "evidence": list(self.evidence)[:8],
            "valid": self.is_valid(),
        }


REFERENT_MISMATCH = "REFERENT_MISMATCH"

# Identity-bearing evidence kinds the generic resolver understands.
_IDENTITY_KINDS = frozenset(
    {
        "display_name",
        "title",
        "name",
        "participant",
        "stable_id",
        "alias",
        "thread_id",
        "container_id",
        "directory_name",
        "tab_title",
        "event_id",
        "email_thread_id",
        "contact_ref",
    }
)
_CONTENT_KINDS = frozenset(
    {
        "content_text",
        "preview_text",
        "body",
        "url",
        "filename",
        "page_text",
        "latest_message",
        "content_match",
        "query_support",
    }
)


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def goal_path(goal: Any, path: str) -> Any:
    """Resolve ``goal.source_contact`` / ``goal.source_query`` style paths."""
    if not path:
        return None
    key = str(path).strip()
    if key.startswith("goal."):
        key = key[5:]
    aliases = {
        "source_contact": ("contact", "source_conversation", "source_contact"),
        "source_conversation": ("contact", "source_conversation", "source_contact"),
        "source_query": ("link_query", "source_query", "content_query", "query"),
        "source_referent": ("contact", "source_conversation", "source_contact"),
        # Author/sender/creator — never alias to contact (container ≠ originator).
        "originator": ("originator",),
        "sender": ("originator", "sender"),
        "destination": ("target_contact", "destination"),
        "target_contact": ("target_contact", "destination"),
        "app": ("app",),
    }
    names = aliases.get(key, (key,))
    if isinstance(goal, dict):
        for n in names:
            if goal.get(n) not in (None, ""):
                return goal.get(n)
        return None
    for n in names:
        val = getattr(goal, n, None)
        if val not in (None, ""):
            return val
    return None


# ---------------------------------------------------------------------------
# Evidence providers (protocol + registry)
# ---------------------------------------------------------------------------


class IdentityEvidenceProvider(Protocol):
    """Domain adapter: raw environment → typed EntityObservation."""

    name: str

    def can_handle(self, candidate: Dict[str, Any]) -> bool: ...

    def observe(self, candidate: Dict[str, Any]) -> EntityObservation: ...


_PROVIDERS: List[IdentityEvidenceProvider] = []


def register_evidence_provider(provider: IdentityEvidenceProvider) -> None:
    """Register a domain adapter. First matching ``can_handle`` wins."""
    # Replace same name; keep order otherwise.
    global _PROVIDERS
    _PROVIDERS = [p for p in _PROVIDERS if getattr(p, "name", "") != provider.name]
    _PROVIDERS.insert(0, provider)


def clear_evidence_providers() -> None:
    _PROVIDERS.clear()


class PassthroughEvidenceProvider:
    """Generic adapter: consume pre-typed evidence or coarse dict fields.

    Never strips previews or knows UI structure. If the environment already
    separated ``identity_evidence`` / ``content_evidence``, those win.
    Otherwise title/name → identity; body/text/url → content.
    """

    name = "passthrough"

    def can_handle(self, candidate: Dict[str, Any]) -> bool:
        return True

    def observe(self, candidate: Dict[str, Any]) -> EntityObservation:
        if isinstance(candidate.get("identity_evidence"), list) or isinstance(
            candidate.get("content_evidence"), list
        ):
            return _observation_from_typed_dict(candidate)

        kind = _norm(
            candidate.get("entity_kind")
            or candidate.get("object_type")
            or candidate.get("kind")
            or candidate.get("type")
            or ""
        )
        eid = str(
            candidate.get("id")
            or candidate.get("entity_id")
            or candidate.get("object_id")
            or ""
        )
        label = str(
            candidate.get("label")
            or candidate.get("title")
            or candidate.get("name")
            or candidate.get("text")
            or ""
        )
        identity: List[IdentityEvidence] = []
        content: List[IdentityEvidence] = []

        for key, ev_kind in (
            ("display_name", "display_name"),
            ("title", "title"),
            ("name", "name"),
            ("stable_id", "stable_id"),
            ("thread_id", "thread_id"),
            ("directory_name", "directory_name"),
            ("tab_title", "tab_title"),
        ):
            if candidate.get(key) not in (None, ""):
                identity.append(
                    IdentityEvidence(
                        kind=ev_kind,
                        value=candidate.get(key),
                        subject=eid,
                        provenance="passthrough",
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
                            provenance="passthrough",
                        )
                    )
        for key, ev_kind in (
            ("sender", "sender"),
            ("originator", "originator"),
            ("author", "author"),
            ("creator", "creator"),
        ):
            if candidate.get(key) not in (None, ""):
                identity.append(
                    IdentityEvidence(
                        kind=ev_kind,
                        value=candidate.get(key),
                        subject=eid,
                        provenance="passthrough",
                        identity_bearing=True,
                    )
                )
        # Coarse fallback: single display label is identity-bearing only when
        # no richer split was provided. Body/text/url stay content.
        if not identity and label:
            identity.append(
                IdentityEvidence(
                    kind="display_name",
                    value=label,
                    subject=eid,
                    provenance="passthrough",
                    confidence=0.7,
                )
            )
        for key, ev_kind in (
            ("content_text", "content_text"),
            ("preview_text", "preview_text"),
            ("body", "body"),
            ("text", "content_text"),
            ("url", "url"),
            ("filename", "filename"),
            ("page_text", "page_text"),
            ("latest_message", "latest_message"),
        ):
            if candidate.get(key) not in (None, ""):
                # Avoid duplicating the identity label into content.
                if key == "text" and _norm(candidate.get(key)) == _norm(
                    identity[0].value if identity else ""
                ):
                    continue
                content.append(
                    IdentityEvidence(
                        kind=ev_kind,
                        value=candidate.get(key),
                        subject=eid,
                        identity_bearing=False,
                        provenance="passthrough",
                    )
                )
        if isinstance(candidate.get("urls"), (list, tuple)):
            for u in candidate["urls"]:
                if u:
                    content.append(
                        IdentityEvidence(
                            kind="url",
                            value=u,
                            subject=eid,
                            identity_bearing=False,
                            provenance="passthrough",
                        )
                    )
        relations: Dict[str, Any] = {}
        for rk in ("container", "container_id", "parent", "thread"):
            if candidate.get(rk) not in (None, ""):
                relations[rk if rk != "container_id" else "container"] = candidate.get(rk)
        for rk in ("sender", "originator", "author"):
            if candidate.get(rk) not in (None, ""):
                relations[rk] = candidate.get(rk)
                relations.setdefault("sender", candidate.get(rk))
                relations.setdefault("originator", candidate.get(rk))
                break
        # Infer self-originator from explicit You: prefixes when no sender field.
        if "sender" not in relations and label:
            import re

            if re.search(r"(?:^|[\s\-–—:])you\s*:", label, flags=re.I):
                relations["sender"] = "self"
                relations["originator"] = "self"
                identity.append(
                    IdentityEvidence(
                        kind="sender",
                        value="self",
                        subject=eid,
                        provenance="passthrough_you_prefix",
                        identity_bearing=True,
                    )
                )
        return EntityObservation(
            entity_kind=kind,
            entity_id=eid,
            label=label,
            identity_evidence=identity,
            content_evidence=content,
            relations=relations,
            raw=candidate,
        )


def _observation_from_typed_dict(candidate: Dict[str, Any]) -> EntityObservation:
    def _parse(items: Any, *, default_bearing: bool) -> List[IdentityEvidence]:
        out: List[IdentityEvidence] = []
        for item in items or []:
            if isinstance(item, IdentityEvidence):
                out.append(item)
                continue
            if not isinstance(item, dict):
                continue
            out.append(
                IdentityEvidence(
                    kind=str(item.get("kind") or item.get("relation") or ""),
                    value=item.get("value")
                    if item.get("value") is not None
                    else item.get("object"),
                    subject=str(item.get("subject") or ""),
                    confidence=float(item.get("confidence") or 1.0),
                    provenance=str(item.get("provenance") or ""),
                    identity_bearing=bool(
                        item.get("identity_bearing", default_bearing)
                    ),
                )
            )
        return out

    return EntityObservation(
        entity_kind=_norm(
            candidate.get("entity_kind") or candidate.get("kind") or ""
        ),
        entity_id=str(candidate.get("id") or candidate.get("entity_id") or ""),
        label=str(candidate.get("label") or candidate.get("title") or ""),
        identity_evidence=_parse(candidate.get("identity_evidence"), default_bearing=True),
        content_evidence=_parse(
            candidate.get("content_evidence"), default_bearing=False
        ),
        relations=dict(candidate.get("relations") or {}),
        raw=candidate,
    )


def observe_entity(candidate: Dict[str, Any]) -> EntityObservation:
    """Run registered domain providers; fall back to passthrough.

    Providers are registered by the composition root
    (``plugin.agent.composition``). Core never imports domain adapters.
    """
    if isinstance(candidate, EntityObservation):
        return candidate
    if not isinstance(candidate, dict):
        return EntityObservation(label=str(candidate or ""))
    for provider in _PROVIDERS:
        try:
            if provider.can_handle(candidate):
                return provider.observe(candidate)
        except Exception:
            continue
    return PassthroughEvidenceProvider().observe(candidate)


# Ensure passthrough exists as last-resort without requiring import side effects.
register_evidence_provider(PassthroughEvidenceProvider())


# ---------------------------------------------------------------------------
# Generic identity resolver
# ---------------------------------------------------------------------------


class IdentityResolver:
    """Evaluate whether typed evidence satisfies a role identity contract.

    Never extracts UI structure. Never imports app adapters.
    """

    def same_identity(
        self, observation: EntityObservation, referent: Any
    ) -> tuple[bool, List[EvidenceNote], List[EvidenceNote]]:
        ref = str(referent or "").strip()
        supporting: List[EvidenceNote] = []
        contradicting: List[EvidenceNote] = []
        if not ref:
            return False, supporting, [EvidenceNote("referent", detail="empty")]

        # Explicit participants: membership is decisive when present.
        participants = [
            e
            for e in observation.identity_evidence
            if e.kind == "participant" and e.identity_bearing
        ]
        if participants:
            names = {_norm(e.value) for e in participants}
            if _norm(ref) in names:
                supporting.append(EvidenceNote("participant", ref, "membership"))
                return True, supporting, contradicting
            contradicting.append(
                EvidenceNote(
                    "participant",
                    [e.value for e in participants[:6]],
                    "not_in_participants",
                )
            )
            return False, supporting, contradicting

        for ev in observation.identity_evidence:
            if not ev.identity_bearing:
                continue
            if ev.kind not in _IDENTITY_KINDS and ev.kind not in {
                "display_name",
                "title",
                "name",
            }:
                continue
            if self._values_same_identity(ev.value, ref):
                supporting.append(
                    EvidenceNote(ev.kind, ev.value, "same_identity")
                )
                return True, supporting, contradicting

        # Content evidence must NOT establish container/thread identity.
        contradicting.append(
            EvidenceNote(
                "identity",
                observation.label[:80],
                "no_identity_evidence_for_referent",
            )
        )
        return False, supporting, contradicting

    def same_content_referent(
        self, observation: EntityObservation, referent: Any
    ) -> tuple[bool, List[EvidenceNote], List[EvidenceNote]]:
        ref = str(referent or "").strip()
        supporting: List[EvidenceNote] = []
        contradicting: List[EvidenceNote] = []
        if not ref:
            return False, supporting, [EvidenceNote("referent", detail="empty")]

        # Adapter may pre-compute match (e.g. host-aware URL support).
        for ev in observation.content_evidence:
            if ev.kind in {"content_match", "query_support"}:
                if ev.value in (True, 1, "true", "yes"):
                    supporting.append(EvidenceNote(ev.kind, True, "adapter_match"))
                    return True, supporting, contradicting
                if ev.value in (False, 0, "false", "no"):
                    contradicting.append(
                        EvidenceNote(ev.kind, False, "adapter_reject")
                    )
                    return False, supporting, contradicting

        blob_parts = [
            str(ev.value)
            for ev in observation.content_evidence
            if ev.kind in _CONTENT_KINDS and ev.value not in (None, "")
        ]
        blob = " ".join(blob_parts)
        if blob and _norm(ref) in _norm(blob):
            supporting.append(EvidenceNote("content_text", ref, "supported"))
            return True, supporting, contradicting
        contradicting.append(
            EvidenceNote("content_text", blob[:120], "unsupported")
        )
        return False, supporting, contradicting

    def equals_binding(
        self,
        observation: EntityObservation,
        bound_label: Any,
    ) -> tuple[bool, List[EvidenceNote], List[EvidenceNote]]:
        bound = str(bound_label or "").strip()
        supporting: List[EvidenceNote] = []
        contradicting: List[EvidenceNote] = []
        if not bound:
            return False, supporting, [EvidenceNote("binding", detail="unbound")]
        container = (
            observation.relations.get("container")
            or observation.relations.get("parent")
            or observation.relations.get("thread")
        )
        if container is None:
            for ev in observation.identity_evidence:
                if ev.kind in {"container_id", "thread_id"} and ev.value:
                    container = ev.value
                    break
        if container is None:
            return False, supporting, [
                EvidenceNote("container", detail="missing_container_relation")
            ]
        if self._values_same_identity(container, bound):
            supporting.append(EvidenceNote("container", container, "equals_binding"))
            return True, supporting, contradicting
        contradicting.append(
            EvidenceNote("container", container, f"!= {bound}")
        )
        return False, supporting, contradicting

    def same_originator(
        self, observation: EntityObservation, referent: Any
    ) -> tuple[bool, List[EvidenceNote], List[EvidenceNote]]:
        """Sender/author/creator match — independent of container membership.

        Referent ``self`` / ``me`` / ``you`` matches UI-marked outgoing messages.
        """
        ref = str(referent or "").strip()
        supporting: List[EvidenceNote] = []
        contradicting: List[EvidenceNote] = []
        if not ref:
            return False, supporting, [EvidenceNote("referent", detail="empty")]

        want_self = self.canonical_identity(ref) == "self"
        senders = [
            e
            for e in observation.identity_evidence
            if e.kind in {"sender", "author", "creator", "originator"}
            and e.identity_bearing
        ]
        # relations.sender is also authoritative when adapters stamp it.
        rel_sender = observation.relations.get("sender") or observation.relations.get(
            "originator"
        )
        if rel_sender not in (None, ""):
            senders.append(
                IdentityEvidence(
                    kind="sender",
                    value=rel_sender,
                    identity_bearing=True,
                    provenance="relation",
                )
            )
        if not senders:
            contradicting.append(
                EvidenceNote("originator", detail="missing_sender_evidence")
            )
            return False, supporting, contradicting

        for ev in senders:
            is_self = self.canonical_identity(ev.value) == "self"
            if want_self and is_self:
                supporting.append(EvidenceNote(ev.kind, ev.value, "same_originator_self"))
                return True, supporting, contradicting
            if not want_self and not is_self and self._values_same_identity(ev.value, ref):
                supporting.append(EvidenceNote(ev.kind, ev.value, "same_originator"))
                return True, supporting, contradicting

        contradicting.append(
            EvidenceNote(
                "originator",
                [e.value for e in senders[:4]],
                f"!= {ref}",
            )
        )
        return False, supporting, contradicting

    # Pronouns / UI labels for the agent-operated account (outgoing messages).
    SELF_ALIASES = frozenset({"self", "me", "i", "you", "myself", "outgoing", "mine"})

    @classmethod
    def canonical_identity(cls, value: Any) -> str:
        """Normalize a *typed identity label*; self-aliases collapse to ``self``.

        Contract: call only on identity labels (sender, originator, contact
        name) — never on arbitrary content text. A sentence like
        ``YouTube sent you a notification`` must not become ``self``.
        """
        n = _norm(value)
        if not n:
            return ""
        # Whole-label aliases only — reject multi-word content blobs.
        if " " in n or len(n) > 24:
            return n
        if n in cls.SELF_ALIASES:
            return "self"
        return n

    @staticmethod
    def values_same_identity(value: Any, referent: Any) -> bool:
        """Public value-level identity equality — not substring-of-content.

        Distinct from :meth:`same_identity`, which scores an observation against
        a referent. Downstream modules (query matching) should call this API
        instead of the private ``_values_same_identity`` helper.

        ``self`` / ``You`` / ``me`` canonicalize to one identity.
        """
        a = IdentityResolver.canonical_identity(value)
        b = IdentityResolver.canonical_identity(referent)
        if not a or not b:
            return False
        if a == b:
            return True
        # Stable IDs often compare case-insensitively as whole tokens.
        if a.replace("-", "") == b.replace("-", "") and " " not in a:
            return True
        return False

    @staticmethod
    def _values_same_identity(value: Any, referent: Any) -> bool:
        """Internal alias for :meth:`values_same_identity`."""
        return IdentityResolver.values_same_identity(value, referent)


_DEFAULT_RESOLVER = IdentityResolver()


def identity_resolver() -> IdentityResolver:
    return _DEFAULT_RESOLVER


# ---------------------------------------------------------------------------
# Role binder (owns semantic binding validity)
# Procedure-specific RoleBindingSpec maps live under plugin.agent.procedures.
# ---------------------------------------------------------------------------


def assess_observation_for_role(
    *,
    spec: RoleBindingSpec,
    observation: EntityObservation,
    goal: Any,
    bindings: Optional[Dict[str, Any]] = None,
    task_relevance: float = 0.0,
    resolver: Optional[IdentityResolver] = None,
) -> CandidateAssessment:
    resolver = resolver or identity_resolver()
    assessment = CandidateAssessment(task_relevance=float(task_relevance or 0.0))
    et = _norm(observation.entity_kind)
    candidates = {_norm(x) for x in (observation.candidate_entity_kinds or set())}
    known = {_norm(x) for x in (spec.expected_entity_kinds or set())}
    container_kinds = {
        "conversation",
        "thread",
        "container",
        "contact",
        "folder",
        "tab",
        "event",
    }
    content_kinds = {
        "message",
        "content_item",
        "link",
        "attachment",
        "document",
        "file",
    }
    if spec.expected_entity_kinds and et:
        if spec.role == "source_object" and et in container_kinds and et not in known:
            assessment.contradicting.append(
                EvidenceNote("entity_kind", et, "invalid_for_source_object")
            )
            assessment.missing_required.append("entity_kind")
        if spec.role in {"source_container", "destination"} and et in content_kinds:
            assessment.contradicting.append(
                EvidenceNote("entity_kind", et, "invalid_for_container_role")
            )
            assessment.missing_required.append("entity_kind")
    elif spec.expected_entity_kinds and not et and candidates:
        # Ambiguous UI widget: allow if candidate set intersects expected kinds.
        if not (candidates & known):
            assessment.missing_required.append("entity_kind")
            assessment.contradicting.append(
                EvidenceNote(
                    "entity_kind",
                    sorted(candidates),
                    "candidate_kinds_miss_role",
                )
            )

    required_ok = "entity_kind" not in assessment.missing_required
    identity_hits = 0
    identity_needed = 0

    for cons in spec.identity_constraints:
        if cons.relation == "equals_binding":
            bound = _binding_label(bindings, cons.referent_source)
            effective_required = bool(cons.required or bound)
            if effective_required:
                identity_needed += 1
            if not bound:
                # Required but unbound → unpaid; confidence stays low.
                if cons.required:
                    assessment.missing_required.append(f"binding:{cons.referent_source}")
                continue
            ok, sup, contra = resolver.equals_binding(observation, bound)
            assessment.supporting.extend(sup)
            assessment.contradicting.extend(contra)
            if ok:
                identity_hits += 1
            elif effective_required:
                required_ok = False
                assessment.missing_required.append(cons.relation)
            continue

        if cons.relation == "same_identity":
            identity_needed += 1
            referent = goal_path(goal, cons.referent_source)
            if referent in (None, "") and cons.value is not None:
                referent = cons.value
            if referent in (None, ""):
                continue
            ok, sup, contra = resolver.same_identity(observation, referent)
            assessment.supporting.extend(sup)
            assessment.contradicting.extend(contra)
            if ok:
                identity_hits += 1
            elif cons.required:
                required_ok = False
                assessment.missing_required.append(cons.relation)
            continue

        if cons.relation == "same_content_referent":
            identity_needed += 1
            referent = goal_path(goal, cons.referent_source)
            if referent in (None, "") and cons.value is not None:
                referent = cons.value
            if referent in (None, ""):
                continue
            ok, sup, contra = resolver.same_content_referent(observation, referent)
            assessment.supporting.extend(sup)
            assessment.contradicting.extend(contra)
            if ok:
                identity_hits += 1
            elif cons.required:
                required_ok = False
                assessment.missing_required.append(cons.relation)
            continue

        if cons.relation == "same_originator":
            identity_needed += 1
            referent = goal_path(goal, cons.referent_source)
            if referent in (None, "") and cons.value is not None:
                referent = cons.value
            if referent in (None, ""):
                if cons.required:
                    assessment.missing_required.append("originator_referent")
                    required_ok = False
                continue
            ok, sup, contra = resolver.same_originator(observation, referent)
            assessment.supporting.extend(sup)
            assessment.contradicting.extend(contra)
            if ok:
                identity_hits += 1
            elif cons.required:
                required_ok = False
                assessment.missing_required.append(cons.relation)
            continue

    if identity_needed:
        assessment.role_identity_confidence = identity_hits / float(identity_needed)
    else:
        assessment.role_identity_confidence = 1.0 if required_ok else 0.0

    assessment.binding_eligible = bool(
        required_ok
        and assessment.role_identity_confidence + 1e-9 >= float(spec.evidence_threshold)
        and "entity_kind" not in assessment.missing_required
    )
    return assessment


def _binding_label(bindings: Optional[Dict[str, Any]], source: str) -> Any:
    if not isinstance(bindings, dict):
        return None
    raw = bindings.get(source)
    if raw is None and source == "source_container":
        raw = bindings.get("source_conversation")
    if isinstance(raw, BindingRecord):
        return raw.label or raw.entity_id
    if isinstance(raw, dict):
        return (
            raw.get("resolved_label")
            or raw.get("label")
            or raw.get("name")
            or raw.get("open_conversation")
            or raw.get("entity_id")
        )
    return raw


def assess_candidate_for_role(
    *,
    spec: RoleBindingSpec,
    candidate: Any,
    goal: Any,
    bindings: Optional[Dict[str, Any]] = None,
    task_relevance: float = 0.0,
    resolver: Optional[IdentityResolver] = None,
) -> CandidateAssessment:
    """Observe (via providers) then assess. Providers own domain extraction."""
    if isinstance(candidate, EntityObservation):
        observation = candidate
    else:
        observation = observe_entity(dict(candidate or {}))
    return assess_observation_for_role(
        spec=spec,
        observation=observation,
        goal=goal,
        bindings=bindings,
        task_relevance=task_relevance,
        resolver=resolver,
    )


def propose_binding(
    *,
    spec: RoleBindingSpec,
    candidate: Any,
    goal: Any,
    bindings: Optional[Dict[str, Any]] = None,
    task_relevance: float = 0.0,
    resolver: Optional[IdentityResolver] = None,
) -> BindingProposal:
    if isinstance(candidate, EntityObservation):
        observation = candidate
    else:
        observation = observe_entity(dict(candidate or {}))
    assessment = assess_observation_for_role(
        spec=spec,
        observation=observation,
        goal=goal,
        bindings=bindings,
        task_relevance=task_relevance,
        resolver=resolver,
    )
    return BindingProposal(
        role=spec.role,
        candidate_id=observation.entity_id,
        candidate_label=observation.label
        or str(
            next(
                (
                    e.value
                    for e in observation.identity_evidence
                    if e.kind in {"display_name", "title", "name"}
                ),
                "",
            )
        ),
        supporting_evidence=list(assessment.supporting),
        contradicting_evidence=list(assessment.contradicting),
        required_constraints_satisfied=bool(assessment.binding_eligible),
        confidence=float(assessment.role_identity_confidence),
        task_relevance=float(assessment.task_relevance),
        assessment=assessment,
    )


class RoleBinder:
    """Owns semantic binding validity. ACT asks this; does not re-implement it."""

    def __init__(self, resolver: Optional[IdentityResolver] = None):
        self.resolver = resolver or identity_resolver()

    def propose(
        self,
        *,
        role: str,
        candidate: Any,
        goal: Any,
        bindings: Optional[Dict[str, Any]] = None,
        task_relevance: float = 0.0,
        specs: Optional[Dict[str, RoleBindingSpec]] = None,
    ) -> BindingProposal:
        if specs is None:
            from plugin.agent.procedures.forward_message import role_specs_for_goal

            specs = role_specs_for_goal(goal)
        spec = specs.get(role) or RoleBindingSpec(role=role)
        return propose_binding(
            spec=spec,
            candidate=candidate,
            goal=goal,
            bindings=bindings,
            task_relevance=task_relevance,
            resolver=self.resolver,
        )

    def binding_from_proposal(self, proposal: BindingProposal) -> BindingRecord:
        return BindingRecord(
            role=proposal.role,
            entity_id=proposal.candidate_id,
            label=proposal.candidate_label,
            status="provisional" if proposal.required_constraints_satisfied else "unresolved",
            confidence=proposal.confidence,
            evidence=[e.detail for e in proposal.supporting_evidence if e.detail],
        )

    def action_allowed(
        self,
        *,
        role: str,
        target: str,
        binding: Optional[BindingRecord] = None,
        # Bind path only (resolve / establish). Not for routine ACT.
        candidate: Any = None,
        goal: Any = None,
        bindings: Optional[Dict[str, Any]] = None,
        allow_propose: bool = False,
        allow_exploratory_open: bool = True,
        task_relevance: float = 0.0,
    ) -> tuple[bool, str, Optional[BindingProposal]]:
        """ACT: consume valid binding. Bind path may propose when allowed.

        Authoritative bind still requires identity contracts. Safe exploratory
        open of a high-recall content match may proceed as a provisional
        relational candidate without claiming a confirmed role binding.
        """
        if binding is not None and binding.is_valid():
            if binding.matches_target(target):
                return True, "binding_valid", None
            return False, "target_does_not_match_valid_binding", None
        if allow_propose and candidate is not None and goal is not None:
            proposal = self.propose(
                role=role,
                candidate=candidate,
                goal=goal,
                bindings=bindings,
                task_relevance=task_relevance,
            )
            if proposal.required_constraints_satisfied:
                return True, "bind_then_act", proposal
            # Provisional relational candidate: content matches source_query
            # while container binding is unresolved. Does NOT authorize opening
            # a brand/contact-shaped row on content match alone (that remains
            # a source_container identity failure). Safe for message/link
            # entities and for source_object acts.
            if allow_exploratory_open:
                obs = (
                    candidate
                    if isinstance(candidate, EntityObservation)
                    else observe_entity(dict(candidate or {}))
                )
                query = goal_path(goal, "goal.source_query")
                originator = goal_path(goal, "goal.originator")
                kind = _norm(obs.entity_kind)
                content_kinds = {
                    "message",
                    "link",
                    "content_item",
                    "attachment",
                    "document",
                }
                if query:
                    ok_c, _, _ = self.resolver.same_content_referent(obs, query)
                    ok_o = True
                    if originator not in (None, ""):
                        ok_o, _, _ = self.resolver.same_originator(obs, originator)
                    if (
                        ok_c
                        and ok_o
                        and (role == "source_object" or kind in content_kinds)
                    ):
                        return True, "provisional_relational_open", proposal
            return False, "identity_contract_unsatisfied", proposal
        return False, "no_valid_binding", None

    def commit_effect(
        self,
        execution_state: Any,
        *,
        proposal: BindingProposal,
        forward_task: Optional[Dict[str, Any]] = None,
        evidence: str = "settled_destination_verified",
    ) -> Optional[Dict[str, Any]]:
        """Authoritative commit API for settled effect → role binding."""
        return _commit_effect_binding(
            execution_state,
            proposal=proposal,
            forward_task=forward_task,
            evidence=evidence,
        )


def role_for_action_family(family: str, *, phase: str = "", **kwargs: Any) -> str:
    """DEPRECATED shim — import procedures.forward_message.role_for_action_family."""
    from plugin.agent.procedures.forward_message import (
        role_for_action_family as _proc_role,
    )

    return _proc_role(family, phase=phase, **kwargs)


def verify_bound_identity(
    *,
    role: str,
    world_fact: Any,
    goal: Any,
    bindings: Optional[Dict[str, Any]] = None,
) -> tuple[bool, BindingProposal]:
    """Post-action continuity: world evidence must still support the role.

    DELETE_TICKET(forward_shims): callers should pass ``RoleBindingSpec`` from
    the active procedure rather than loading forward_message here.
    """
    from plugin.agent.procedures.forward_message import role_specs_for_goal

    specs = role_specs_for_goal(goal)
    spec = specs.get(role) or RoleBindingSpec(role=role)
    proposal = propose_binding(
        spec=spec,
        candidate=world_fact,
        goal=goal,
        bindings=bindings,
        task_relevance=0.0,
    )
    return bool(proposal.required_constraints_satisfied), proposal


def record_negative_evidence(
    execution_state: Any,
    *,
    role: str,
    candidate_label: str,
    reason: str = REFERENT_MISMATCH,
    attempt_id: str = "",
) -> None:
    if execution_state is None:
        return
    aid = str(
        attempt_id
        or getattr(execution_state, "active_attempt_id", "")
        or getattr(execution_state, "last_effect_attempt_id", "")
        or ""
    ).strip()
    key = f"{_norm(role)}|{_norm(candidate_label)}"
    if aid:
        key = f"{key}|{aid}"
    try:
        bag = getattr(execution_state, "binding_negative_evidence", None)
        if not isinstance(bag, dict):
            bag = {}
        entry = dict(bag.get(key) or {})
        entry["role"] = role
        entry["label"] = candidate_label
        entry["reason"] = reason
        entry["attempt_id"] = aid
        entry["count"] = int(entry.get("count") or 0) + 1
        bag[key] = entry
        execution_state.binding_negative_evidence = bag
    except Exception:
        pass
    try:
        closure = dict(getattr(execution_state, "last_effect_closure", None) or {})
        modes = list(closure.get("modes") or [])
        if REFERENT_MISMATCH not in modes and "referent_mismatch" not in modes:
            modes.append("referent_mismatch")
            modes.append(REFERENT_MISMATCH)
        closure["modes"] = modes
        closure["referent_mismatch_role"] = role
        closure["referent_mismatch_label"] = str(candidate_label or "")[:160]
        if aid:
            closure["referent_mismatch_attempt_id"] = aid
        if _norm(role) in {"source_container", "destination"}:
            closure["referent_repair_owed"] = False
            closure["referent_search_needed"] = True
            closure["retrieve_ready"] = False
        else:
            closure["referent_repair_owed"] = True
        execution_state.last_effect_closure = closure
    except Exception:
        pass


def is_negatively_evidenced(
    execution_state: Any, *, role: str, candidate_label: str
) -> bool:
    if execution_state is None:
        return False
    key = f"{_norm(role)}|{_norm(candidate_label)}"
    bag = getattr(execution_state, "binding_negative_evidence", None)
    if not isinstance(bag, dict):
        return False
    return key in bag


def apply_referent_mismatch(
    execution_state: Any,
    *,
    role: str,
    candidate_label: str,
    forward_task: Optional[Dict[str, Any]] = None,
    attempt_id: str = "",
) -> Optional[Dict[str, Any]]:
    record_negative_evidence(
        execution_state,
        role=role,
        candidate_label=candidate_label,
        attempt_id=attempt_id,
    )
    if not isinstance(forward_task, dict):
        return forward_task
    try:
        from plugin.agent.task_binding import ForwardTaskState

        state = ForwardTaskState.from_dict(forward_task)
        slot = {
            "source_container": "source_conversation",
            "source_object": "source_object",
            "destination": "destination",
        }.get(role, role)
        b = state.binding(slot)
        b.status = "invalidated"
        b.resolved_entity_id = None
        b.confidence = 0.0
        b.evidence = list(b.evidence or []) + [
            f"{REFERENT_MISMATCH}:{candidate_label[:80]}"
        ]
        state.invalidate_downstream_of(slot)
        state.binding_repair = True
        state.local_objective = f"repair {slot} after {REFERENT_MISMATCH}"
        state.derive_phase(leftover=False)
        return state.to_dict()
    except Exception:
        return forward_task


def note_transition_pending(
    execution_state: Any,
    *,
    establishes_roles: Optional[list] = None,
    target_label: str = "",
    reason: str = "expected_transition_not_settled_yet",
    attempt_id: str = "",
) -> None:
    """Record a non-terminal early-frame miss for one navigation/open attempt.

    Requires an explicit ``attempt_id`` from the Action — ambient ExecutionState
    ids are never used (would reintroduce cross-attempt attribution).
    Foreign mismatch debt for another attempt stays; same-attempt provisional
    mismatch may be retracted (unsettled frame does not owe SEARCH).
    """
    if execution_state is None:
        return
    aid = str(attempt_id or "").strip()
    if not aid:
        return
    try:
        closure = dict(getattr(execution_state, "last_effect_closure", None) or {})
        modes = list(closure.get("modes") or [])
        if reason not in modes:
            modes.append(reason)
        closure["modes"] = modes
        closure["transition_pending"] = True
        closure["pending_attempt_id"] = aid
        closure["pending_establishes_roles"] = [
            str(r) for r in (establishes_roles or []) if str(r).strip()
        ]
        if target_label:
            closure["pending_open_target"] = str(target_label)[:160]
        try:
            closure["pending_since_frame"] = int(
                getattr(execution_state, "unified_frame", 0) or 0
            )
        except Exception:
            closure["pending_since_frame"] = 0
        # Retract only this attempt's own provisional mismatch — never foreign debt.
        mismatch_aid = str(closure.get("referent_mismatch_attempt_id") or "").strip()
        if mismatch_aid and mismatch_aid == aid:
            modes = [
                m
                for m in list(closure.get("modes") or [])
                if str(m) not in {REFERENT_MISMATCH, "referent_mismatch"}
            ]
            closure["modes"] = modes
            closure.pop("referent_search_needed", None)
            closure.pop("referent_mismatch_role", None)
            closure.pop("referent_mismatch_label", None)
            closure.pop("referent_mismatch_attempt_id", None)
            closure["referent_repair_owed"] = False
            # Negative evidence stays but is no longer terminal until settle.
            try:
                bag = getattr(execution_state, "binding_negative_evidence", None)
                if isinstance(bag, dict):
                    for entry in bag.values():
                        if not isinstance(entry, dict):
                            continue
                        if str(entry.get("attempt_id") or "").strip() != aid:
                            continue
                        if str(entry.get("status") or "") == "superseded":
                            continue
                        entry["status"] = "pending_settle"
            except Exception:
                pass
        execution_state.last_effect_closure = closure
    except Exception:
        pass


def clear_referent_mismatch_debt(
    execution_state: Any,
    *,
    role: str = "source_container",
    verified_label: str = "",
    attempt_id: str = "",
) -> bool:
    """Supersede pending / mismatch debt for one attempt only.

    Requires explicit ``attempt_id`` (Action-scoped). Ambient ExecutionState
    fallback is forbidden. Pending and mismatch ids checked independently.
    """
    if execution_state is None:
        return False
    role_n = _norm(role)
    aid = str(attempt_id or "").strip()
    if not aid:
        return False
    cleared = False
    try:
        closure = dict(getattr(execution_state, "last_effect_closure", None) or {})
        pending_aid = str(closure.get("pending_attempt_id") or "").strip()
        mismatch_aid = str(closure.get("referent_mismatch_attempt_id") or "").strip()
        if not aid:
            return False
        if pending_aid == aid:
            closure["transition_pending"] = False
            closure.pop("pending_establishes_roles", None)
            closure.pop("pending_open_target", None)
            closure.pop("pending_attempt_id", None)
            modes = [
                m
                for m in list(closure.get("modes") or [])
                if str(m) != "expected_transition_not_settled_yet"
            ]
            closure["modes"] = modes
            cleared = True
        if mismatch_aid == aid:
            if _norm(closure.get("referent_mismatch_role")) == role_n or not closure.get(
                "referent_mismatch_role"
            ):
                closure.pop("referent_mismatch_role", None)
                closure.pop("referent_mismatch_label", None)
                closure.pop("referent_mismatch_attempt_id", None)
                closure["referent_search_needed"] = False
                closure["referent_repair_owed"] = False
                modes = [
                    m
                    for m in list(closure.get("modes") or [])
                    if str(m) not in {REFERENT_MISMATCH, "referent_mismatch"}
                ]
                closure["modes"] = modes
                cleared = True
        if not cleared:
            return False
        if verified_label:
            closure["verified_container_label"] = str(verified_label)[:160]
        execution_state.last_effect_closure = closure
    except Exception:
        return False
    # Supersede (do not delete) negative evidence for this attempt_id + role.
    try:
        bag = getattr(execution_state, "binding_negative_evidence", None)
        if isinstance(bag, dict) and aid:
            for _key, entry in bag.items():
                if not isinstance(entry, dict):
                    continue
                if _norm(entry.get("role")) != role_n:
                    continue
                if str(entry.get("attempt_id") or "").strip() != aid:
                    continue
                entry["status"] = "superseded"
                entry["superseded_by"] = (
                    f"verified:{verified_label[:80]}" if verified_label else aid
                )
            execution_state.binding_negative_evidence = bag
    except Exception:
        pass
    return True


def _commit_effect_binding(
    execution_state: Any,
    *,
    proposal: BindingProposal,
    forward_task: Optional[Dict[str, Any]] = None,
    evidence: str = "settled_destination_verified",
) -> Optional[Dict[str, Any]]:
    """Internal implementation — production callers use ``RoleBinder.commit_effect``.

    Writes a ``BindingRecord`` and syncs ``ForwardTaskState``. Never touches
    ``source_object`` when committing ``source_container``. Confirmed status
    requires ``resolved_entity_id`` or ``resolved_label``.
    """
    if proposal is None or not proposal.required_constraints_satisfied:
        return forward_task
    role = str(proposal.role or "").strip()
    label = str(proposal.candidate_label or "").strip()
    if not role or not label:
        return forward_task
    if _norm(role) == "source_object":
        return forward_task
    record = BindingRecord(
        role=role,
        entity_id=str(proposal.candidate_id or ""),
        label=label,
        status="confirmed",
        confidence=max(float(proposal.confidence or 0.0), 0.9),
        evidence=[e.detail for e in (proposal.supporting_evidence or []) if e.detail]
        + [f"{evidence}:{label[:80]}"],
    )
    try:
        bag = getattr(execution_state, "role_bindings", None)
        if not isinstance(bag, dict):
            bag = {}
        bag[role] = record.to_dict() if hasattr(record, "to_dict") else {
            "role": record.role,
            "entity_id": record.entity_id,
            "label": record.label,
            "status": record.status,
            "confidence": record.confidence,
            "evidence": list(record.evidence or []),
        }
        if execution_state is not None:
            execution_state.role_bindings = bag
    except Exception:
        pass
    if not isinstance(forward_task, dict):
        return forward_task
    try:
        from plugin.agent.task_binding import ForwardTaskState

        state = ForwardTaskState.from_dict(forward_task)
        slot = {
            "source_container": "source_conversation",
            "source_object": "source_object",
            "destination": "destination",
        }.get(role, role)
        if slot == "source_object":
            return forward_task
        b = state.binding(slot)
        eid = None
        try:
            if str(proposal.candidate_id or "").strip().isdigit():
                eid = int(proposal.candidate_id)
        except (TypeError, ValueError):
            eid = None
        b.resolved_entity_id = eid
        b.resolved_label = label[:160]
        b.status = "confirmed"
        b.confidence = max(float(b.confidence or 0.0), float(record.confidence or 0.9))
        b.evidence = list(b.evidence or []) + [f"{evidence}:{label[:80]}"]
        if slot == "source_conversation":
            state.predicates.source_conversation_open = True
        state.binding_repair = False
        state.derive_phase(leftover=False)
        return state.to_dict()
    except Exception:
        return forward_task


def commit_effect_binding(
    execution_state: Any,
    *,
    proposal: BindingProposal,
    forward_task: Optional[Dict[str, Any]] = None,
    evidence: str = "settled_destination_verified",
) -> Optional[Dict[str, Any]]:
    """Deprecated compatibility shim — routes through ``RoleBinder.commit_effect``."""
    return RoleBinder().commit_effect(
        execution_state,
        proposal=proposal,
        forward_task=forward_task,
        evidence=evidence,
    )


def confirm_established_role(
    forward_task: Optional[Dict[str, Any]],
    *,
    role: str,
    label: str,
    evidence: str = "settled_destination_verified",
    execution_state: Any = None,
    proposal: Optional[BindingProposal] = None,
) -> Optional[Dict[str, Any]]:
    """Back-compat wrapper — prefer ``RoleBinder.commit_effect`` with a proposal."""
    binder = RoleBinder()
    if proposal is not None:
        return binder.commit_effect(
            execution_state,
            proposal=proposal,
            forward_task=forward_task,
            evidence=evidence,
        )
    fake = BindingProposal(
        role=role,
        candidate_id="",
        candidate_label=label,
        confidence=0.9,
        required_constraints_satisfied=True,
        supporting_evidence=[],
    )
    return binder.commit_effect(
        execution_state,
        proposal=fake,
        forward_task=forward_task,
        evidence=evidence,
    )


# Back-compat aliases used by earlier wiring / tests.
Evidence = EvidenceNote
RoleBindingPolicy = RoleBindingSpec
