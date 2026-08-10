"""Plugin runtime state — WorldModel is primary; ExecutionState tracks closed-loop progress."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Callable
from typing import Any, Deque, Dict, List, Optional, Tuple

from plugin.agent.action import Action, PlanStep
from plugin.agent.transition.belief_state import Belief, BeliefStore, BeliefUpdate, Experiment, GoalCondition, Hypothesis, Uncertainty
from plugin.agent.transition.attribution import HypothesisLayers
from plugin.agent.transition.experience import StateExperience
from plugin.agent.transition.types import ExplorationBranch, InteractionContext
from plugin.worldmodel.capability import CapabilityMemory
from plugin.worldmodel.model import WorldModel, WorldPatch
from plugin.agent.executive.workspace import AttemptRecord, ExecutiveWorkspace, WorkspaceProposal

# Distinct moves whose attempt history is kept. Generous — a run makes far fewer
# distinct moves than iterations — but bounded, so a long run cannot turn its own
# history into unbounded context.
MAX_TRACKED_ATTEMPTS = 48


@dataclass
class ExecutionState:
    iteration: int = 0
    step: int = 0  # alias used by older code
    last_action: Optional[str] = None
    last_plan_step: Optional[PlanStep] = None
    last_target_id: Optional[int] = None
    last_result: Optional[Dict[str, Any]] = None
    last_world_signature: Optional[str] = None
    last_semantic_state_signature: Optional[str] = None
    repeated_action_count: int = 0
    unchanged_world_count: int = 0
    semantic_repeat_count: int = 0
    # Cumulative ledger of every move tried, keyed by family+target+surface.
    # See note_attempt() for why the consecutive counter above is not enough.
    action_attempts: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    planner_invocations: int = 0
    recent_action_state_pairs: Deque[Tuple[str, str]] = field(
        default_factory=lambda: deque(maxlen=8)
    )
    prohibited_actions: Dict[str, int] = field(default_factory=dict)  # key → remaining skips
    last_verification: Optional[Dict[str, Any]] = None
    failures: List[str] = field(default_factory=list)
    # One-shot overlay when ax_type proved the query but ingest missed it
    search_query_hint: str = ""
    search_query_hint_ttl: int = 0  # consume across a few cycles then drop
    search_hypothesis_index: int = 0
    search_refinement_pending: bool = False
    open_contact_fail_streak: int = 0
    type_query_fail_streak: int = 0
    end_call_fail_streak: int = 0
    ambiguous_observe_count: int = 0
    last_resolved_contact: str = ""
    world_id: str = "w0"
    world_seq: int = 0
    belief_store: BeliefStore = field(default_factory=BeliefStore)
    active_uncertainty: Optional[Uncertainty] = None
    active_hypotheses: List[Hypothesis] = field(default_factory=list)
    active_experiment: Optional[Experiment] = None
    goal_conditions: List[GoalCondition] = field(default_factory=list)
    belief_updates: List[BeliefUpdate] = field(default_factory=list)
    last_belief_update: Optional[BeliefUpdate] = None
    state_experience: StateExperience = field(default_factory=StateExperience)
    hypothesis_layers: HypothesisLayers = field(default_factory=HypothesisLayers)
    last_transition: Optional[Dict[str, Any]] = None
    last_attribution: Optional[Dict[str, Any]] = None
    # Bounded history of recent surprises (actions whose result was not what we
    # predicted). Fed to perception so the model sees the *pattern* of failures,
    # not just the last one, and can re-perceive at finer granularity — the
    # perception analogue of attending over prior context.
    recent_surprises: List[Dict[str, Any]] = field(default_factory=list)
    # Last X accepted world snapshots (compact). REFLECT packets use these as
    # prior perceptions so the perceptor can explain prediction error against
    # what it believed before the act, not only the fresh frame.
    recent_perceptions: List[Dict[str, Any]] = field(default_factory=list)
    # Last surprise_explanation from a REFLECT look (cause / confidence / next).
    last_surprise_explanation: Optional[Dict[str, Any]] = None
    # Fingerprint of the last failed motor the brain must not re-issue unchanged.
    last_failed_motor_key: str = ""
    # Families+points that produced no world effect (e.g. reveal without menu).
    # Fed to unified perception as avoid_families so the same latch is not re-offered.
    avoid_motor_keys: List[str] = field(default_factory=list)
    # Forward-leg ring buffer for overloaded revert_effects (capability, intention,
    # post-look prediction/selection deltas). Cap enforced by append helper.
    effect_trace: List[Dict[str, Any]] = field(default_factory=list)
    # Last selection_consistency_error verdict from post-act look.
    last_selection_consistency: Optional[Dict[str, Any]] = None
    # Goal × world branch fitness (admissible / blockers) — backtrack evidence.
    last_branch_fitness: Optional[Dict[str, Any]] = None
    # Compat alias populated alongside last_branch_fitness.
    last_branch_consistency: Optional[Dict[str, Any]] = None
    # Goal content tokens (link_query, …) for consistency / revert analyze.
    goal_referents: List[str] = field(default_factory=list)
    # Compound search episode: querying → retrieving → ranking → complete|failed.
    # Incomplete until chosen (or unique fit / failed). Commit is outside search.
    search_episode: Optional[Dict[str, Any]] = None
    # Last find attempt progress (delta / empty). Zero progress ⇒ retreat before
    # re-entering MetaAction.SEARCH (loop convergence; no failure catalog).
    last_search_progress: Optional[Dict[str, Any]] = None
    # Set when a search episode fails empty / zero progress; cleared by
    # BACKTRACK or INFORMATION_GATHERING so SEARCH may start fresh.
    search_retreat_owed: bool = False
    # After revert_effects succeeds: next look should re_ground_then_act.
    pending_repair_after_revert: Optional[Dict[str, Any]] = None
    last_revert_plan: Optional[Dict[str, Any]] = None
    # Last accepted world surface; change invalidates carried geometry.
    last_accepted_surface: str = ""
    # Bumped when surface changes or geometry is explicitly invalidated.
    geometry_generation: int = 0
    # The executive's single authoritative record of task state: arbitrated
    # beliefs, open questions, attempts and transitions. The sync helpers and
    # assess_executive_judgement read/write it through workspace_of(); without
    # it the whole executive belief layer is inert.
    workspace: ExecutiveWorkspace = field(default_factory=ExecutiveWorkspace)
    # Consecutive executive BACKTRACK meta-actions with no intervening real move.
    # Backtracking repeatedly with no new evidence is not progress; once it runs
    # long the branch space is exhausted and the executive escalates instead of
    # thrashing. Reset whenever a non-backtrack move is taken.
    consecutive_backtracks: int = 0
    # Consecutive executive INFORMATION_GATHERING meta-actions. Re-planning the
    # branch order executes nothing and, once the re-perception budget is spent,
    # suppresses the next look as well, so a run of these learns nothing and
    # changes nothing while costing a full iteration each. It shares the
    # backtrack counter's exhaustion rule, but at five that is far too slack for
    # a move this inert; this counts it separately so it can be cut off sooner.
    consecutive_information_gathering: int = 0
    # Consecutive MetaAction.SEARCH turns (find-stage actuation). Cap in meta_action.
    consecutive_searches: int = 0
    # Consecutive PERCEIVE looks without falling through to ACT. Looking for
    # grounded geometry forever (live 135459) never binds a motor; cap then ACT.
    consecutive_perceives: int = 0
    # Consecutive diagnostic re-looks spent on surprises without the world moving.
    # A surprise buys a look carrying the failed attempt, which is how the model
    # works out why its move did nothing. But looking again at a world that keeps
    # not moving stops paying: past the cap the executive broadens the search
    # instead of re-reading the same screen. Reset the moment the world moves.
    consecutive_surprise_relooks: int = 0
    # One-executive contract: after any non-observe act, the next iteration must
    # run a fresh perceive (stage1 multimodal) before choosing the next capability.
    # AX settle / TransitionEvaluator must not substitute for that look.
    must_executive_reperceive: bool = False
    # Soft perception-quality hints (retention_low / worldview_low / …). Advisory
    # for meta only — never aliases must_executive_reperceive (hard look debt).
    perception_soft_signals: List[str] = field(default_factory=list)
    # True after ACT stamps unified_last_expectation from the decision's claim.
    # Cleared once post-act perceive scores that intention (note_prediction_error).
    # Stops a compact look with no expected_transition from wiping the claim
    # before it is scored.
    act_intention_pending: bool = False
    # Stays set until a *fresh* stage1 reading lands (not phash reuse / not a
    # failed look). Blocks perceive→ACT fallthrough onto a pre-act world.
    post_action_reperceive_pending: bool = False
    # Snapshot at act time (diagnostics); clear pending on any fresh stage1 look.
    post_action_baseline_open: str = ""
    post_action_baseline_sig: str = ""
    # Affordances the runtime measured as inert (invoked, app did not move). The
    # frontier is rebuilt from scratch each frame, so without this record a
    # control already proven dead is offered to the perceptor as a live option
    # again on the very next look. Written by the world critic.
    dead_affordances: List[Dict[str, Any]] = field(default_factory=list)
    # After reveal_actions probe: short-lived note that an overlay should be
    # ingested into affordance_set. Cleared when grounded controls land or
    # post-perceive marks failed_reveal.
    reveal_handoff: Optional[Dict[str, Any]] = None
    # Last post-perceive effect-closure modes (expected_overlay_missing, …).
    last_effect_closure: Optional[Dict[str, Any]] = None
    # Milestone clocks for responsiveness (monotonic timestamps).
    epistemic_success_at: float = 0.0
    affordance_grounded_at: float = 0.0
    referent_selected_at: float = 0.0
    instrumental_commit_at: float = 0.0
    reveal_gesture_attempts: int = 0
    # Next reveal motor after an incomplete/failed probe (live 153213):
    # context_click → hover → then prefer select_content (toolbar Forward path).
    # Actor/consultation honor this so motor-ok context_click cannot loop forever.
    reveal_probe_mode: str = "context_click"
    # When set (usually after hover also fails), consultation prefers this
    # capability instead of re-issuing reveal_actions at the same latch.
    reveal_prefer_capability: str = ""
    # Generic intention execution stack (IntentionFrame). Top = currently
    # executing; parents may be suspended_by_child. See intention_frame.py.
    intention_stack: List[Any] = field(default_factory=list)
    # Grounded invoke/commit controls from the last frontier reconcile — the
    # durable affordance_set substrate for invoke_affordance (parity with
    # addressable_entity materialization).
    last_grounded_affordance_set: List[Dict[str, Any]] = field(default_factory=list)
    # Perceptor stance from last look: act_clear | explore_needed | ambiguous.
    last_affordance_stance: str = ""
    # Last affordance frontier packet the perceptor/brain shared.
    last_affordance_frontier: Optional[Dict[str, Any]] = None
    # Exclusive filter_input site (Search) from the last look's AX/OCR evidence.
    # Decision consultation binds compose_search_query here when VLM objects omit
    # the field (live 123746). Cleared/replaced each perception packet build;
    # also cleared when leaving reach_source / non-filter surfaces (125715).
    last_filter_geometry: Optional[Dict[str, Any]] = None
    # OCR menu-verb hints (Forward/Reply/…) measured under reveal_handoff.
    # Used only to enrich the accepted document before post-accept promote —
    # never as a direct affordance_set invent path (live 125715).
    last_overlay_ocr_menu: Optional[List[Dict[str, Any]]] = None
    # Branches abandoned for making no progress. Read by should_escalate() to
    # call branch exhaustion and send the next decision to the deep reasoner.
    no_progress_replans: int = 0
    # Consecutive commits refused because the screen had moved on since it was
    # perceived. Bounded: a target that never settles (a live-updating list, a
    # playing video) would otherwise abort forever, and an agent that never
    # commits is no better than one that commits wrongly. Reset on any commit.
    consecutive_stale_aborts: int = 0
    # Times the agent took the foreground back from another app mid-task. Purely
    # diagnostic — the reclaim itself is unconditional and uncapped, because the
    # interruptions it answers (a call, a notification) recur by nature.
    foreground_reclaims: int = 0
    active_action_world_id: str = ""
    # World-uncertainty flag: prefer re-observe + fresh affordances; never revise intent
    world_exploration_needed: bool = False
    world_explore_observe_count: int = 0
    # Trajectory / branch awareness
    interaction_context: InteractionContext = field(default_factory=InteractionContext)
    exploration_branch: ExplorationBranch = field(default_factory=ExplorationBranch)
    perception_incomplete: bool = False
    last_perception_failure_modes: List[str] = field(default_factory=list)
    perception_cycle_stalled: bool = False
    last_perception_stall_signature: str = ""
    perception_stall_count: int = 0
    perception_stall_reason: str = ""
    capability_memory: CapabilityMemory = field(default_factory=CapabilityMemory)
    # Forward binding: identical Observe suppression
    identical_observe_streak: int = 0
    last_observe_signature: str = ""
    suppress_observe: bool = False
    storage_cleanup_signature: str = ""
    storage_cleanup_count: int = 0

    def bump_world_id(self, *, significant: bool = True) -> str:
        if significant:
            self.world_seq += 1
            self.world_id = f"w{self.world_seq}"
        return self.world_id

    def note_surprise(self, entry: Dict[str, Any], *, cap: int = 5) -> None:
        """Append one surprise to the bounded history, de-duping the same frame.

        Kept small on purpose: perception needs the recent *shape* of failures
        (what we tried, what actually happened), not an unbounded transcript.
        """
        if not isinstance(entry, dict) or not entry:
            return
        frame = entry.get("iteration")
        if self.recent_surprises and frame is not None:
            if self.recent_surprises[-1].get("iteration") == frame:
                # Same iteration re-emitting (e.g. across a perception skip):
                # replace rather than duplicate.
                self.recent_surprises[-1] = entry
                return
        self.recent_surprises.append(entry)
        if len(self.recent_surprises) > cap:
            del self.recent_surprises[0 : len(self.recent_surprises) - cap]

    def note_perception(
        self,
        document: Dict[str, Any],
        *,
        iteration: Optional[int] = None,
        screenshot_path: str = "",
        cap: int = 4,
    ) -> None:
        """Append a compact accepted-world snapshot for REFLECT priors."""
        if not isinstance(document, dict) or not document:
            return
        objects_out: List[Dict[str, Any]] = []
        for obj in (document.get("objects") or [])[:8]:
            if not isinstance(obj, dict):
                continue
            entry_o: Dict[str, Any] = {
                "id": str(obj.get("id") or "")[:40],
                "kind": str(obj.get("kind") or "")[:40],
                "text": str(obj.get("text") or obj.get("label") or "")[:80],
            }
            pt = obj.get("point")
            if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                try:
                    entry_o["point"] = [float(pt[0]), float(pt[1])]
                except (TypeError, ValueError):
                    pass
            if obj.get("matches_goal"):
                entry_o["matches_goal"] = True
            objects_out.append(entry_o)
        snap: Dict[str, Any] = {
            "iteration": int(iteration if iteration is not None else self.iteration or 0),
            "surface": str(document.get("surface") or "")[:40],
            "open_conversation": str(document.get("open_conversation") or "")[:80],
            "focused_field_role": str(
                document.get("focused_field_role")
                or getattr(self, "focused_field_role", "")
                or ""
            )[:40],
            "objects": objects_out,
        }
        path = str(screenshot_path or "").strip()
        if path:
            snap["screenshot_path"] = path[-200:]
        # De-dupe same iteration (re-persist / layer merge).
        if self.recent_perceptions and self.recent_perceptions[-1].get("iteration") == snap["iteration"]:
            self.recent_perceptions[-1] = snap
        else:
            self.recent_perceptions.append(snap)
        if len(self.recent_perceptions) > cap:
            del self.recent_perceptions[0 : len(self.recent_perceptions) - cap]

    def advance_search_hypothesis(self, n_hypotheses: int) -> bool:
        """Move to next search hypothesis. Returns True if advanced."""
        if n_hypotheses <= 1:
            return False
        if self.search_hypothesis_index >= n_hypotheses - 1:
            return False
        self.search_hypothesis_index += 1
        self.search_refinement_pending = True
        self.open_contact_fail_streak = 0
        self.type_query_fail_streak = 0
        self.clear_search_query_hint()
        return True

    def set_search_query_hint(self, query: str, *, ttl: int = 3) -> None:
        q = (query or "").strip()
        if not q:
            return
        self.search_query_hint = q
        self.search_query_hint_ttl = max(ttl, 1)

    def peek_search_query_hint(self) -> str:
        if self.search_query_hint_ttl <= 0:
            return ""
        return self.search_query_hint

    def tick_search_query_hint(self) -> None:
        if self.search_query_hint_ttl > 0:
            self.search_query_hint_ttl -= 1
            if self.search_query_hint_ttl <= 0:
                self.search_query_hint = ""

    def clear_search_query_hint(self) -> None:
        self.search_query_hint = ""
        self.search_query_hint_ttl = 0


    def action_key(self, step: PlanStep) -> str:
        return f"{step.action.lower()}|{step.semantic_target}|{step.text}"

    def record(self, step: PlanStep, execution: Dict[str, Any]) -> None:
        self.iteration += 1
        self.step = self.iteration
        self.last_plan_step = step
        self.last_action = step.action.lower()
        self.last_result = execution
        self._commit_action_attempt(step, execution)

    def _commit_action_attempt(self, step: PlanStep, execution: Dict[str, Any]) -> None:
        """Land the executed action in the workspace — the one authoritative record.

        Only the runtime knows what was truly executed and what came back, so the
        attempt (and the step it consumed from the budget) is written straight
        into the workspace here rather than reconstructed elsewhere. The unified
        world document, when present, is kept in sync so the next model call sees
        the real outcome.
        """
        exec_map = execution if isinstance(execution, dict) else {}
        ok = bool(exec_map.get("ok"))
        message = str(exec_map.get("message") or "").strip()
        outcome = f"{'ok' if ok else 'failed'}:{message}" if message else ("ok" if ok else "failed")
        family = str(getattr(step, "action_family", "") or "").strip() or str(step.action or "").strip().lower()
        target = str(getattr(step, "semantic_target", "") or "").strip()
        self.workspace.commit(
            WorkspaceProposal(
                source="runtime",
                frame=int(self.iteration or 0),
                attempts=[
                    AttemptRecord(
                        frame=int(self.iteration or 0),
                        kind="action",
                        action=family,
                        target=target,
                        outcome=outcome,
                    )
                ],
                budgets={"steps_used": int(self.workspace.budgets.steps_used) + 1},
            )
        )
        document = getattr(self, "unified_world_document", None)
        if isinstance(document, dict):
            from plugin.agent.world_document import record_attempt

            self.unified_world_document = record_attempt(
                document,
                frame=int(self.iteration or 0),
                action=family,
                target=target,
                result=outcome,
            )

    def record_search_attempt(self, query: str, outcome: str) -> None:
        """Record a search the agent ran, as a workspace attempt.

        ``search_attempt_log`` is a *view* of these — there is deliberately no
        second store to drift from. Search refinement reads the log; the truth
        lives in the workspace.
        """
        q = str(query or "").strip()
        if not q:
            return
        self.workspace.commit(
            WorkspaceProposal(
                source="runtime",
                frame=int(self.iteration or 0),
                attempts=[
                    AttemptRecord(
                        frame=int(self.iteration or 0),
                        kind="search",
                        action="search",
                        text=q,
                        outcome=str(outcome or "").strip(),
                    )
                ],
            )
        )

    @property
    def search_attempt_log(self) -> List[Dict[str, Any]]:
        """The search attempts, in the legacy ``{"q","outcome"}`` shape.

        A pure view of the workspace attempts so the two can never disagree.
        """
        return self.workspace.search_attempts()

    def record_verification(self, verification: Dict[str, Any]) -> None:
        self.last_verification = verification

    def apply_belief_update(self, update: BeliefUpdate) -> Belief:
        belief = self.belief_store.apply_update(update)
        self.belief_updates.append(update)
        self.last_belief_update = update
        return belief

    def record_belief_updates(self, updates: List[BeliefUpdate]) -> None:
        for update in updates or []:
            self.apply_belief_update(update)

    def set_active_uncertainty(self, uncertainty: Optional[Uncertainty]) -> None:
        self.active_uncertainty = uncertainty
        self.belief_store.active_uncertainty_id = ""
        if uncertainty is not None:
            key = uncertainty.question.strip().lower()
            self.belief_store.uncertainties[key] = uncertainty
            self.belief_store.active_uncertainty_id = key

    def set_active_hypotheses(self, hypotheses: List[Hypothesis]) -> None:
        self.active_hypotheses = list(hypotheses or [])
        self.belief_store.active_hypothesis_ids = []
        for hyp in self.active_hypotheses:
            key = hyp.explanation.strip().lower()
            self.belief_store.hypotheses[key] = hyp
            self.belief_store.active_hypothesis_ids.append(key)

    def set_active_experiment(self, experiment: Optional[Experiment]) -> None:
        self.active_experiment = experiment
        self.belief_store.active_experiment_id = ""
        if experiment is not None:
            key = experiment.capability.strip().lower()
            self.belief_store.experiments[key] = experiment
            self.belief_store.active_experiment_id = key

    def add_goal_condition(self, goal_condition: GoalCondition) -> None:
        self.goal_conditions.append(goal_condition)
        self.belief_store.goal_conditions[goal_condition.proposition] = goal_condition

    def record_failure(self, reason: str) -> None:
        self.failures.append(reason)

    def note_attempt(
        self,
        *,
        family: str,
        target: str,
        surface: str = "",
        effect: str = "",
        iteration: int = 0,
    ) -> Dict[str, Any]:
        """Record that this move was tried here, and what came of it.

        A cumulative ledger, unlike ``repeated_action_count``, which resets the
        moment anything else is executed. That counter therefore says nothing
        about a loop that alternates -- and alternating is the normal shape of a
        stuck agent, because each failure prompts a different next move which
        then leads back. Observed live: right_click(message) → resolve_entity(
        same message) → right_click(message), for thirteen minutes, with the
        consecutive counter sitting at 1 the whole time and the model told
        nothing, so every attempt arrived looking like its first.
        """
        fam = " ".join(str(family or "").strip().lower().split())
        tgt = " ".join(str(target or "").strip().lower().split())[:60]
        if not fam:
            return {}
        key = f"{fam}|{tgt}|{' '.join(str(surface or '').strip().lower().split())}"
        entry = self.action_attempts.get(key)
        if entry is None:
            entry = {
                "family": fam,
                "target": tgt,
                "surface": str(surface or "").strip().lower(),
                "attempts": 0,
                "effects": [],
            }
            self.action_attempts[key] = entry
        entry["attempts"] = int(entry.get("attempts", 0)) + 1
        entry["last_iteration"] = int(iteration or 0)
        eff = str(effect or "").strip().lower()
        if eff:
            effects = entry.setdefault("effects", [])
            if isinstance(effects, list):
                effects.append(eff)
                del effects[:-4]
        # Bounded: a long run must not turn its own history into context bloat.
        if len(self.action_attempts) > MAX_TRACKED_ATTEMPTS:
            for stale in sorted(
                self.action_attempts,
                key=lambda k: int(self.action_attempts[k].get("last_iteration", 0)),
            )[: len(self.action_attempts) - MAX_TRACKED_ATTEMPTS]:
                self.action_attempts.pop(stale, None)
        return dict(entry)

    def repeated_attempts(self, *, minimum: int = 2, limit: int = 8) -> List[Dict[str, Any]]:
        """Moves tried here at least ``minimum`` times, most-tried first.

        The shape every caller that has to warn a model about a loop wants: what
        was tried, how often, and what it did. Bounded because a stuck run can
        accumulate more of these than are worth spending prompt on.
        """
        tried = [
            {
                "family": str(entry.get("family") or ""),
                "target": str(entry.get("target") or ""),
                "attempts": int(entry.get("attempts") or 0),
                "effects": [str(effect) for effect in (entry.get("effects") or [])][-3:],
            }
            for entry in self.action_attempts.values()
            if isinstance(entry, dict) and int(entry.get("attempts") or 0) >= int(minimum)
        ]
        tried.sort(key=lambda item: item["attempts"], reverse=True)
        return tried[: max(0, int(limit))]

    def attempts_for(self, *, family: str, target: str, surface: str = "") -> int:
        """How many times this exact move has been tried here, ever."""
        fam = " ".join(str(family or "").strip().lower().split())
        tgt = " ".join(str(target or "").strip().lower().split())[:60]
        key = f"{fam}|{tgt}|{' '.join(str(surface or '').strip().lower().split())}"
        entry = self.action_attempts.get(key) or {}
        return int(entry.get("attempts", 0) or 0)

    def note_world_signature(self, signature: str, step: Optional[PlanStep]) -> None:
        if self.last_world_signature is not None and signature == self.last_world_signature:
            self.unchanged_world_count += 1
        else:
            self.unchanged_world_count = 0
        if step is not None:
            key = self.action_key(step)
            pair = (key, signature)
            if self.recent_action_state_pairs and self.recent_action_state_pairs[-1] == pair:
                self.repeated_action_count += 1
            else:
                self.repeated_action_count = 1
            self.recent_action_state_pairs.append(pair)
            # Same action + same world twice → prohibit briefly
            if self.repeated_action_count >= 2:
                self.prohibited_actions[key] = max(self.prohibited_actions.get(key, 0), 2)
        self.last_world_signature = signature

    def note_semantic_state(self, signature: str, step: Optional[PlanStep] = None) -> bool:
        """Track semantically repeated states so the controller can replan sooner."""
        sig = " ".join((signature or "").strip().split())
        if not sig:
            return False
        if sig == self.last_semantic_state_signature:
            self.semantic_repeat_count += 1
        else:
            self.last_semantic_state_signature = sig
            self.semantic_repeat_count = 1

        if step is not None:
            key = self.action_key(step)
            pair = (key, sig)
            if self.recent_action_state_pairs and self.recent_action_state_pairs[-1] == pair:
                self.repeated_action_count += 1
            elif key:
                self.repeated_action_count = max(1, self.repeated_action_count)
        return self.semantic_repeat_count >= 3

    def is_prohibited(self, step: PlanStep) -> bool:
        key = self.action_key(step)
        left = self.prohibited_actions.get(key, 0)
        return left > 0

    def note_perception_stall(self, signature: str, *, reason: str = "") -> bool:
        """Track repeated unresolved perception states and surface a cycle-stall flag."""
        sig = " ".join((signature or "").strip().split())
        if not sig:
            return self.perception_cycle_stalled
        if sig == self.last_perception_stall_signature:
            self.perception_stall_count += 1
        else:
            self.last_perception_stall_signature = sig
            self.perception_stall_count = 1
        self.perception_stall_reason = reason or self.perception_stall_reason
        self.perception_cycle_stalled = self.perception_stall_count >= 2
        return self.perception_cycle_stalled

    def clear_perception_stall(self) -> None:
        self.perception_cycle_stalled = False
        self.last_perception_stall_signature = ""
        self.perception_stall_count = 0
        self.perception_stall_reason = ""

    def clear_semantic_repeat(self) -> None:
        self.last_semantic_state_signature = None
        self.semantic_repeat_count = 0

    def tick_prohibitions(self) -> None:
        dead = []
        for k, v in self.prohibited_actions.items():
            if v <= 1:
                dead.append(k)
            else:
                self.prohibited_actions[k] = v - 1
        for k in dead:
            self.prohibited_actions.pop(k, None)

    def oscillating(self) -> bool:
        pairs = list(self.recent_action_state_pairs)
        if len(pairs) < 4:
            return False
        a, b, c, d = pairs[-4:]
        return a == c and b == d and a != b


@dataclass
class RuntimeState:
    world_model: WorldModel = field(default_factory=WorldModel)
    active_task: str = ""
    execution_state: ExecutionState = field(default_factory=ExecutionState)
    conversation: List[Dict[str, str]] = field(default_factory=list)
    patches: List[WorldPatch] = field(default_factory=list)
    perception_summary_callback: Optional[Callable[[str], None]] = None

    def note_user(self, text: str) -> None:
        self.conversation.append({"role": "user", "content": text})

    def note_assistant(self, text: str) -> None:
        self.conversation.append({"role": "assistant", "content": text})
