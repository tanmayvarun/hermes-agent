"""The executive runtime: the agent that owns the task, not the app."""

from plugin.agent.executive.capabilities import (
    CapabilityDescriptor,
    CapabilityRegistry,
    default_registry,
)
from plugin.agent.executive.result import (
    CapabilityResult,
    Observation,
    from_capability_outcome,
    from_unified_proposal,
)
from plugin.agent.executive.meta_action import (
    MetaAction,
    MetaChoice,
    MetaContext,
    select_meta_action,
)
from plugin.agent.executive.hierarchy import (
    ModeContext,
    cognitive_mode,
    decision_ladder,
    mode_triggers,
)
from plugin.agent.executive.value import (
    ValueInputs,
    action_value,
    value_breakdown,
)
from plugin.agent.executive.perception_query import (
    PerceptionQuery,
    from_sufficiency as perception_query_from_sufficiency,
)
from plugin.agent.executive.questions import (
    Hypothesis,
    InformationGap,
    OpenQuestion,
    QuestionLedger,
)
from plugin.agent.executive.sufficiency import (
    DecisionSufficiency,
    SufficiencyInputs,
    assess_sufficiency,
)
from plugin.agent.executive.workspace import (
    AttemptRecord,
    Budgets,
    Claim,
    CommitDecision,
    CommitVerdict,
    Contradiction,
    ExecutiveWorkspace,
    GoalState,
    Intent,
    TransitionRecord,
    WorkspaceProposal,
    phase_ladder_for,
)

__all__ = [
    "AttemptRecord",
    "Budgets",
    "CapabilityDescriptor",
    "CapabilityRegistry",
    "CapabilityResult",
    "Claim",
    "CommitDecision",
    "CommitVerdict",
    "Contradiction",
    "DecisionSufficiency",
    "ExecutiveWorkspace",
    "GoalState",
    "Hypothesis",
    "InformationGap",
    "Intent",
    "MetaAction",
    "MetaChoice",
    "MetaContext",
    "ModeContext",
    "Observation",
    "OpenQuestion",
    "PerceptionQuery",
    "QuestionLedger",
    "SufficiencyInputs",
    "TransitionRecord",
    "ValueInputs",
    "WorkspaceProposal",
    "action_value",
    "assess_sufficiency",
    "cognitive_mode",
    "decision_ladder",
    "default_registry",
    "from_capability_outcome",
    "from_unified_proposal",
    "mode_triggers",
    "perception_query_from_sufficiency",
    "phase_ladder_for",
    "select_meta_action",
    "value_breakdown",
]
