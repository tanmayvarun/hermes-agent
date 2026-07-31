"""Run-local state experience — suppress ineffective/regressive actions per world signature."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Set

from plugin.agent.action import Action
from plugin.agent.transition.types import SearchNode, TransitionOutcome

_RETRIABLE_NO_EFFECT_FAMILIES = {
    "type_query",
    "open_search",
    "open_contact",
    "select_content",
    "select_forward_target",
    "scroll_content",
    "dismiss",
}

_PROMISING_RETRY_PROGRESS_THRESHOLD = 0.25


def action_experience_key(action: Action) -> str:
    return f"{action.action_family or action.action.lower()}:{ (action.semantic_target or '').lower() }:{action.text or ''}"


def action_family_key(action: Action) -> str:
    return str(action.action_family or action.action.lower() or "").strip().lower()


@dataclass
class StateBucket:
    ineffective_actions: Set[str] = field(default_factory=set)
    regressive_actions: Set[str] = field(default_factory=set)
    promising_actions: Set[str] = field(default_factory=set)
    family_attempts: Dict[str, int] = field(default_factory=dict)
    family_successes: Dict[str, int] = field(default_factory=dict)
    family_failures: Dict[str, int] = field(default_factory=dict)
    visit_count: int = 0


@dataclass
class StateExperience:
    """Per approximate world state, remember what failed or helped (current run only)."""

    buckets: Dict[str, StateBucket] = field(default_factory=dict)
    search_trace: List[SearchNode] = field(default_factory=list)
    search_tree_root_id: int = 0
    current_search_node_id: int = 0
    next_search_node_id: int = 1
    pending_backtrack_family: str = ""  # hint: dismiss | end_call | observe

    def bucket(self, state_signature: str) -> StateBucket:
        sig = state_signature or "unknown"
        if sig not in self.buckets:
            self.buckets[sig] = StateBucket()
        return self.buckets[sig]

    def visit(self, state_signature: str) -> None:
        b = self.bucket(state_signature)
        b.visit_count += 1

    def record_outcome(
        self,
        state_signature: str,
        action: Action,
        outcome: TransitionOutcome,
        *,
        progress_delta: float = 0.0,
        predicted_outcome: str = "",
        predicted_progress: float = 0.0,
        predicted_affordances: List[str] | None = None,
    ) -> None:
        key = action_experience_key(action)
        fam = action_family_key(action)
        b = self.bucket(state_signature)
        if fam:
            b.family_attempts[fam] = b.family_attempts.get(fam, 0) + 1
        attempts = b.family_attempts.get(fam, 0) if fam else 0
        if outcome == TransitionOutcome.NO_EFFECT:
            retryable = fam in _RETRIABLE_NO_EFFECT_FAMILIES or (
                getattr(action, "reversible", True) and fam not in {"start_call"}
            )
            if retryable and not (
                fam and attempts >= 2 and b.family_successes.get(fam, 0) == 0
            ):
                # Reversible actions can fail due to transient focus, occlusion,
                # or an actuator bug. Keep a small retry window, but stop
                # re-issuing the same family forever when it keeps producing no effect.
                b.promising_actions.add(key)
                b.ineffective_actions.discard(key)
                b.regressive_actions.discard(key)
                if fam:
                    b.family_failures[fam] = b.family_failures.get(fam, 0) + 1
            else:
                b.ineffective_actions.add(key)
                if fam:
                    b.family_failures[fam] = b.family_failures.get(fam, 0) + 1
                if fam == "start_call":
                    self.pending_backtrack_family = "observe"
                elif fam:
                    self.pending_backtrack_family = self._best_recovery_family(b, exclude=fam) or "observe"
        elif outcome == TransitionOutcome.REGRESSION:
            b.regressive_actions.add(key)
            if fam:
                b.family_failures[fam] = b.family_failures.get(fam, 0) + 1
        elif outcome in {
            TransitionOutcome.PROGRESS,
            TransitionOutcome.GOAL_SATISFIED,
            TransitionOutcome.PROMISING_UNRESOLVED,
        }:
            b.promising_actions.add(key)
            b.ineffective_actions.discard(key)
            b.regressive_actions.discard(key)
            if fam:
                b.family_successes[fam] = b.family_successes.get(fam, 0) + 1
        if outcome == TransitionOutcome.PROMISING_UNRESOLVED and fam:
            # A promising branch is useful only if it keeps opening up new
            # affordances. If the same family keeps landing in a near-miss,
            # prefer the next strongest family from the same state bucket.
            attempts = b.family_attempts.get(fam, 0)
            if attempts >= 2 and progress_delta < _PROMISING_RETRY_PROGRESS_THRESHOLD:
                b.ineffective_actions.add(key)
                alternate = self._best_recovery_family(b, exclude=fam)
                if alternate:
                    self.pending_backtrack_family = alternate
                elif progress_delta <= 0.05:
                    self.pending_backtrack_family = "observe"
                else:
                    self.pending_backtrack_family = ""
            else:
                self.pending_backtrack_family = ""
        elif outcome == TransitionOutcome.UNCERTAIN and progress_delta < -0.05:
            # Uncertain alone is not regressive — only soft mark when clearly negative
            pass

        parent_id = self.current_search_node_id
        node_id = self.next_search_node_id
        self.next_search_node_id += 1
        if self.search_tree_root_id == 0:
            self.search_tree_root_id = node_id
        node = SearchNode(
            node_id=node_id,
            world_signature=state_signature,
            parent_node_id=parent_id,
            incoming_action_key=key,
            predicted_outcome=predicted_outcome,
            predicted_progress=predicted_progress,
            predicted_affordances=list(predicted_affordances or []),
            observed_outcome=outcome.value,
            prediction_error="" if not predicted_outcome or predicted_outcome == outcome.value else f"{predicted_outcome}->{outcome.value}",
            tried_actions=list(b.ineffective_actions | b.regressive_actions),
            value_estimate=progress_delta,
        )
        self.search_trace.append(node)
        self.current_search_node_id = node_id
        if parent_id:
            for prev in reversed(self.search_trace[:-1]):
                if prev.node_id == parent_id:
                    prev.children_node_ids.append(node_id)
                    break

        if outcome == TransitionOutcome.REGRESSION:
            self.pending_backtrack_family = "dismiss"
        elif outcome == TransitionOutcome.PROMISING_UNRESOLVED:
            # Stay on the branch — do not hint dismiss/observe thrash
            self.pending_backtrack_family = ""
        elif outcome == TransitionOutcome.NO_EFFECT:
            if action.action_family != "scroll_content":
                if fam and b.family_failures.get(fam, 0) >= 2 and b.family_successes.get(fam, 0) == 0:
                    self.pending_backtrack_family = self._best_recovery_family(b, exclude=fam) or "observe"
                else:
                    self.pending_backtrack_family = ""

    def _best_recovery_family(self, bucket: StateBucket, *, exclude: str = "") -> str:
        """Choose the strongest already-learned family for this state."""
        best_family = ""
        best_score = 0.0
        skip = {exclude.strip().lower()} if exclude else set()
        for fam, attempts in bucket.family_attempts.items():
            if not fam or fam in skip or attempts <= 0:
                continue
            successes = bucket.family_successes.get(fam, 0)
            failures = bucket.family_failures.get(fam, 0)
            score = (successes + 1.0) / (attempts + 1.0) - 0.12 * max(0, failures - successes)
            if score > best_score:
                best_score = score
                best_family = fam
        if best_family and best_family != "observe":
            return best_family
        if "observe" not in skip and bucket.family_attempts.get("observe", 0) > 0:
            return "observe"
        return ""

    def is_suppressed(self, state_signature: str, action: Action) -> bool:
        key = action_experience_key(action)
        fam = action_family_key(action)
        b = self.bucket(state_signature)
        if self.pending_backtrack_family:
            desired = self.pending_backtrack_family.strip().lower()
            # "observe" is an escape hatch, not a hard exclusion. Treat it as a
            # soft hint so a promising sibling can still win when the world is
            # telling us there is more to do.
            if desired and desired != "observe" and fam != desired:
                return True
        if key in b.ineffective_actions or key in b.regressive_actions:
            return True
        if fam and b.family_attempts.get(fam, 0) >= 3:
            failures = b.family_failures.get(fam, 0)
            successes = b.family_successes.get(fam, 0)
            if failures >= 2 and failures > successes + 1:
                return True
        return False

    def filter_actions(self, state_signature: str, actions: List[Action]) -> List[Action]:
        if self.pending_backtrack_family:
            desired = self.pending_backtrack_family.strip().lower()
            if desired and desired != "observe":
                preferred = [a for a in actions if action_family_key(a) == desired]
                if preferred:
                    return preferred
                non_observe = [a for a in actions if action_family_key(a) != "observe"]
                if non_observe:
                    return non_observe
        kept = [a for a in actions if not self.is_suppressed(state_signature, a)]
        # Always keep Observe as escape hatch if everything suppressed
        if not kept:
            if self.pending_backtrack_family and self.pending_backtrack_family.strip().lower() != "observe":
                non_observe = [
                    a
                    for a in actions
                    if action_family_key(a) != "observe" and not self.is_suppressed(state_signature, a)
                ]
                if non_observe:
                    return non_observe
            for a in actions:
                if a.action_family == "observe" or a.action.lower() == "observe":
                    return [a]
            return actions[:1] if actions else []
        return kept

    def boost_for(self, state_signature: str, action: Action) -> float:
        key = action_experience_key(action)
        fam = action_family_key(action)
        b = self.bucket(state_signature)
        if key in b.promising_actions:
            return 0.15
        if fam:
            attempts = max(1, b.family_attempts.get(fam, 0))
            successes = b.family_successes.get(fam, 0)
            failures = b.family_failures.get(fam, 0)
            if successes > 0:
                return min(0.2, 0.05 * successes + 0.01 * min(attempts, 5))
            if failures > 0:
                return max(-0.18, -0.06 * min(failures, 3))
        if self.pending_backtrack_family and action.action_family == self.pending_backtrack_family:
            return 0.25
        if self.pending_backtrack_family and action.action_family in {"dismiss", "end_call", "observe"}:
            if action.action_family == "observe":
                return 0.1
        return 0.0
