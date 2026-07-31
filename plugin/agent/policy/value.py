"""Heuristic value / distance-to-goal (no neural nets)."""

from __future__ import annotations

from plugin.agent.action import Action
from plugin.agent.features import StateFeatures
from plugin.agent.goal import Goal

_DEFAULT_PERCEPTION_PROMOTION_THRESHOLD = 0.7


def _screen_kind(features: StateFeatures) -> str:
    kind = str(getattr(features, "screen_kind", "") or "").strip().lower()
    if kind:
        return kind
    return str(features.screen_bucket or "unknown").strip().lower() or "unknown"


def value_of_features(features: StateFeatures) -> float:
    """Scalar progress in [0, 1]."""
    return float(features.goal_progress)


def _perception_promotion_threshold() -> float:
    try:
        from hermes_cli.config import load_config_readonly

        cfg = load_config_readonly() or {}
        agent_cfg = cfg.get("agent") if isinstance(cfg.get("agent"), dict) else {}
        raw = agent_cfg.get("perception_summary_promotion_threshold", _DEFAULT_PERCEPTION_PROMOTION_THRESHOLD)
        return max(0.0, min(1.0, float(raw)))
    except Exception:
        return _DEFAULT_PERCEPTION_PROMOTION_THRESHOLD


def _perception_promotion_threshold_for_family(family: str) -> float:
    base = _perception_promotion_threshold()
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


def _selected_procedure_stage(features: StateFeatures) -> dict:
    stage = features.extras.get("selected_procedure_stage") or {}
    return stage if isinstance(stage, dict) else {}


def _stage_progress_value(stage: dict) -> tuple[float, float, bool, set[str]]:
    stage_progress = 0.0
    try:
        stage_progress = max(0.0, min(1.0, float(stage.get("stage_progress") or 0.0)))
    except (TypeError, ValueError):
        stage_progress = 0.0
    threshold = 0.0
    try:
        threshold = max(0.0, min(1.0, float(stage.get("confidence_threshold") or 0.0)))
    except (TypeError, ValueError):
        threshold = 0.0
    reversible = bool(stage.get("reversible", True))
    preferred = {
        str(x).strip().lower()
        for x in (stage.get("preferred_capabilities") or [])
        if str(x).strip()
    }
    return stage_progress, threshold, reversible, preferred


def _capability_type_for_action(action: Action, goal: Goal) -> str:
    cap_type = str(action.capability_type or "").strip()
    if cap_type:
        return cap_type
    fam = str(action.action_family or "").strip().lower()
    if not fam:
        return ""
    try:
        from plugin.worldmodel.capability import action_family_to_capability_type

        return str(
            action_family_to_capability_type(
                fam,
                semantic_target=action.semantic_target,
                text=action.text,
            )
            or ""
        ).strip()
    except Exception:
        return ""


def _stage_alignment_bias(action: Action, features: StateFeatures, goal: Goal) -> float:
    stage = _selected_procedure_stage(features)
    if not stage or bool(stage.get("complete")):
        return 0.0
    stage_progress, threshold, reversible, preferred = _stage_progress_value(stage)
    fam = str(action.action_family or "").strip().lower()
    cap_type = _capability_type_for_action(action, goal).strip().lower()
    stage_id = str(stage.get("stage_id") or "").strip().lower()
    stage_objective = str(stage.get("stage_objective") or "").strip().lower()

    bias = 0.0
    if preferred:
        if cap_type and cap_type in preferred:
            bias += 0.38 if stage_progress < threshold else 0.24
        elif fam != "observe":
            bias -= 0.18
            if stage_progress < threshold:
                bias -= 0.1

    if not reversible and fam != "observe":
        if stage_progress < threshold:
            bias -= 0.28
        else:
            bias += 0.04 if cap_type and cap_type in preferred else -0.06

    if stage_id and any(term in stage_id for term in ("open", "inspect", "identify", "locate")):
        if fam in {"type_query", "open_search"} and (not cap_type or cap_type not in preferred):
            bias -= 0.08
    if stage_objective and any(term in stage_objective for term in ("message", "link", "conversation", "timeline")):
        if fam == "observe":
            bias += 0.04
        elif fam in {"open_search", "type_query"} and (not cap_type or cap_type not in preferred):
            bias -= 0.05
    return bias


def perception_synthesis_bonus(action: Action, features: StateFeatures, goal: Goal) -> float:
    """Let the perception LLM nudge candidate scoring without hardcoding app logic."""
    synth = features.extras.get("perception_llm") or {}
    if not isinstance(synth, dict):
        return 0.0
    try:
        conf = max(0.0, min(1.0, float(synth.get("confidence", 0.0) or 0.0)))
    except (TypeError, ValueError):
        conf = 0.0
    likely_family = str(synth.get("likely_next_family") or "").strip().lower()
    likely_target = str(synth.get("likely_next_target") or "").strip().lower()
    avoid = {str(x).strip().lower() for x in (synth.get("avoid_families") or []) if str(x).strip()}
    bonus = 0.0
    fam = str(action.action_family or "").strip().lower()
    target = str(action.semantic_target or "").strip().lower()
    def _matches_prompt_target() -> bool:
        if not likely_target or not target:
            return False
        return (
            target == likely_target
            or likely_target in target
            or target in likely_target
        )
    if likely_family and fam == likely_family:
        bonus += 0.35 * max(conf, 0.2)
    if likely_family == "open_contact" and fam == "open_contact" and _matches_prompt_target():
        bonus += 0.35 * max(conf, 0.3)
    if likely_family == "open_contact" and fam in {"type_query", "open_search", "explore_chrome"}:
        bonus -= 0.42 * max(conf, 0.4)
    if likely_target and target and _matches_prompt_target():
        bonus += 0.15 * max(conf, 0.2)
    if fam == "observe":
        if bool(synth.get("needs_followup_observe")):
            bonus += 0.12
        elif likely_family and likely_family != "observe":
            bonus -= 0.08 * max(conf, 0.4)
    if fam in avoid:
        bonus -= 0.22 * max(conf, 0.3)
    if goal.kind == "whatsapp_forward_message" and fam in {"open_contact", "type_query", "explore_chrome"}:
        # Screen synthesis can tilt forward-navigation, but the app overlay still
        # owns the concrete leaf constraints.
        bonus += 0.0
    return bonus + _stage_alignment_bias(action, features, goal)


def predicted_value_delta(action: Action, features: StateFeatures, goal: Goal) -> float:
    """
    Expected improvement if this action succeeds given current world.
    World evidence dominates: actions that ignore already-satisfied preconditions score low.
    """
    fam = action.action_family or _infer_family(action, goal)
    target = (action.semantic_target or "").strip().lower()
    contact = (goal.contact or "").strip().lower()
    target_is_goal = bool(contact) and (target == contact or contact in target)
    stage_bias = _stage_alignment_bias(action, features, goal)
    phase = str(features.extras.get("forward_phase") or "")
    source_rows = list(features.extras.get("source_conversation_rows") or [])
    source_rows_visible = bool(source_rows)
    ft = features.extras.get("forward_task") or {}
    preds = (ft.get("predicates") if isinstance(ft, dict) else None) or {}
    bindings = (ft.get("bindings") if isinstance(ft, dict) else None) or {}
    src_obj = bindings.get("source_object") if isinstance(bindings, dict) else {}
    src_status = str((src_obj or {}).get("status") or "unresolved")
    dest = (goal.target_contact or "").strip().lower()
    picker = bool(preds.get("destination_picker_visible"))
    perception_summary = features.extras.get("perception_summary") or {}
    promoted_family = ""
    promoted_target = ""
    promoted_confidence = 0.0
    if isinstance(perception_summary, dict):
        promoted_family = str(perception_summary.get("likely_next_family") or "").strip().lower()
        promoted_target = str(perception_summary.get("likely_next_target") or "").strip().lower()
        try:
            promoted_confidence = max(0.0, min(1.0, float(perception_summary.get("confidence", 0.0) or 0.0)))
        except (TypeError, ValueError):
            promoted_confidence = 0.0
    perception_promoted = bool(
        promoted_family
        and promoted_family != "observe"
        and promoted_family == fam
        and promoted_confidence >= _perception_promotion_threshold_for_family(fam)
    )

    if perception_promoted:
        if fam == "open_contact":
            if target_is_goal or promoted_target == target or features.query_matches_goal or features.has_named_entity:
                return 0.9 + stage_bias
            if features.extras.get("latent_conversation_open") or features.extras.get("source_conversation_visible"):
                return 0.8 + stage_bias
            return 0.6 + stage_bias
        if fam == "type_query" and promoted_family == "open_contact":
            return (-0.45 if not features.search_focused else -0.2) + stage_bias
        if fam == "type_query":
            if promoted_target and (target == promoted_target or promoted_target in target or target in promoted_target):
                return 0.85 + stage_bias
            return 0.7 + stage_bias
    if fam == "start_call":
        if goal.kind == "whatsapp_voice_call" and target in {"call", "voice call", "voice", "audio call"}:
            return 0.95 + stage_bias
        if features.conversation_open or features.extras.get("latent_conversation_open") or features.extras.get("call_available"):
            return 0.8 + stage_bias
        return 0.55 + stage_bias
    if fam in {"probe_hover", "probe_context_menu", "probe_focus"}:
        branch_affs = {str(a).strip().lower() for a in (features.extras.get("branch_affordances") or [])}
        if goal.kind == "whatsapp_forward_message" and phase in {"FIND_LINK", "OPEN_FORWARD"}:
            if (
                ("reveal_message_actions" in branch_affs or "probe_hover" in branch_affs or "probe_context_menu" in branch_affs)
                and (preds.get("source_object_selected") or src_status in {"provisional", "confirmed"})
                and not bool(preds.get("forward_surface_open"))
                and not bool(preds.get("destination_picker_visible"))
            ):
                if fam == "probe_hover":
                    return 0.68 + stage_bias
                if fam == "probe_context_menu":
                    return 0.64 + stage_bias
                if fam == "probe_focus":
                    return 0.28 + stage_bias
        if features.extras.get("branch_active") or features.extras.get("world_exploration_needed"):
            return 0.16 + stage_bias
        if _screen_kind(features) in {"conversation", "list", "search_results", "detail", "sidebar"}:
            return 0.08 + stage_bias
        return -0.05 + stage_bias
    if fam == "open_search":
        return (-0.25 if promoted_family == "open_contact" else (0.55 if not features.search_focused else -0.35)) + stage_bias
    if fam in {"dismiss", "end_call"}:
        return 0.75 + stage_bias

    # Forward predicate bans first — must beat generic explore_chrome / type scores
    if goal.kind == "whatsapp_forward_message":
        fwd = _forward_value_delta(action, features, goal, fam=fam, target=target)
        if fwd is not None:
            return fwd

    if features.call_ringing:
        return (-0.5 if fam != "observe" else 0.0) + stage_bias

    if fam == "end_call":
        return (0.55 if features.leftover_call else -0.4) + stage_bias

    if fam == "dismiss":
        if target in {"clear menu", "close menu", "menu dismiss"}:
            return 0.7 + stage_bias
        if str(features.extras.get("active_surface") or "").strip().lower() == "menu" and not features.has_dialog:
            return 0.65 + stage_bias
        return (0.5 if features.has_dialog else -0.4) + stage_bias

    if fam == "start_call":
        if features.extras.get("actuation_weak") or features.extras.get("world_exploration_needed"):
            return -0.15 + stage_bias  # prefer observe/explore over blind Call retry
        branch_affs = {str(a).strip().lower() for a in (features.extras.get("branch_affordances") or [])}
        if features.extras.get("branch_active") and (
            "initiate_voice" in branch_affs
            or features.extras.get("active_surface") == "call_picker"
        ):
            return (0.8 if (features.call_available or features.conversation_open or features.extras.get("latent_conversation_open")) else 0.55) + stage_bias
        if features.conversation_open and features.call_available:
            return 0.9 + stage_bias
        if features.conversation_open:
            return 0.55 + stage_bias
        return -0.35 + stage_bias

    if fam == "explore_chrome":
        if features.extras.get("world_exploration_needed") or features.extras.get("actuation_weak"):
            if int(features.extras.get("world_explore_observe_count") or 0) >= 1:
                return 0.7 + stage_bias
            return 0.4 + stage_bias
        if features.conversation_open:
            return 0.15 + stage_bias
        return -0.1 + stage_bias

    if fam == "open_contact":
        if goal.kind == "whatsapp_voice_call" and (
            features.conversation_open
            or features.call_available
            or features.extras.get("latent_conversation_open")
        ):
            if target_is_goal:
                return -0.25 + stage_bias
        if promoted_family == "open_contact" and promoted_confidence >= _perception_promotion_threshold_for_family("open_contact"):
            if target_is_goal or promoted_target == target or features.query_matches_goal or features.has_named_entity:
                return 0.96 + stage_bias
            if features.extras.get("latent_conversation_open") or features.extras.get("source_conversation_visible"):
                return 0.82 + stage_bias
            return 0.7 + stage_bias
        if phase in {"FIND_LINK", "OPEN_FORWARD", "DONE"}:
            return -0.8 + stage_bias
        if phase == "OPEN_SOURCE" and target_is_goal:
            if source_rows_visible or features.extras.get("source_conversation_visible"):
                return (0.95 if features.has_named_entity else 0.85) + stage_bias
            return (0.9 if features.has_named_entity else 0.75) + stage_bias
        if phase == "PICK_DEST" and dest and (target == dest or dest in target):
            return (0.7 if picker else -0.5) + stage_bias
        if features.extras.get("result_surface_visible") and features.query_matches_goal:
            if target_is_goal or str(features.extras.get("active_surface") or "") == "search_results":
                return 0.75 + stage_bias
            return 0.45 + stage_bias
        if promoted_family == "open_contact" and promoted_confidence >= _perception_promotion_threshold_for_family("open_contact"):
            if target_is_goal or promoted_target == target or features.query_matches_goal or features.has_named_entity:
                return 0.9 + stage_bias
            if features.extras.get("latent_conversation_open") or features.extras.get("source_conversation_visible"):
                return 0.8 + stage_bias
            return 0.55 + stage_bias
        if str(features.extras.get("resolution_policy") or "") != "auto":
            return -0.6 + stage_bias
        if not target_is_goal:
            return -0.45 + stage_bias
        if features.query_matches_goal and features.has_named_entity:
            return 0.75 + stage_bias
        if features.has_named_entity:
            return 0.35 + stage_bias
        return -0.3 + stage_bias

    if fam == "type_query":
        if promoted_family == "open_contact" and promoted_confidence >= _perception_promotion_threshold_for_family("open_contact"):
            if target_is_goal or promoted_target == target or features.query_matches_goal:
                return -0.65 + stage_bias
            return (-0.45 if not features.search_focused else -0.2) + stage_bias
        if features.extras.get("search_refinement_pending"):
            active = str(features.extras.get("active_search_hypothesis") or "").strip().lower()
            q = str(features.extras.get("search_query") or "").strip().lower()
            if active and q and active == q:
                return -0.35 + stage_bias
            return 0.95 + stage_bias
        if features.extras.get("result_surface_visible") and features.query_matches_goal:
            return -0.7 + stage_bias
        if (
            features.extras.get("world_exploration_needed")
            and features.conversation_open
            and features.query_matches_goal
        ):
            return -0.45 + stage_bias  # stay in-world; do not revise search/intent
        active = str(features.extras.get("active_search_hypothesis") or "").strip().lower()
        q = str(features.extras.get("search_query") or "").strip().lower()
        if active and q and active == q:
            return -0.55 + stage_bias  # already typed this hypothesis
        if features.query_matches_goal and active and q and active in q:
            return -0.55 + stage_bias
        if features.has_dialog or features.leftover_call:
            return -0.2 + stage_bias
        return (0.55 if not features.has_text_query else 0.35) + stage_bias

    if fam == "open_search":
        if promoted_family == "open_contact" and promoted_confidence >= _perception_promotion_threshold_for_family("open_contact"):
            if features.search_focused:
                return -0.25 + stage_bias
            return -0.4 + stage_bias
        if features.search_focused:
            return -0.4 + stage_bias
        if phase == "OPEN_SOURCE" and (source_rows_visible or features.extras.get("source_conversation_visible")):
            return (0.2 if not features.extras.get("result_surface_visible") else -0.2) + stage_bias
        if (
            features.query_matches_goal
            or features.extras.get("result_surface_visible")
            or features.extras.get("search_refinement_pending")
        ):
            return 0.85 + stage_bias
        if features.conversation_open or features.has_named_entity:
            return 0.7 + stage_bias
        if _screen_kind(features) in {"detail", "list", "search", "input"}:
            return 0.75 + stage_bias
        if str(features.extras.get("wa_screen") or "").lower() in {"list", "search"}:
            return 0.6 + stage_bias
        return 0.35 + stage_bias

    if fam == "observe":
        if goal.kind == "whatsapp_voice_call" and (
            features.conversation_open
            or features.call_available
            or features.extras.get("latent_conversation_open")
        ):
            return -0.35 + stage_bias
        if features.extras.get("result_surface_visible") and features.query_matches_goal:
            return -0.1 + stage_bias
        if features.extras.get("search_refinement_pending"):
            return -0.45 + stage_bias
        branch_affs = {str(a).strip().lower() for a in (features.extras.get("branch_affordances") or [])}
        if features.extras.get("branch_active") and (
            "initiate_voice" in branch_affs
            or features.extras.get("active_surface") == "call_picker"
        ):
            return -0.05 + stage_bias
        if features.extras.get("world_exploration_needed"):
            if int(features.extras.get("world_explore_observe_count") or 0) >= 1:
                return -0.2 + stage_bias
            return 0.65 + stage_bias
        if features.extras.get("actuation_weak"):
            return 0.5 + stage_bias
        if str(features.extras.get("resolution_policy") or "") in {"observe", "ask"}:
            return 0.55 + stage_bias  # refine / surface candidates — do not guess
        if features.needs_reobserve or features.mean_belief < 0.55:
            return 0.6 + stage_bias
        if features.query_matches_goal and not features.has_named_entity:
            return 0.35 + stage_bias
        if features.worldview_score < 0.55:
            return 0.4 + stage_bias
        return 0.05 + stage_bias

    return stage_bias


def _forward_value_delta(
    action: Action,
    features: StateFeatures,
    goal: Goal,
    *,
    fam: str,
    target: str,
) -> float | None:
    """Forward-specific scores/bans. None → fall through to generic family scoring."""
    dest = (goal.target_contact or "").strip().lower()
    query = (goal.link_query or "").strip().lower()
    source = (goal.contact or "").strip().lower()
    open_c = str(features.extras.get("open_conversation") or "").lower()
    phase = str(features.extras.get("forward_phase") or "")
    stage_bias = _stage_alignment_bias(action, features, goal)
    ft = features.extras.get("forward_task") or {}
    preds = (ft.get("predicates") if isinstance(ft, dict) else None) or {}
    bindings = (ft.get("bindings") if isinstance(ft, dict) else None) or {}
    src_obj = bindings.get("source_object") if isinstance(bindings, dict) else {}
    src_status = str((src_obj or {}).get("status") or "unresolved")
    picker = bool(preds.get("destination_picker_visible"))
    on_dest = bool(dest) and dest.split()[0] in open_c if dest else False
    typed = (action.text or "").strip().lower()
    suppress_obs = bool(
        features.extras.get("suppress_observe")
        or (isinstance(ft, dict) and ft.get("suppress_observe"))
    )
    perception_summary = features.extras.get("perception_summary") or {}
    promoted_family = ""
    promoted_target = ""
    promoted_confidence = 0.0
    if isinstance(perception_summary, dict):
        promoted_family = str(perception_summary.get("likely_next_family") or "").strip().lower()
        promoted_target = str(perception_summary.get("likely_next_target") or "").strip().lower()
        try:
            promoted_confidence = max(0.0, min(1.0, float(perception_summary.get("confidence", 0.0) or 0.0)))
        except (TypeError, ValueError):
            promoted_confidence = 0.0
    if promoted_family and promoted_family == fam and promoted_confidence >= _perception_promotion_threshold_for_family(fam):
        if fam == "open_contact":
            if phase == "OPEN_SOURCE" and source and (
                target == source or source in target or promoted_target == target
            ):
                return 0.96 + stage_bias
            if phase == "PICK_DEST" and dest and (target == dest or dest in target or promoted_target == target) and picker:
                return 0.72 + stage_bias
            return 0.8 + stage_bias
        if fam == "type_query" and promoted_family == "open_contact":
            return (0.05 if features.search_focused else -0.25) + stage_bias
        if fam == "type_query":
            return (0.9 if phase == "OPEN_SOURCE" else 0.65) + stage_bias
        if fam == "open_search":
            return 0.6 + stage_bias
        if fam == "start_call":
            return 0.78 + stage_bias
        if fam in {"dismiss", "end_call"}:
            return 0.8 + stage_bias
        if fam == "explore_chrome":
            return 0.5 + stage_bias

    # Hard bans (always apply)
    if phase == "PRECLEAR" and fam not in {"end_call", "dismiss", "observe"}:
        return -0.9 + stage_bias
    if fam == "explore_chrome" and target in {"more", "more options", "menu"}:
        return -0.95 + stage_bias
    if fam == "select_forward_target" and not picker:
        return -0.95 + stage_bias
    if fam == "start_call":
        return -0.95 + stage_bias
    if fam == "observe" and suppress_obs:
        return -0.9 + stage_bias
    if fam == "forward_message" and src_status in {"unresolved", "invalidated"}:
        return -0.9 + stage_bias
    if phase == "PICK_DEST" and not picker and fam in {"type_query", "select_forward_target"}:
        return -0.95 + stage_bias

    if phase in {"OPEN_SOURCE", "FIND_LINK", "OPEN_FORWARD"} and fam == "select_forward_target":
        return -0.95 + stage_bias

    if fam == "type_query":
        # Hard invariant: Search bar is for contacts (source/dest), NEVER for link_query
        if query and typed and (
            typed == query
            or query in typed
            or typed in query
            or (len(query) >= 5 and typed.startswith(query[:5]))
        ):
            return -0.99 + stage_bias
        if phase == "OPEN_SOURCE":
            if source and (typed == source or source in typed):
                return 0.9 + stage_bias
            if dest and (typed == dest or dest in typed):
                return -0.95 + stage_bias
            return (-0.75 if promoted_family == "open_contact" else -0.5) + stage_bias
        if phase in {"FIND_LINK", "OPEN_FORWARD"}:
            return -0.95 + stage_bias  # no typing into Search while resolving message content
        if phase == "PICK_DEST":
            if not picker:
                return -0.95 + stage_bias
            if dest and (typed == dest or dest in typed):
                return 0.9 + stage_bias
            if source and (typed == source or source in typed):
                return -0.5 + stage_bias
            return 0.2 + stage_bias
        if dest and (typed == dest or dest in typed or typed.startswith(dest.split()[0] if dest else "")):
            return -0.95 + stage_bias
        return None

    if fam == "select_content":
        if phase == "OPEN_FORWARD" and bool(preds.get("source_object_selected")):
            return -0.99 + stage_bias
        return (0.85 if phase == "FIND_LINK" else 0.4) + stage_bias
    if fam == "scroll_content":
        frontier = features.extras.get("capability_frontier") or []
        if any(str(node.get("type") or "").lower() == "scrollcontent" for node in frontier if isinstance(node, dict)):
            if phase in {"FIND_LINK", "OPEN_FORWARD", "OPEN_SOURCE"}:
                return (0.92 if src_status in {"unresolved", "ambiguous", "provisional"} else 0.7) + stage_bias
        if phase in {"FIND_LINK", "OPEN_FORWARD"}:
            if src_status in {"unresolved", "ambiguous", "provisional"}:
                return 0.78 + stage_bias
            return 0.45 + stage_bias
        return 0.15 + stage_bias
    if fam == "explore_chrome" and target == "go to most recent message":
        if phase in {"FIND_LINK", "OPEN_FORWARD"}:
            return 0.82 + stage_bias
        return 0.25 + stage_bias
    if fam == "forward_message":
        if phase == "FIND_LINK":
            return -0.3 + stage_bias
        return (0.98 if phase == "OPEN_FORWARD" else (0.62 if phase == "PICK_DEST" else -0.4)) + stage_bias
    if fam == "select_forward_target":
        return (0.95 if phase == "PICK_DEST" and picker and not on_dest else -0.5) + stage_bias
    if fam == "open_contact":
        if phase == "OPEN_SOURCE" and source and (target == source or source in target):
            return 0.8 + stage_bias
        if dest and target == dest and phase == "PICK_DEST" and picker:
            return 0.7 + stage_bias
        if phase == "PICK_DEST" and source and target == source:
            return -0.5 + stage_bias
        if phase in {"FIND_LINK", "OPEN_FORWARD"}:
            return -0.95 + stage_bias
        return None
    if fam == "end_call":
        return (0.9 if phase == "PRECLEAR" or features.leftover_call else -0.4) + stage_bias
    if fam == "explore_chrome":
        return -0.5 + stage_bias  # prefer object-bound actions during forward

    return None


def _infer_family(action: Action, goal: Goal) -> str:
    act = action.action.lower()
    sem = (action.semantic_target or "").lower()
    if act == "observe":
        return "observe"
    if act == "dismiss":
        return "dismiss"
    if act == "type":
        return "type_query"
    if act == "click":
        if "end" in sem:
            return "end_call"
        if sem in {"call", "voice call", "audio call"}:
            return "start_call"
        if sem == "search":
            return "open_search"
        if goal.contact and goal.contact.lower() in sem:
            return "open_contact"
        return "open_contact"
    return "observe"
