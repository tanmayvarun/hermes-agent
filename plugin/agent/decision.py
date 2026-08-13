"""DecisionEngine — Goal + World + PolicyPrior + Value → one Action."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from plugin.agent.action import Action
from plugin.agent.apps.registry import get_overlay
from plugin.agent.features import StateFeatures
from plugin.agent.goal import Goal, GoalStatus, evaluate_goal
from plugin.agent.policy.prior import PolicyPrior
from plugin.perception.representation import structured_perception_bridge
from plugin.agent.procedure import current_procedure_stage
from plugin.agent.transition.types import FrontierAction, TransitionSummary
from plugin.agent.transition.types import ActionPrediction
from plugin.worldmodel.entities.normalize import _clean_label
from plugin.worldmodel.model import WorldModel

if TYPE_CHECKING:
    from plugin.agent.runtime.state import ExecutionState

# Mix weights: evidence (value) dominates prior; low worldview boosts observe
ALPHA_PRIOR = 0.30
BETA_VALUE = 0.55
GAMMA_EVIDENCE = 0.25  # extra world-consistency bonus

_DEFAULT_IRREVERSIBLE_ACTION_CONFIDENCE_THRESHOLD = 0.7
_DEFAULT_PERCEPTION_PROMOTION_THRESHOLD = 0.7


@dataclass
class DecisionTrace:
    features: Dict[str, Any] = field(default_factory=dict)
    candidates: List[Dict[str, Any]] = field(default_factory=list)
    chosen: Optional[Dict[str, Any]] = None
    goal_status: Optional[Dict[str, Any]] = None
    selector: Optional[Dict[str, Any]] = None
    selector_confidence: float = 0.0
    branch_strategy: Optional[Dict[str, Any]] = None
    transition_summary: Optional[TransitionSummary] = None


@dataclass
class DecisionEngine:
    """Defines the next actor step when the brain has chosen meta ACT.

    Not the loop brain: executive judgement schedules tools; this capability
    turns accepted world + consultation into a concrete ``Action`` for the actor.
    """

    prior: PolicyPrior = field(default_factory=PolicyPrior.load)
    alpha: float = ALPHA_PRIOR
    beta: float = BETA_VALUE
    gamma: float = GAMMA_EVIDENCE
    selector_enabled: bool = False
    selector_task: str = "decision"
    high_risk_selector_task: str = "decision_high_risk"
    selector_caller: Optional[Any] = None
    last_trace: Optional[DecisionTrace] = None

    @staticmethod
    def _requires_entity_grounding(action: Action) -> bool:
        """Only actions that materially depend on a concrete content/contact target need grounding."""
        return (action.action_family or "") in {
            "select_content",
            "forward_message",
            "select_forward_target",
            "start_call",
        }

    @staticmethod
    def _grounding_matches_candidate(candidate: Action, entity: Any) -> bool:
        if entity is None or not getattr(entity, "visible", False):
            return False
        fam = str(getattr(candidate, "action_family", "") or "").strip().lower()
        target = _clean_label(getattr(candidate, "semantic_target", "") or "").lower()
        text = _clean_label(getattr(candidate, "text", "") or "").lower()
        label = _clean_label(
            " ".join(
                [
                    getattr(entity, "label", "") or "",
                    getattr(entity, "semantic_role", "") or "",
                    getattr(entity, "role", "") or "",
                    str((getattr(entity, "attributes", {}) or {}).get("description") or ""),
                ]
            )
        ).lower()
        if fam in {"type_query", "open_search"}:
            if any(tok in label for tok in ("settings", "call", "video", "voice", "menu", "more")):
                return False
            return "search" in label or "query" in label or "find" in label or "start new chat" in label
        if fam == "open_contact":
            if any(tok in label for tok in ("search", "settings", "call", "video", "voice", "more options")):
                return False
            return bool(label) and not any(tok in label for tok in ("search", "settings", "more options"))
        if fam in {"forward_message", "select_forward_target"}:
            return "forward" in label or "message" in label or bool(target) or bool(text)
        if fam == "select_content":
            return any(tok in label for tok in ("message", "timeline", "chat", "row", "card", "link"))
        if fam in {"probe_hover", "probe_context_menu", "probe_focus"}:
            return any(tok in label for tok in ("message", "row", "card", "conversation", "timeline", "chat"))
        return True

    @staticmethod
    def _candidate_requires_high_risk_reasoning(candidate: Action) -> bool:
        """High-risk actions are any non-observe actuators that leave a footprint."""
        if candidate.action_family == "observe":
            return False
        if getattr(candidate, "reversible", True) is False:
            return True
        cap_type = str(getattr(candidate, "capability_type", "") or "").strip()
        return cap_type in {
            "InitiateVoiceCall",
            "InitiateVideoCall",
            "ForwardMessage",
            "SendMessage",
        }

    @classmethod
    def _needs_high_risk_reasoning(cls, candidates: List[Action]) -> bool:
        return any(cls._candidate_requires_high_risk_reasoning(cand) for cand in candidates)

    @classmethod
    def _goal_requires_high_risk_reasoning(cls, goal: Goal, candidates: List[Action]) -> bool:
        """Treat forward-message search steps as high-risk trajectory gates.

        The act of searching for the source conversation is still reversible,
        but it is part of a forwarding trajectory whose later steps are not.
        When the frontier is already in that lane, keep the selector in the
        high-risk path so it reasons over the irreversible contract and does
        not optimize the search step in isolation.
        """
        if goal.kind != "whatsapp_forward_message":
            return False
        return any(
            cand.action_family in {
                "type_query",
                "open_contact",
                "open_search",
                "select_content",
                "select_forward_target",
                "forward_message",
            }
            for cand in candidates
        )

    @staticmethod
    def _should_validate_single_candidate_with_llm(candidate: Action, goal: Goal) -> bool:
        """Let the selector validate lone but goal-shaping actuators."""
        fam = (candidate.action_family or "").strip()
        if fam in {
            "select_content",
            "select_forward_target",
            "forward_message",
            "start_call",
        }:
            return True
        if fam == "type_query" and goal.kind == "whatsapp_forward_message":
            return True
        return False

    @staticmethod
    def _perception_promotion_threshold() -> float:
        try:
            from hermes_cli.config import load_config_readonly

            cfg = load_config_readonly() or {}
            agent_cfg = cfg.get("agent") if isinstance(cfg.get("agent"), dict) else {}
            raw = agent_cfg.get(
                "perception_summary_promotion_threshold",
                _DEFAULT_PERCEPTION_PROMOTION_THRESHOLD,
            )
            return max(0.0, min(1.0, float(raw)))
        except Exception:
            return _DEFAULT_PERCEPTION_PROMOTION_THRESHOLD

    @classmethod
    def _perception_promotion_threshold_for_family(cls, family: str) -> float:
        base = cls._perception_promotion_threshold()
        fam = str(family or "").strip().lower()
        if fam == "open_contact":
            return min(base, 0.55)
        if fam in {"type_query", "open_search", "explore_chrome"}:
            return min(base, 0.5)
        if fam == "dismiss":
            return min(base, 0.55)
        if fam in {"start_call", "end_call", "forward_message"}:
            return max(base, 0.7)
        return base

    # Canonical action families the controller can actually execute.
    _CANONICAL_ACTION_FAMILIES = frozenset(
        {
            "observe",
            "open_search",
            "type_query",
            "compose_search_query",
            "resolve_entity",
            "open_contact",
            "select_content",
            "forward_message",
            "select_forward_target",
            "dismiss",
            "start_call",
            "end_call",
            "explore_chrome",
            "scroll_content",
            "locate_content",
            "open_entity",
            "select_content",
            "reveal_actions",
            "invoke_affordance",
            "dismiss_transient",
            "commit_irreversible",
            "probe_hover",
            "probe_context_menu",
            "probe_focus",
        }
    )

    # Intent keywords, not per-model string aliases: a screen-understanding
    # model may name the same intent many ways, so classify by what the words
    # mean rather than maintaining an exhaustive alias table.
    _FAMILY_INTENT_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("observe", ("window", "focus_app", "activate", "wait", "screenshot", "inspect")),
        (
            "compose_search_query",
            ("compose_search", "author_query", "craft_query", "search_query", "query_author"),
        ),
        (
            "resolve_entity",
            (
                "resolve_entity",
                "resolve_candidate",
                "select_candidate",
                "disambiguate",
                "pick_recipient",
                "choose_destination",
            ),
        ),
        ("type_query", ("type", "enter_text", "input", "query")),
        # Before open_search: "find the message about X" is locating content on
        # the surface you are on, not opening the app's search chrome.
        ("locate_content", ("locate", "find_in", "find_message", "seek", "look_for", "hunt")),
        ("open_search", ("search", "find", "filter")),
        ("open_entity", ("open_entity", "open_conversation", "open_thread", "open_channel")),
        ("open_contact", ("chat", "conversation", "contact", "thread", "recipient")),
        (
            "select_content",
            (
                "select_content",
                "select_message",
                "focus_message",
                "message",
                "link",
                "bubble",
                "content",
                "row",
            ),
        ),
        ("reveal_actions", ("reveal_actions", "context_menu", "right_click", "show_actions")),
        # "forward"/"share" as free-form labels map to invoking the affordance,
        # not to a bundled forward plan. Exact family forward_message still
        # matches the canonical set before keywords run.
        ("invoke_affordance", ("invoke_affordance", "forward", "share", "reply")),
        ("commit_irreversible", ("commit_irreversible", "send_message", "confirm_send")),
        ("dismiss_transient", ("dismiss_transient", "dismiss_overlay", "clear_menu")),
        ("dismiss", ("dismiss", "close", "cancel", "escape")),
        ("scroll_content", ("scroll", "backtrack", "history")),
    )

    @classmethod
    def _classify_perception_family(cls, family: str) -> str:
        """Resolve a free-form perceptor family label to a canonical family."""
        fam = str(family or "").strip().lower().replace("-", "_").replace(" ", "_")
        if not fam:
            return ""
        if fam in cls._CANONICAL_ACTION_FAMILIES:
            return fam
        for canonical, keywords in cls._FAMILY_INTENT_KEYWORDS:
            if any(keyword in fam for keyword in keywords):
                return canonical
        return fam

    @staticmethod
    def _ax_content_starved(features: StateFeatures) -> bool:
        """True when the AX tree exposes only app/window chrome, no content.

        On such frames there is nothing to ground a label or coordinate click
        against, so keyboard-driven navigation is the only reliable actuator.
        """
        extras = features.extras if isinstance(getattr(features, "extras", None), dict) else {}
        raw = extras.get("app_content_node_count")
        if raw is None:
            # Feature builders publish this under the worldview score instead
            # of promoting it into extras.
            score = getattr(features, "worldview_score", None)
            if not isinstance(score, dict):
                score = extras.get("worldview_score")
            components = score.get("components") if isinstance(score, dict) else None
            if isinstance(components, dict):
                raw = components.get("app_content_node_count")
        if raw is None:
            return False
        try:
            return int(raw) <= 0
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _search_holds_query(features: Optional[StateFeatures], query: str) -> bool:
        """True when search already contains ``query`` (AX or typed evidence).

        An authored-but-not-yet-typed compose result must not count — that
        previously unlocked point-click open_entity while the field was empty.
        """
        q = (query or "").strip().lower()
        if not q or features is None:
            return False
        if getattr(features, "query_matches_goal", False):
            return True
        extras = features.extras if isinstance(getattr(features, "extras", None), dict) else {}
        if extras.get("composed_query_pending"):
            return False
        for key in ("search_query", "search_query_hint", "last_typed_query"):
            val = str(extras.get(key) or "").strip().lower()
            if val and (q in val or val in q):
                return True
        return False

    @classmethod
    def _normalize_perception_family(
        cls,
        family: str,
        summary: Dict[str, Any],
        goal: Goal,
        features: Optional[StateFeatures] = None,
    ) -> str:
        """Map multimodal family aliases onto the shared action-family vocabulary.

        Screen-understanding models emit their own labels (``search``,
        ``chat_selection``, ...) rather than the controller's canonical action
        families. Normalizing here keeps one shared routing contract for every
        surface instead of teaching each caller a model's vocabulary.
        """
        fam = cls._classify_perception_family(family)
        text = str(summary.get("likely_next_text") or "").strip()
        target = str(summary.get("likely_next_target") or "").strip()
        query = text or target or (goal.contact or "")
        starved = features is not None and cls._ax_content_starved(features)

        # One multimodal experiment: raise search and type the query.
        # ax_type opens search via Cmd+F before typing, so a bare
        # "open the search bar" recommendation collapses into one step.
        if fam == "open_search" and query:
            return "type_query"

        # Content-starved AX frames cannot ground a contact row click. Reach
        # the same conversation through search, which is keyboard-driven and
        # does not depend on an AX node the app never published.
        if (
            starved
            and query
            and not cls._search_holds_query(features, query)
            and fam in {
                "open_contact",
                "open_entity",
                "select_content",
                "probe_hover",
                "probe_focus",
                "scroll_content",
            }
        ):
            # Author a query first when the only cue is a bare entity name;
            # type_query comes after compose (or when the model already authored).
            from plugin.agent.capabilities.compose_search_query import is_bare_entity_query

            if is_bare_entity_query(query, goal):
                return "compose_search_query"
            return "type_query"

        # Unrecognized family with a concrete target: keep the loop moving via
        # the grounded path instead of falling back to another Observe.
        if fam and fam not in cls._CANONICAL_ACTION_FAMILIES and query:
            if starved:
                from plugin.agent.capabilities.compose_search_query import is_bare_entity_query

                return "compose_search_query" if is_bare_entity_query(query, goal) else "type_query"
            return "open_contact"
        return fam

    @classmethod
    def _family_to_action(
        cls,
        family: str,
        goal: Goal,
        summary: Dict[str, Any],
        features: Optional[StateFeatures] = None,
    ) -> tuple[str, str, str]:
        fam = cls._normalize_perception_family(family, summary, goal, features)
        target = str(summary.get("likely_next_target") or "").strip()
        text = str(summary.get("likely_next_text") or "").strip()
        if fam in {"open_contact", "start_call", "dismiss", "end_call", "explore_chrome", "open_search"}:
            action = "Click"
        elif fam == "compose_search_query":
            action = "ComposeSearchQuery"
            # Argument is optional notes; authorship uses the goal evidence bag.
            text = text or ""
            target = target or ""
        elif fam == "type_query":
            action = "Type"
            if not text:
                text = target if target and "search" not in target.lower() else (goal.contact or "")
            if not text:
                text = goal.contact or ""
        else:
            action = "Observe"
        if fam == "open_search":
            # ax_click only uses the Cmd+F search shortcut for exact "Search".
            target = "Search"
        elif fam == "dismiss" and not target:
            target = "Dismiss"
        elif fam == "end_call" and not target:
            target = "End Call"
        elif fam == "explore_chrome" and not target:
            target = str(summary.get("active_surface") or "chrome")
        elif fam == "start_call" and not target:
            target = goal.contact or "Call"
        elif fam == "open_contact" and not target:
            target = goal.contact or ""
        elif fam == "type_query":
            target = "Search"
        return action, target, text

    @staticmethod
    def _prediction_for_candidate(
        candidate: Action,
        *,
        goal: Goal,
        features: StateFeatures,
        branch: Any = None,
        confidence: float = 0.0,
    ) -> ActionPrediction:
        branch_surface = ""
        if branch is not None and getattr(branch, "active", False):
            branch_surface = str(getattr(branch, "active_surface", "") or "").strip()
        if not branch_surface:
            branch_surface = str(features.extras.get("active_surface") or features.screen_bucket or "")
        branch_hypothesis = ""
        if branch is not None and getattr(branch, "active", False):
            branch_hypothesis = str(getattr(branch, "frontier_hypothesis", "") or "")
        predicted = getattr(candidate, "prediction", None)
        if isinstance(predicted, dict):
            predicted_dict = predicted
        elif hasattr(predicted, "to_dict") and callable(predicted.to_dict):
            try:
                predicted_dict = predicted.to_dict()
            except Exception:
                predicted_dict = {}
        else:
            predicted_dict = {}
        expected_affordances = list(predicted_dict.get("expected_affordances") or [])
        if not expected_affordances:
            expected_affordances = list(features.extras.get("branch_affordances") or [])
        if not expected_affordances:
            if candidate.action_family == "type_query":
                expected_affordances = ["search_query_updates", "results_refresh"]
            elif candidate.action_family == "open_contact":
                expected_affordances = ["conversation_open", "source_content_visible"]
            elif candidate.action_family == "start_call":
                expected_affordances = ["call_picker_or_call_state"]
            elif candidate.action_family == "observe":
                expected_affordances = ["fresh_observation"]
        expected_non_changes = list(predicted_dict.get("expected_non_changes") or [])
        if candidate.action_family == "observe":
            expected_non_changes = ["no_actuation"]
        elif candidate.action_family in {"open_contact", "type_query", "start_call"}:
            expected_non_changes = ["goal_reference_should_remain"]
        predicted_outcome = str(candidate.expected_predicate or "").strip()
        if not predicted_outcome:
            if candidate.action_family == "observe":
                predicted_outcome = "observation_refresh"
            elif candidate.action_family == "type_query":
                predicted_outcome = f"SearchQueryEquals({candidate.text or goal.contact or candidate.semantic_target})"
            elif candidate.action_family == "open_contact":
                predicted_outcome = f"ConversationOpen({candidate.semantic_target or goal.contact or ''})"
            elif candidate.action_family == "start_call":
                predicted_outcome = "CallSurfaceOrRingingVisible"
        return ActionPrediction(
            action_key=f"{candidate.action.lower()}|{candidate.semantic_target}|{candidate.text}",
            action_family=candidate.action_family,
            semantic_target=candidate.semantic_target,
            strategy="strategic" if candidate.action_family == "observe" and branch is not None and getattr(branch, "active", False) else "local",
            branch_hypothesis=branch_hypothesis,
            expected_surface=branch_surface,
            expected_progress=max(0.0, float(candidate.score or 0.0)),
            expected_affordances=expected_affordances,
            expected_non_changes=expected_non_changes,
            predicted_outcome=predicted_outcome,
            reversible=bool(getattr(candidate, "reversible", True)),
            confidence=round(max(0.0, min(1.0, confidence)), 4),
            rationale=str(candidate.rationale or ""),
        )

    @staticmethod
    def _selected_procedure_stage(features: StateFeatures) -> Dict[str, Any]:
        stage = features.extras.get("selected_procedure_stage") or {}
        return stage if isinstance(stage, dict) else {}

    def _procedure_stage_alignment_bonus(
        self,
        candidate: Action,
        features: StateFeatures,
        *,
        capability_type: str = "",
    ) -> float:
        stage = self._selected_procedure_stage(features)
        if not stage or bool(stage.get("complete")):
            return 0.0
        preferred = {
            str(x).strip().lower()
            for x in (stage.get("preferred_capabilities") or [])
            if str(x).strip()
        }
        stage_progress = 0.0
        try:
            stage_progress = max(0.0, min(1.0, float(stage.get("stage_progress") or 0.0)))
        except (TypeError, ValueError):
            stage_progress = 0.0
        stage_threshold = 0.0
        try:
            stage_threshold = max(0.0, min(1.0, float(stage.get("confidence_threshold") or 0.0)))
        except (TypeError, ValueError):
            stage_threshold = 0.0
        cap_type = str(capability_type or getattr(candidate, "capability_type", "") or "").strip()
        if not cap_type:
            try:
                from plugin.worldmodel.capability import action_family_to_capability_type

                cap_type = action_family_to_capability_type(
                    candidate.action_family,
                    semantic_target=candidate.semantic_target,
                    text=candidate.text,
                )
            except Exception:
                cap_type = ""
        cap_key = cap_type.strip().lower()
        bonus = 0.0
        if preferred:
            if cap_key in preferred:
                bonus += 0.34
            elif candidate.action_family != "observe":
                bonus -= 0.22
        if not bool(stage.get("reversible", True)) and candidate.action_family != "observe":
            # The stage itself is the confidence gate for irreversible actuators.
            if stage_progress < stage_threshold:
                bonus -= 0.28
            else:
                bonus += 0.06
        return bonus

    @staticmethod
    def _sync_branch_frontier(
        *,
        branch: Any,
        execution_state: "ExecutionState",
        state_sig: str,
        features: StateFeatures,
        goal: Goal,
        candidates: List[Action],
        exp: Any = None,
        branch_surface: str = "",
        branch_preferred_family: str = "",
    ) -> None:
        if branch is None or not getattr(branch, "active", False):
            return
        frontier_snapshot: List[FrontierAction] = []
        for cand in candidates:
            fam = cand.action_family
            tried = bool(exp.is_suppressed(state_sig, cand)) if exp is not None else False
            total = float(getattr(cand, "score", 0.0) or 0.0)
            frontier_score = total
            branch_affs = {str(a).strip().lower() for a in (features.extras.get("branch_affordances") or [])}
            if not tried:
                frontier_score += 0.15 * 0.9
            else:
                frontier_score -= 0.1
            if branch_surface == "call_picker":
                frontier_score += 0.2 if fam == "start_call" else 0.05
            if branch_surface == "search_results":
                frontier_score += 0.15 if fam == "open_contact" else 0.02
            if fam == "forward_message" and any(
                a in branch_affs for a in {"forwardmessage", "forward_message", "reveal_message_actions"}
            ):
                frontier_score += 0.28
            if fam == "select_content" and any(a in branch_affs for a in {"reveal_message_actions", "selectcontent"}):
                frontier_score += 0.18
            if fam in {"probe_hover", "probe_context_menu", "probe_focus"} and any(
                a in branch_affs for a in {"revealhiddenactions", "probesurface", "reveal_message_actions"}
            ):
                frontier_score += 0.14
            if branch_preferred_family:
                if fam == branch_preferred_family:
                    frontier_score += 0.25
                elif fam == "observe" and branch_preferred_family != "observe":
                    frontier_score -= 0.2
            novelty = 0.9 if not tried else 0.2
            semantic_relevance = max(0.0, float(getattr(cand, "value_delta", 0.0) or 0.0)) + max(
                0.0, float(getattr(cand, "evidence_score", 0.0) or 0.0)
            )
            actionability = max(0.0, total)
            information_gain = 0.0
            if fam in {"start_call", "explore_chrome"}:
                information_gain += 0.6
            if fam == "open_contact" and branch_surface == "search_results":
                information_gain += 0.45
            if fam == "observe":
                information_gain += 0.2 if not tried else 0.05
            if branch_surface == "call_picker":
                information_gain += 0.2
            if branch_surface == "search_results":
                information_gain += 0.15 if fam == "open_contact" else 0.02
            risk = max(0.0, -float(getattr(cand, "value_delta", 0.0) or 0.0))
            frontier_snapshot.append(
                FrontierAction(
                    state_signature=state_sig,
                    action_key=execution_state.action_key(cand),
                    action_family=fam,
                    semantic_target=cand.semantic_target,
                    text=cand.text,
                    hypothesis_label=cand.frontier_label,
                    tried=tried,
                    novelty=round(novelty, 4),
                    semantic_relevance=round(semantic_relevance, 4),
                    actionability=round(actionability, 4),
                    information_gain=round(information_gain, 4),
                    risk=round(risk, 4),
                    score=round(
                        frontier_score
                        + 0.15 * novelty
                        + 0.35 * information_gain
                        - 0.4 * risk,
                        4,
                    ),
                )
            )
        frontier_snapshot.sort(key=lambda a: a.score, reverse=True)
        branch.set_frontier(frontier_snapshot[:12], state_signature=state_sig)

    def _unified_fast_path(
        self,
        goal: Goal,
        world: WorldModel,
        features: StateFeatures,
        execution_state: Any,
        candidates: List[Action],
    ) -> Optional[Action]:
        """Perceive → critic → brain, then execute the brain's capability.

        The multimodal perceptor updates the world and publishes the affordance
        frontier; the critic accepts/rejects the world delta; ``brain`` chooses
        the capability. An inadmissible choice falls through to
        enumerate-score-select (without perception ``likely_next_*`` nudges).
        """
        from plugin.agent.brain import choose_next_capability, publish_brain_choice
        from plugin.agent.unified_cognition import (
            consult_unified_cognition,
            proposal_to_action,
            should_escalate,
            unified_cognition_enabled,
        )

        if not unified_cognition_enabled():
            return None
        # The executive asked to deliberate (meta-action THINK, cognitive mode
        # deliberative, or a PROBE that wants a fresh reveal). That is a request
        # about *how* to decide, not whether to look — and under the one-executive
        # contract the brain *is* that deliberative chooser. Perceive first
        # (refresh world / critic / geometry), then let the brain choose. Older
        # code withheld the action so enumerate/score could run; that rival
        # chooser is gone — deliberation is brain/unified only.
        deliberate = bool(getattr(execution_state, "force_deliberation", False))
        if deliberate:
            execution_state.force_deliberation = False
            features.extras["forced_deliberation"] = True
        try:
            proposal = consult_unified_cognition(goal, world, features, execution_state)
        except Exception as exc:  # never let cognition failure kill the loop
            features.extras["unified_cognition"] = {"error": str(exc)[:200]}
            return None

        action: Optional[Action] = None
        reason = "no_proposal"
        action_rank = -1
        rejected_siblings: List[str] = []
        brain_trace: Dict[str, Any] = {}
        if proposal is not None:
            # Brain chooses after critic; perception must not fill next_action.
            brain_trace = choose_next_capability(
                proposal, goal, features=features, execution_state=execution_state
            )
            publish_brain_choice(features, proposal, brain_trace)
            cand_action, cand_reason = proposal_to_action(
                proposal,
                goal,
                world,
                features,
                execution_state=execution_state,
            )
            if cand_action is not None:
                action, reason, action_rank = cand_action, cand_reason, 0
            else:
                reason = cand_reason
                fam = str((proposal.next_action or {}).get("family") or "unknown")
                rejected_siblings.append(f"{fam}:{cand_reason}")
            self._apply_belief_updates(proposal, features)
            # Persist the perceptor's own honest account of what it could not
            # establish (evidence_gaps) and how much of the surface it saw
            # (coverage), stamped with this frame. The executive reads these when
            # judging sufficiency instead of assuming a full, gap-free view — the
            # perceptor names the gap, the executive decides what to do about it.
            if execution_state is not None:
                execution_state.last_unified_proposal = {
                    "frame": int(
                        getattr(execution_state, "decision_frame", None)
                        if getattr(execution_state, "decision_frame", None) is not None
                        else getattr(execution_state, "iteration", 0)
                        or 0
                    ),
                    "evidence_gaps": [str(g) for g in (proposal.evidence_gaps or []) if str(g).strip()],
                    "coverage": proposal.coverage,
                    "confidence": float(proposal.confidence or 0.0),
                    "surface": str((proposal.observed_state or {}).get("surface") or "").strip(),
                    # A reversible reveal move the perceptor thinks is worth taking
                    # to expose latent affordances. Lets the executive choose PROBE
                    # when a look would not help but an action could reveal.
                    "probe_available": bool(getattr(proposal, "recommended_probe", None)),
                    # The model's belief patch is the perceptor's read of the
                    # scene. It must reach the one authoritative workspace, not
                    # only features.extras — that is what lets the workspace
                    # arbitrate contradictions and count belief flips.
                    "beliefs": [
                        {
                            "predicate": str(u.get("predicate") or "").strip(),
                            "value": u.get("value"),
                            "confidence": u.get("confidence"),
                            "evidence": u.get("evidence"),
                        }
                        for u in (proposal.belief_updates or [])
                        if isinstance(u, dict) and str(u.get("predicate") or "").strip()
                    ][:16],
                }

        escalate, escalate_reason = should_escalate(
            proposal, features, admissible=action is not None
        )
        features.extras["unified_cognition"] = {
            **(proposal.to_dict() if proposal is not None else {}),
            "admissibility": reason,
            "escalated": escalate,
            "escalation_reason": escalate_reason,
            "action_rank": action_rank,
            "rejected_siblings": rejected_siblings,
            # Deliberation is satisfied by running the brain above — not by
            # withholding. Kept for traces that still key this field.
            "withheld_for_deliberation": False,
            "deliberation_requested": deliberate,
        }
        # Escalation is a diagnostic / deep-path hint. It must not discard an
        # admissible brain choice — live: compose_search_query was dropped for
        # missing_evidence_at_confidence and the loop fell through to Observe.
        if action is None:
            return None

        # A prohibition is the runtime's cycle detector, which cannot tell
        # searching from looping: scrolling a conversation to hunt for a message
        # repeats the same action by design and reveals new content each time.
        # For a reversible action that judgement belongs to the model, which can
        # see whether the screen moved, so the repetition is reported to it via
        # the packet instead of vetoing the move. Irreversible actions still stop
        # here, where a wrong repeat cannot be undone.
        if execution_state is not None and execution_state.is_prohibited(action):
            if not action.reversible:
                features.extras["unified_cognition"]["admissibility"] = "prohibited"
                return None
            features.extras["unified_cognition"]["repeat_allowed"] = True
        if not action.reversible and proposal is not None:
            if proposal.confidence < self.irreversible_action_confidence_threshold():
                features.extras["unified_cognition"]["admissibility"] = "irreversible_below_threshold"
                return None

        self._bind_capability(action, features, world, goal)
        action.observed_in_world = str(getattr(execution_state, "world_id", "") or "")
        self.last_trace = DecisionTrace(
            features=features.to_dict(),
            candidates=[
                {
                    "action": a.action,
                    "target": a.semantic_target,
                    "family": a.action_family,
                    "score": round(a.score, 4),
                }
                for a in candidates[:12]
            ],
            goal_status={"reason": "unified_multimodal_fast_path"},
            chosen={
                "action": action.action,
                "target": action.semantic_target,
                "text": action.text,
                "family": action.action_family,
                "grounding_reason": action.grounding_reason,
                "grounding_confidence": action.grounding_confidence,
            },
        )
        return action

    @staticmethod
    def _apply_belief_updates(proposal: Any, features: StateFeatures) -> None:
        """Record the model's belief patch for the runtime's own bookkeeping."""
        updates = [
            update
            for update in (getattr(proposal, "belief_updates", None) or [])
            if isinstance(update, dict) and str(update.get("predicate") or "").strip()
        ]
        if updates:
            features.extras["unified_belief_updates"] = updates[:12]
        surface = str((getattr(proposal, "observed_state", None) or {}).get("surface") or "").strip()
        if surface:
            features.extras["unified_observed_surface"] = surface

    def _bind_capability(
        self,
        action: Action,
        features: StateFeatures,
        world: WorldModel,
        goal: Goal,
    ) -> None:
        """Attach capability metadata so reversibility gates still apply."""
        raw = features.extras.get("capability_graph")
        if not isinstance(raw, dict) or not raw:
            return
        try:
            from plugin.worldmodel.capability import CapabilityGraph

            cap_graph = CapabilityGraph.from_dict(raw)
            cap = cap_graph.capability_for_action(
                action_family=action.action_family,
                semantic_target=action.semantic_target,
                text=action.text,
            )
            if cap is not None:
                action.capability_id = cap.capability_id
                action.capability_type = cap.type
                action.reversible = bool(getattr(cap, "reversible", True))
        except Exception:
            return

    # Keyboard-driven and reversible: these need no coordinate or entity
    # grounding, so a confident screen reading is sufficient evidence to act.
    _PERCEPTION_ENDORSABLE_FAMILIES = frozenset({"open_search", "type_query"})

    @classmethod
    def _endorse_with_perception(
        cls,
        candidates: List[Action],
        family: str,
        confidence: float,
        summary: Dict[str, Any],
    ) -> int:
        """Attach perception evidence to already-enumerated candidates.

        Enumerated search actions carry no grounding, so the grounding filter
        drops them and only Observe survives. When the perceptor is confident
        about a reversible keyboard action, that reading is the grounding.
        """
        if family not in cls._PERCEPTION_ENDORSABLE_FAMILIES:
            return 0
        text = str(summary.get("likely_next_text") or "").strip()
        endorsed = 0
        for cand in candidates:
            if float(getattr(cand, "grounding_confidence", 0.0) or 0.0) >= confidence:
                continue
            cand.grounding_confidence = confidence
            cand.grounding_reason = "multimodal_perception"
            cand.evidence_score = max(float(getattr(cand, "evidence_score", 0.0) or 0.0), confidence)
            if not str(getattr(cand, "text", "") or "").strip() and text:
                cand.text = text
            endorsed += 1
        return endorsed

    def _promote_perception_candidate(
        self,
        goal: Goal,
        world: WorldModel,
        features: StateFeatures,
        candidates: List[Action],
    ) -> Optional[Action]:
        def skip(reason: str) -> None:
            if isinstance(getattr(features, "extras", None), dict):
                features.extras["perception_promotion_skipped"] = reason
            return None

        summary = structured_perception_bridge(features=features, world=world)
        if not isinstance(summary, dict):
            return skip("no_summary")
        raw_family = str(summary.get("likely_next_family") or "").strip().lower()
        family = self._normalize_perception_family(raw_family, summary, goal, features)
        if not family or family == "observe":
            return skip(f"family_not_actionable:{raw_family or 'empty'}->{family or 'empty'}")
        non_observe_scores = [
            float(getattr(cand, "score", 0.0) or 0.0)
            for cand in candidates
            if cand.action_family != "observe"
        ]
        frontier_strength = max(non_observe_scores) if non_observe_scores else 0.0
        if frontier_strength >= 0.25 and family in {"open_contact", "type_query", "start_call"}:
            return skip(f"frontier_strong:{round(frontier_strength, 3)}")
        try:
            confidence = max(0.0, min(1.0, float(summary.get("confidence", 0.0) or 0.0)))
        except (TypeError, ValueError):
            confidence = 0.0
        threshold = self._perception_promotion_threshold_for_family(family)
        if confidence < threshold:
            return skip(f"below_threshold:{round(confidence, 3)}<{round(threshold, 3)}")
        already = [cand for cand in candidates if cand.action_family == family]
        if already:
            endorsed = self._endorse_with_perception(already, family, confidence, summary)
            return skip(
                f"family_already_enumerated:{family}"
                + (f":endorsed={endorsed}" if endorsed else "")
            )
        action, target, text = self._family_to_action(family, goal, summary, features)
        if action == "Observe":
            return skip(f"action_resolved_to_observe:{family}")
        temp_candidate = Action(
            action=action,
            semantic_target=target,
            text=text,
            action_family=family,
        )
        if self._procedure_stage_alignment_bonus(temp_candidate, features) < 0.0:
            stage = self._selected_procedure_stage(features)
            if stage.get("preferred_capabilities"):
                return skip(f"procedure_stage_conflict:{family}")
        rationale_target = target or text or family
        expected = {
            "open_contact": f"ConversationOpen({rationale_target})",
            "type_query": f"SearchQueryEquals({text or rationale_target})",
            "start_call": "",
            "dismiss": "NoUnexpectedDialog",
            "end_call": "CallStateIs(idle)",
            "open_search": "SearchInputFocused",
            "explore_chrome": "",
        }.get(family, "")
        # Chrome-only AX trees still allow Cmd+F / type search; treat the
        # multimodal recommendation as grounded enough for reversible search.
        grounding_confidence = confidence if family in {"open_search", "type_query"} else 0.0
        return Action(
            action=action,
            semantic_target=target,
            text=text,
            rationale=(
                f"promoted from perception_summary family={family} "
                f"(raw={raw_family or family}) confidence={round(confidence, 3)}"
            ),
            expected_predicate=expected,
            action_family=family,
            score=0.0,
            evidence_score=confidence,
            grounding_confidence=grounding_confidence,
            grounding_reason="multimodal_perception" if grounding_confidence else "",
            frontier_label=f"perception:{family}:{rationale_target}".strip(":"),
            frontier_score=round(confidence, 4),
        )

    @staticmethod
    def _high_risk_reasoning_effort() -> str:
        try:
            from hermes_cli.config import load_config_readonly

            cfg = load_config_readonly() or {}
            agent_cfg = cfg.get("agent") if isinstance(cfg.get("agent"), dict) else {}
            raw = agent_cfg.get("high_risk_selector_reasoning_effort", "high")
            effort = str(raw or "high").strip().lower()
            return effort or "high"
        except Exception:
            return "high"

    def _high_risk_selector_call_kwargs(self) -> Dict[str, Any]:
        return {
            "reasoning_config": {
                "enabled": True,
                "effort": self._high_risk_reasoning_effort(),
            }
        }

    def _branch_strategy_call_kwargs(self) -> Dict[str, Any]:
        return {
            "reasoning_config": {
                "enabled": True,
                "effort": "high",
            }
        }

    @staticmethod
    def _branch_strategy_should_run(features: StateFeatures, branch: Any, candidates: List[Action]) -> bool:
        if branch is None or not getattr(branch, "active", False):
            return False
        non_observe = [cand for cand in candidates if cand.action_family != "observe"]
        return len(non_observe) >= 2

    @staticmethod
    def _explicit_branch_edge_choice(
        candidates: List[Action],
        *,
        branch_strategy: Any = None,
        branch_preferred_family: str = "",
        pending_backtrack_family: str = "",
    ) -> Optional[Action]:
        desired_families: List[str] = []
        if branch_strategy is not None:
            preferred = str(getattr(branch_strategy, "preferred_family", "") or "").strip().lower()
            backtrack = str(getattr(branch_strategy, "backtrack_family", "") or "").strip().lower()
            if preferred:
                desired_families.append(preferred)
            if backtrack and backtrack not in desired_families:
                desired_families.append(backtrack)
        for fam in (branch_preferred_family, pending_backtrack_family):
            fam = str(fam or "").strip().lower()
            if fam and fam not in desired_families:
                desired_families.append(fam)
        for fam in desired_families:
            fam_candidates = [cand for cand in candidates if cand.action_family == fam and cand.action_family != "observe"]
            if not fam_candidates:
                continue
            return max(
                fam_candidates,
                key=lambda cand: (
                    float(getattr(cand, "score", 0.0) or 0.0),
                    float(getattr(cand, "frontier_score", 0.0) or 0.0),
                    1.0 if not getattr(cand, "tried", False) else 0.0,
                ),
            )
        return None

    @staticmethod
    def _strict_selector_mode() -> bool:
        try:
            raw = os.getenv("HERMES_SELECTOR_STRICT", "")
            return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}
        except Exception:
            return False

    @staticmethod
    def _selector_should_reason(
        *,
        candidates: List[Action],
        features: StateFeatures,
        branch: Any,
    ) -> bool:
        """Trigger the LLM when the frontier is semantically ambiguous."""
        non_observe = [cand for cand in candidates if cand.action_family != "observe"]
        stage = features.extras.get("selected_procedure_stage") or {}
        if isinstance(stage, dict) and stage and non_observe and not bool(stage.get("complete")):
            return True
        plausible = [cand for cand in non_observe if cand.score > 0.0]
        if len(plausible) >= 2:
            top = plausible[0].score
            second = plausible[1].score
            if top - second <= 0.22:
                return True
        if branch is not None and getattr(branch, "active", False):
            return True
        if bool(features.extras.get("world_exploration_needed")) or bool(features.extras.get("perception_incomplete")):
            return True
        if bool(features.extras.get("perception_cycle_stalled")):
            return True
        return False

    def irreversible_action_confidence_threshold(self) -> float:
        try:
            from hermes_cli.config import load_config_readonly

            cfg = load_config_readonly() or {}
            agent_cfg = cfg.get("agent") if isinstance(cfg.get("agent"), dict) else {}
            raw = agent_cfg.get("irreversible_action_confidence_threshold", _DEFAULT_IRREVERSIBLE_ACTION_CONFIDENCE_THRESHOLD)
            return max(0.0, min(1.0, float(raw)))
        except Exception:
            return _DEFAULT_IRREVERSIBLE_ACTION_CONFIDENCE_THRESHOLD

    def action_grounding_confidence_threshold(self) -> float:
        try:
            from hermes_cli.config import load_config_readonly

            cfg = load_config_readonly() or {}
            agent_cfg = cfg.get("agent") if isinstance(cfg.get("agent"), dict) else {}
            raw = agent_cfg.get("action_grounding_confidence_threshold", 0.7)
            return max(0.0, min(1.0, float(raw)))
        except Exception:
            return 0.7

    @staticmethod
    def _grounded_action_candidates(candidates: List[Action], *, grounding_threshold: float) -> List[Action]:
        out: List[Action] = []
        selector_arbitrable_families = {
            "type_query",
            "open_search",
            "open_contact",
            "start_call",
            "select_content",
            "forward_message",
            "select_forward_target",
        }
        for cand in candidates:
            if cand.action_family == "observe":
                out.append(cand)
                continue
            grounding_confidence = float(getattr(cand, "grounding_confidence", 0.0) or 0.0)
            if getattr(cand, "target_entity_id", None) is not None or grounding_confidence >= grounding_threshold:
                out.append(cand)
                continue
            if cand.action_family in selector_arbitrable_families and (
                getattr(cand, "capability_id", "") or getattr(cand, "capability_type", "") or cand.semantic_target or cand.text
            ):
                out.append(cand)
        return out

    @staticmethod
    def _best_grounded_non_observe_candidate(candidates: List[Action], *, grounding_threshold: float) -> Optional[Action]:
        selector_arbitrable_families = {
            "type_query",
            "open_search",
            "open_contact",
            "start_call",
            "select_content",
            "forward_message",
            "select_forward_target",
        }
        grounded = [
            cand
            for cand in candidates
            if cand.action_family != "observe"
            and (
                getattr(cand, "target_entity_id", None) is not None
                or float(getattr(cand, "grounding_confidence", 0.0) or 0.0) >= grounding_threshold
                or (
                    cand.action_family in selector_arbitrable_families
                    and (
                        getattr(cand, "capability_id", "")
                        or getattr(cand, "capability_type", "")
                        or cand.semantic_target
                        or cand.text
                    )
                )
            )
        ]
        if not grounded:
            return None
        return max(
            grounded,
            key=lambda cand: (
                float(getattr(cand, "grounding_confidence", 0.0) or 0.0),
                float(getattr(cand, "score", 0.0) or 0.0),
                float(getattr(cand, "frontier_score", 0.0) or 0.0),
            ),
        )

    def _observe_when_unified_declines(
        self,
        features: StateFeatures,
        execution_state: "ExecutionState",
        goal: Goal,
    ) -> Action:
        """Safe default when brain/unified does not return an admissible act.

        There is no legacy candidate/value/frontier chooser behind this: meta
        and brain own the decision. Declining means look again, not Cmd+F —
        except when meta SEARCH already named an entity-resolution gap with a
        searchable scope: that must realize as type_query, not Observe.
        """
        meta_now = str(getattr(execution_state, "last_meta_action", "") or "").strip().lower()
        if meta_now == "search":
            try:
                from plugin.agent.executive.search_applicability import (
                    evaluate_entity_resolution_search,
                    type_query_for_gap,
                )

                eval_result = evaluate_entity_resolution_search(execution_state)
                query = type_query_for_gap(eval_result.gap) if eval_result.applicable else ""
                if query:
                    from plugin.agent.decision_consultation import (
                        _resolve_filter_geometry_site,
                    )

                    site = _resolve_filter_geometry_site(
                        execution_state=execution_state, features=features
                    )
                    pt = site.get("target_point")
                    point = None
                    if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                        try:
                            point = (float(pt[0]), float(pt[1]))
                        except (TypeError, ValueError):
                            point = None
                    action = Action(
                        action="Type",
                        action_family="type_query",
                        text=query,
                        semantic_target=query,
                        rationale=(
                            "entity_resolution_search: type_query after unified decline"
                        ),
                        expected_predicate="SearchResultsUpdated",
                        reversible=True,
                        frontier_label=f"type_query {query}",
                        observed_in_world=str(
                            getattr(execution_state, "world_id", "") or ""
                        ),
                        target_point=point,
                        grounding_reason="entity_resolution_search_fallback",
                        grounding_confidence=0.8 if point else 0.55,
                    )
                    self.last_trace = DecisionTrace(
                        features=features.to_dict(),
                        candidates=[],
                        goal_status={
                            "reason": "entity_resolution_search_type_query",
                            "goal_kind": goal.kind,
                        },
                        chosen={
                            "action": action.action,
                            "family": action.action_family,
                            "text": action.text,
                            "rationale": action.rationale,
                        },
                    )
                    return action
            except Exception:
                pass

        # Entity resolved, conversation not open: do not Observe-thrash. Ranking
        # established EntityRef; next motor is open_entity (resolution ≠ navigation).
        # Live 210526: resolve_entity succeeded then unified declined → Observe loop
        # while still on search_results.
        try:
            from plugin.agent.capabilities.search_episode import search_episode_of

            ep = search_episode_of(execution_state) or {}
            chosen = str(ep.get("chosen_label") or "").strip()
            ep_status = str(ep.get("status") or "").strip().lower()
            doc = getattr(execution_state, "unified_world_document", None)
            if not isinstance(doc, dict):
                doc = {}
            surface = str(doc.get("surface") or "").strip().lower()
            if not surface and isinstance(features.extras, dict):
                surface = str(
                    features.extras.get("screen_bucket")
                    or features.extras.get("wa_screen")
                    or ""
                ).strip().lower()
            on_search = surface in {
                "search",
                "search_results",
                "chat_list",
                "list",
            } or surface.endswith("search")
            open_conv = str(doc.get("open_conversation") or "").strip()
            if (
                ep_status == "complete"
                and chosen
                and on_search
                and not open_conv
                and meta_now != "search"
            ):
                action = Action(
                    action="Click",
                    action_family="open_entity",
                    text=chosen,
                    semantic_target=chosen,
                    rationale=(
                        "search_complete_open_chosen: entity resolved; "
                        "open conversation from search_results (not Observe)"
                    ),
                    expected_predicate="conversation",
                    reversible=True,
                    frontier_label=f"open_entity {chosen}",
                    observed_in_world=str(
                        getattr(execution_state, "world_id", "") or ""
                    ),
                    grounding_reason="search_complete_after_resolve",
                    grounding_confidence=0.75,
                )
                self.last_trace = DecisionTrace(
                    features=features.to_dict(),
                    candidates=[],
                    goal_status={
                        "reason": "search_complete_open_entity",
                        "goal_kind": goal.kind,
                    },
                    chosen={
                        "action": action.action,
                        "family": action.action_family,
                        "text": action.text,
                        "rationale": action.rationale,
                    },
                )
                return action
        except Exception:
            pass

        reason = "unified_declined_no_legacy_fallthrough"
        uc = features.extras.get("unified_cognition") if isinstance(features.extras, dict) else None
        if isinstance(uc, dict):
            detail = str(uc.get("admissibility") or uc.get("escalation_reason") or "").strip()
            if detail:
                reason = f"{reason}:{detail}"
        action = Action(
            action="Observe",
            action_family="observe",
            rationale=reason,
            expected_predicate="WorldObserved",
            reversible=True,
            frontier_label="re-perceive current state",
            observed_in_world=str(getattr(execution_state, "world_id", "") or ""),
        )
        self.last_trace = DecisionTrace(
            features=features.to_dict(),
            candidates=[],
            goal_status={"reason": reason, "goal_kind": goal.kind},
            chosen={
                "action": action.action,
                "family": action.action_family,
                "rationale": action.rationale,
            },
        )
        return action

    def define_action_step(
        self,
        goal: Goal,
        world: WorldModel,
        execution_state: "ExecutionState",
        *,
        worldview_score: float = 1.0,
        state_signature: str = "",
        state_experience: Any = None,
    ) -> Optional[Action]:
        """Brain capability: define the next actuation step for the actor.

        Called only after meta ACT. Assembles perceptor/world context, consults
        unified cognition + text-LLM decision consultation, and returns a fully
        specified ``Action`` (capability + args + grounding hooks) for the actor
        — or Observe / None when consultation cannot define a step.
        """
        execution_state.planner_invocations += 1
        execution_state.tick_prohibitions()

        status = evaluate_goal(goal, world)
        if status.succeeded:
            self.last_trace = DecisionTrace(
                goal_status={"succeeded": True, "reason": status.reason},
            )
            return None

        overlay = get_overlay(goal.app, world)
        features = overlay.features(world, goal, worldview_score=worldview_score)
        proc = goal.ensure_procedure()
        if proc is not None:
            features.extras["selected_procedure_id"] = proc.id
            features.extras["selected_procedure_title"] = proc.title
            features.extras["selected_procedure_score"] = round(float(goal.procedure_score or 0.0), 4)
            features.extras["selected_procedure_reasons"] = list(goal.procedure_reasons or [])
            features.extras["selected_procedure"] = proc.to_dict()
            stage = current_procedure_stage(goal, features)
            if stage is not None:
                features.extras["selected_procedure_stage"] = stage
                features.extras["selected_procedure_stage_id"] = str(stage.get("stage_id") or "")
                features.extras["selected_procedure_stage_objective"] = str(stage.get("stage_objective") or "")
                features.extras["selected_procedure_stage_required_predicates"] = list(
                    stage.get("required_predicates") or []
                )
                features.extras["selected_procedure_stage_satisfied_predicates"] = list(
                    stage.get("satisfied_predicates") or []
                )
                features.extras["selected_procedure_stage_missing_predicates"] = list(
                    stage.get("missing_predicates") or []
                )
                features.extras["selected_procedure_stage_preferred_capabilities"] = list(
                    stage.get("preferred_capabilities") or []
                )
                features.extras["selected_procedure_stage_recovery"] = list(stage.get("recovery") or [])
                features.extras["selected_procedure_stage_reversible"] = bool(stage.get("reversible", True))
                features.extras["selected_procedure_stage_confidence_threshold"] = round(
                    float(stage.get("confidence_threshold") or 0.0),
                    4,
                )
                features.extras["selected_procedure_stage_progress"] = round(
                    float(stage.get("stage_progress") or 0.0),
                    4,
                )
                features.extras["selected_procedure_progress"] = round(
                    float(stage.get("procedure_progress") or 0.0),
                    4,
                )
        # Sync scene graph (Stage 3–7) onto features for attention-aware scoring
        scene = getattr(world, "last_scene_graph", None) or {}
        scene_graph_obj = None
        action_family_to_capability_type = lambda *_args, **_kwargs: ""  # noqa: E731
        grounded_action_for_capability = lambda *_args, **_kwargs: None  # noqa: E731
        goal_capability_types = lambda _goal: []  # noqa: E731
        if scene and not scene.get("error"):
            try:
                from plugin.worldmodel.scene.affordances import enrich_world_graph
                from plugin.worldmodel.scene.types import WorldGraph

                scene_graph_obj = enrich_world_graph(
                    WorldGraph.from_dict(scene),
                    list(world.entities.values()),
                    goal=goal,
                )
                scene = scene_graph_obj.to_dict()
                world.last_scene_graph = scene
                features.extras["world_graph"] = scene
                attn = scene.get("attention") or {}
                features.extras["scene_attention_regions"] = list(attn.get("region_ids") or [])
                features.extras["scene_attention_entities"] = list(attn.get("entity_ids") or [])
            except Exception:
                if scene:
                    features.extras["world_graph"] = scene
        # Sync typed/authored search evidence onto features *before* the unified
        # fast path. Remaps (resubmit vs click result) read these extras; when
        # they arrived only after unified cognition, the agent retyped forever.
        if features.query_matches_goal and features.extras.get("search_query"):
            world.overlay_hints["search_query"] = str(features.extras["search_query"])
        hint = execution_state.peek_search_query_hint()
        if hint and not features.query_matches_goal:
            world.overlay_hints["search_query"] = hint
            features = overlay.features(world, goal, worldview_score=worldview_score)
        if hint:
            features.extras["search_query_hint"] = hint
        pending = str(getattr(execution_state, "composed_query_pending", "") or "").strip()
        if pending:
            features.extras["composed_query_pending"] = pending
        locate_q = str(getattr(execution_state, "last_locate_query", "") or "").strip()
        if locate_q:
            features.extras["last_locate_query"] = locate_q
            features.extras["last_locate_realization"] = str(
                getattr(execution_state, "last_locate_realization", "") or ""
            )
            features.extras["last_locate_found"] = bool(
                getattr(execution_state, "last_locate_found", False)
            )
            features.extras["last_locate_effect_status"] = str(
                getattr(execution_state, "last_locate_effect_status", "") or ""
            )
            features.extras["locate_effect_verify_owed"] = bool(
                getattr(execution_state, "locate_effect_verify_owed", False)
            )
        doc = getattr(execution_state, "unified_world_document", None)
        if isinstance(doc, dict) and doc:
            features.extras["world_document"] = doc
            features.extras["focused_field_role"] = str(
                getattr(execution_state, "focused_field_role", "")
                or doc.get("focused_field_role")
                or ""
            )
        attempts = list(getattr(execution_state, "search_attempt_log", None) or [])
        if attempts:
            features.extras["search_attempt_log"] = attempts
        # Surface the goal contract (what "done" means, what must hold) so the
        # reasoning model applies the success conditions and constraints — the
        # executive consults its own contract rather than leaving it inert on the
        # workspace. Especially the irreversibility constraints, which bear on
        # whether a commit is safe.
        _ws = getattr(execution_state, "workspace", None)
        _gc = getattr(_ws, "goal", None) if _ws is not None else None
        if _gc is not None and (getattr(_gc, "success_conditions", None) or getattr(_gc, "constraints", None)):
            features.extras["goal_success_conditions"] = list(_gc.success_conditions or [])
            features.extras["goal_constraints"] = list(_gc.constraints or [])
        # Persist empty-hit evidence so compose refuses to repeat the dead query.
        if features.extras.get("search_empty"):
            dead = str(
                features.extras.get("search_query")
                or features.extras.get("search_query_hint")
                or ""
            ).strip()
            if dead:
                execution_state.record_search_attempt(dead, "no_results")
                features.extras["search_attempt_log"] = list(
                    getattr(execution_state, "search_attempt_log", None) or []
                )

        # Brain/unified owns the choice. No promote-row short-circuit and no
        # enumerate_candidates + value/frontier ranking fallthrough — those
        # rival choosers overrode meta/brain (live: SearchConversation typed
        # contact-only "Pallavi" after failed open_entity / reflect→observe).
        unified_action = self._unified_fast_path(goal, world, features, execution_state, [])
        if unified_action is not None:
            return unified_action
        return self._observe_when_unified_declines(features, execution_state, goal)

    def _evidence_bonus(
        self,
        action: Action,
        features: StateFeatures,
        goal: Goal,
        execution_state: Optional["ExecutionState"] = None,
    ) -> float:
        """Hard world constraints — prior cannot override these."""
        fam = action.action_family
        target = (action.semantic_target or "").strip().lower()
        contact = (goal.contact or "").strip().lower()
        resolved = str(features.extras.get("resolved_contact") or "").strip().lower()
        target_is_goal = bool(contact) and (
            target == contact
            or contact in target
            or (resolved and (target == resolved or resolved in target))
        )
        rows = features.extras.get("search_result_rows") or []
        rows_visible = bool(rows)
        source_visible = bool(features.extras.get("source_conversation_visible"))

        if fam == "type_query" and features.query_matches_goal:
            active = str(features.extras.get("active_search_hypothesis") or "").strip().lower()
            q = str(features.extras.get("search_query") or "").strip().lower()
            cands = features.extras.get("contact_candidates") or []
            rows = features.extras.get("search_result_rows") or []
            # Never retype over unexplored / resolvable results
            if features.extras.get("result_surface_visible") or cands or rows:
                if active and q and active != q and active not in q and not cands and not rows:
                    return 0.15  # refine spelling only when surface empty
                return -0.85
            if active and q and (active == q or active in q):
                return -1.0
            # Different hypothesis than current query — allow retype only if no candidates
            if cands or features.has_named_entity:
                return -0.8
            return 0.2
        if fam == "type_query" and (
            features.extras.get("result_surface_visible")
            or (features.extras.get("contact_candidates") or [])
            or features.extras.get("perception_incomplete")
        ):
            return -0.85
        policy = str(features.extras.get("resolution_policy") or "")
        if fam == "open_contact" and policy == "auto" and features.has_named_entity:
            return 0.85 if (features.extras.get("result_surface_visible") or rows_visible) else 0.35
        if fam == "open_contact" and policy != "auto":
            if (features.extras.get("result_surface_visible") or rows_visible) and features.query_matches_goal:
                return 0.35
            return -0.9
        if fam == "open_contact" and goal.kind == "whatsapp_forward_message":
            phase = str(features.extras.get("forward_phase") or "")
            if phase in {"FIND_LINK", "OPEN_FORWARD", "DONE"}:
                return -0.85
            if phase == "OPEN_SOURCE" and target_is_goal:
                if source_visible:
                    return 1.0
                if rows_visible or features.extras.get("result_surface_visible"):
                    return 0.85
            if phase == "PICK_DEST" and target_is_goal:
                return 0.7
        if fam == "open_contact" and not target_is_goal:
            return -0.8
        if fam == "open_contact" and (features.extras.get("result_surface_visible") or rows_visible) and features.query_matches_goal:
            return 0.7
        if fam == "open_contact" and features.query_matches_goal and features.has_named_entity:
            return 0.45 if rows_visible else 0.15
        if fam == "open_contact" and source_visible and target_is_goal:
            return 0.9
        if fam == "open_contact" and not features.has_named_entity:
            return -0.5
        if fam == "start_call" and features.conversation_open:
            return 0.7
        if fam == "start_call" and (
            features.extras.get("latent_conversation_open")
            or features.extras.get("branch_active")
            or features.extras.get("active_surface") in {"call_picker", "search_results"}
        ):
            # Occluded conversation / call picker — still a valid call branch
            target = (action.semantic_target or "").strip().lower()
            branch_affs = {str(a).strip().lower() for a in (features.extras.get("branch_affordances") or [])}
            if target in {"voice", "voice call", "audio call"} or "initiate_voice" in branch_affs:
                return 1.05
            if "select_participants" in branch_affs or "initiate_video" in branch_affs:
                return 0.8
            return 0.6
        if fam == "start_call" and not features.conversation_open:
            return -0.6
        if fam == "type_query" and features.extras.get("branch_active"):
            # Do not abandon a promising overlay to re-search
            return -0.7
        if fam == "observe" and features.extras.get("branch_active"):
            obs_n = int(features.extras.get("branch_observe_count") or 0)
            branch_affs = {str(a).strip().lower() for a in (features.extras.get("branch_affordances") or [])}
            if "initiate_voice" in branch_affs or features.extras.get("active_surface") in {"call_picker", "search_results"}:
                return -0.15 if obs_n >= 1 else -0.05
            return -0.2 if obs_n >= 1 else 0.35
        if fam == "dismiss" and bool(features.extras.get("storage_pressure")):
            return -0.95
        if fam == "dismiss" and features.has_dialog:
            return 0.85
        if fam == "dismiss" and not features.has_dialog:
            return -0.7
        if fam == "end_call" and features.leftover_call:
            return 0.9
        if fam == "end_call" and not features.leftover_call:
            return -0.6
        if fam == "observe" and features.extras.get("actuation_weak"):
            return 0.55
        if fam == "observe" and features.extras.get("perception_cycle_stalled"):
            return -0.65
        if fam == "observe" and features.extras.get("perception_incomplete"):
            return 0.65
        if fam == "observe" and features.extras.get("result_surface_visible") and features.query_matches_goal:
            return -0.15
        if fam == "observe" and features.extras.get("source_conversation_visible") and goal.kind == "whatsapp_forward_message":
            return -0.25
        if fam == "observe" and features.extras.get("world_exploration_needed"):
            # One re-perceive is enough; then try alternate affordances in-world
            if int(features.extras.get("world_explore_observe_count") or 0) >= 1:
                return -0.25
            return 0.7  # incomplete world model → perceive before mutating intent
        if fam == "explore_chrome" and (
            features.extras.get("world_exploration_needed") or features.extras.get("actuation_weak")
        ):
            obs_n = int(features.extras.get("world_explore_observe_count") or 0)
            return 0.75 if obs_n >= 1 else 0.45
        if fam == "explore_chrome":
            return 0.05
        if fam == "start_call" and features.extras.get("actuation_weak"):
            # After one observe, allow alternate call targets (not the suppressed key)
            if int(features.extras.get("world_explore_observe_count") or 0) >= 1:
                return 0.15
            return -0.35
        if fam == "type_query" and features.extras.get("world_exploration_needed") and features.conversation_open:
            # Do not escape into re-search when the open chat is still believed correct
            return -0.5
        streak = int(getattr(execution_state, "type_query_fail_streak", 0) or 0)
        if fam == "type_query" and streak > 0:
            # Failed typing should demote repeated search typing until another surface-changing step occurs.
            return -0.55 - 0.15 * min(streak, 4)
        if fam == "open_search" and streak > 0:
            return 0.18 + 0.08 * min(streak, 3)
        if fam == "type_query" and features.extras.get("result_surface_visible") and features.query_matches_goal:
            return -0.7
        if fam == "observe" and policy in {"observe", "ask"}:
            # Prefer typing next hypothesis over idle observe when hyps remain
            if int(features.extras.get("hypotheses_remaining") or 0) > 0 and not features.query_matches_goal:
                return 0.15
            return 0.7
        if fam == "observe" and (features.needs_reobserve or features.mean_belief < 0.55):
            if int(features.extras.get("hypotheses_remaining") or 0) > 0:
                return 0.2
            return 0.75
        if fam == "type_query" and int(features.extras.get("hypotheses_remaining") or 0) >= 0:
            if not features.query_matches_goal and not (
                features.extras.get("contact_candidates") or features.extras.get("result_surface_visible")
            ):
                return 0.35  # boost trying hypotheses
        if fam == "observe" and features.query_matches_goal and not features.has_named_entity:
            return 0.45
        if fam == "open_contact" and (features.extras.get("result_surface_visible") or rows_visible) and features.query_matches_goal:
            return 0.65
        if fam == "open_contact" and features.mean_belief < 0.45:
            return -0.4
        return 0.0


# Module-level default engine (tests may construct fresh ones)
_DEFAULT_ENGINE: Optional[DecisionEngine] = None


def get_decision_engine() -> DecisionEngine:
    global _DEFAULT_ENGINE
    if _DEFAULT_ENGINE is None:
        _DEFAULT_ENGINE = DecisionEngine()
    return _DEFAULT_ENGINE


def define_action_step(
    goal: Goal,
    world_model: WorldModel,
    execution_state: "ExecutionState",
    *,
    worldview_score: float = 1.0,
    engine: Optional[DecisionEngine] = None,
) -> Optional[Action]:
    """Module helper: brain capability that defines the next actor step."""
    eng = engine or get_decision_engine()
    return eng.define_action_step(goal, world_model, execution_state, worldview_score=worldview_score)


# Backward-compatible alias (prefer ``define_action_step``).
decide = define_action_step
DecisionEngine.decide = DecisionEngine.define_action_step  # type: ignore[method-assign]
