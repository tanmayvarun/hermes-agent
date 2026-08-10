"""Post-action perception quality gate — diagnose incomplete frames and retry before judgment.

Fusion merges sources on ingest; this module decides whether the *post-action*
snapshot is epistemically complete enough to evaluate progress or advance intent.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple


def feature_get(feats: Optional[Dict[str, Any]], key: str, default: Any = None) -> Any:
    """Read feature from StateFeatures.to_dict() — top-level or nested extras."""
    feats = feats or {}
    if key in feats and feats[key] is not None:
        return feats[key]
    extras = feats.get("extras")
    if isinstance(extras, dict) and key in extras and extras[key] is not None:
        return extras[key]
    # Explicit null in extras still counts as "present but null" for settlement checks
    if isinstance(extras, dict) and key in extras:
        return extras[key]
    return default


def feature_has(feats: Optional[Dict[str, Any]], key: str) -> bool:
    feats = feats or {}
    if key in feats:
        return True
    extras = feats.get("extras")
    return isinstance(extras, dict) and key in extras


def _worldview_component(patch: Any, key: str, default: Any = None) -> Any:
    """Read a component from the current worldview score if present."""
    wv = getattr(patch, "worldview_score", None)
    if not isinstance(wv, dict):
        return default
    if key in wv and wv[key] is not None:
        return wv[key]
    components = wv.get("components")
    if isinstance(components, dict) and key in components and components[key] is not None:
        return components[key]
    return default


def _primary_frame_is_usable(*, view: Dict[str, Any], features: Dict[str, Any], patch: Any) -> bool:
    """
    Return True when the post-action frame is rich enough to keep acting even if
    source agreement is imperfect.
    """
    node_count = int(_worldview_component(patch, "node_count", 0) or 0)
    coverage = float(_worldview_component(patch, "coverage", 0.0) or 0.0)
    mean_belief = float(_worldview_component(patch, "mean_belief", 0.0) or 0.0)
    screen = str(view.get("screen") or "").upper()
    screen_bucket = str(features.get("screen_bucket") or features.get("screen_kind") or "").upper()

    actionable_rows = feature_get(features, "search_result_rows") or []
    contact_candidates = feature_get(features, "contact_candidates") or []
    conversation_messages = feature_get(features, "conversation_messages") or []
    visible_contacts = feature_get(features, "visible_contacts") or []

    rich_metrics = node_count >= 40 and coverage >= 0.6 and mean_belief >= 0.65
    rich_surface = screen in {"LIST", "SEARCH", "SEARCH_RESULTS", "DIALOG", "CONVERSATION"} or screen_bucket in {
        "LIST",
        "SEARCH",
        "SEARCH_RESULTS",
        "DIALOG",
        "CONVERSATION",
    }
    evidence_rich = bool(actionable_rows or contact_candidates or conversation_messages or visible_contacts)
    return bool((rich_metrics and rich_surface) or evidence_rich)


@dataclass
class PostPerceiveProfile:
    max_retries: int = 1
    min_extra_settle_s: float = 0.4
    require_resolution_settled: bool = False
    require_query_decidable: bool = False
    retry_on: Tuple[str, ...] = (
        "needs_reobserve",
        "fusion_agreement_low",
        "resolution_unset",
        "result_surface_ambiguous",
    )
    on_exhausted: str = "uncertain"  # uncertain | continue


POST_PERCEIVE_PROFILES: Dict[str, PostPerceiveProfile] = {
    "type_query": PostPerceiveProfile(
        max_retries=2,
        min_extra_settle_s=0.55,
        require_resolution_settled=True,
        require_query_decidable=True,
        retry_on=(
            "needs_reobserve",
            "fusion_agreement_low",
            "resolution_unset",
            "query_hint_ax_mismatch",
            "result_surface_ambiguous",
        ),
        on_exhausted="uncertain",
    ),
    "open_contact": PostPerceiveProfile(
        max_retries=2,
        min_extra_settle_s=0.45,
        require_resolution_settled=False,
        retry_on=("needs_reobserve", "fusion_agreement_low"),
    ),
    "select_content": PostPerceiveProfile(
        max_retries=1,
        min_extra_settle_s=0.35,
        require_resolution_settled=False,
        retry_on=("needs_reobserve", "fusion_agreement_low"),
    ),
    "start_call": PostPerceiveProfile(
        max_retries=1,
        min_extra_settle_s=0.35,
        retry_on=("needs_reobserve", "fusion_agreement_low"),
    ),
    # After reveal_actions the overlay is short-lived. AX settle alone cannot
    # ground menus; keep retries short and let the owed multimodal look finish
    # discovery. affordance_set_empty only blocks once that look has run.
    "reveal_actions": PostPerceiveProfile(
        max_retries=2,
        min_extra_settle_s=0.25,
        require_resolution_settled=False,
        retry_on=(
            "needs_reobserve",
            "fusion_agreement_low",
            "affordance_set_empty",
            "expected_overlay_missing",
        ),
        on_exhausted="uncertain",
    ),
    "default": PostPerceiveProfile(max_retries=1, min_extra_settle_s=0.3),
}


def profile_for(action_family: str) -> PostPerceiveProfile:
    return POST_PERCEIVE_PROFILES.get(action_family or "", POST_PERCEIVE_PROFILES["default"])


@dataclass
class PerceptionAssessment:
    settled: bool = False
    failure_modes: List[str] = field(default_factory=list)
    retry_strategy: str = ""  # reobserve | reobserve_longer | give_up | ""
    evidence: Dict[str, Any] = field(default_factory=dict)
    perception_incomplete: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _grounded_affordance_count(
    *, features: Dict[str, Any], execution_state: Any = None
) -> int:
    if execution_state is not None:
        try:
            from plugin.agent.affordance_frontier import grounded_affordance_set_of

            n = len(grounded_affordance_set_of(execution_state))
            if n:
                return n
        except Exception:
            pass
        frontier = getattr(execution_state, "last_affordance_frontier", None)
        if isinstance(frontier, dict):
            n = 0
            for aff in frontier.get("observed_actions") or []:
                if not isinstance(aff, dict):
                    continue
                if str(aff.get("family") or "") not in {
                    "invoke_affordance",
                    "commit_irreversible",
                }:
                    continue
                if aff.get("actuators"):
                    n += 1
            if n:
                return n
    extras = features.get("extras") if isinstance(features.get("extras"), dict) else {}
    raw = extras.get("grounded_affordance_count")
    try:
        return int(raw or 0)
    except (TypeError, ValueError):
        return 0


def _reveal_handoff_pending(execution_state: Any, features: Dict[str, Any]) -> bool:
    if execution_state is not None:
        handoff = getattr(execution_state, "reveal_handoff", None)
        if isinstance(handoff, dict) and str(handoff.get("surface") or "").strip():
            return True
    extras = features.get("extras") if isinstance(features.get("extras"), dict) else {}
    return bool(extras.get("reveal_handoff"))


def assess_post_action_perception(
    *,
    action_family: str,
    view: Dict[str, Any],
    features: Dict[str, Any],
    patch: Any = None,
    search_query_hint: str = "",
    execution_state: Any = None,
) -> PerceptionAssessment:
    """Diagnose whether post-action perception is complete enough to judge the world."""
    profile = profile_for(action_family)
    modes: List[str] = []
    evidence: Dict[str, Any] = {"action_family": action_family}

    q = str(view.get("search_query") or feature_get(features, "search_query") or "").strip()
    hint = (search_query_hint or "").strip()
    typed_query_landed = bool(q) and (
        bool(feature_get(features, "has_text_query"))
        or bool(feature_get(features, "search_focused"))
        or feature_has(features, "search_query")
    )

    needs_reobs = bool(features.get("needs_reobserve")) or bool(
        feature_get(features, "needs_reobserve")
    )
    if patch is not None:
        needs_reobs = needs_reobs or bool(getattr(patch, "needs_reobserve", False))
        wv = getattr(patch, "worldview_score", None) or {}
        if isinstance(wv, dict):
            needs_reobs = needs_reobs or bool(wv.get("needs_reobserve"))
            agreement = (getattr(patch, "fusion", None) or {}).get("agreement")
            if agreement is None and isinstance(wv.get("components"), dict):
                fusion = (wv.get("components") or {}).get("fusion") or {}
                agreement = fusion.get("agreement")
            evidence["fusion_agreement"] = agreement
            if agreement is not None:
                try:
                    # Typing into a verified editable field is a landing action:
                    # once the query is visibly present, we should not keep
                    # retrying merely because source fusion was imperfect.
                    # reveal_actions must not treat rich CONVERSATION as usable
                    # while a reveal handoff still awaits affordance_set.
                    usable = _primary_frame_is_usable(
                        view=view, features=features, patch=patch
                    )
                    if action_family == "reveal_actions" and _reveal_handoff_pending(
                        execution_state, features
                    ):
                        usable = False
                    if float(agreement) < 0.85 and not (
                        action_family == "type_query" and typed_query_landed
                    ) and not usable:
                        modes.append("fusion_agreement_low")
                except (TypeError, ValueError):
                    pass
    reveal_pending = action_family == "reveal_actions" and _reveal_handoff_pending(
        execution_state, features
    )
    if needs_reobs:
        usable = _primary_frame_is_usable(view=view, features=features, patch=patch)
        if reveal_pending:
            usable = False
        if not usable:
            modes.append("needs_reobserve")
        else:
            evidence["needs_reobserve_overridden"] = True

    # reveal_actions completeness: demand grounded affordance_set only after the
    # owed post-act multimodal look has finished. AX settle right after the
    # probe still has look debt and must not thrash / failed_reveal early.
    if action_family == "reveal_actions":
        grounded_n = _grounded_affordance_count(
            features=features, execution_state=execution_state
        )
        evidence["grounded_affordance_count"] = grounded_n
        screen = str(view.get("screen") or "").upper()
        surface = str(
            feature_get(features, "active_surface")
            or feature_get(features, "surface")
            or ""
        ).strip().lower()
        overlay_evidenced = surface in {
            "context_menu",
            "forward_picker",
            "dialog",
            "action_menu",
        } or screen in {"DIALOG"}
        evidence["overlay_evidenced"] = overlay_evidenced
        look_owed = False
        if execution_state is not None:
            look_owed = bool(
                getattr(execution_state, "post_action_reperceive_pending", False)
            ) or bool(getattr(execution_state, "must_executive_reperceive", False))
        evidence["post_act_look_owed"] = look_owed
        if reveal_pending and not look_owed:
            if grounded_n == 0:
                modes.append("affordance_set_empty")
            if not overlay_evidenced and grounded_n == 0:
                modes.append("expected_overlay_missing")
        elif grounded_n > 0:
            evidence["affordance_set"] = True

    policy = feature_get(features, "resolution_policy")
    conf = feature_get(features, "resolution_confidence")
    evidence["resolution_policy"] = policy
    evidence["resolution_confidence"] = conf

    if profile.require_resolution_settled:
        # Settled means resolve() ran and produced a real policy string
        if policy is None or policy == "" or (isinstance(policy, str) and policy.lower() == "null"):
            modes.append("resolution_unset")
        elif not feature_has(features, "resolution_policy") and not feature_has(features, "resolution_confidence"):
            modes.append("resolution_unset")

    if hint and q and hint.lower() != q.lower() and hint.lower() not in q.lower() and q.lower() not in hint.lower():
        modes.append("query_hint_ax_mismatch")

    query_matches = bool(features.get("query_matches_goal"))
    if profile.require_query_decidable and action_family == "type_query":
        # For generic typed input, the landing signal is the typed text itself.
        # We only hold the branch open when the query never visibly landed.
        if not q and not hint:
            modes.append("result_surface_ambiguous")
        elif q and not typed_query_landed:
            # The query is present in the view but we do not yet have a clean
            # landing signal from the editable target, so ask for one settle pass.
            modes.append("result_surface_ambiguous")

    # Deduplicate modes preserving order
    seen = set()
    uniq_modes = []
    for m in modes:
        if m not in seen:
            seen.add(m)
            uniq_modes.append(m)

    retryable = [m for m in uniq_modes if m in profile.retry_on]
    settled = len(retryable) == 0
    if settled:
        return PerceptionAssessment(
            settled=True,
            failure_modes=uniq_modes,
            retry_strategy="",
            evidence=evidence,
            perception_incomplete=False,
        )

    strategy = "reobserve"
    if "needs_reobserve" in retryable or "fusion_agreement_low" in retryable:
        strategy = "reobserve_longer"
    elif "affordance_set_empty" in retryable or "expected_overlay_missing" in retryable:
        strategy = "reobserve"
    elif "resolution_unset" in retryable or "result_surface_ambiguous" in retryable:
        strategy = "reobserve"
    elif "query_hint_ax_mismatch" in retryable:
        strategy = "reobserve"

    return PerceptionAssessment(
        settled=False,
        failure_modes=uniq_modes,
        retry_strategy=strategy,
        evidence=evidence,
        perception_incomplete=True,
    )


def settled_empty_search_results(
    *,
    view: Dict[str, Any],
    features: Dict[str, Any],
    perception_settled: bool,
) -> Tuple[bool, str]:
    """
    True only when it is safe to conclude the landed query yielded no actionable results.
    Returns (ok_to_treat_as_empty, block_reason).
    """
    if not perception_settled:
        return False, "perception_incomplete"
    q_match = bool(features.get("query_matches_goal"))
    if not q_match:
        return False, "query_not_matched"
    rows = feature_get(features, "search_result_rows") or []
    cands = feature_get(features, "contact_candidates") or []
    if rows or cands:
        return False, "results_present"
    if feature_get(features, "result_surface_visible") and (rows or cands):
        return False, "results_present"
    policy = feature_get(features, "resolution_policy")
    if policy is None or policy == "":
        return False, "perception_incomplete"
    if policy == "auto":
        return False, "auto_resolution"
    conf = feature_get(features, "resolution_confidence")
    if conf is None:
        return False, "perception_incomplete"
    q = str(view.get("search_query") or feature_get(features, "search_query") or "").strip()
    if not q:
        return False, "no_query"
    return True, "settled_empty"
