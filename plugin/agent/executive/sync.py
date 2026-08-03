"""Bridges between the legacy stores and the workspace.

Everything here exists so callers can keep their current shape while the
workspace becomes the one place the answer comes from. Each helper proposes;
the workspace decides.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from plugin.agent.executive.questions import Hypothesis, InformationGap, OpenQuestion
from plugin.agent.executive.workspace import (
    Claim,
    ExecutiveWorkspace,
    GoalState,
    TransitionRecord,
    WorkspaceProposal,
)

# Surfaces that are direct evidence of where the task stands. A phase derived
# from one of these may move backwards, because the screen really did.
SURFACE_EVIDENCED = {"forward_picker", "context_menu", "conversation", "chat_list", "search"}


def workspace_of(execution_state: Any) -> Optional[ExecutiveWorkspace]:
    workspace = getattr(execution_state, "workspace", None)
    return workspace if isinstance(workspace, ExecutiveWorkspace) else None


def bind_goal(execution_state: Any, goal: Any) -> Optional[ExecutiveWorkspace]:
    """Attach the goal once, so the workspace knows which phase ladder applies."""
    workspace = workspace_of(execution_state)
    if workspace is None or goal is None:
        return workspace
    if not workspace.goal.kind:
        workspace.goal = GoalState.from_goal(goal)
    return workspace


def commit_reading(
    execution_state: Any,
    *,
    source: str,
    surface: str = "",
    open_conversation: Optional[str] = None,
    phase: Optional[str] = None,
    confidence: float = 0.0,
    evidence: str = "",
) -> Optional[ExecutiveWorkspace]:
    """Offer one frame's reading of where the task stands."""
    workspace = workspace_of(execution_state)
    if workspace is None:
        return None
    surface_norm = str(surface or "").strip().lower()
    workspace.commit(
        WorkspaceProposal(
            source=source,
            frame=int(getattr(execution_state, "iteration", 0) or 0),
            surface=surface_norm,
            open_conversation=open_conversation,
            phase=phase,
            allow_phase_regression=surface_norm in SURFACE_EVIDENCED,
            confidence=confidence,
            evidence=evidence,
        )
    )
    return workspace


def commit_beliefs(
    execution_state: Any,
    *,
    source: str,
    facts: Dict[str, Any],
    confidence: float = 0.0,
    evidence: str = "",
    status: str = "observed",
) -> Optional[ExecutiveWorkspace]:
    """Offer a set of believed facts for the workspace to arbitrate.

    ``facts`` maps a fact name to either a plain value or a ``(value,
    confidence)`` pair. Empty values are dropped here so a submodule that simply
    did not read a fact this frame never proposes to erase it. ``status`` is the
    epistemic status these facts carry (observed by default). The workspace
    decides what to accept and records any contradiction.
    """
    workspace = workspace_of(execution_state)
    if workspace is None or not facts:
        return None
    frame = int(getattr(execution_state, "iteration", 0) or 0)
    claims: Dict[str, Claim] = {}
    for key, raw in facts.items():
        if raw is None:
            continue
        if isinstance(raw, tuple) and len(raw) == 2:
            value, conf = raw
        else:
            value, conf = raw, confidence
        value = str(value or "").strip()
        if not value:
            continue
        claims[str(key)] = Claim(
            value=value,
            source=source,
            confidence=float(conf or 0.0),
            frame=frame,
            evidence=evidence,
            status=status,
        )
    if not claims:
        return None
    workspace.commit(
        WorkspaceProposal(source=source, frame=frame, confidence=confidence, evidence=evidence, facts=claims)
    )
    return workspace


def commit_bindings(
    execution_state: Any,
    *,
    bindings: Dict[str, Any],
    source: str = "task_binding",
    evidence: str = "",
) -> Optional[ExecutiveWorkspace]:
    """Record object bindings (source/destination) as authoritative workspace facts.

    A domain may keep a task-specific state object to *derive* a phase, but the
    binding of an object to the goal — what the source object is, once resolved —
    belongs in the one authoritative record, not only in that state object. Each
    resolved binding contributes a ``binding.<name>`` fact whose epistemic status
    mirrors the domain's resolution status (resolved -> observed, provisional/
    ambiguous -> inferred). Unresolved bindings carry no value and are dropped:
    an unknown is represented by the *absence* of the fact (and by an open
    question), not by a fact that would flip when it finally resolves.
    """
    workspace = workspace_of(execution_state)
    if workspace is None or not isinstance(bindings, dict) or not bindings:
        return None
    frame = int(getattr(execution_state, "iteration", 0) or 0)
    status_to_epistemic = {
        "confirmed": "observed",
        "resolved": "observed",
        "provisional": "inferred",
        "ambiguous": "inferred",
    }
    facts: Dict[str, Claim] = {}
    for name, binding in bindings.items():
        if not isinstance(binding, dict):
            continue
        status = str(binding.get("status") or "").strip().lower()
        value = str(
            binding.get("resolved_value")
            or binding.get("resolved_label")
            or (
                binding.get("resolved_entity_id")
                if binding.get("resolved_entity_id") is not None
                else ""
            )
            or ""
        ).strip()
        if not value or status not in status_to_epistemic:
            # Unresolved / valueless binding: nothing authoritative to record yet.
            continue
        facts[f"binding.{name}"] = Claim(
            value=value,
            source=source,
            confidence=float(binding.get("confidence") or 0.0),
            frame=frame,
            evidence=evidence,
            status=status_to_epistemic[status],
        )
    if not facts:
        return None
    workspace.commit(WorkspaceProposal(source=source, frame=frame, facts=facts))
    return workspace


def has_resolved_binding(execution_state: Any, name: str) -> bool:
    """Whether the workspace authoritatively holds a resolved binding for ``name``."""
    workspace = workspace_of(execution_state)
    if workspace is None:
        return False
    return workspace.fact(f"binding.{name}") is not None


def commit_transition(
    execution_state: Any,
    *,
    action: str,
    family: str,
    before_surface: str,
    after_surface: str,
    outcome: str,
    progress_delta: float = 0.0,
) -> Optional[ExecutiveWorkspace]:
    workspace = workspace_of(execution_state)
    if workspace is None:
        return None
    workspace.commit(
        WorkspaceProposal(
            source="transition",
            frame=int(getattr(execution_state, "iteration", 0) or 0),
            transitions=[
                TransitionRecord(
                    frame=int(getattr(execution_state, "iteration", 0) or 0),
                    action=action,
                    family=family,
                    before_surface=str(before_surface or "").strip().lower(),
                    after_surface=str(after_surface or "").strip().lower(),
                    outcome=outcome,
                    progress_delta=progress_delta,
                )
            ],
        )
    )
    return workspace


def open_exploration_question(
    execution_state: Any,
    *,
    question: str,
    kind: str = "where_is",
    tested_by: str = "",
    hypothesis: str = "",
) -> Optional[ExecutiveWorkspace]:
    """Register the question a new exploration branch is built to answer.

    Exploration is keyed by this question, not by the action, so a later action
    that only re-tests an already-settled question is visibly redundant.
    """
    workspace = workspace_of(execution_state)
    if workspace is None or not str(question or "").strip():
        return None
    frame = int(getattr(execution_state, "iteration", 0) or 0)
    proposal = WorkspaceProposal(
        source="exploration",
        frame=frame,
        ask=[OpenQuestion(text=question, kind=kind, raised_frame=frame, tested_by=[tested_by] if tested_by else [])],
        gaps=[InformationGap(description=question, question_id=question, blocking=True, raised_frame=frame)],
    )
    if hypothesis:
        proposal.hypotheses = [
            Hypothesis(statement=hypothesis, question_id=question, raised_frame=frame)
        ]
    workspace.commit(proposal)
    return workspace


def settle_exploration_question(
    execution_state: Any,
    *,
    question: str,
    answered: bool,
    evidence: str = "",
) -> Optional[ExecutiveWorkspace]:
    """Close the question a branch tested, so it is not re-explored."""
    workspace = workspace_of(execution_state)
    if workspace is None or not str(question or "").strip():
        return None
    frame = int(getattr(execution_state, "iteration", 0) or 0)
    proposal = WorkspaceProposal(source="exploration", frame=frame)
    if answered:
        proposal.answers = [(question, evidence or "resolved", evidence)]
    else:
        proposal.abandon = [(question, evidence or "branch exhausted")]
    workspace.commit(proposal)
    return workspace


def question_already_settled(execution_state: Any, question: str) -> bool:
    workspace = workspace_of(execution_state)
    if workspace is None:
        return False
    return workspace.questions.is_settled(question)


def workspace_blocking_uncertainties(execution_state: Any) -> list:
    workspace = workspace_of(execution_state)
    if workspace is None:
        return []
    return workspace.questions.blocking_uncertainties()


def assess_executive_judgement(
    execution_state: Any,
    *,
    blocking_uncertainties: Optional[list] = None,
    evidence_gaps: Optional[list] = None,
    coverage: Optional[float] = None,
    has_grounded_action: bool = False,
    previously_suppressed: bool = False,
    last_action_surprised: bool = False,
    awaiting_verification: bool = False,
    hard_block: bool = False,
    probe_available: bool = False,
    ambiguous: bool = False,
    steps_remaining: Optional[int] = None,
    goal_complete: bool = False,
):
    """Compute this frame's sufficiency and meta-action, and record them.

    Runs for every goal, every iteration. The verdict is stored on the
    execution state (``last_sufficiency`` / ``last_meta_action``) so the loop
    can consult one authoritative judgement of act-vs-perceive instead of the
    old always-perceive default. Whether it *drives* control flow is decided by
    the caller; this function only computes and records.
    """
    from plugin.agent.executive.hierarchy import (
        ModeContext,
        cognitive_mode,
        decision_ladder,
    )
    from plugin.agent.executive.meta_action import (
        MetaAction,
        MetaContext,
        select_meta_action,
    )
    from plugin.agent.executive.perception_query import from_sufficiency
    from plugin.agent.executive.sufficiency import SufficiencyInputs, assess_sufficiency

    blocking = list(blocking_uncertainties or [])
    streak = int(getattr(execution_state, "identical_observe_streak", 0) or 0)
    sufficiency = assess_sufficiency(
        SufficiencyInputs(
            blocking_uncertainties=blocking,
            declared_evidence_gaps=list(evidence_gaps or []),
            has_grounded_action=bool(has_grounded_action),
            identical_observe_streak=streak,
            coverage=coverage,
            previously_suppressed=previously_suppressed,
            last_action_surprised=bool(last_action_surprised),
        )
    )

    # A blocking question that the workspace has already settled, with no world
    # change since (a stale streak / prior suppression), must not trigger yet
    # another look — that is the re-search failure the executive is built to end.
    branch_stale = previously_suppressed or streak >= 2
    question_settled = bool(
        blocking
        and branch_stale
        and all(question_already_settled(execution_state, q) for q in blocking)
    )

    meta_ctx = MetaContext(
        sufficiency=sufficiency,
        has_grounded_action=bool(has_grounded_action),
        awaiting_verification=bool(awaiting_verification),
        last_action_surprised=bool(last_action_surprised),
        branch_stale=branch_stale,
        question_settled=question_settled,
        hard_block=bool(hard_block),
        probe_available=bool(probe_available),
        ambiguous=bool(ambiguous),
        steps_remaining=int(steps_remaining) if steps_remaining is not None else 99,
    )
    # Two expressions of the same policy: the value scorer weighs moves, the
    # ladder states the precedence plainly. The ladder is authoritative for the
    # live loop (explicit precedence is what the runtime should walk), but we
    # keep the scorer's value breakdown for the trace and defer to it on the
    # ladder's terminal fallback so we never escalate to the user spuriously.
    scored = select_meta_action(meta_ctx)
    ladder = decision_ladder(meta_ctx, goal_complete=bool(goal_complete))
    meta = ladder
    if (
        ladder.action == MetaAction.ASK_USER
        and not hard_block
        and str(ladder.reason or "").startswith("fallback")
    ):
        meta = scored
    # Carry the value breakdown so the trace shows *why* each move scored as it
    # did, even when the ladder (not the scorer) chose.
    merged_scores = dict(scored.scores)
    merged_scores.update({f"ladder_{k}": v for k, v in (ladder.scores or {}).items()})
    meta.scores = merged_scores

    contradictions = 0
    workspace = workspace_of(execution_state)
    if workspace is not None:
        try:
            contradictions = len(workspace.unresolved_contradictions)
        except Exception:
            contradictions = 0
    mode = cognitive_mode(
        ModeContext(
            ambiguous=not sufficiency.sufficient_to_act and not sufficiency.observe_has_value,
            branch_exhausted=branch_stale,
            contradiction=contradictions > 0,
            last_action_surprised=bool(last_action_surprised),
        )
    )
    query = from_sufficiency(sufficiency)

    if execution_state is not None:
        execution_state.last_sufficiency = sufficiency.to_dict()
        execution_state.last_meta_action = meta.action.value
        execution_state.last_cognitive_mode = mode
        execution_state.last_perception_query = query.to_dict()
    return sufficiency, meta


def workspace_snapshot(execution_state: Any) -> Dict[str, Any]:
    workspace = workspace_of(execution_state)
    return workspace.to_dict() if workspace is not None else {}
