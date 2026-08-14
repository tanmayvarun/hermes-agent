"""BrainWorkspace — evolving cognitive state for the MetaActor.

Does not commit identity or intentions. Slice 1 stores activation evidence only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from plugin.agent.brain.turn_representation import TurnRepresentation


@dataclass
class BrainWorkspace:
    """Persistent contextual representation for the active session/turn loop."""

    turn: str = ""
    session_ref: str = ""
    working_context: dict[str, Any] = field(default_factory=dict)
    provisional_interpretation: Optional[TurnRepresentation] = None
    known_facts: list[dict[str, Any]] = field(default_factory=list)
    retrieved_evidence: list[dict[str, Any]] = field(default_factory=list)
    hypotheses: list[dict[str, Any]] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    unresolved_references: list[dict[str, Any]] = field(default_factory=list)
    bindings: list[dict[str, Any]] = field(default_factory=list)
    current_intention: str = ""
    desired_effects: list[str] = field(default_factory=list)
    progress: list[dict[str, Any]] = field(default_factory=list)
    semantic_attempt_history: list[dict[str, Any]] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    active_context_refs: list[str] = field(default_factory=list)
    activation_signature: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def activation_trace(self) -> dict[str, Any]:
        """Compact trace for acceptance_trace / debugging — no commits."""
        return {
            "turn": self.turn,
            "session_ref": self.session_ref,
            "activation_signature": dict(self.activation_signature or {}),
            "evidence_count": len(self.retrieved_evidence),
            "active_context_refs": list(self.active_context_refs),
            "unresolved_references": list(self.unresolved_references),
            "entity_names": [
                str(e.get("canonical_name") or e.get("ref") or "")
                for e in self.retrieved_evidence
                if e.get("ref_kind") == "entity" or e.get("canonical_name")
            ],
            "provisional_status": (
                self.provisional_interpretation.interpretation_status
                if self.provisional_interpretation
                else None
            ),
            "bindings": list(self.bindings),
            "committed": False,
        }
