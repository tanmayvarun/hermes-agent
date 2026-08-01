"""Trajectory-aware control types — outcomes of short branches, not single-frame screenshots."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class TransitionOutcome(str, Enum):
    """Immediate classification after a transition — defer judgment when uncertain."""

    GOAL_SATISFIED = "goal_satisfied"  # GOAL_REACHED
    PROGRESS = "progress"  # CLEAR_PROGRESS
    PROMISING_UNRESOLVED = "promising_unresolved"
    NO_EFFECT = "no_effect"
    REGRESSION = "regression"  # CLEAR_REGRESSION — requires positive contradiction
    UNCERTAIN = "uncertain"


class Observability(str, Enum):
    """Visibility of a belief — occluded ≠ false."""

    CONFIRMED_TRUE = "confirmed_true"
    CONFIRMED_FALSE = "confirmed_false"
    NOT_CURRENTLY_OBSERVABLE = "not_currently_observable"
    UNKNOWN = "unknown"
    STALE = "stale"


@dataclass
class ContextualBelief:
    value: bool = False
    confidence: float = 0.0
    observability: str = Observability.UNKNOWN.value
    last_confirmed_world: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @property
    def effective(self) -> bool:
        """True when confirmed or still believed while occluded."""
        if self.observability == Observability.CONFIRMED_FALSE.value:
            return False
        if self.observability == Observability.CONFIRMED_TRUE.value:
            return True
        if self.observability == Observability.NOT_CURRENTLY_OBSERVABLE.value:
            return bool(self.value) and self.confidence >= 0.4
        return bool(self.value) and self.confidence >= 0.55


@dataclass
class InteractionContext:
    """Latent interaction state that survives overlays / temporary occlusion."""

    selected_target: str = ""
    target_confidence: float = 0.0
    originating_world: str = ""
    active_surface: str = ""  # conversation | call_picker | search | unknown
    surface_state: Dict[str, str] = field(default_factory=dict)
    selected_object_label: str = ""
    latent_affordances: List[str] = field(default_factory=list)
    selected_object: ContextualBelief = field(default_factory=ContextualBelief)
    open_conversation: ContextualBelief = field(default_factory=ContextualBelief)
    reversible: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "selected_target": self.selected_target,
            "target_confidence": self.target_confidence,
            "originating_world": self.originating_world,
            "active_surface": self.active_surface,
            "surface_state": dict(self.surface_state),
            "selected_object_label": self.selected_object_label,
            "latent_affordances": list(self.latent_affordances),
            "selected_object": self.selected_object.to_dict(),
            "open_conversation": self.open_conversation.to_dict(),
            "reversible": self.reversible,
        }


@dataclass
class AffordanceDelta:
    newly_available: List[str] = field(default_factory=list)
    lost: List[str] = field(default_factory=list)
    relevance_score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ActionPrediction:
    """First-class expectation attached to a chosen action."""

    action_key: str = ""
    action_family: str = ""
    semantic_target: str = ""
    strategy: str = "local"  # local | strategic
    branch_hypothesis: str = ""
    expected_surface: str = ""
    expected_progress: float = 0.0
    expected_affordances: List[str] = field(default_factory=list)
    expected_non_changes: List[str] = field(default_factory=list)
    predicted_outcome: str = ""
    reversible: bool = True
    confidence: float = 0.0
    rationale: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BranchStrategy:
    """LLM-proposed strategic search direction for an active branch."""

    strategy_id: str = ""
    preferred_family: str = ""
    backtrack_family: str = ""
    avoid_families: List[str] = field(default_factory=list)
    branch_hypothesis: str = ""
    expected_surface: str = ""
    confidence: float = 0.0
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FrontierAction:
    """A single candidate on the local search frontier."""

    state_signature: str = ""
    action_key: str = ""
    action_family: str = ""
    semantic_target: str = ""
    text: str = ""
    hypothesis_label: str = ""
    tried: bool = False
    novelty: float = 0.0
    semantic_relevance: float = 0.0
    actionability: float = 0.0
    information_gain: float = 0.0
    risk: float = 0.0
    score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BranchPolicy:
    # Safety caps only; ordinary continuation should be driven by evidence.
    max_depth: int = 8
    max_no_effect_actions: int = 2
    max_observations: int = 2
    max_stagnant_steps: int = 2
    max_surface_rotations: int = 3
    max_contradictions: int = 2
    min_frontier_plausibility: float = 0.25
    reversible_required: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ExplorationBranch:
    """Bounded local search after a promising but unresolved transition."""

    origin_state: str = ""
    entry_action: str = ""
    current_state: str = ""
    active_surface: str = ""
    last_surface: str = ""
    depth: int = 0
    no_effect_count: int = 0
    observe_count: int = 0
    stagnant_steps: int = 0
    surface_rotations: int = 0
    reversible: bool = True
    active: bool = False
    frontier_hypothesis: str = ""
    frontier_plausibility: float = 0.0
    contradiction_count: int = 0
    newly_relevant_affordances: List[str] = field(default_factory=list)
    frontier: List[FrontierAction] = field(default_factory=list)
    frontier_state_signature: str = ""
    frontier_invalidations: int = 0
    stale_frontier_reason: str = ""
    policy: BranchPolicy = field(default_factory=BranchPolicy)
    strategy: BranchStrategy = field(default_factory=BranchStrategy)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "origin_state": self.origin_state,
            "entry_action": self.entry_action,
            "current_state": self.current_state,
            "active_surface": self.active_surface,
            "last_surface": self.last_surface,
            "depth": self.depth,
            "no_effect_count": self.no_effect_count,
            "observe_count": self.observe_count,
            "stagnant_steps": self.stagnant_steps,
            "surface_rotations": self.surface_rotations,
            "reversible": self.reversible,
            "active": self.active,
            "frontier_hypothesis": self.frontier_hypothesis,
            "frontier_plausibility": self.frontier_plausibility,
            "contradiction_count": self.contradiction_count,
            "newly_relevant_affordances": list(self.newly_relevant_affordances),
            "frontier": [entry.to_dict() for entry in self.frontier],
            "frontier_state_signature": self.frontier_state_signature,
            "frontier_invalidations": self.frontier_invalidations,
            "stale_frontier_reason": self.stale_frontier_reason,
            "policy": self.policy.to_dict(),
            "strategy": self.strategy.to_dict(),
        }

    def note_step(
        self,
        *,
        state_signature: str = "",
        surface: str = "",
        newly_relevant_affordances: List[str] | None = None,
    ) -> None:
        if surface:
            if not self.active_surface:
                self.active_surface = surface
            elif surface != self.active_surface:
                self.last_surface = self.active_surface
                self.active_surface = surface
                self.surface_rotations += 1
                self.stagnant_steps = 0
        if state_signature:
            if self.current_state and state_signature == self.current_state and not newly_relevant_affordances:
                self.stagnant_steps += 1
            else:
                self.stagnant_steps = 0
            self.current_state = state_signature
        if newly_relevant_affordances:
            for affordance in newly_relevant_affordances:
                if affordance not in self.newly_relevant_affordances:
                    self.newly_relevant_affordances.append(affordance)
            self.stagnant_steps = 0

    def set_frontier(self, frontier: List[FrontierAction], *, state_signature: str = "") -> None:
        self.frontier = list(frontier)
        if state_signature:
            self.frontier_state_signature = state_signature
        if self.frontier:
            best = max(self.frontier, key=lambda entry: entry.score)
            self.frontier_hypothesis = best.hypothesis_label
            self.frontier_plausibility = best.score
        else:
            self.frontier_hypothesis = ""
            self.frontier_plausibility = 0.0

    def invalidate_frontier(self, *, reason: str = "") -> None:
        self.frontier_invalidations += 1
        self.stale_frontier_reason = reason
        self.frontier = []
        self.frontier_state_signature = ""
        self.frontier_hypothesis = ""
        self.frontier_plausibility = 0.0
        self.active = False

    def best_frontier(self, *, only_untried: bool = False) -> Optional[FrontierAction]:
        if not self.frontier:
            return None
        frontier = [entry for entry in self.frontier if (not only_untried) or not entry.tried]
        if not frontier:
            return None
        return max(frontier, key=lambda entry: entry.score)

    def best_non_observe_frontier(self, *, only_untried: bool = False) -> Optional[FrontierAction]:
        """Prefer a real sibling action over an observe escape hatch."""
        if not self.frontier:
            return None
        frontier = [
            entry
            for entry in self.frontier
            if entry.action_family != "observe" and ((not only_untried) or not entry.tried)
        ]
        if not frontier:
            return None
        return max(frontier, key=lambda entry: entry.score)

    def frontier_exhausted(self) -> bool:
        if not self.frontier:
            return False
        return all(entry.tried or entry.score <= 0.0 for entry in self.frontier)

    def budget_exhausted(self) -> bool:
        p = self.policy
        has_promising_frontier = any(
            (not entry.tried) and entry.score > 0.0 for entry in self.frontier
        )
        if has_promising_frontier:
            if p.reversible_required and not self.reversible:
                return True
            if self.contradiction_count >= p.max_contradictions:
                return True
            if self.no_effect_count >= p.max_no_effect_actions:
                return True
            if self.observe_count >= p.max_observations:
                return True
            return False
        if self.contradiction_count >= p.max_contradictions:
            return True
        if self.no_effect_count >= p.max_no_effect_actions:
            return True
        if self.observe_count >= p.max_observations:
            return True
        if self.stagnant_steps >= p.max_stagnant_steps:
            return True
        if self.surface_rotations >= p.max_surface_rotations and self.stagnant_steps > 0:
            return True
        if p.reversible_required and not self.reversible:
            return True
        if self.frontier and self.frontier_exhausted() and self.stagnant_steps > 0:
            return True
        # Hard safety stop only, not the ordinary continuation rule.
        if (
            self.depth >= p.max_depth
            and not self.newly_relevant_affordances
            and self.frontier_plausibility <= p.min_frontier_plausibility
        ):
            return True
        return False


@dataclass
class ActionTarget:
    """Action binding valid only for the world version it was observed in."""

    entity_id: Optional[int] = None
    semantic: str = ""
    observed_in_world: str = ""

    def is_valid_for(self, world_id: str) -> bool:
        if not self.observed_in_world:
            return True
        return self.observed_in_world == world_id


@dataclass
class TransitionResult:
    changed: bool = False
    stabilized: bool = False
    change_score: float = 0.0
    reasons: List[str] = field(default_factory=list)
    polls: int = 0
    timed_out: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ProgressAssessment:
    goal_constraints_satisfied_delta: float = 0.0
    target_resolution_delta: float = 0.0
    uncertainty_delta: float = 0.0
    affordance_relevance_delta: float = 0.0
    irreversible_risk_delta: float = 0.0
    progress_delta: float = 0.0
    notes: List[str] = field(default_factory=list)
    # Structured trajectory fields (scalar alone is insufficient)
    execution_succeeded: bool = True
    meaningful_change: bool = False
    state_understood: bool = True
    goal_progress: str = "unknown"  # clear | promising | none | regression | unknown
    newly_relevant_affordances: List[str] = field(default_factory=list)
    context_preserved: bool = True
    branch_reversible: bool = True
    contradiction_evidence: List[str] = field(default_factory=list)
    affordance_delta: Optional[Dict[str, Any]] = None
    occlusion_notes: List[str] = field(default_factory=list)
    predicted_transition: str = ""
    observed_transition: str = ""
    new_capabilities: List[str] = field(default_factory=list)
    lost_capabilities: List[str] = field(default_factory=list)
    frontier_delta: float = 0.0
    confidence_delta: float = 0.0
    selected_capability_id: str = ""
    selected_capability_type: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TransitionAttempt:
    before_world_id: str
    after_world_id: str
    action_family: str = ""
    action_key: str = ""
    prediction: Dict[str, Any] = field(default_factory=dict)
    prediction_error: Dict[str, Any] = field(default_factory=dict)
    observed_change: bool = False
    progress_delta: float = 0.0
    outcome: str = TransitionOutcome.UNCERTAIN.value
    change_score: float = 0.0
    reasons: List[str] = field(default_factory=list)
    assessment: Optional[Dict[str, Any]] = None
    attribution: Optional[Dict[str, Any]] = None
    effect_kind: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TransitionSummary:
    outcome: str = ""
    progress_delta: float = 0.0
    change_score: float = 0.0
    prediction: Dict[str, Any] = field(default_factory=dict)
    prediction_error: Dict[str, Any] = field(default_factory=dict)
    diagnosis: Dict[str, Any] = field(default_factory=dict)
    goal_progress: str = ""
    meaningful_change: bool = False
    state_understood: bool = True
    context_preserved: bool = True
    branch_reversible: bool = True
    newly_relevant_affordances: List[str] = field(default_factory=list)
    contradiction_evidence: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    risk: float = 0.0
    confidence_delta: float = 0.0
    effect_kind: str = ""
    failure_domain: str = ""
    action_family: str = ""
    selected_capability_id: str = ""
    selected_capability_type: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SearchNode:
    """Run-local search node with parent/child links."""

    node_id: int
    world_signature: str
    parent_node_id: int = 0
    parent_world_signature: str = ""
    incoming_action_key: str = ""
    predicted_outcome: str = ""
    predicted_progress: float = 0.0
    predicted_affordances: List[str] = field(default_factory=list)
    observed_outcome: str = ""
    prediction_error: str = ""
    tried_actions: List[str] = field(default_factory=list)
    value_estimate: float = 0.0
    branch_label: str = ""
    children_node_ids: List[int] = field(default_factory=list)
