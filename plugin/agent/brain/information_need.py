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

    need_type: str  # entity_resolution | referent | effect_check | ...
    subject: str
    competing_hypotheses: list[Any] = field(default_factory=list)
    desired_discrimination: str = ""
    evidence_already_known: list[dict[str, Any]] = field(default_factory=list)
    required_confidence: float = 0.0
    budget: int = 4  # meaningful probe attempts remaining at start
    context: dict[str, Any] = field(default_factory=dict)

    def missing_features(self) -> set[str]:
        """Features that would help discriminate competing hypotheses."""
        known = {
            str(e.get("kind") or e.get("evidence_kind") or "")
            for e in self.evidence_already_known
            if e
        }
        # Domain-agnostic defaults; callers may pass desired_discrimination
        # as comma-separated feature tags.
        wanted: set[str] = set()
        if self.desired_discrimination:
            wanted |= {
                p.strip()
                for p in self.desired_discrimination.split(",")
                if p.strip()
            }
        if self.need_type == "entity_resolution":
            wanted |= {
                "working_context",
                "memory_aggregates",
                "reference_history",
                "channel_activity",
            }
        return {w for w in wanted if w and w not in known}


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
    uncertainty_notes: list[str] = field(default_factory=list)
    budget_remaining: int = 0
    resolved: bool = False
    resolution_entity_id: str = ""
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
