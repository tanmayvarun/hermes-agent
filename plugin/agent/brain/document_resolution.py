"""Document-resolution EvidenceStrategy — proves the generic episode is domain-neutral.

Uses DocumentHypothesis only. Identity types are intentionally absent.
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
    def assess(
        self,
        need: InformationNeed,
        hypotheses: list[Any],
        *,
        last_result: Optional[EvidenceResult] = None,
        attempted_kinds: Optional[set[str]] = None,
    ) -> EvidenceNeedAssessment:
        hyps = [h for h in hypotheses if isinstance(h, DocumentHypothesis)]
        attempted = set(attempted_kinds or ())

        wc = [h for h in hyps if h.working_context_hit]
        if len(wc) == 1:
            return EvidenceNeedAssessment(
                resolved=True,
                resolution_ref=wc[0].doc_id,
                resolution_reason="working_context_document",
            )

        recent = [h for h in hyps if h.recent_file_hit]
        if len(recent) == 1 and "recent_file_memory" in attempted:
            return EvidenceNeedAssessment(
                resolved=True,
                resolution_ref=recent[0].doc_id,
                resolution_reason="recent_file_memory",
            )

        # mtime dominance after filesystem probe
        if "filesystem_metadata" in attempted and hyps:
            ranked = sorted(hyps, key=lambda h: h.filesystem_mtime_rank, reverse=True)
            if len(ranked) >= 2 and ranked[0].filesystem_mtime_rank >= ranked[1].filesystem_mtime_rank + 0.4:
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
        if len(wc) != 1 and "working_context" not in attempted:
            ambiguities.append("no_unique_working_context_doc")
            preferred.append("working_context")
        if len(recent) != 1 and "recent_file_memory" not in attempted:
            ambiguities.append("no_unique_recent_file")
            preferred.append("recent_file_memory")
        if "filesystem_metadata" not in attempted and (
            "recent_file_memory" in attempted or not preferred
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
                h.working_context_hit = True
                h.notes.append("working_context_doc")
                hits.append(h.doc_id)
        if hits:
            return EvidenceResult(
                status=EVIDENCE_FOUND,
                provider_id=self.provider_id,
                evidence_kind=evidence_kind,
                payload={"hits": hits},
            )
        return EvidenceResult(
            status=NO_EVIDENCE,
            provider_id=self.provider_id,
            evidence_kind=evidence_kind,
        )


@dataclass
class RecentFileMemoryProvider:
    """Fixture-friendly recent-file memory probe."""

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
                h.recent_file_hit = True
                h.notes.append("recent_file_memory")
                hits.append(h.doc_id)
        if hits:
            return EvidenceResult(
                status=EVIDENCE_FOUND,
                provider_id=self.provider_id,
                evidence_kind=evidence_kind,
                payload={"hits": hits},
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
        updated = 0
        for h in hypotheses:
            if not isinstance(h, DocumentHypothesis):
                continue
            if h.doc_id in self.mtime_by_id:
                h.filesystem_mtime_rank = float(self.mtime_by_id[h.doc_id])
                h.notes.append(f"mtime={h.filesystem_mtime_rank:.2f}")
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
    reg.register(RecentFileMemoryProvider(recent_titles=list(recent_files or [])))
    reg.register(FilesystemMetadataProvider(mtime_by_id=dict(mtime_by_id or {})))
    return run_evidence_acquisition(
        need,
        registry=reg,
        strategy=DocumentResolutionEvidenceStrategy(),
        hypotheses=list(hypotheses),
    )
