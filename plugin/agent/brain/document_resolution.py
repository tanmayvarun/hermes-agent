"""Document-resolution EvidenceStrategy — proves the generic episode is domain-neutral.

Uses DocumentHypothesis only. Providers return EvidenceResult; strategy.incorporate
updates hypotheses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from plugin.agent.brain.evidence_acquisition import run_evidence_acquisition
from plugin.agent.brain.information_need import (
    EVIDENCE_FOUND,
    EvidenceAcquisitionEpisode,
    EvidenceNeedAssessment,
    EvidenceResult,
    InformationNeed,
    NO_EVIDENCE,
)
from plugin.agent.information import InformationCapabilityRegistry


@dataclass
class DocumentHypothesis:
    """Minimal document candidate for document_resolution strategies."""

    doc_id: str
    title: str
    path: str = ""
    working_context_hit: bool = False
    recent_file_hit: bool = False
    filesystem_mtime_rank: float = 0.0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "title": self.title,
            "path": self.path,
            "working_context_hit": self.working_context_hit,
            "recent_file_hit": self.recent_file_hit,
            "filesystem_mtime_rank": self.filesystem_mtime_rank,
            "notes": list(self.notes),
        }


class DocumentResolutionEvidenceStrategy:
    def incorporate(
        self,
        result: EvidenceResult,
        hypotheses: list[Any],
        *,
        need: InformationNeed,
    ) -> list[Any]:
        if result.status != EVIDENCE_FOUND:
            return list(hypotheses)
        payload = dict(result.payload or {})
        kind = result.evidence_kind
        for h in hypotheses:
            if not isinstance(h, DocumentHypothesis):
                continue
            if kind == "working_context":
                hits = set(payload.get("preferred_doc_ids") or [])
                if h.doc_id in hits:
                    h.working_context_hit = True
                    h.notes.append("working_context_doc")
            elif kind == "recent_file_memory":
                hits = set(payload.get("recent_doc_ids") or [])
                if h.doc_id in hits:
                    h.recent_file_hit = True
                    h.notes.append("recent_file_memory")
            elif kind == "filesystem_metadata":
                ranks = dict(payload.get("mtime_rank_by_id") or {})
                if h.doc_id in ranks:
                    h.filesystem_mtime_rank = float(ranks[h.doc_id])
                    h.notes.append(f"mtime={h.filesystem_mtime_rank:.2f}")
        return list(hypotheses)

    def assess(
        self,
        need: InformationNeed,
        hypotheses: list[Any],
        *,
        last_result: Optional[EvidenceResult] = None,
        attempted_pairs: Optional[set[tuple[str, str]]] = None,
    ) -> EvidenceNeedAssessment:
        hyps = [h for h in hypotheses if isinstance(h, DocumentHypothesis)]
        pairs = set(attempted_pairs or ())
        attempted_kinds = {k for k, _ in pairs}

        wc = [h for h in hyps if h.working_context_hit]
        if len(wc) == 1:
            return EvidenceNeedAssessment(
                resolved=True,
                resolution_ref=wc[0].doc_id,
                resolution_reason="working_context_document",
            )

        recent = [h for h in hyps if h.recent_file_hit]
        if len(recent) == 1 and "recent_file_memory" in attempted_kinds:
            return EvidenceNeedAssessment(
                resolved=True,
                resolution_ref=recent[0].doc_id,
                resolution_reason="recent_file_memory",
            )

        if "filesystem_metadata" in attempted_kinds and hyps:
            ranked = sorted(hyps, key=lambda h: h.filesystem_mtime_rank, reverse=True)
            if (
                len(ranked) >= 2
                and ranked[0].filesystem_mtime_rank
                >= ranked[1].filesystem_mtime_rank + 0.4
            ):
                return EvidenceNeedAssessment(
                    resolved=True,
                    resolution_ref=ranked[0].doc_id,
                    resolution_reason="filesystem_mtime_dominance",
                )
            if len(ranked) == 1:
                return EvidenceNeedAssessment(
                    resolved=True,
                    resolution_ref=ranked[0].doc_id,
                    resolution_reason="single_document",
                )

        preferred: list[str] = []
        ambiguities: list[str] = []
        if len(wc) != 1:
            ambiguities.append("no_unique_working_context_doc")
            preferred.append("working_context")
        if len(recent) != 1:
            ambiguities.append("no_unique_recent_file")
            preferred.append("recent_file_memory")
        # Filesystem discrimination when still competing after (or instead of) recent.
        if len(hyps) >= 2 and (
            "recent_file_memory" in attempted_kinds or len(recent) != 1 or not preferred
        ):
            ambiguities.append("need_filesystem_discrimination")
            preferred.append("filesystem_metadata")

        return EvidenceNeedAssessment(
            remaining_ambiguities=ambiguities or ["competing_documents"],
            discriminating_features=list(preferred),
            preferred_evidence_kinds=preferred,
        )


@dataclass
class DocumentWorkingContextProvider:
    provider_id: str = "doc_working_context"
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
        active = str(
            (need.context.get("working_context") or {}).get("recent_document_id")
            or (need.context.get("working_context") or {}).get("recent_document")
            or ""
        ).strip().lower()
        hits = []
        for h in hypotheses:
            if not isinstance(h, DocumentHypothesis):
                continue
            if active and (
                active == h.doc_id.lower()
                or active == h.title.lower()
                or active in h.title.lower()
            ):
                hits.append(h.doc_id)
        if hits:
            return EvidenceResult(
                status=EVIDENCE_FOUND,
                provider_id=self.provider_id,
                evidence_kind=evidence_kind,
                payload={"preferred_doc_ids": hits},
            )
        return EvidenceResult(
            status=NO_EVIDENCE,
            provider_id=self.provider_id,
            evidence_kind=evidence_kind,
        )


@dataclass
class RecentFileMemoryProvider:
    provider_id: str = "recent_file_memory"
    evidence_kinds: frozenset[str] = frozenset({"recent_file_memory"})
    recent_titles: list[str] = field(default_factory=list)

    def can_serve(self, need: InformationNeed, evidence_kind: str) -> bool:
        return evidence_kind in self.evidence_kinds

    def probe(
        self,
        need: InformationNeed,
        *,
        evidence_kind: str,
        hypotheses: list[Any],
    ) -> EvidenceResult:
        recent = {
            str(t).strip().lower()
            for t in (
                list(self.recent_titles)
                + list((need.context.get("recent_files") or []))
            )
            if t
        }
        hits = []
        for h in hypotheses:
            if not isinstance(h, DocumentHypothesis):
                continue
            if h.title.lower() in recent or any(r in h.title.lower() for r in recent):
                hits.append(h.doc_id)
        if hits:
            return EvidenceResult(
                status=EVIDENCE_FOUND,
                provider_id=self.provider_id,
                evidence_kind=evidence_kind,
                payload={"recent_doc_ids": hits},
            )
        return EvidenceResult(
            status=NO_EVIDENCE,
            provider_id=self.provider_id,
            evidence_kind=evidence_kind,
        )


@dataclass
class FilesystemMetadataProvider:
    provider_id: str = "filesystem_metadata"
    evidence_kinds: frozenset[str] = frozenset({"filesystem_metadata"})
    mtime_by_id: dict[str, float] = field(default_factory=dict)

    def can_serve(self, need: InformationNeed, evidence_kind: str) -> bool:
        return evidence_kind in self.evidence_kinds

    def probe(
        self,
        need: InformationNeed,
        *,
        evidence_kind: str,
        hypotheses: list[Any],
    ) -> EvidenceResult:
        ranks = {
            h.doc_id: float(self.mtime_by_id[h.doc_id])
            for h in hypotheses
            if isinstance(h, DocumentHypothesis) and h.doc_id in self.mtime_by_id
        }
        if ranks:
            return EvidenceResult(
                status=EVIDENCE_FOUND,
                provider_id=self.provider_id,
                evidence_kind=evidence_kind,
                payload={"mtime_rank_by_id": ranks},
            )
        return EvidenceResult(
            status=NO_EVIDENCE,
            provider_id=self.provider_id,
            evidence_kind=evidence_kind,
        )


@dataclass
class EmptyRecentFileMemoryProvider:
    """First-provider miss for adaptive reassessment goldens."""

    provider_id: str = "recent_file_memory_empty"
    evidence_kinds: frozenset[str] = frozenset({"recent_file_memory"})

    def can_serve(self, need: InformationNeed, evidence_kind: str) -> bool:
        return evidence_kind in self.evidence_kinds

    def probe(
        self,
        need: InformationNeed,
        *,
        evidence_kind: str,
        hypotheses: list[Any],
    ) -> EvidenceResult:
        return EvidenceResult(
            status=NO_EVIDENCE,
            provider_id=self.provider_id,
            evidence_kind=evidence_kind,
            notes="no_recent_files",
        )


def acquire_for_document_resolution(
    hypotheses: list[DocumentHypothesis],
    *,
    subject: str = "the deck",
    working_context: Optional[dict[str, Any]] = None,
    recent_files: Optional[list[str]] = None,
    mtime_by_id: Optional[dict[str, float]] = None,
    budget: int = 4,
    attempt_budget: int = 8,
    prefer_empty_recent_first: bool = False,
) -> EvidenceAcquisitionEpisode:
    need = InformationNeed(
        need_type="document_resolution",
        subject=subject,
        competing_hypotheses=list(hypotheses),
        budget=budget,
        attempt_budget=attempt_budget,
        context={
            "working_context": dict(working_context or {}),
            "recent_files": list(recent_files or []),
        },
    )
    reg = InformationCapabilityRegistry()
    reg.register(DocumentWorkingContextProvider())
    if prefer_empty_recent_first:
        # Same evidence kind, weak provider first — proves kind is not exhausted.
        reg.register(EmptyRecentFileMemoryProvider())
    reg.register(RecentFileMemoryProvider(recent_titles=list(recent_files or [])))
    reg.register(FilesystemMetadataProvider(mtime_by_id=dict(mtime_by_id or {})))
    return run_evidence_acquisition(
        need,
        registry=reg,
        strategy=DocumentResolutionEvidenceStrategy(),
        hypotheses=list(hypotheses),
    )
