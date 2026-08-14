"""Brain package — MetaActor workspace, activation, provisional turn reps,
generic evidence acquisition.

Slice 1: ContextActivation before semantic commitment.
See docs/design/brain-metaactor.md.
"""

from plugin.agent.brain.context_activation import (
    ActivationSignature,
    activate_context,
    build_activation_signature,
    consultation_context_from_workspace,
)
from plugin.agent.brain.evidence_acquisition import (
    acquire_for_entity_resolution,
    run_evidence_acquisition,
)
from plugin.agent.brain.information_need import (
    EvidenceAcquisitionEpisode,
    EvidenceResult,
    InformationNeed,
)
from plugin.agent.brain.turn_representation import TurnRepresentation
from plugin.agent.brain.workspace import BrainWorkspace

__all__ = [
    "ActivationSignature",
    "BrainWorkspace",
    "EvidenceAcquisitionEpisode",
    "EvidenceResult",
    "InformationNeed",
    "TurnRepresentation",
    "acquire_for_entity_resolution",
    "activate_context",
    "build_activation_signature",
    "consultation_context_from_workspace",
    "run_evidence_acquisition",
]
