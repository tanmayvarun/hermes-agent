"""Generic information need + evidence results for Brain/MetaActor gathering.

Identity resolution is one use case. The same types support referent resolution,
effect verification, method executability, etc.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


# EvidenceResult.status
EVIDENCE_FOUND = "EVIDENCE_FOUND"
NO_EVIDENCE = "NO_EVIDENCE"
NO_CAPABILITY = "NO_CAPABILITY"
ERROR = "ERROR"


@dataclass
class InformationNeed:
    """What the Brain still needs before a semantic commitment."""

    need_type: str  # entity_resolution | document_resolution | effect_check | ...
    subject: str
    competing_hypotheses: list[Any] = field(default_factory=list)
    desired_discrimination: str = ""
    evidence_already_known: list[dict[str, Any]] = field(default_factory=list)
    required_confidence: float = 0.0
    budget: int = 4  # meaningful information probes
    attempt_budget: int = 8  # operational ceiling (includes NO_CAPABILITY/ERROR)
    context: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.evidence_already_known, list):
            self.evidence_already_known = list(self.evidence_already_known or [])


@dataclass
class EvidenceNeedAssessment:
    """Reassessment of remaining uncertainty after (or before) a probe.

    Domain strategies produce this; the generic episode only consumes it.
    """

    remaining_ambiguities: list[str] = field(default_factory=list)
    discriminating_features: list[str] = field(default_factory=list)
    preferred_evidence_kinds: list[str] = field(default_factory=list)
    resolved: bool = False
    resolution_ref: str = ""
    resolution_reason: str = ""
    notes: str = ""

    def next_kind(self, attempted_kinds: set[str]) -> Optional[str]:
        for kind in self.preferred_evidence_kinds:
            if kind and kind not in attempted_kinds:
                return kind
        return None


@dataclass
class EvidenceResult:
    """Outcome of one information-capability probe."""

    status: str  # EVIDENCE_FOUND | NO_EVIDENCE | NO_CAPABILITY | ERROR
    provider_id: str
    evidence_kind: str
    payload: dict[str, Any] = field(default_factory=dict)
    notes: str = ""

    @property
    def is_meaningful_attempt(self) -> bool:
        """True when a capable provider actually ran (found or empty)."""
        return self.status in {EVIDENCE_FOUND, NO_EVIDENCE}

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "provider_id": self.provider_id,
            "evidence_kind": self.evidence_kind,
            "payload": dict(self.payload),
            "notes": self.notes,
        }


@dataclass
class EvidenceAcquisitionEpisode:
    """Bounded MetaActor episode: gather until resolved or budget exhausted."""

    information_need: InformationNeed
    probes_attempted: list[EvidenceResult] = field(default_factory=list)
    evidence_found: list[EvidenceResult] = field(default_factory=list)
    hypotheses: list[Any] = field(default_factory=list)
    assessments: list[EvidenceNeedAssessment] = field(default_factory=list)
    uncertainty_notes: list[str] = field(default_factory=list)
    budget_remaining: int = 0
    attempt_budget_remaining: int = 0
    resolved: bool = False
    resolution_ref: str = ""
    resolution_reason: str = ""

    def probe_labels(self) -> list[str]:
        out: list[str] = []
        for r in self.probes_attempted:
            if r.status == NO_CAPABILITY:
                out.append(f"skip_no_capability:{r.provider_id}")
            elif r.status == ERROR:
                out.append(f"skip_error:{r.provider_id}:{r.notes}")
            else:
                out.append(f"{r.provider_id}:{r.status}")
        return out
