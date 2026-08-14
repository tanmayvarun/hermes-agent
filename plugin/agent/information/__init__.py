"""Information capability providers — substrates for MetaActor SEARCH.

Providers return EvidenceResult payloads only. They must not mutate Brain
hypotheses; domain EvidenceStrategy.incorporate applies interpretation.
WhatsApp HTTP lives here, not under agent/brain/.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

from plugin.agent.brain.identity_hypothesis import IdentityHypothesis
from plugin.agent.brain.information_need import (
    EVIDENCE_FOUND,
    ERROR,
    NO_CAPABILITY,
    NO_EVIDENCE,
    EvidenceResult,
    InformationNeed,
)

logger = logging.getLogger(__name__)


class InformationEvidenceProvider(Protocol):
    provider_id: str
    evidence_kinds: frozenset[str]

    def can_serve(self, need: InformationNeed, evidence_kind: str) -> bool: ...

    def probe(
        self,
        need: InformationNeed,
        *,
        evidence_kind: str,
        hypotheses: list[Any],
    ) -> EvidenceResult: ...


@dataclass
class WorkingContextEvidenceProvider:
    """L1 / session working context — returns preferred ids; no hyp mutation."""

    provider_id: str = "working_context"
    evidence_kinds: frozenset[str] = frozenset({"working_context"})

    def can_serve(self, need: InformationNeed, evidence_kind: str) -> bool:
        return evidence_kind in self.evidence_kinds

    def probe(
        self,
        need: InformationNeed,
        *,
        evidence_kind: str,
        hypotheses: list[Any],
    ) -> EvidenceResult:
        wc = dict(need.context.get("working_context") or {})
        l1 = str(wc.get("recent_entity_name") or wc.get("recent_entity") or "").lower()
        lid = str(wc.get("recent_entity_id") or "")
        hits: list[str] = []
        for h in hypotheses:
            if not isinstance(h, IdentityHypothesis):
                continue
            if (lid and h.entity_id == lid) or (
                l1 and l1 in (h.display_name or "").lower()
            ):
                hits.append(h.entity_id)
        if hits:
            return EvidenceResult(
                status=EVIDENCE_FOUND,
                provider_id=self.provider_id,
                evidence_kind=evidence_kind,
                payload={"preferred_entity_ids": hits, "l1_name": l1, "l1_id": lid},
            )
        return EvidenceResult(
            status=NO_EVIDENCE,
            provider_id=self.provider_id,
            evidence_kind=evidence_kind,
            notes="no_l1_match",
            payload={"l1_name": l1, "l1_id": lid},
        )


@dataclass
class MemoryAggregateEvidenceProvider:
    provider_id: str = "memory_aggregates"
    evidence_kinds: frozenset[str] = frozenset({"memory_aggregates"})
    memory: Any = None

    def can_serve(self, need: InformationNeed, evidence_kind: str) -> bool:
        return evidence_kind in self.evidence_kinds and self.memory is not None

    def probe(
        self,
        need: InformationNeed,
        *,
        evidence_kind: str,
        hypotheses: list[Any],
    ) -> EvidenceResult:
        if self.memory is None or not hasattr(self.memory, "get_aggregate"):
            return EvidenceResult(
                status=NO_CAPABILITY,
                provider_id=self.provider_id,
                evidence_kind=evidence_kind,
                notes="no_aggregate_api",
            )
        by_entity: dict[str, dict[str, Any]] = {}
        for h in hypotheses:
            if not isinstance(h, IdentityHypothesis):
                continue
            try:
                ent = (
                    self.memory.get_entity(h.entity_id)
                    if hasattr(self.memory, "get_entity")
                    else None
                )
                scope = getattr(ent, "scope", "personal") if ent else "personal"
                agg = self.memory.get_aggregate("user:local", h.entity_id, scope=scope)
                if agg is None:
                    continue
                meta = dict(agg.metadata or {})
                by_entity[h.entity_id] = {
                    "frequency_known": bool(meta.get("frequency_known")),
                    "count_30d": float(agg.count_30d or 0),
                    "last_interaction_at": (
                        float(agg.last_interaction_at)
                        if agg.last_interaction_at
                        else None
                    ),
                }
            except Exception as exc:
                by_entity[h.entity_id] = {"error": str(exc)}
        if by_entity:
            return EvidenceResult(
                status=EVIDENCE_FOUND,
                provider_id=self.provider_id,
                evidence_kind=evidence_kind,
                payload={"by_entity": by_entity},
            )
        return EvidenceResult(
            status=NO_EVIDENCE,
            provider_id=self.provider_id,
            evidence_kind=evidence_kind,
        )


@dataclass
class MemoryReferenceHistoryProvider:
    provider_id: str = "reference_history"
    evidence_kinds: frozenset[str] = frozenset({"reference_history"})
    memory: Any = None

    def can_serve(self, need: InformationNeed, evidence_kind: str) -> bool:
        return evidence_kind in self.evidence_kinds and self.memory is not None

    def probe(
        self,
        need: InformationNeed,
        *,
        evidence_kind: str,
        hypotheses: list[Any],
    ) -> EvidenceResult:
        if self.memory is None or not hasattr(self.memory, "recent_reference_support"):
            return EvidenceResult(
                status=NO_CAPABILITY,
                provider_id=self.provider_id,
                evidence_kind=evidence_kind,
                notes="no_reference_api",
            )
        surface = need.subject
        by_entity: dict[str, float] = {}
        for h in hypotheses:
            if not isinstance(h, IdentityHypothesis):
                continue
            try:
                by_entity[h.entity_id] = float(
                    self.memory.recent_reference_support(surface, h.entity_id) or 0.0
                )
            except Exception:
                by_entity[h.entity_id] = 0.0
        if any(v > 0 for v in by_entity.values()):
            return EvidenceResult(
                status=EVIDENCE_FOUND,
                provider_id=self.provider_id,
                evidence_kind=evidence_kind,
                payload={"reference_support_by_entity": by_entity},
            )
        return EvidenceResult(
            status=NO_EVIDENCE,
            provider_id=self.provider_id,
            evidence_kind=evidence_kind,
            payload={"reference_support_by_entity": by_entity},
        )


@dataclass
class WhatsAppContactEvidenceProvider:
    """Structured WhatsApp contact activity — raw payload only."""

    provider_id: str = "whatsapp_contacts"
    evidence_kinds: frozenset[str] = frozenset({"channel_activity"})
    bridge_base_url: str = "http://127.0.0.1:3000"
    timeout_s: float = 2.0
    enabled: bool = True

    def can_serve(self, need: InformationNeed, evidence_kind: str) -> bool:
        if not self.enabled:
            return False
        channel = str(need.context.get("channel") or "").lower()
        if channel and channel not in {"whatsapp", "wa", ""}:
            return False
        return evidence_kind in self.evidence_kinds

    def probe(
        self,
        need: InformationNeed,
        *,
        evidence_kind: str,
        hypotheses: list[Any],
    ) -> EvidenceResult:
        if not self.enabled:
            return EvidenceResult(
                status=NO_CAPABILITY,
                provider_id=self.provider_id,
                evidence_kind=evidence_kind,
                notes="disabled",
            )
        try:
            req = urllib.request.Request(
                f"{self.bridge_base_url.rstrip('/')}/contacts", method="GET"
            )
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            return EvidenceResult(
                status=ERROR,
                provider_id=self.provider_id,
                evidence_kind=evidence_kind,
                notes=str(exc),
            )

        by_jid: dict[str, dict[str, Any]] = {}
        by_name: dict[str, dict[str, Any]] = {}
        for c in payload.get("contacts") or []:
            jid = str(c.get("external_id") or "")
            name = str(c.get("display_name") or "").strip().lower()
            if jid:
                by_jid[jid] = c
            if name:
                by_name[name] = c

        by_entity: dict[str, dict[str, Any]] = {}
        for h in hypotheses:
            if not isinstance(h, IdentityHypothesis):
                continue
            hit = None
            for jid in h.channel.external_ids:
                if jid in by_jid:
                    hit = by_jid[jid]
                    break
            if hit is None:
                hit = by_name.get((h.display_name or "").strip().lower())
            if hit is None:
                continue
            entry: dict[str, Any] = {}
            if hit.get("last_interaction_at") is not None:
                try:
                    entry["last_interaction_at"] = float(hit["last_interaction_at"])
                except (TypeError, ValueError):
                    pass
            if hit.get("interaction_count_30d") is not None and hit.get("frequency_known"):
                try:
                    entry["interaction_count_30d"] = float(hit["interaction_count_30d"])
                    entry["frequency_known"] = True
                except (TypeError, ValueError):
                    pass
            if entry:
                by_entity[h.entity_id] = entry

        if by_entity:
            return EvidenceResult(
                status=EVIDENCE_FOUND,
                provider_id=self.provider_id,
                evidence_kind=evidence_kind,
                payload={"by_entity": by_entity},
            )
        return EvidenceResult(
            status=NO_EVIDENCE,
            provider_id=self.provider_id,
            evidence_kind=evidence_kind,
            notes="no_matching_contacts",
        )


@dataclass
class InformationCapabilityRegistry:
    """Maps InformationNeed evidence kinds → available providers."""

    providers: list[Any] = field(default_factory=list)

    def register(self, provider: Any) -> None:
        self.providers.append(provider)

    def providers_for(self, need: InformationNeed, evidence_kind: str) -> list[Any]:
        return [
            p
            for p in self.providers
            if evidence_kind in getattr(p, "evidence_kinds", frozenset())
            and p.can_serve(need, evidence_kind)
        ]

    def select_provider(
        self,
        need: InformationNeed,
        *,
        preferred_kinds: list[str],
        attempted_pairs: set[tuple[str, str]],
        blacklisted: Optional[set[str]] = None,
    ) -> Optional[tuple[str, Any]]:
        """Next (kind, provider) that has not been attempted.

        V1 order: preferred kinds, then registration order within kind.
        Does not exhaust a kind after a single weak/empty provider.
        """
        blocked = set(blacklisted or ())
        for kind in preferred_kinds:
            for p in self.providers_for(need, kind):
                pid = str(getattr(p, "provider_id", "") or "")
                if not pid or pid in blocked:
                    continue
                if (kind, pid) in attempted_pairs:
                    continue
                return kind, p
        return None


def default_registry_for_entity_resolution(
    memory: Any,
    *,
    world_probes: bool = True,
    bridge_base_url: str = "http://127.0.0.1:3000",
) -> InformationCapabilityRegistry:
    reg = InformationCapabilityRegistry()
    reg.register(WorkingContextEvidenceProvider())
    reg.register(MemoryAggregateEvidenceProvider(memory=memory))
    reg.register(MemoryReferenceHistoryProvider(memory=memory))
    reg.register(
        WhatsAppContactEvidenceProvider(
            bridge_base_url=bridge_base_url, enabled=world_probes
        )
    )
    return reg
