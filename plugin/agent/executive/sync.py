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
    # Keep the authored Goal on execution_state so meta referent-search and
    # branch fitness can read contact / link_query without only GoalState.
    if getattr(execution_state, "goal", None) is None:
        try:
            execution_state.goal = goal
        except Exception:
            pass
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


def _destination_search_needed(execution_state: Any) -> bool:
    """True when SEARCH is the correct epistemic move for an unresolved destination.

    Generic rule (``search_applicability``): known criteria + entity not visible
    + searchable scope available. Visible-but-unselected is ACT select; selected
    is ACT commit; missing search facility is EXPLORE — not a Forward-only patch
    (live 203259 / architect review).
    """
    if execution_state is None:
        return False
    try:
        from plugin.agent.executive.search_applicability import (
            attach_search_opportunities,
            entity_resolution_search_needed,
        )

        attach_search_opportunities(execution_state)
        return bool(entity_resolution_search_needed(execution_state))
    except Exception:
        return False


def _route_discovery_meta_kwargs(
    execution_state: Any, referent_signals: Dict[str, Any]
) -> Dict[str, Any]:
    """Populate MetaContext fields for effect-closed route discovery.

    Reveal is a bounded episode: pending unpaid look may advise EXPLORE;
    ``failed_reveal`` / probe exhaustion terminates incomplete debt so meta
    can ACT (escalated gesture) or THINK — not monopolize EXPLORE forever.
    Success path: grounded set or perceptor ``act_clear`` clears debt.
    """
    out: Dict[str, Any] = {
        "route_discovery_owed": False,
        "incomplete_reveal": False,
        "expected_overlay_missing": False,
        "forbid_content_act_fingerprint": "",
        "referent_repair_owed": False,
        "role_identity_search_owed": False,
        "act_clear": False,
        "reveal_episode_failed": False,
        "reveal_prefer_capability": "",
        "intention_explore_active": False,
        "intention_locally_exhausted": False,
        "locate_effect_verify_owed": False,
    }
    if execution_state is None:
        return out
    # IntentionFrame signals (generic intent-level retry).
    try:
        from plugin.agent.executive.intention_frame import (
            IntentionStatus,
            active_intention_frame,
            apply_derived_status,
            is_local_route_exhausted,
        )

        iframe = active_intention_frame(execution_state)
        if iframe is not None:
            apply_derived_status(iframe)
            pred = str(iframe.intention.success_predicate or "")
            if pred == "forward_affordance_grounded":
                exhausted = is_local_route_exhausted(iframe) or iframe.status in {
                    IntentionStatus.EXHAUSTED.value,
                    IntentionStatus.BLOCKED.value,
                }
                out["intention_locally_exhausted"] = bool(exhausted)
                out["intention_explore_active"] = bool(
                    not exhausted
                    and iframe.status == IntentionStatus.ACTIVE.value
                    and (
                        bool(iframe.method_frontier.eligible_methods())
                        or bool(iframe.pending_effect_verification)
                    )
                )
                # Episode-failed for meta only when intention is exhausted.
                if exhausted:
                    out["reveal_episode_failed"] = True
                elif out["intention_explore_active"]:
                    out["reveal_episode_failed"] = False
            elif pred in {"source_query_located", "content_located"}:
                exhausted = is_local_route_exhausted(iframe) or iframe.status in {
                    IntentionStatus.EXHAUSTED.value,
                    IntentionStatus.BLOCKED.value,
                }
                out["intention_locally_exhausted"] = bool(exhausted)
    except Exception:
        pass
    if bool(getattr(execution_state, "locate_effect_verify_owed", False)):
        out["locate_effect_verify_owed"] = True
    handoff = getattr(execution_state, "reveal_handoff", None)
    handoff_failed = False
    handoff_pending = False
    if isinstance(handoff, dict):
        handoff_failed = bool(handoff.get("failed_reveal")) or str(
            handoff.get("status") or ""
        ).strip().lower() in {"failed_reveal", "failed"}
        handoff_pending = (
            not handoff_failed
            and bool(str(handoff.get("surface") or "").strip())
            and bool(handoff.get("incomplete_reveal"))
        )
        # Only a *pending* unpaid look counts as incomplete for meta debt.
        out["incomplete_reveal"] = bool(handoff_pending)
        out["reveal_episode_failed"] = bool(handoff_failed)
    closure = getattr(execution_state, "last_effect_closure", None)
    if isinstance(closure, dict):
        modes = [str(m) for m in (closure.get("modes") or []) if str(m).strip()]
        out["expected_overlay_missing"] = "expected_overlay_missing" in modes or bool(
            closure.get("expected_overlay_missing")
        )
        # Closure incomplete only while the episode is still open — not after
        # a terminal failed_reveal (live 142848 EXPLORE monopoly).
        if closure.get("incomplete_reveal") and not handoff_failed:
            out["incomplete_reveal"] = True
        if closure.get("referent_repair_owed"):
            out["referent_repair_owed"] = True
        mode_blob = " ".join(modes).lower()
        mismatch_role = str(closure.get("referent_mismatch_role") or "").strip().lower()
        # Typed role mismatch: container/destination → SEARCH re-resolve;
        # object/selection → ACT repair. Do not conflate with GROUNDING.
        if "referent_mismatch" in mode_blob or "referent_mismatch" in modes:
            if mismatch_role in {"source_container", "destination"} or (
                not mismatch_role and closure.get("referent_search_needed")
            ):
                out["role_identity_search_owed"] = True
                out["referent_repair_owed"] = False
            else:
                out["referent_repair_owed"] = True
        elif any(
            tok in mode_blob
            for tok in (
                "wrong_target",
                "target_deselected",
                "selection_inconsistent",
            )
        ):
            out["referent_repair_owed"] = True
        if closure.get("referent_search_needed") and mismatch_role in {
            "source_container",
            "destination",
            "",
        }:
            out["role_identity_search_owed"] = True
        fp = str(closure.get("fingerprint") or "").strip()
        if fp:
            out["forbid_content_act_fingerprint"] = fp
    sel = getattr(execution_state, "last_selection_consistency", None)
    if isinstance(sel, dict) and sel.get("applicable") and sel.get("consistent") is False:
        out["referent_repair_owed"] = True
    if not out["forbid_content_act_fingerprint"]:
        out["forbid_content_act_fingerprint"] = str(
            getattr(execution_state, "last_failed_motor_key", "") or ""
        ).strip()
    grounded_n = 0
    try:
        from plugin.agent.affordance_frontier import grounded_affordance_set_of

        grounded_n = len(grounded_affordance_set_of(execution_state) or [])
    except Exception:
        grounded_n = len(
            list(getattr(execution_state, "last_grounded_affordance_set", None) or [])
        )
    content_known = bool(
        referent_signals.get("complete")
        or referent_signals.get("content_located")
        or str(referent_signals.get("chosen_label") or "").strip()
    )
    address_known = bool(referent_signals.get("address_known"))
    # Route discovery only while a probe still has information value:
    # pending unpaid look, or content known + empty grounded + budget left.
    # Terminal failed_reveal does *not* keep route debt (escalation → ACT).
    reveal_attempts = int(
        getattr(execution_state, "reveal_gesture_attempts", 0) or 0
    )
    prefer = str(
        getattr(execution_state, "reveal_prefer_capability", "") or ""
    ).strip()
    out["reveal_prefer_capability"] = prefer
    failed_motor = str(
        getattr(execution_state, "last_failed_motor_key", "") or ""
    ).strip()
    probe_budget_left = not handoff_failed
    out["route_discovery_owed"] = bool(
        not handoff_failed
        and (
            out["incomplete_reveal"]
            or out["expected_overlay_missing"]
            or (
                content_known
                and address_known
                and grounded_n == 0
                and not bool(referent_signals.get("failed"))
                and probe_budget_left
                and (reveal_attempts > 0 or bool(prefer) or bool(failed_motor))
                # Prefer-capability after failed escalate is ACT evidence, not
                # a reason to keep EXPLORE latched once the episode failed.
                and not bool(prefer and handoff_failed)
            )
        )
    )
    # Perceptor act-clear: only when stance is honest (geometry-backed) or the
    # grounded affordance_set already has actuators. Do not infer from QC +
    # overlay surface alone — that over-claimed clear without a clickable
    # control (live 171627 Observe thrash).
    stance = str(getattr(execution_state, "last_affordance_stance", "") or "").strip().lower()
    act_clear = stance == "act_clear"
    if not act_clear:
        uni = getattr(execution_state, "last_unified_proposal", None)
        if isinstance(uni, dict):
            if str(uni.get("affordance_stance") or "").strip().lower() == "act_clear":
                act_clear = True
    out["act_clear"] = bool(act_clear or grounded_n > 0)
    # Stamp epistemic milestone once SearchResult commits a chosen label.
    try:
        import time as _time

        if content_known and float(
            getattr(execution_state, "epistemic_success_at", 0.0) or 0.0
        ) <= 0.0:
            execution_state.epistemic_success_at = float(_time.monotonic())
        # Clear sticky reveal/route debt whenever control is grounded *or*
        # perceptor says act_clear — not only on the first grounded stamp.
        if grounded_n > 0 or act_clear:
            if grounded_n > 0 and float(
                getattr(execution_state, "affordance_grounded_at", 0.0) or 0.0
            ) <= 0.0:
                execution_state.affordance_grounded_at = float(_time.monotonic())
            out["incomplete_reveal"] = False
            out["expected_overlay_missing"] = False
            out["route_discovery_owed"] = False
            out["act_clear"] = True
            out["reveal_episode_failed"] = False
            try:
                if isinstance(handoff, dict):
                    execution_state.reveal_handoff = None
            except Exception:
                pass
            if isinstance(closure, dict) and (
                closure.get("incomplete_reveal")
                or closure.get("expected_overlay_missing")
            ):
                try:
                    execution_state.last_effect_closure = {
                        **dict(closure),
                        "incomplete_reveal": False,
                        "expected_overlay_missing": False,
                    }
                except Exception:
                    pass
        elif handoff_failed:
            # Terminal probe: no meta incomplete/route compulsion; escalation
            # prefs on execution_state remain for the next ACT choice.
            out["incomplete_reveal"] = False
            out["route_discovery_owed"] = False
            out["reveal_episode_failed"] = True
            if isinstance(closure, dict) and closure.get("incomplete_reveal"):
                try:
                    execution_state.last_effect_closure = {
                        **dict(closure),
                        "incomplete_reveal": False,
                    }
                except Exception:
                    pass
        # Clear referent repair once selection is consistent again.
        if (
            isinstance(sel, dict)
            and sel.get("applicable")
            and sel.get("consistent") is True
        ):
            out["referent_repair_owed"] = False
            if isinstance(closure, dict) and closure.get("referent_repair_owed"):
                try:
                    execution_state.last_effect_closure = {
                        **dict(getattr(execution_state, "last_effect_closure", None) or closure),
                        "referent_repair_owed": False,
                    }
                except Exception:
                    pass
            if float(getattr(execution_state, "referent_selected_at", 0.0) or 0.0) <= 0.0:
                execution_state.referent_selected_at = float(_time.monotonic())
    except Exception:
        pass
    return out


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
    meta_chooser: Optional[Any] = None,
    blockers: Optional[Dict[str, Any]] = None,
    housekeeping_capabilities: Optional[list] = None,
):
    """Compute this frame's sufficiency and meta-action, and record them.

    Runs for every goal, every iteration. The verdict is stored on the
    execution state (``last_sufficiency`` / ``last_meta_action``) so the loop
    can consult one authoritative judgement of act-vs-perceive instead of the
    old always-perceive default. Whether it *drives* control flow is decided by
    the caller; this function only computes and records.

    Meta-action is always LLM-chosen (``meta_chooser`` injectable for tests).
    There is no ladder fallback and no env kill switch.
    """
    from plugin.agent.executive.hierarchy import (
        ModeContext,
        cognitive_mode,
        mode_triggers,
    )
    from plugin.agent.executive.meta_action import (
        MetaContext,
        reperception_exhausted,
        select_meta_action,
    )
    from plugin.agent.executive.meta_consultation import resolve_meta_choice
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
    #
    # A run of surprises that each bought a look and still left the world
    # unmoved is the same condition reached by a different road: this branch has
    # stopped converging, so it is stale and the executive should broaden rather
    # than re-read the screen again.
    #
    # Post-act debt is separate: while the executive has not finished
    # re-perceive after a motor write, surprise-relook exhaustion must not
    # skip rung-1 and jump to the next decide (live 033711).
    post_action_look_owed = bool(
        getattr(execution_state, "post_action_reperceive_pending", False)
        or getattr(execution_state, "must_executive_reperceive", False)
    )
    relooks_exhausted = reperception_exhausted(execution_state) and not post_action_look_owed
    branch_stale = previously_suppressed or streak >= 2 or relooks_exhausted
    question_settled = bool(
        blocking
        and branch_stale
        and all(question_already_settled(execution_state, q) for q in blocking)
    )

    # Streak budgets live on execution_state; the executive consumes them as
    # meta inputs. The loop must not rewrite the resulting MetaChoice to ACT.
    from plugin.agent.executive.meta_action import (
        BACKTRACK_STREAK_CAP,
        INFORMATION_GATHERING_STREAK_CAP,
        PERCEIVE_STREAK_CAP,
        PROBE_STREAK_CAP,
        SEARCH_STREAK_CAP,
        THINK_STREAK_CAP,
    )

    backtrack_exhausted = (
        int(getattr(execution_state, "consecutive_backtracks", 0) or 0)
        >= BACKTRACK_STREAK_CAP
    )
    information_gathering_exhausted = (
        int(getattr(execution_state, "consecutive_information_gathering", 0) or 0)
        >= INFORMATION_GATHERING_STREAK_CAP
    )
    think_exhausted = (
        int(getattr(execution_state, "consecutive_thinks", 0) or 0) >= THINK_STREAK_CAP
    )
    probe_exhausted = (
        int(getattr(execution_state, "consecutive_probes", 0) or 0) >= PROBE_STREAK_CAP
    )
    perceive_streak_exhausted = (
        int(getattr(execution_state, "consecutive_perceives", 0) or 0)
        >= PERCEIVE_STREAK_CAP
    )
    search_exhausted = (
        int(getattr(execution_state, "consecutive_searches", 0) or 0) >= SEARCH_STREAK_CAP
    )

    contradictions = 0
    workspace = workspace_of(execution_state)
    phase = ""
    if workspace is not None:
        try:
            contradictions = len(workspace.unresolved_contradictions)
        except Exception:
            contradictions = 0
        phase = str(getattr(workspace, "phase", "") or "").strip().lower()
    # Mode triggers must be known *before* meta choice so the LLM packet
    # includes the same discriminators mined from live executive_judgement.
    new_goal = getattr(execution_state, "last_meta_action", None) is None
    high_consequence = phase in {
        "invoke_forward",
        "choose_destination",
        "act_on_content",
        "commit",
    }
    no_matching_procedure = (
        not has_grounded_action
        and not probe_available
        and not sufficiency.observe_has_value
        and not sufficiency.sufficient_to_act
    )
    mode_ctx = ModeContext(
        new_goal=bool(new_goal),
        ambiguous=not sufficiency.sufficient_to_act and not sufficiency.observe_has_value,
        branch_exhausted=branch_stale,
        high_consequence=bool(high_consequence),
        contradiction=contradictions > 0,
        no_matching_procedure=bool(no_matching_procedure),
        last_action_surprised=bool(last_action_surprised),
    )
    mode = cognitive_mode(mode_ctx)
    triggers = mode_triggers(mode_ctx)
    soft = [
        str(s)
        for s in (getattr(execution_state, "perception_soft_signals", None) or [])
        if str(s).strip()
    ][:4]
    for sig in soft:
        if sig not in triggers:
            triggers.append(sig)
    query = from_sufficiency(sufficiency)
    contract = contract_status(execution_state) if execution_state is not None else {}

    from plugin.agent.executive.meta_situation import MetaSituation

    from plugin.agent.capabilities.housekeeping import (
        admissible_housekeeping_capabilities,
    )

    blocker_view = dict(blockers or {})
    hk_caps = [
        dict(c)
        for c in (housekeeping_capabilities or [])
        if isinstance(c, dict) and str(c.get("name") or "").strip()
    ]
    if not hk_caps and blocker_view:
        hk_caps = admissible_housekeeping_capabilities(blocker_view)

    situation = MetaSituation(
        cognitive_mode=mode,
        mode_triggers=list(triggers),
        static_streak=streak,
        coverage=coverage,
        evidence_gaps=[str(g) for g in (evidence_gaps or []) if str(g).strip()][:6],
        blocking_uncertainties=[str(q) for q in blocking if str(q).strip()][:6],
        perception_query=query.to_dict() if hasattr(query, "to_dict") else {},
        goal_contract={
            "satisfied": list(contract.get("satisfied") or []),
            "pending": list(contract.get("pending") or []),
            "constraints": list(contract.get("constraints") or []),
            "all_satisfied": bool(
                goal_complete or contract.get("all_satisfied")
            ),
        },
        phase=phase or str(contract.get("phase") or ""),
        last_meta_action=str(getattr(execution_state, "last_meta_action", "") or ""),
        last_action=str(getattr(execution_state, "last_action", "") or ""),
        consecutive_surprise_relooks=int(
            getattr(execution_state, "consecutive_surprise_relooks", 0) or 0
        ),
        consecutive_perceives=int(
            getattr(execution_state, "consecutive_perceives", 0) or 0
        ),
        consecutive_thinks=int(getattr(execution_state, "consecutive_thinks", 0) or 0),
        consecutive_probes=int(getattr(execution_state, "consecutive_probes", 0) or 0),
        consecutive_backtracks=int(
            getattr(execution_state, "consecutive_backtracks", 0) or 0
        ),
        consecutive_information_gathering=int(
            getattr(execution_state, "consecutive_information_gathering", 0) or 0
        ),
        consecutive_searches=int(
            getattr(execution_state, "consecutive_searches", 0) or 0
        ),
        blockers=blocker_view,
        housekeeping_capabilities=hk_caps,
    )

    fitness = getattr(execution_state, "last_branch_fitness", None)
    if not isinstance(fitness, dict) or not fitness:
        try:
            from plugin.agent.capabilities.branch_fitness import (
                compute_branch_fitness,
                needed_evidence_kinds_for_goal,
            )
            from plugin.agent.apps.registry import get_overlay

            doc = getattr(execution_state, "unified_world_document", None)
            doc = dict(doc) if isinstance(doc, dict) else {}
            overlay = get_overlay(
                str(getattr(getattr(execution_state, "goal", None), "app", None) or "WhatsApp"),
                None,
            )
            enrich = getattr(overlay, "enrich_world_document", None)
            if callable(enrich):
                doc = enrich(doc)
            goal_obj = getattr(execution_state, "goal", None)
            fitness = compute_branch_fitness(
                doc,
                needed_kinds=needed_evidence_kinds_for_goal(goal_obj),
                goal=goal_obj,
                goal_referents=list(getattr(execution_state, "goal_referents", None) or []),
                selection_consistency=getattr(
                    execution_state, "last_selection_consistency", None
                ),
            )
            execution_state.last_branch_fitness = fitness
            execution_state.last_branch_consistency = fitness
        except Exception:
            fitness = {}
    branch_unfit = isinstance(fitness, dict) and fitness.get("admissible") is False

    referent_signals: Dict[str, Any] = {}
    try:
        from plugin.agent.capabilities.resolve_entity import open_matches_referent
        from plugin.agent.capabilities.search_episode import (
            goal_search_criteria,
            meta_referent_search_signals,
        )

        doc = getattr(execution_state, "unified_world_document", None)
        surf = ""
        if isinstance(doc, dict):
            surf = str(doc.get("surface") or "")
        goal_obj = getattr(execution_state, "goal", None)
        ws = workspace_of(execution_state)
        # Prefer authored Goal; fall back to workspace GoalState (subject/query).
        if goal_obj is None and ws is not None and getattr(ws, "goal", None) is not None:
            goal_obj = ws.goal
        open_c = ""
        if ws is not None:
            open_c = str(getattr(ws, "open_conversation", "") or "").strip()
        if not open_c and isinstance(doc, dict):
            open_c = str(doc.get("open_conversation") or "").strip()
        contact, link_q, _dest = goal_search_criteria(goal_obj)
        # Identity match only — participant CSVs / weak containment must not
        # clear referent-search debt (live 214626: group header named Pallavi).
        if open_c and contact:
            source_open = bool(open_matches_referent(open_c, contact))
        else:
            source_open = False
        # Settle verify + debt clear belong to the controller transition path
        # (attempt-scoped). Sync must not erase mismatch debt merely because
        # the correct conversation happens to be open.
        content_located = False
        try:
            extras = {}
            if isinstance(doc, dict):
                extras = doc
            content_located = bool(
                extras.get("source_content_visible")
                or extras.get("timeline_query_hit")
                or extras.get("query_in_timeline")
            )
            if not content_located and link_q and isinstance(doc, dict):
                from plugin.agent.source_query_binding import document_locates_source_query

                # Soft locate requires query identity — not "any URL in chat".
                content_located = document_locates_source_query(doc, link_q)
        except Exception:
            content_located = False
        referent_signals = meta_referent_search_signals(
            execution_state,
            phase=phase or str(contract.get("phase") or ""),
            source_chat_open=source_open,
            surface=surf,
            goal=goal_obj,
            content_located=content_located,
            document=doc if isinstance(doc, dict) else None,
        )
        if search_exhausted:
            referent_signals["exhausted"] = True
        # In-loop leave-wrong-conversation debt (live 145943): foreign open
        # pane must not be treated as "already in a chat → hunt / compose".
        ph_l = str(phase or contract.get("phase") or "").strip().lower().replace("-", "_")
        leave_phases = {
            "",
            "reach_source",
            "open_source",
            "preclear",
        }
        source_row_ready = bool(referent_signals.get("source_contact_open_ready"))
        if (
            execution_state is not None
            and ph_l in leave_phases
            and open_c
            and contact
            and not source_open
        ):
            execution_state.leave_wrong_conversation_owed = True
            execution_state.leave_wrong_conversation_open = open_c
            execution_state.leave_wrong_conversation_source = contact
            execution_state.source_contact_open_ready = source_row_ready
            execution_state.source_contact_open_label = str(
                referent_signals.get("source_contact_open_label") or ""
            )
            try:
                from plugin.agent.capabilities.locus_contract import (
                    stamp_wrong_locus_debt,
                )

                stamp_wrong_locus_debt(
                    execution_state,
                    kind="container",
                    forbidden="foreign_container",
                    required="open_matches_referent(source)",
                    why=f"foreign_open:{open_c!r}!={contact!r}",
                )
            except Exception:
                pass
            # Drop stale reveal predictions while the source container is wrong.
            exp = getattr(execution_state, "unified_last_expectation", None)
            if (
                isinstance(exp, dict)
                and str(exp.get("surface") or "").strip().lower()
                in {"context_menu", "action_menu", "selection_mode", "message_actions"}
                and surf in {"search", "search_results", "chat_list", "conversation"}
            ):
                try:
                    execution_state.unified_last_expectation = None
                    execution_state.act_intention_pending = False
                except Exception:
                    pass
        elif execution_state is not None:
            execution_state.leave_wrong_conversation_owed = False
            execution_state.leave_wrong_conversation_open = ""
            execution_state.leave_wrong_conversation_source = ""
            execution_state.source_contact_open_ready = source_row_ready and not source_open
            execution_state.source_contact_open_label = (
                str(referent_signals.get("source_contact_open_label") or "")
                if (source_row_ready and not source_open)
                else ""
            )
            # Clear container wrong-locus debt once source is open / leave resolved.
            if str(getattr(execution_state, "wrong_locus_kind", "") or "") in {
                "",
                "container",
            }:
                try:
                    from plugin.agent.capabilities.locus_contract import (
                        clear_wrong_locus_debt,
                    )

                    clear_wrong_locus_debt(execution_state)
                except Exception:
                    pass
        # Field wrong-locus: composer focused while hunting content.
        if execution_state is not None:
            role = str(
                (doc or {}).get("focused_field_role")
                or getattr(execution_state, "focused_field_role", "")
                or ""
            ).strip().lower()
            from plugin.agent.capabilities.locus_contract import (
                COMPOSER_FIELD_ROLES,
                FILTER_FIELD_ROLES,
                clear_wrong_locus_debt,
                stamp_wrong_locus_debt,
            )

            if role in COMPOSER_FIELD_ROLES and source_open:
                # Past container-open: composer focus must not become type locus.
                stamp_wrong_locus_debt(
                    execution_state,
                    kind="field",
                    forbidden="composer",
                    required="filter_field",
                    why=f"composer_focused:{role}",
                )
            elif role in FILTER_FIELD_ROLES and str(
                getattr(execution_state, "wrong_locus_kind", "") or ""
            ) == "field":
                clear_wrong_locus_debt(execution_state)
    except Exception:
        referent_signals = {}

    locate_verify_owed = bool(
        getattr(execution_state, "locate_effect_verify_owed", False)
    )
    meta_ctx = MetaContext(
        sufficiency=sufficiency,
        has_grounded_action=bool(has_grounded_action),
        awaiting_verification=(
            bool(awaiting_verification) or post_action_look_owed or locate_verify_owed
        ),
        last_action_surprised=bool(last_action_surprised),
        post_action_look_owed=post_action_look_owed,
        branch_stale=branch_stale,
        question_settled=question_settled,
        reperception_exhausted=relooks_exhausted,
        hard_block=bool(hard_block),
        probe_available=bool(probe_available),
        ambiguous=bool(ambiguous),
        steps_remaining=int(steps_remaining) if steps_remaining is not None else 99,
        backtrack_exhausted=backtrack_exhausted,
        information_gathering_exhausted=information_gathering_exhausted,
        think_exhausted=think_exhausted,
        probe_exhausted=probe_exhausted,
        perceive_streak_exhausted=perceive_streak_exhausted,
        branch_unfit=branch_unfit,
        branch_fitness=fitness if isinstance(fitness, dict) else None,
        referent_search_needed=bool(referent_signals.get("needed")),
        search_episode_incomplete=bool(referent_signals.get("incomplete")),
        search_episode_complete=bool(referent_signals.get("complete")),
        search_episode_failed=bool(referent_signals.get("failed")),
        search_exhausted=bool(referent_signals.get("exhausted") or search_exhausted),
        search_retreat_owed=bool(
            referent_signals.get("retreat_owed")
            or getattr(execution_state, "search_retreat_owed", False)
        ),
        search_progress=referent_signals.get("progress")
        if isinstance(referent_signals.get("progress"), dict)
        else getattr(execution_state, "last_search_progress", None),
        search_episode=referent_signals.get("episode")
        if isinstance(referent_signals.get("episode"), dict)
        else None,
        address_known=bool(referent_signals.get("address_known")),
        retrieve_ready=bool(referent_signals.get("retrieve_ready")),
        source_contact_open_ready=bool(
            referent_signals.get("source_contact_open_ready")
        ),
        leave_wrong_conversation_owed=bool(
            getattr(execution_state, "leave_wrong_conversation_owed", False)
        ),
        wrong_locus_recovery_owed=bool(
            getattr(execution_state, "wrong_locus_recovery_owed", False)
        ),
        wrong_locus_kind=str(
            getattr(execution_state, "wrong_locus_kind", "") or ""
        ),
        search_has_criteria=bool(
            referent_signals.get("has_criteria")
            if "has_criteria" in referent_signals
            else True
        ),
        destination_search_needed=_destination_search_needed(execution_state),
        grounding_reground_only=bool(
            getattr(execution_state, "grounding_reground_only", False)
        ),
        **_route_discovery_meta_kwargs(execution_state, referent_signals),
    )
    # Grounding-local recovery: suppress SEARCH/EXPLORE pressure until reground.
    if bool(getattr(meta_ctx, "grounding_reground_only", False)):
        meta_ctx.destination_search_needed = False
        meta_ctx.referent_search_needed = False
        meta_ctx.route_discovery_owed = False
        meta_ctx.intention_explore_active = False
        meta_ctx.post_action_look_owed = True
    # Entity-resolution SEARCH owns the next epistemic move: do not let latent
    # route-discovery EXPLORE compete with picker type_query (live 203259).
    if bool(getattr(meta_ctx, "destination_search_needed", False)):
        meta_ctx.route_discovery_owed = False
        meta_ctx.incomplete_reveal = False
        meta_ctx.expected_overlay_missing = False
        meta_ctx.intention_explore_active = False
    # Role identity failure owns SEARCH until a new eligible candidate binds.
    if bool(getattr(meta_ctx, "role_identity_search_owed", False)):
        meta_ctx.referent_search_needed = True
        meta_ctx.retrieve_ready = False
        meta_ctx.referent_repair_owed = False
        meta_ctx.route_discovery_owed = False
        meta_ctx.intention_explore_active = False
    # Live: LLM chooses the meta-action (text stack / meta_choice). Ladder and
    # scorer remain as offline fallback + advisory scores for the trace — never
    # silently replace an ASK_USER fallback with the scorer.
    scored = select_meta_action(meta_ctx)
    meta = resolve_meta_choice(
        meta_ctx,
        goal_complete=bool(goal_complete or situation.goal_contract.get("all_satisfied")),
        chooser=meta_chooser,
        situation=situation,
    )
    merged_scores = dict(scored.scores or {})
    merged_scores.update({f"scorer_{k}": v for k, v in (scored.scores or {}).items()})
    for k, v in (meta.scores or {}).items():
        merged_scores[k] = v
    meta.scores = merged_scores

    if execution_state is not None:
        execution_state.last_sufficiency = sufficiency.to_dict()
        execution_state.last_meta_action = meta.action.value
        execution_state.last_cognitive_mode = mode
        execution_state.last_mode_triggers = triggers
        execution_state.last_perception_query = query.to_dict()
        # Next look (if any) inherits reflect mode when meta chose REFLECT.
        if meta.action.value == "reflect":
            execution_state.perception_mode = "reflect"
    return sufficiency, meta


def contract_status(execution_state: Any) -> Dict[str, Any]:
    """Report the goal contract and which success conditions are met so far.

    The contract (success conditions + constraints) is the executive's own
    definition of "done" and "what must hold". It lived on the workspace but was
    never consulted; this reads it and estimates progress from the one signal the
    core has that is domain-general — the phase's position on the registered
    ladder — so the executive can (a) know how many success conditions remain,
    (b) judge completion at the contract level, and (c) surface the constraints
    that still bind. The mapping is deliberately coarse: phases and success
    conditions both describe the same task arc, so ladder progress is a fair
    proxy for how much of the contract is satisfied.
    """
    workspace = workspace_of(execution_state)
    if workspace is None:
        return {}
    success = list(workspace.goal.success_conditions or [])
    constraints = list(workspace.goal.constraints or [])
    ladder = workspace.ladder()
    phase = str(workspace.phase or "").strip().lower()
    satisfied: list = []
    pending: list = list(success)
    if success and ladder and phase in ladder:
        span = max(1, len(ladder) - 1)
        fraction = ladder.index(phase) / span
        n = max(0, min(len(success), round(fraction * len(success))))
        satisfied = list(success[:n])
        pending = list(success[n:])
    all_satisfied = bool(success) and not pending
    return {
        "success_conditions": success,
        "constraints": constraints,
        "satisfied": satisfied,
        "pending": pending,
        "all_satisfied": all_satisfied,
        "phase": phase,
    }


def workspace_snapshot(execution_state: Any) -> Dict[str, Any]:
    workspace = workspace_of(execution_state)
    return workspace.to_dict() if workspace is not None else {}
