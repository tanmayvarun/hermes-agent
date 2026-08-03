"""DecisionEngine — Goal + World + PolicyPrior + Value → one Action."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from plugin.agent.action import Action
from plugin.agent.apps.registry import get_overlay
from plugin.agent.action_models.integration import action_prior_bonus, maybe_collect_action_prior_runs
from plugin.agent.features import StateFeatures
from plugin.agent.goal import Goal, GoalStatus, evaluate_goal
from plugin.agent.decision_selector import select_action_with_llm
from plugin.agent.decision_selector import select_branch_strategy_with_llm
from plugin.agent.policy.candidates import enumerate_candidates
from plugin.agent.policy.frontier import action_hypothesis_label, frontier_summary
from plugin.agent.policy.prior import PolicyPrior
from plugin.agent.policy.value import (
    perception_synthesis_bonus,
    predicted_value_delta,
    value_of_features,
)
from plugin.agent.perception_synthesis import synthesize_perception
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
        """One multimodal call produces the belief update and the next action.

        The model proposes; this method disposes. An inadmissible proposal, a
        low-confidence one, or unresolved contradictions all fall through to
        the enumerate-score-select path, which then escalates to the deep text
        reasoner. That keeps a single model on the fast path and two models
        only on escalation.
        """
        from plugin.agent.unified_cognition import (
            consult_unified_cognition,
            proposal_to_action,
            ranked_action_candidates,
            should_escalate,
            unified_cognition_enabled,
        )

        if not unified_cognition_enabled():
            return None
        # The executive asked to deliberate (meta-action THINK, or a PROBE that
        # wants a fresh reveal). Skip the multimodal fast path this once so the
        # enumerate/score/consult reasoner runs instead, then clear the request.
        if getattr(execution_state, "force_deliberation", False):
            execution_state.force_deliberation = False
            features.extras["forced_deliberation"] = True
            return None
        try:
            proposal = consult_unified_cognition(goal, world, features, execution_state)
        except Exception as exc:  # never let cognition failure kill the loop
            features.extras["unified_cognition"] = {"error": str(exc)[:200]}
            return None

        action: Optional[Action] = None
        reason = "no_proposal"
        action_rank = -1
        rejected_siblings: List[str] = []
        if proposal is not None:
            # The model returns a ranked frontier, best first. Try each in order:
            # a considered alternative the model already offered beats sending the
            # whole run to the slow text reasoner because the top pick happened to
            # be inadmissible (e.g. a pointer move with no target). We record the
            # rank we landed on and the siblings we rejected, for the trace.
            candidates_ranked = ranked_action_candidates(proposal)
            if not candidates_ranked and proposal.next_action:
                candidates_ranked = [dict(proposal.next_action)]
            original_head = proposal.next_action
            for idx, cand in enumerate(candidates_ranked):
                proposal.next_action = cand
                cand_action, cand_reason = proposal_to_action(proposal, goal, world, features)
                if cand_action is not None:
                    action, reason, action_rank = cand_action, cand_reason, idx
                    break
                fam = str(cand.get("family") or "").strip().lower() or "unknown"
                rejected_siblings.append(f"{fam}:{cand_reason}")
                reason = cand_reason
            if action is None:
                proposal.next_action = original_head
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
        }
        if action is None or escalate:
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

    def _promote_visible_search_result(
        self,
        goal: Goal,
        world: WorldModel,
        features: StateFeatures,
        overlay: Any,
        execution_state: Any,
    ) -> Optional[Action]:
        """Open a visible row that matches the contact we need, deterministically.

        When a row that names the contact we are trying to open is right there on
        screen — a search result, or a source-conversation row in the list — the
        move is to open it, not to re-search and not to idle on observe waiting
        for the perception model to say what is already visible. The real
        safeguard is the *name match* to the contact we need; the surface it
        appears on (search results vs. chat list) is app-specific noise. This is
        why it is gated on a matching row, not on query_matches_goal.
        """
        extras = features.extras or {}
        surface_up = bool(
            extras.get("result_surface_visible")
            or extras.get("search_result_rows")
            or extras.get("source_conversation_visible")
        )
        if not surface_up:
            return None
        target = str(goal.contact or getattr(goal, "target_contact", "") or "").strip()
        if not target:
            return None

        # If we are already inside the conversation with the target, there is
        # nothing to open — promoting open_contact here would reopen the chat we
        # are in (or, on a call task, preempt the actual call). This mirrors the
        # value model's demotion of open_contact once the source is open.
        open_c = str((features.extras or {}).get("open_conversation") or "").strip().lower()
        tl_target = target.lower()
        if open_c and (tl_target in open_c or open_c in tl_target):
            return None

        try:
            candidates = enumerate_candidates(goal, world, features, overlay)
        except Exception:
            return None
        opens = [
            cand
            for cand in candidates
            if cand.action_family == "open_contact" and str(cand.semantic_target or "").strip()
        ]
        if not opens:
            return None

        tl = target.lower()
        matched = [
            cand
            for cand in opens
            if tl in cand.semantic_target.lower() or cand.semantic_target.lower() in tl
        ]
        chosen = max(matched or opens, key=lambda cand: float(getattr(cand, "score", 0.0) or 0.0))
        if not matched:
            # No row actually matches the target — do not open the wrong contact.
            return None

        self._bind_capability(chosen, features, world, goal)
        chosen.observed_in_world = str(getattr(execution_state, "world_id", "") or "")
        chosen.grounding_reason = chosen.grounding_reason or "visible_search_result"
        self.last_trace = DecisionTrace(
            features=features.to_dict(),
            candidates=[],
            goal_status={"reason": "deterministic_visible_search_result_promotion"},
            chosen={
                "action": chosen.action,
                "target": chosen.semantic_target,
                "family": chosen.action_family,
            },
        )
        return chosen

    def decide(
        self,
        goal: Goal,
        world: WorldModel,
        execution_state: "ExecutionState",
        *,
        worldview_score: float = 1.0,
        state_signature: str = "",
        state_experience: Any = None,
    ) -> Optional[Action]:
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

        # Unified cognition is the fast path: one multimodal pass over pixels,
        # AX evidence, task state and goal yields the belief update and the
        # next action together. Only when it declines or is inadmissible do we
        # fall back to split perception plus the text selector below.
        unified_action = self._unified_fast_path(goal, world, features, execution_state, [])
        if unified_action is not None:
            return unified_action

        # A visible search-result row that matches the target is opened directly,
        # without a perception-model round-trip: the answer is on screen.
        promoted_row = self._promote_visible_search_result(
            goal, world, features, overlay, execution_state
        )
        if promoted_row is not None:
            return promoted_row

        non_observe_count = 0
        try:
            non_observe_count = len([cand for cand in candidates if cand.action_family != "observe"])
        except Exception:
            non_observe_count = 0
        synthesize_perception_needed = (
            self.selector_enabled
            or self.selector_caller is not None
            or non_observe_count == 0
        )
        if synthesize_perception_needed:
            try:
                view = (
                    overlay.raw_view_dict(world)
                    if hasattr(overlay, "raw_view_dict")
                    else overlay.view_dict(world)
                )
                synth = synthesize_perception(goal, world, view, features, worldview=worldview_score)
                if synth is not None:
                    summary_bridge = structured_perception_bridge(features=features, world=world)
                    summary_bridge.update({
                        "screen_type": synth.screen_type,
                        "active_surface": synth.active_surface,
                        "likely_next_family": synth.likely_next_family,
                        "likely_next_target": synth.likely_next_target,
                        "likely_next_text": synth.likely_next_text,
                        "confidence": round(float(synth.confidence or 0.0), 4),
                    })
                    features.extras["perception_summary"] = summary_bridge
                    # Generic perception-to-policy bridge: when the screen synthesizer
                    # identifies a dialog, promote that into the feature layer so
                    # candidate generation can surface a dismiss branch even if the
                    # AX tree does not expose a neat button label.
                    if not bool(features.extras.get("storage_pressure")):
                        if synth.screen_type == "dialog" or synth.likely_next_family == "dismiss":
                            features.has_dialog = True
            except Exception:
                pass
        cap_graph = None
        try:
            from plugin.worldmodel.capability import (
                CapabilityGraph,
                action_family_to_capability_type,
                grounded_action_for_capability,
                goal_capability_types,
            )

            cap_raw = features.extras.get("capability_graph") or getattr(world, "last_capability_graph", None) or {}
            if isinstance(cap_raw, dict):
                cap_graph = CapabilityGraph.from_dict(cap_raw)
                features.extras["goal_capability_types"] = goal_capability_types(goal)
                selected_cap = cap_graph.select_for_goal(goal)
                features.extras["selected_capability_id"] = "" if selected_cap is None else selected_cap.capability_id
                features.extras["selected_capability_type"] = "" if selected_cap is None else selected_cap.type
                features.extras["capability_frontier"] = [node.to_dict() for node in cap_graph.select_frontier(goal)]
                features.extras["capability_graph"] = cap_graph.to_dict()
        except Exception:
            cap_graph = None
        active_subgraph = (
            features.extras.get("active_cognitive_subgraph")
            or getattr(world, "last_active_subgraph", None)
            or {}
        )
        cap_graph_focus = cap_graph
        if cap_graph is not None:
            try:
                from plugin.worldmodel.capability import project_capability_graph

                cap_graph_focus = project_capability_graph(
                    cap_graph,
                    active_entity_ids=list((active_subgraph or {}).get("active_entity_ids") or []),
                    focus_region_ids=list((active_subgraph or {}).get("focus_region_ids") or []),
                    goal=goal,
                )
            except Exception:
                cap_graph_focus = cap_graph
        # Re-sync after optional features rebuilds in the fallback path.
        hint = execution_state.peek_search_query_hint()
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

        # Expose active search hypothesis for candidates / inspect
        ref = goal.ensure_reference() if goal.contact else None
        hyp_i = int(getattr(execution_state, "search_hypothesis_index", 0) or 0)
        features.extras["search_hypothesis_index"] = hyp_i
        active_hypothesis = goal.search_text(hyp_i) if goal.contact else ""
        features.extras["active_search_hypothesis"] = active_hypothesis
        current_query = str(features.extras.get("search_query") or "").strip().lower()
        active_query = str(active_hypothesis or "").strip().lower()
        if getattr(execution_state, "search_refinement_pending", False):
            features.extras["search_refinement_pending"] = True
        elif hyp_i > 0 and current_query and active_query and current_query != active_query:
            features.extras["search_refinement_pending"] = True
        if ref is not None:
            features.extras["reference"] = ref.to_dict()
            features.extras["search_hypotheses"] = list(ref.search_hypotheses or [])
        features.extras["goal_hypotheses"] = goal.intent_hypotheses()
        if goal.prompt:
            features.extras["goal_prompt"] = goal.prompt
        features.extras["goal_summary"] = goal.description

        # If more hypotheses remain, do not treat fusion needs_reobserve as hard observe-only
        n_hyps = len((ref.search_hypotheses if ref else None) or []) or 1
        features.extras["hypotheses_remaining"] = max(0, n_hyps - hyp_i - 1)
        layers = getattr(execution_state, "hypothesis_layers", None)
        if layers is not None:
            features.extras["hypothesis_layers"] = layers.to_dict()
            if float(getattr(layers, "actuation_confidence", 1.0) or 1.0) < 0.45:
                features.extras["actuation_weak"] = True
        belief_store = getattr(execution_state, "belief_store", None)
        if belief_store is not None:
            features.extras["belief_store"] = belief_store.to_dict()
            if getattr(execution_state, "last_belief_update", None) is not None:
                features.extras["last_belief_update"] = execution_state.last_belief_update.to_dict()
            if getattr(execution_state, "active_uncertainty", None) is not None:
                features.extras["active_uncertainty"] = execution_state.active_uncertainty.to_dict()
            if getattr(execution_state, "active_hypotheses", None):
                features.extras["active_hypotheses"] = [h.to_dict() for h in execution_state.active_hypotheses[-3:]]
            if getattr(execution_state, "active_experiment", None) is not None:
                features.extras["active_experiment"] = execution_state.active_experiment.to_dict()
        if getattr(execution_state, "world_exploration_needed", False):
            features.extras["world_exploration_needed"] = True
            features.extras["actuation_weak"] = True
            features.extras["world_explore_observe_count"] = int(
                getattr(execution_state, "world_explore_observe_count", 0) or 0
            )
        if getattr(execution_state, "perception_incomplete", False):
            features.extras["perception_incomplete"] = True
            features.extras["perception_failure_modes"] = list(
                getattr(execution_state, "last_perception_failure_modes", None) or []
            )
        if getattr(execution_state, "perception_cycle_stalled", False):
            features.extras["perception_cycle_stalled"] = True
            features.extras["perception_stall_count"] = int(
                getattr(execution_state, "perception_stall_count", 0) or 0
            )
            features.extras["perception_stall_reason"] = str(
                getattr(execution_state, "perception_stall_reason", "") or ""
            )

        # Trajectory / latent context — keep call path alive across overlays
        ctx = getattr(execution_state, "interaction_context", None)
        branch = getattr(execution_state, "exploration_branch", None)
        if ctx is not None:
            features.extras["interaction_context"] = ctx.to_dict()
            if getattr(ctx.open_conversation, "effective", False):
                features.extras["latent_conversation_open"] = True
                # Soft-open so start_call isn't hard-blocked when header is occluded
                if not features.conversation_open:
                    features.conversation_open = True
            active_surface = getattr(ctx, "active_surface", "")
            if active_surface in {"call_picker", "search_results"}:
                features.extras["active_surface"] = active_surface
            if active_surface == "call_picker":
                features.call_available = True
        if branch is not None and getattr(branch, "active", False):
            features.extras["branch_active"] = True
            features.extras["branch_depth"] = int(getattr(branch, "depth", 0) or 0)
            features.extras["branch_affordances"] = list(
                getattr(branch, "newly_relevant_affordances", None) or []
            )
            # Prefer local branch actions over re-search
            features.extras["world_exploration_needed"] = False
            branch_surface = str(getattr(branch, "active_surface", "") or features.extras.get("active_surface") or "")
            if branch_surface == "search_results":
                features.extras["result_surface_visible"] = True
            if "initiate_voice" in (features.extras.get("branch_affordances") or []):
                features.call_available = True
                if not features.conversation_open:
                    features.conversation_open = True
        branch_preferred_family = ""
        if branch is not None and getattr(branch, "active", False):
            preferred_frontier = branch.best_non_observe_frontier(only_untried=True) or branch.best_non_observe_frontier()
            if preferred_frontier is not None:
                branch_preferred_family = str(preferred_frontier.action_family or "").strip().lower()
            if not branch_preferred_family and state_experience is not None:
                branch_preferred_family = str(getattr(state_experience, "pending_backtrack_family", "") or "").strip().lower()
            if branch_preferred_family:
                features.extras["branch_preferred_family"] = branch_preferred_family

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

        state_sig = state_signature or str(
            features.extras.get("world_signature")
            or features.screen_bucket
            or getattr(execution_state, "world_id", "")
            or "unknown"
        )
        features.extras["state_signature"] = state_sig

        exp = state_experience
        if exp is None:
            exp = getattr(execution_state, "state_experience", None)
        try:
            from plugin.agent.trajectory_memory import get_trajectory_memory

            traj_memory = get_trajectory_memory()
        except Exception:
            traj_memory = None

        goal_cap_types = set(features.extras.get("goal_capability_types") or [])
        selected_capability_id = str(features.extras.get("selected_capability_id") or "")
        candidates = enumerate_candidates(goal, world, features, overlay)
        if exp is not None:
            candidates = exp.filter_actions(state_sig, candidates)
            features.extras["experience_suppressed"] = True
            features.extras["pending_backtrack"] = getattr(exp, "pending_backtrack_family", "") or ""

        perception_candidate = self._promote_perception_candidate(goal, world, features, candidates)
        if perception_candidate is not None:
            candidates.append(perception_candidate)
            features.extras["perception_promoted_candidate"] = {
                "action": perception_candidate.action,
                "family": perception_candidate.action_family,
                "target": perception_candidate.semantic_target,
                "confidence": round(float(perception_candidate.evidence_score or 0.0), 4),
            }
            if (
                perception_candidate.action_family == "open_contact"
                and float(perception_candidate.evidence_score or 0.0)
                >= self._perception_promotion_threshold_for_family("open_contact")
            ):
                self.last_trace = DecisionTrace(
                    features=features.to_dict(),
                    candidates=[
                        {
                            "action": a.action,
                            "target": a.semantic_target,
                            "family": a.action_family,
                            "capability_id": a.capability_id,
                            "capability_type": a.capability_type,
                            "score": round(a.score, 4),
                            "prior": round(a.prior_score, 4),
                            "value_delta": round(a.value_delta, 4),
                            "evidence": round(a.evidence_score, 4),
                            "frontier_label": a.frontier_label,
                            "frontier_score": round(a.frontier_score, 4),
                        }
                        for a in candidates[:12]
                    ],
                    goal_status={
                        "succeeded": False,
                        "impossible": False,
                        "reason": "perception_promotion_open_contact",
                    },
                    chosen={
                        "action": perception_candidate.action,
                        "target": perception_candidate.semantic_target,
                        "text": perception_candidate.text,
                        "family": perception_candidate.action_family,
                        "capability_id": perception_candidate.capability_id,
                        "capability_type": perception_candidate.capability_type,
                        "target_entity_id": perception_candidate.target_entity_id,
                        "score": round(perception_candidate.score, 4),
                        "rationale": perception_candidate.rationale,
                        "grounding_reason": perception_candidate.grounding_reason,
                    },
                )
                return perception_candidate

        action_prior_runs = []
        try:
            action_prior_runs = maybe_collect_action_prior_runs(goal, world, features, candidates)
            if action_prior_runs:
                features.extras["action_prior_runs"] = [run.to_dict() for run in action_prior_runs]
        except Exception:
            action_prior_runs = []

        branch_strategy = None
        branch_strategy_trace = None
        if self._branch_strategy_should_run(features, branch, candidates):
            try:
                branch_strategy, branch_strategy_trace = select_branch_strategy_with_llm(
                    goal,
                    world,
                    features,
                    candidates,
                    cap_graph=cap_graph_focus,
                    caller=self.selector_caller,
                    frontier_summary=frontier_summary(goal, features, candidates),
                    branch=branch.to_dict() if branch is not None and hasattr(branch, "to_dict") else None,
                    task="branch_strategy",
                    call_kwargs=self._branch_strategy_call_kwargs(),
                )
            except Exception as exc:
                from agent.auxiliary_client import LLMProviderExhaustedError

                if isinstance(exc, LLMProviderExhaustedError):
                    if self.selector_enabled or self.selector_caller is not None:
                        raise
                    branch_strategy = None
                    branch_strategy_trace = {"error": "branch_strategy_unavailable"}
                else:
                    branch_strategy = None
                    branch_strategy_trace = {"error": "branch_strategy_failed"}
            if branch_strategy is not None:
                features.extras["branch_strategy"] = branch_strategy.to_dict()
                if branch is not None and getattr(branch, "active", False):
                    branch.strategy = branch_strategy
                if branch_strategy.preferred_family:
                    branch_preferred_family = branch_strategy.preferred_family
                elif branch_strategy.backtrack_family:
                    branch_preferred_family = branch_strategy.backtrack_family
                if branch_strategy.backtrack_family and not branch_strategy.preferred_family:
                    experience.pending_backtrack_family = branch_strategy.backtrack_family
                if branch_strategy.avoid_families:
                    features.extras["branch_avoid_families"] = list(branch_strategy.avoid_families)
                if branch_preferred_family:
                    features.extras["branch_preferred_family"] = branch_preferred_family
                features.extras["branch_strategy_reason"] = branch_strategy.reason
                features.extras["branch_strategy_confidence"] = round(float(branch_strategy.confidence or 0.0), 4)
            if branch_strategy_trace is not None:
                features.extras["branch_strategy_trace"] = branch_strategy_trace
        explicit_branch_choice = None
        explicit_branch_commit = False
        if branch is not None and getattr(branch, "active", False):
            explicit_branch_choice = self._explicit_branch_edge_choice(
                candidates,
                branch_strategy=branch_strategy,
                branch_preferred_family=branch_preferred_family,
                pending_backtrack_family=str(getattr(exp, "pending_backtrack_family", "") or ""),
            )
            if explicit_branch_choice is not None and (
                branch_strategy is not None
                or branch_preferred_family
                or str(getattr(exp, "pending_backtrack_family", "") or "").strip()
            ):
                explicit_branch_commit = True
                features.extras["branch_edge_commit"] = {
                    "family": explicit_branch_choice.action_family,
                    "target": explicit_branch_choice.semantic_target,
                    "reason": (
                        "branch_strategy"
                        if branch_strategy is not None and explicit_branch_choice.action_family
                        in {
                            str(getattr(branch_strategy, "preferred_family", "") or "").strip().lower(),
                            str(getattr(branch_strategy, "backtrack_family", "") or "").strip().lower(),
                        }
                        else "branch_hint"
                    ),
                }

        if any(cand.action_family != "observe" for cand in candidates):
            allow_single_candidate = True
            selector_candidates: List[Action] = []
            observe_candidate = None
            for cand in candidates:
                if execution_state.is_prohibited(cand):
                    continue
                fam = cand.action_family
                cand_cap_type = action_family_to_capability_type(
                    fam,
                    semantic_target=cand.semantic_target,
                    text=cand.text,
                )
                cap = None
                if cap_graph is not None:
                    cap = cap_graph.capability_for_action(
                        action_family=fam,
                        semantic_target=cand.semantic_target,
                        text=cand.text,
                    )
                    if cap is not None:
                        cand.capability_id = cap.capability_id
                        cand.capability_type = cap.type
                    else:
                        cand.capability_type = cand_cap_type
                else:
                    cand.capability_type = cand_cap_type
                p = self.prior.score(fam, features, goal)
                dv = predicted_value_delta(cand, features, goal)
                ev = self._evidence_bonus(cand, features, goal, execution_state)
                ev += action_prior_bonus(cand, action_prior_runs)
                ev += perception_synthesis_bonus(cand, features, goal)
                if cap_graph is not None and cap is not None:
                    if cap.type in goal_cap_types:
                        ev += 0.16
                        if cap.visible:
                            ev += 0.08
                    if selected_capability_id and cap.capability_id == selected_capability_id:
                        ev += 0.12
                    if not cap.visible and fam != "observe":
                        ev -= 0.10
                    cand.reversible = bool(cap.reversibility)
                ev += self._procedure_stage_alignment_bonus(
                    cand,
                    features,
                    capability_type=cand.capability_type or cand_cap_type,
                )
                if traj_memory is not None:
                    ev += float(
                        traj_memory.score(
                            goal,
                            features,
                            fam,
                            state_signature=state_sig,
                        )
                    )
                cand.prior_score = p
                cand.value_delta = dv
                cand.evidence_score = ev
                cand.score = self.alpha * p + self.beta * dv + self.gamma * ev
                cand.observed_in_world = str(getattr(execution_state, "world_id", "") or "")
                cand.frontier_label = action_hypothesis_label(goal, features, cand)
                cand.frontier_score = round(float(cand.score or 0.0), 4)
                cand.prediction = self._prediction_for_candidate(
                    cand,
                    goal=goal,
                    features=features,
                    branch=branch,
                    confidence=float(cand.frontier_score or 0.0),
                ).to_dict()
                active_uncertainty = features.extras.get("active_uncertainty") or {}
                uncertainty_question = str(active_uncertainty.get("question") or "").lower()
                if fam == "observe" and any(tok in uncertainty_question for tok in ("perception", "stale", "uncertain")):
                    cand.score += 0.08
                if fam in {"open_search", "type_query"} and "search" in uncertainty_question:
                    cand.score += 0.06
                selector_candidates.append(cand)
                if observe_candidate is None and fam == "observe":
                    observe_candidate = cand
            frontier_label_summary = frontier_summary(goal, features, selector_candidates)
            features.extras["frontier_hypotheses"] = frontier_label_summary
            high_risk_reasoning = self._needs_high_risk_reasoning(selector_candidates) or self._goal_requires_high_risk_reasoning(goal, selector_candidates)
            use_selector = self.selector_enabled or self.selector_caller is not None or high_risk_reasoning
            grounding_threshold = self.action_grounding_confidence_threshold()
            grounded_selector_candidates = self._grounded_action_candidates(
                selector_candidates,
                grounding_threshold=grounding_threshold,
            )
            grounded_non_observe_candidates = [
                cand for cand in grounded_selector_candidates if cand.action_family != "observe"
            ]
            if not grounded_non_observe_candidates:
                use_selector = False

            self.last_trace = DecisionTrace(
                features=features.to_dict(),
                candidates=[
                    {
                        "action": a.action,
                        "target": a.semantic_target,
                        "family": a.action_family,
                        "capability_id": a.capability_id,
                        "capability_type": a.capability_type,
                        "score": round(a.score, 4),
                        "prior": round(a.prior_score, 4),
                        "value_delta": round(a.value_delta, 4),
                        "evidence": round(a.evidence_score, 4),
                        "frontier_label": a.frontier_label,
                        "frontier_score": round(a.frontier_score, 4),
                    }
                    for a in selector_candidates[:12]
                ],
                goal_status={
                    "succeeded": status.succeeded,
                    "impossible": status.impossible,
                    "reason": status.reason,
                },
                chosen=None,
            )
            self.last_trace.branch_strategy = branch_strategy_trace
            if explicit_branch_commit:
                self.last_trace.features.setdefault("extras", {})["branch_edge_commit"] = features.extras.get(
                    "branch_edge_commit"
                )
            selector_choice = None
            selector_trace = None
            if explicit_branch_choice is not None:
                selector_choice = explicit_branch_choice
                selector_trace = {
                    "reason": "branch_edge_commit",
                    "committed_family": explicit_branch_choice.action_family,
                    "committed_target": explicit_branch_choice.semantic_target,
                }
            elif use_selector:
                try:
                    selector_task = self.high_risk_selector_task if high_risk_reasoning else self.selector_task
                    selector_choice, selector_trace = select_action_with_llm(
                        goal,
                        world,
                        features,
                        grounded_selector_candidates,
                        cap_graph=cap_graph_focus,
                        task=selector_task,
                        caller=self.selector_caller,
                        allow_single_candidate=allow_single_candidate,
                        frontier_summary=frontier_label_summary,
                        action_prior_runs=[run.to_dict() for run in action_prior_runs],
                        irreversible_threshold=self.irreversible_action_confidence_threshold(),
                        grounding_threshold=grounding_threshold,
                        call_kwargs=self._high_risk_selector_call_kwargs() if high_risk_reasoning else None,
                    )
                except Exception as exc:
                    from agent.auxiliary_client import LLMProviderExhaustedError

                    if isinstance(exc, LLMProviderExhaustedError):
                        if self.selector_enabled or self.selector_caller is not None:
                            raise
                        selector_choice = None
                        selector_trace = {"error": "selector_unavailable"}
                    else:
                        selector_choice = None
                        selector_trace = {"error": "selector_failed"}

            self.last_trace.selector = selector_trace
            self.last_trace.selector_confidence = float((selector_trace or {}).get("confidence") or 0.0)
            grounding_reason = ""
            grounding_confidence = 0.0
            if not grounded_non_observe_candidates:
                selector_choice = observe_candidate
                selector_trace = {
                    **(selector_trace or {}),
                    "reason": "grounding_recovery",
                    "grounded_candidates": 0,
                    "grounding_threshold": round(float(grounding_threshold or 0.0), 4),
                }
            self._sync_branch_frontier(
                branch=branch,
                execution_state=execution_state,
                state_sig=state_sig,
                features=features,
                goal=goal,
                candidates=selector_candidates,
                exp=exp,
                branch_surface=str(features.extras.get("active_surface") or ""),
                branch_preferred_family=branch_preferred_family,
            )

            if not grounded_non_observe_candidates:
                selector_choice = observe_candidate
                selector_trace = {
                    **(selector_trace or {}),
                    "reason": "grounding_recovery",
                    "grounded_candidates": 0,
                    "grounding_threshold": round(float(grounding_threshold or 0.0), 4),
                }
            elif selector_choice is None and not use_selector:
                selector_choice = max(
                    grounded_non_observe_candidates,
                    default=observe_candidate,
                    key=lambda cand: float(getattr(cand, "score", 0.0) or 0.0),
                )
                selector_trace = selector_trace or {"reason": "selector_disabled"}
            elif selector_choice is None and use_selector:
                reason = str((selector_trace or {}).get("reason") or "").strip().lower()
                selector_choice = max(
                    grounded_non_observe_candidates,
                    default=observe_candidate,
                    key=lambda cand: float(getattr(cand, "score", 0.0) or 0.0),
                )
                fallback_reason = reason or str((selector_trace or {}).get("error") or "").strip().lower()
                selector_trace = {
                    **(selector_trace or {}),
                    "reason": "llm_no_choice_fallback",
                    "fallback_reason": fallback_reason or "unknown",
                    "fallback_action": getattr(selector_choice, "action", ""),
                    "fallback_family": getattr(selector_choice, "action_family", ""),
                }

            if selector_choice is None:
                selector_choice = observe_candidate
                selector_trace = selector_trace or {"reason": "grounding_recovery"}
            best = selector_choice
            if best is not None and best.action_family == "observe":
                best_non_observe = self._best_grounded_non_observe_candidate(
                    selector_candidates,
                    grounding_threshold=grounding_threshold,
                )
                if best_non_observe is not None and best_non_observe.action_family in {"open_search", "type_query", "open_contact"}:
                    best = best_non_observe
                else:
                    best = observe_candidate or best
            if best is not None and best.action_family != "observe":
                if (
                    getattr(best, "target_entity_id", None) is None
                    and float(getattr(best, "grounding_confidence", 0.0) or 0.0) < grounding_threshold
                ):
                    best = observe_candidate or best
                    grounding_reason = "grounding_recovery"
                    grounding_confidence = 0.0
            if best is not None and best.action_family != "observe" and cap_graph_focus is not None:
                cap = cap_graph_focus.capability_for_action(
                    action_family=best.action_family,
                    semantic_target=best.semantic_target,
                    text=best.text,
                )
                if cap is not None:
                    can_skip_irreversible_gate = (
                        best.action_family == "start_call"
                        and goal.kind == "whatsapp_voice_call"
                        and (
                            features.conversation_open
                            or features.call_available
                            or features.extras.get("latent_conversation_open")
                        )
                    )
                    if (
                        not cap.reversibility
                        and self.last_trace.selector_confidence < self.irreversible_action_confidence_threshold()
                        and not can_skip_irreversible_gate
                    ):
                        best = observe_candidate or best
                        grounding_reason = "blocked_below_irreversible_threshold"
                    else:
                        grounded = grounded_action_for_capability(
                            cap,
                            entities=list(world.entities.values()),
                            graph=scene_graph_obj if scene_graph_obj is not None else None,
                        )
                        best.capability_id = cap.capability_id
                        best.capability_type = cap.type
                        best.reversible = bool(cap.reversibility)
                        if grounded is not None:
                            grounded_entity = (
                                world.entities.get(int(grounded.entity_id))
                                if grounded.entity_id is not None
                                else None
                            )
                            if grounded_entity is not None and not self._grounding_matches_candidate(best, grounded_entity):
                                grounded = None
                                grounding_reason = "rejected_mismatched_grounding"
                                grounding_confidence = 0.0
                            else:
                                best.target_entity_id = grounded.entity_id
                                grounding_reason = grounded.reason
                                grounding_confidence = grounded.confidence
                        if grounded is None and self._requires_entity_grounding(best):
                            best = observe_candidate or best
                            grounding_reason = grounding_reason or "unresolved_grounding"
            if best is None:
                return None
            if (
                best.action_family != "observe"
                and best.target_entity_id is None
                and self._requires_entity_grounding(best)
            ):
                raise RuntimeError(
                    f"LLM-selected action {best.action_family} could not be grounded; refusing observe fallback"
                )
            best.grounding_reason = grounding_reason
            best.grounding_confidence = grounding_confidence
            self.last_trace.chosen = {
                "action": best.action,
                "target": best.semantic_target,
                "text": best.text,
                "family": best.action_family,
                "capability_id": best.capability_id,
                "capability_type": best.capability_type,
                "target_entity_id": best.target_entity_id,
                "score": round(best.score, 4),
                "rationale": best.rationale,
                "grounding_reason": best.grounding_reason,
            }
            return best

        scored: List[Action] = []
        frontier_snapshot: List[FrontierAction] = []
        branch_affs = {str(a).strip().lower() for a in (features.extras.get("branch_affordances") or [])}
        branch_surface = str(features.extras.get("active_surface") or "")
        for cand in candidates:
            tried = False
            if exp is not None:
                tried = bool(exp.is_suppressed(state_sig, cand))
            if execution_state.is_prohibited(cand):
                continue
            fam = cand.action_family
            cand_cap_type = action_family_to_capability_type(
                fam,
                semantic_target=cand.semantic_target,
                text=cand.text,
            )
            p = self.prior.score(fam, features, goal)
            dv = predicted_value_delta(cand, features, goal)
            ev = self._evidence_bonus(cand, features, goal, execution_state)
            ev += perception_synthesis_bonus(cand, features, goal)
            cap = None
            if cap_graph is not None:
                cap = cap_graph.capability_for_action(
                    action_family=fam,
                    semantic_target=cand.semantic_target,
                    text=cand.text,
                )
                if cap is not None:
                    cand.capability_id = cap.capability_id
                    cand.capability_type = cap.type
                    cand.reversible = bool(cap.reversibility)
                    if cap.type in goal_cap_types:
                        ev += 0.16
                        if cap.visible:
                            ev += 0.08
                    if selected_capability_id and cap.capability_id == selected_capability_id:
                        ev += 0.12
                    if not cap.visible and fam != "observe":
                        ev -= 0.10
                else:
                    cand.capability_type = cand_cap_type
            ev += self._procedure_stage_alignment_bonus(
                cand,
                features,
                capability_type=cand.capability_type or cand_cap_type,
            )
            if exp is not None:
                ev += float(exp.boost_for(state_sig, cand))
            if traj_memory is not None:
                ev += float(
                    traj_memory.score(
                        goal,
                        features,
                        fam,
                        state_signature=state_sig,
                    )
                )
            # Low worldview → nudge observe
            if fam == "observe" and worldview_score < 0.55:
                ev += 0.25
            # After NO_EFFECT on start_call, prefer non-call families
            if fam == "start_call" and exp is not None and exp.is_suppressed(state_sig, cand):
                continue
            total = self.alpha * p + self.beta * dv + self.gamma * ev
            # Generic scene attention: prefer targets in attended regions;
            # penalize same-label collisions outside attention (e.g. mic in composer).
            scene = features.extras.get("world_graph") or getattr(world, "last_scene_graph", None)
            if isinstance(scene, dict) and scene.get("attention") and cand.semantic_target:
                try:
                    from plugin.worldmodel.scene.affordances import attention_score_delta
                    from plugin.worldmodel.scene.types import WorldGraph

                    total += attention_score_delta(
                        WorldGraph.from_dict(scene),
                        semantic_target=cand.semantic_target,
                        entities=list(world.entities.values()),
                    )
                except Exception:
                    pass
            if branch is not None and getattr(branch, "active", False):
                if not tried:
                    total += 0.06
                else:
                    total -= 0.1
                if branch_surface == "search_results" and fam == "open_contact":
                    total += 0.28
                if branch_surface == "search_results" and fam == "start_call":
                    total -= 0.18
                if fam == "open_contact" and branch_surface == "search_results":
                    total += 0.22
                if fam == "start_call" and (
                    cand_cap_type in {"InitiateVoiceCall", "InitiateVideoCall"}
                    or cand.semantic_target.lower() in {"voice", "voice call", "audio call"}
                    or "initiate_voice" in branch_affs
                    or branch_surface == "call_picker"
                ):
                    total += 0.18
                if fam == "explore_chrome" and branch_affs:
                    total += 0.05
                if fam == "forward_message" and any(
                    a in branch_affs for a in {"forwardmessage", "forward_message", "reveal_message_actions"}
                ):
                    total += 0.28
                if fam == "select_content" and any(
                    a in branch_affs for a in {"reveal_message_actions", "selectcontent"}
                ):
                    total += 0.18
                if fam in {"probe_hover", "probe_context_menu", "probe_focus"} and any(
                    a in branch_affs for a in {"revealhiddenactions", "probesurface", "reveal_message_actions"}
                ):
                    total += 0.14
                if branch.frontier_hypothesis and cand.frontier_label == branch.frontier_hypothesis:
                    total += 0.12
                if branch_preferred_family:
                    if fam == branch_preferred_family:
                        total += 0.30
                    elif fam == "observe" and branch_preferred_family != "observe":
                        total -= 0.22
            if fam == "start_call" and not (
                features.conversation_open or features.call_available or features.extras.get("latent_conversation_open")
            ):
                total -= 0.18
            active_uncertainty = features.extras.get("active_uncertainty") or {}
            uncertainty_question = str(active_uncertainty.get("question") or "").lower()
            if fam == "observe" and any(tok in uncertainty_question for tok in ("perception", "stale", "uncertain")):
                total += 0.08
            if fam in {"open_search", "type_query"} and "search" in uncertainty_question:
                total += 0.06
            frontier_score = total
            if branch is not None and getattr(branch, "active", False):
                frontier_score += 0.15 * (0.9 if not tried else 0.2)
                frontier_score += 0.35 * (
                    0.6 if fam in {"start_call", "explore_chrome"} else 0.2 if fam == "observe" and not tried else 0.05
                )
                frontier_score -= 0.4 * max(0.0, -dv)
                if tried:
                    frontier_score -= 0.15
                if branch_preferred_family:
                    if fam == branch_preferred_family:
                        frontier_score += 0.25
                    elif fam == "observe" and branch_preferred_family != "observe":
                        frontier_score -= 0.20
                if branch_surface == "search_results" and fam == "open_contact":
                    frontier_score += 0.15
                if branch_surface == "search_results" and fam == "start_call":
                    frontier_score -= 0.15
            cand.prior_score = p
            cand.value_delta = dv
            cand.evidence_score = ev
            cand.score = total
            cand.observed_in_world = str(getattr(execution_state, "world_id", "") or "")
            cand.frontier_label = action_hypothesis_label(goal, features, cand)
            cand.frontier_score = round(float(total or 0.0), 4)
            cand.prediction = self._prediction_for_candidate(
                cand,
                goal=goal,
                features=features,
                branch=branch,
                confidence=float(cand.frontier_score or 0.0),
            ).to_dict()
            scored.append(cand)
            if branch is not None and getattr(branch, "active", False):
                novelty = 0.9 if not tried else 0.2
                semantic_relevance = max(0.0, dv) + max(0.0, ev)
                actionability = max(0.0, total)
                information_gain = 0.0
                if fam in {"start_call", "explore_chrome"}:
                    information_gain += 0.6
                if cap is not None and not cap.visible:
                    information_gain += 0.1
                if fam == "open_contact" and branch_surface == "search_results":
                    information_gain += 0.45
                if fam == "observe":
                    information_gain += 0.2 if not tried else 0.05
                if branch_surface == "call_picker":
                    information_gain += 0.2
                if branch_surface == "search_results":
                    information_gain += 0.15 if fam == "open_contact" else 0.02
                if fam == "forward_message" and any(
                    a in branch_affs for a in {"forwardmessage", "forward_message", "reveal_message_actions"}
                ):
                    information_gain += 0.2
                risk = max(0.0, -dv)
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

        scored.sort(key=lambda a: a.score, reverse=True)
        self._sync_branch_frontier(
            branch=branch,
            execution_state=execution_state,
            state_sig=state_sig,
            features=features,
            goal=goal,
            candidates=scored,
            exp=exp,
            branch_surface=branch_surface,
            branch_preferred_family=branch_preferred_family,
        )
        self.last_trace = DecisionTrace(
            features=features.to_dict(),
            candidates=[
                {
                    "action": a.action,
                    "target": a.semantic_target,
                    "family": a.action_family,
                    "capability_id": a.capability_id,
                    "capability_type": a.capability_type,
                    "score": round(a.score, 4),
                    "prior": round(a.prior_score, 4),
                    "value_delta": round(a.value_delta, 4),
                    "evidence": round(a.evidence_score, 4),
                    "frontier_label": a.frontier_label,
                    "frontier_score": round(a.frontier_score, 4),
                }
                for a in scored[:12]
            ],
            goal_status={
                "succeeded": status.succeeded,
                "impossible": status.impossible,
                "reason": status.reason,
            },
            chosen=None,
        )
        self.last_trace.branch_strategy = branch_strategy_trace
        perception_summary = structured_perception_bridge(features=features, world=world)
        if isinstance(perception_summary, dict):
            promoted_family = str(perception_summary.get("likely_next_family") or "").strip().lower()
            try:
                promoted_confidence = max(0.0, min(1.0, float(perception_summary.get("confidence", 0.0) or 0.0)))
            except (TypeError, ValueError):
                promoted_confidence = 0.0
            if promoted_family == "open_contact" and promoted_confidence >= self._perception_promotion_threshold_for_family("open_contact"):
                best_open_contact = max(
                    (cand for cand in scored if cand.action_family == "open_contact"),
                    default=None,
                    key=lambda cand: cand.score,
                )
                best_observe_score = next(
                    (cand.score for cand in scored if cand.action_family == "observe"),
                    float("-inf"),
                )
                if best_open_contact is not None and best_open_contact.score >= best_observe_score:
                    grounding_reason = ""
                    grounding_confidence = 0.0
                    if cap_graph_focus is not None:
                        cap = cap_graph_focus.capability_for_action(
                            action_family=best_open_contact.action_family,
                            semantic_target=best_open_contact.semantic_target,
                            text=best_open_contact.text,
                        )
                        if cap is not None:
                            grounded = grounded_action_for_capability(
                                cap,
                                entities=list(world.entities.values()),
                                graph=scene_graph_obj if scene_graph_obj is not None else None,
                                )
                            best_open_contact.capability_id = cap.capability_id
                            best_open_contact.capability_type = cap.type
                            best_open_contact.reversible = bool(cap.reversibility)
                            if grounded is not None:
                                grounded_entity = (
                                    world.entities.get(int(grounded.entity_id))
                                    if grounded.entity_id is not None
                                    else None
                                )
                                if grounded_entity is not None and not self._grounding_matches_candidate(
                                    best_open_contact,
                                    grounded_entity,
                                ):
                                    grounding_reason = "rejected_mismatched_grounding"
                                    grounding_confidence = 0.0
                                else:
                                    best_open_contact.target_entity_id = grounded.entity_id
                                    grounding_reason = grounded.reason
                                    grounding_confidence = grounded.confidence
                    best_open_contact.grounding_reason = grounding_reason
                    best_open_contact.grounding_confidence = grounding_confidence
                    self.last_trace.chosen = {
                        "action": best_open_contact.action,
                        "target": best_open_contact.semantic_target,
                        "text": best_open_contact.text,
                        "family": best_open_contact.action_family,
                        "capability_id": best_open_contact.capability_id,
                        "capability_type": best_open_contact.capability_type,
                        "target_entity_id": best_open_contact.target_entity_id,
                        "score": round(best_open_contact.score, 4),
                        "rationale": best_open_contact.rationale,
                        "grounding_reason": best_open_contact.grounding_reason,
                    }
                    return best_open_contact
        selector_choice = None
        selector_trace = None
        if not scored:
            return None
        best = None
        grounding_reason = ""
        grounding_confidence = 0.0
        observe_candidate = next((cand for cand in scored if cand.action_family == "observe"), None)
        frontier_label_summary = frontier_summary(goal, features, scored)
        features.extras["frontier_hypotheses"] = frontier_label_summary
        high_risk_reasoning = self._needs_high_risk_reasoning(scored) or self._goal_requires_high_risk_reasoning(goal, scored)
        allow_single_candidate = True
        use_selector = self.selector_enabled or self.selector_caller is not None or high_risk_reasoning
        strict_selector = self._strict_selector_mode()
        selector_unavailable = False
        grounding_threshold = self.action_grounding_confidence_threshold()
        grounded_scored_candidates = self._grounded_action_candidates(scored, grounding_threshold=grounding_threshold)
        grounded_non_observe_scored = [cand for cand in grounded_scored_candidates if cand.action_family != "observe"]
        if not grounded_non_observe_scored:
            use_selector = False
        if use_selector:
            try:
                selector_task = self.high_risk_selector_task if high_risk_reasoning else self.selector_task
                selector_choice, selector_trace = select_action_with_llm(
                    goal,
                    world,
                    features,
                    grounded_scored_candidates,
                    cap_graph=cap_graph,
                    task=selector_task,
                    caller=self.selector_caller,
                    allow_single_candidate=allow_single_candidate,
                    frontier_summary=frontier_label_summary,
                    action_prior_runs=[run.to_dict() for run in action_prior_runs] if action_prior_runs else None,
                    irreversible_threshold=self.irreversible_action_confidence_threshold(),
                    grounding_threshold=grounding_threshold,
                    call_kwargs=self._high_risk_selector_call_kwargs() if high_risk_reasoning else None,
                )
            except Exception as exc:
                from agent.auxiliary_client import LLMProviderExhaustedError

                if isinstance(exc, LLMProviderExhaustedError):
                    selector_unavailable = True
                    reason = str(exc).strip().lower()
                    if "not_ambiguous_enough" not in reason and (
                        self.selector_enabled or self.selector_caller is not None or strict_selector
                    ):
                        raise
                    selector_choice = None
                    selector_trace = {
                        "error": "selector_unavailable",
                        "reason": "not_ambiguous_enough" if "not_ambiguous_enough" in reason else reason or "unknown",
                    }
                else:
                    selector_choice = None
                    selector_trace = {"error": "selector_failed"}

            self.last_trace.selector = selector_trace
        if selector_choice is not None:
            best = selector_choice
            if selector_choice.action_family == "observe":
                best_non_observe = self._best_grounded_non_observe_candidate(
                    scored,
                    grounding_threshold=grounding_threshold,
                )
                if best_non_observe is not None and best_non_observe.action_family in {"open_search", "type_query", "open_contact"}:
                    best = best_non_observe
                else:
                    best = observe_candidate or selector_choice
        else:
            if strict_selector and use_selector:
                from agent.auxiliary_client import LLMProviderExhaustedError

                reason = str((selector_trace or {}).get("reason") or (selector_trace or {}).get("error") or "").strip().lower() or "unknown"
                if reason not in {"not_ambiguous_enough", "llm_no_choice_fallback", "unknown"}:
                    raise LLMProviderExhaustedError(f"strict selector mode: {reason}")
                best = max(
                    grounded_non_observe_scored,
                    default=observe_candidate,
                    key=lambda cand: float(getattr(cand, "score", 0.0) or 0.0),
                )
                selector_choice = best
                selector_trace = {
                    **(selector_trace or {}),
                    "reason": "llm_no_choice_fallback",
                    "fallback_reason": reason,
                    "fallback_action": getattr(best, "action", ""),
                    "fallback_family": getattr(best, "action_family", ""),
                }
            if selector_unavailable and not self.selector_enabled and self.selector_caller is None:
                best = max(
                    grounded_non_observe_scored,
                    default=observe_candidate,
                    key=lambda cand: float(getattr(cand, "score", 0.0) or 0.0),
                )
            else:
                reason = str((selector_trace or {}).get("reason") or (selector_trace or {}).get("error") or "").strip().lower() or "unknown"
                best = max(
                    grounded_non_observe_scored,
                    default=observe_candidate,
                    key=lambda cand: float(getattr(cand, "score", 0.0) or 0.0),
                )
                if strict_selector:
                    from agent.auxiliary_client import LLMProviderExhaustedError

                    if reason not in {"not_ambiguous_enough", "llm_no_choice_fallback", "unknown"}:
                        raise LLMProviderExhaustedError(
                            f"strict selector mode: no usable LLM choice ({reason or 'unknown'})"
                        )
                selector_trace = {
                    **(selector_trace or {}),
                    "reason": "llm_no_choice_fallback",
                    "fallback_reason": reason or str((selector_trace or {}).get("error") or "").strip().lower() or "unknown",
                    "fallback_action": getattr(best, "action", ""),
                    "fallback_family": getattr(best, "action_family", ""),
                }
        if best is None:
            best = max(
                grounded_non_observe_scored,
                default=observe_candidate,
                key=lambda cand: float(getattr(cand, "score", 0.0) or 0.0),
            )
        if best is not None and best.action_family != "observe":
            if (
                getattr(best, "target_entity_id", None) is None
                and float(getattr(best, "grounding_confidence", 0.0) or 0.0) < grounding_threshold
            ):
                best = observe_candidate or best
                grounding_reason = "grounding_recovery"
                grounding_confidence = 0.0
        if best is not None and best.action_family == "observe":
            perception_summary = structured_perception_bridge(features=features, world=world)
            promoted_family = ""
            promoted_confidence = 0.0
            if isinstance(perception_summary, dict):
                promoted_family = str(perception_summary.get("likely_next_family") or "").strip().lower()
                try:
                    promoted_confidence = max(0.0, min(1.0, float(perception_summary.get("confidence", 0.0) or 0.0)))
                except (TypeError, ValueError):
                    promoted_confidence = 0.0
            if promoted_family == "open_contact" and promoted_confidence >= self._perception_promotion_threshold_for_family("open_contact"):
                best_open_contact = max(
                    (cand for cand in scored if cand.action_family == "open_contact"),
                    default=None,
                    key=lambda cand: cand.score,
                )
                if best_open_contact is not None:
                    best = best_open_contact
        if best is not None and best.action_family == "observe":
            perception_summary = structured_perception_bridge(features=features, world=world)
            promoted_family = ""
            promoted_confidence = 0.0
            if isinstance(perception_summary, dict):
                promoted_family = str(perception_summary.get("likely_next_family") or "").strip().lower()
                try:
                    promoted_confidence = max(0.0, min(1.0, float(perception_summary.get("confidence", 0.0) or 0.0)))
                except (TypeError, ValueError):
                    promoted_confidence = 0.0
            if promoted_family == "open_contact" and promoted_confidence >= self._perception_promotion_threshold_for_family("open_contact"):
                best_open_contact = max(
                    (cand for cand in scored if cand.action_family == "open_contact"),
                    default=None,
                    key=lambda cand: cand.score,
                )
                if best_open_contact is not None and best_open_contact.action_family == "open_contact":
                    best = best_open_contact
            if best.action_family == "observe":
                best_non_observe = max(
                    grounded_non_observe_scored,
                    default=None,
                    key=lambda cand: cand.score,
                )
                if best_non_observe is not None:
                    best = best_non_observe
        if best is not None and best.action_family == "observe":
            perception_summary = structured_perception_bridge(features=features, world=world)
            promoted_family = str((perception_summary or {}).get("likely_next_family") or "").strip().lower()
            try:
                promoted_confidence = max(0.0, min(1.0, float((perception_summary or {}).get("confidence", 0.0) or 0.0)))
            except (TypeError, ValueError):
                promoted_confidence = 0.0
            if promoted_family == "open_contact" and promoted_confidence >= self._perception_promotion_threshold_for_family("open_contact"):
                best_open_contact = max(
                    (cand for cand in scored if cand.action_family == "open_contact"),
                    default=None,
                    key=lambda cand: cand.score,
                )
                if best_open_contact is not None:
                    best = best_open_contact
        # Reject clearly anti-world actions if anything better-ish exists
        if cap_graph_focus is not None and best.action_family != "observe":
            cap = cap_graph_focus.capability_for_action(
                action_family=best.action_family,
                semantic_target=best.semantic_target,
                text=best.text,
            )
            if cap is not None:
                grounded = grounded_action_for_capability(
                    cap,
                    entities=list(world.entities.values()),
                    graph=scene_graph_obj if scene_graph_obj is not None else None,
                )
                best.capability_id = cap.capability_id
                best.capability_type = cap.type
                best.reversible = bool(cap.reversibility)
                if grounded is not None:
                    best.target_entity_id = grounded.entity_id
                    grounding_reason = grounded.reason
                    grounding_confidence = grounded.confidence
        if (
            best.action_family != "observe"
            and best.target_entity_id is None
            and self._requires_entity_grounding(best)
        ):
            raise RuntimeError(
                f"LLM-selected action {best.action_family} could not be grounded; refusing observe fallback"
            )
        best.grounding_reason = grounding_reason
        best.grounding_confidence = grounding_confidence
        self.last_trace.chosen = {
            "action": best.action,
            "target": best.semantic_target,
            "text": best.text,
            "family": best.action_family,
            "capability_id": best.capability_id,
            "capability_type": best.capability_type,
            "target_entity_id": best.target_entity_id,
            "score": round(best.score, 4),
            "rationale": best.rationale,
            "grounding_reason": best.grounding_reason,
        }
        return best

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


def decide(
    goal: Goal,
    world_model: WorldModel,
    execution_state: "ExecutionState",
    *,
    worldview_score: float = 1.0,
    engine: Optional[DecisionEngine] = None,
) -> Optional[Action]:
    eng = engine or get_decision_engine()
    return eng.decide(goal, world_model, execution_state, worldview_score=worldview_score)
