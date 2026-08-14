"""Brain package — MetaActor workspace, activation, provisional turn reps.

Slice 1: ContextActivation before semantic commitment.
See docs/design/brain-metaactor.md.
"""

from plugin.agent.brain.context_activation import (
    ActivationSignature,
    activate_context,
    build_activation_signature,
    consultation_context_from_workspace,
)
from plugin.agent.brain.turn_representation import TurnRepresentation
from plugin.agent.brain.workspace import BrainWorkspace

__all__ = [
    "ActivationSignature",
    "BrainWorkspace",
    "TurnRepresentation",
    "activate_context",
    "build_activation_signature",
    "consultation_context_from_workspace",
]
