"""Information capability providers — substrates for MetaActor SEARCH.

Brain/MetaActor requests evidence kinds; providers decide how to obtain them.
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
    """L1 / session working context — no world I/O."""

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
                h.context.l1_preferred = True
                h.context.working_context_hit = True
                h.gather_notes.append("working_context_prefer")
                hits.append(h.entity_id)
        if hits:
            return EvidenceResult(
                status=EVIDENCE_FOUND,
                provider_id=self.provider_id,
                evidence_kind=evidence_kind,
                payload={"preferred_entity_ids": hits},
            )
        return EvidenceResult(
            status=NO_EVIDENCE,
            provider_id=self.provider_id,
            evidence_kind=evidence_kind,
            notes="no_l1_match",
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
        updated = 0
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
                h.salience.frequency_known = bool(meta.get("frequency_known"))
                if h.salience.frequency_known:
                    h.salience.frequency = min(1.0, float(agg.count_30d or 0) / 50.0)
                if agg.last_interaction_at and not h.salience.last_interaction_at:
                    h.salience.last_interaction_at = float(agg.last_interaction_at)
                    days = max(
                        0.0,
                        (time.time() - float(agg.last_interaction_at)) / 86400.0,
                    )
                    h.salience.recency = max(0.0, 1.0 - days / 180.0)
                h.gather_notes.append(
                    f"aggregate freq_known={h.salience.frequency_known} "
                    f"recency={h.salience.recency:.2f}"
                )
                updated += 1
            except Exception as exc:
                h.gather_notes.append(f"aggregate_error:{exc}")
        if updated:
            return EvidenceResult(
                status=EVIDENCE_FOUND,
                provider_id=self.provider_id,
                evidence_kind=evidence_kind,
                payload={"updated": updated},
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
        found = 0
        for h in hypotheses:
            if not isinstance(h, IdentityHypothesis):
                continue
            try:
                h.context.reference_support = float(
                    self.memory.recent_reference_support(surface, h.entity_id) or 0.0
                )
                h.gather_notes.append(
                    f"reference_support={h.context.reference_support:.2f}"
                )
                if h.context.reference_support > 0:
                    found += 1
            except Exception as exc:
                h.gather_notes.append(f"reference_error:{exc}")
        if found:
            return EvidenceResult(
                status=EVIDENCE_FOUND,
                provider_id=self.provider_id,
                evidence_kind=evidence_kind,
                payload={"supported": found},
            )
        return EvidenceResult(
            status=NO_EVIDENCE,
            provider_id=self.provider_id,
            evidence_kind=evidence_kind,
        )


@dataclass
class WhatsAppContactEvidenceProvider:
    """Structured WhatsApp contact activity — information substrate, not Brain."""

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

        now = time.time()
        updated = 0
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
            # Optional frequency if bridge exposes real counts (never unread→freq)
            if hit.get("interaction_count_30d") is not None and hit.get(
                "frequency_known"
            ):
                try:
                    h.salience.frequency_known = True
                    h.salience.frequency = min(
                        1.0, float(hit["interaction_count_30d"]) / 50.0
                    )
                    h.gather_notes.append(f"wa_contacts:freq={h.salience.frequency:.2f}")
                    updated += 1
                except (TypeError, ValueError):
                    pass
            last = hit.get("last_interaction_at")
            if last is None:
                h.gather_notes.append("wa_contacts:no_timestamp")
                continue
            try:
                last_f = float(last)
            except (TypeError, ValueError):
                continue
            h.salience.last_interaction_at = last_f
            days = max(0.0, (now - last_f) / 86400.0)
            h.salience.recency = max(0.0, 1.0 - days / 180.0)
            h.gather_notes.append(f"wa_contacts:recency={h.salience.recency:.3f}")
            updated += 1

        if updated:
            return EvidenceResult(
                status=EVIDENCE_FOUND,
                provider_id=self.provider_id,
                evidence_kind=evidence_kind,
                payload={"updated": updated},
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
