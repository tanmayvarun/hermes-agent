"""Enumerate legal actions from *current* world affordances — no scripted retry plan.

Invariant (intent vs world uncertainty):
  Action failure → re-observe + rebuild candidates from the new world.
  Do NOT revise the user's reference/intent unless observations contradict it.
  This is online search over observed states, not "retry Call until verifier passes."
"""

from __future__ import annotations

from typing import List

from plugin.agent.action import Action
from plugin.agent.apps.base import AppOverlay
from plugin.agent.features import StateFeatures
from plugin.agent.goal import Goal
from plugin.agent.apps.whatsapp_targets import exact_label_visible
from plugin.agent.apps.whatsapp_targets import in_composer_band
from plugin.worldmodel.entities.normalize import _clean_label
from plugin.worldmodel.capability import CapabilityGraph
from plugin.worldmodel.model import WorldModel

_DISMISS_LABELS = ("Not Now", "Later", "Cancel", "OK", "Close", "Clear Menu", "Don't Allow", "Allow")
_END_LABELS = ("End Call", "End call", "Decline")
_VOICE_AFFORDANCES = (
    "Call",
    "Voice",
    "Voice call",
    "Voice Call",
    "Audio call",
    "Audio Call",
)
_EXPLORE_CHROME = (
    "Menu",
    "More",
    "More options",
    "Chat info",
    "Info",
    "Open call dropdown menu",
)

_VOICE_NEGATIVE_LABELS = {
    "end call",
    "end call button",
    "decline",
    "hang up",
}


def _screen_kind(features: StateFeatures) -> str:
    kind = str(getattr(features, "screen_kind", "") or "").strip().lower()
    if kind:
        return kind
    return str(features.screen_bucket or "unknown").strip().lower() or "unknown"


def _preferred_scroll_direction(goal: Goal, features: StateFeatures) -> str:
    """Choose scroll direction from the local search surface, not from a fixed default."""
    if goal.kind == "whatsapp_forward_message":
        phase = str(features.extras.get("forward_phase") or "")
        if phase in {"FIND_LINK", "OPEN_SOURCE"}:
            return "up"
    return "down"


def _preferred_scroll_amount(goal: Goal, features: StateFeatures) -> int:
    """Use a larger leaf scroll when searching through chat history for a source object."""
    if goal.kind == "whatsapp_forward_message":
        phase = str(features.extras.get("forward_phase") or "")
        if phase in {"FIND_LINK", "OPEN_SOURCE"}:
            return 6
    return 3


def _visible_search_result_rows(features: StateFeatures) -> List[str]:
    rows = features.extras.get("search_result_rows") or []
    out: List[str] = []
    seen = set()
    for row in rows:
        label = _clean_label(str(row))
        low = label.lower()
        if not label or low in seen:
            continue
        seen.add(low)
        out.append(label)
    return out


def _latent_probe_candidates(goal: Goal, world: WorldModel, features: StateFeatures) -> List[Action]:
    cap_raw = features.extras.get("capability_graph") or getattr(world, "last_capability_graph", {}) or {}
    try:
        cap_graph = CapabilityGraph.from_dict(cap_raw) if isinstance(cap_raw, dict) else CapabilityGraph()
    except Exception:
        cap_graph = CapabilityGraph()

    surface = str(features.extras.get("active_surface") or "").strip().lower()
    branch_active = bool(features.extras.get("branch_active")) or bool(features.extras.get("world_exploration_needed"))
    if not branch_active and surface not in {"conversation", "list", "search_results", "detail", "sidebar"}:
        return []

    probe_nodes = [
        cap
        for cap in cap_graph.nodes.values()
        if cap.type in {"RevealHiddenActions", "ProbeSurface"}
        and (not cap.visible or bool(getattr(cap, "evidence", {}).get("latent")))
    ]
    if not probe_nodes:
        probe_nodes = [
            cap_graph.nodes[node.capability_id]
            for node in cap_graph.frontier
            if node.capability_id in cap_graph.nodes and node.type in {"RevealHiddenActions", "ProbeSurface"}
        ]

    by_id = {e.id: e for e in world.entities.values() if e.visible}
    probe_actions: List[Action] = []
    seen_targets = set()
    for cap in probe_nodes:
        ent_id = None
        if getattr(cap, "provider_entities", None):
            for candidate_id in cap.provider_entities:
                if candidate_id in by_id:
                    ent_id = candidate_id
                    break
        entity = by_id.get(ent_id) if ent_id is not None else None
        if entity is None:
            continue
        target = _clean_label(entity.label or entity.semantic_role or "").strip()
        key = (cap.type, target.lower())
        if key in seen_targets:
            continue
        seen_targets.add(key)
        if cap.type == "RevealHiddenActions":
            probe_actions.append(
                Action(
                    action="Hover",
                    semantic_target=target,
                    rationale=f"probe hover to reveal latent actions on {target}",
                    expected_predicate="LatentActionsRevealed",
                    action_family="probe_hover",
                    score=0.18,
                    prior_score=0.05,
                    value_delta=0.08,
                    evidence_score=0.12,
                    reversible=True,
                    target_entity_id=entity.id,
                    capability_type="RevealHiddenActions",
                    frontier_label="reveal hidden actions",
                    frontier_score=0.18,
                )
            )
            probe_actions.append(
                Action(
                    action="ContextClick",
                    semantic_target=target,
                    rationale=f"open context menu to reveal latent actions on {target}",
                    expected_predicate="LatentActionsRevealed",
                    action_family="probe_context_menu",
                    score=0.16,
                    prior_score=0.04,
                    value_delta=0.07,
                    evidence_score=0.1,
                    reversible=True,
                    target_entity_id=entity.id,
                    capability_type="RevealHiddenActions",
                    frontier_label="reveal hidden actions",
                    frontier_score=0.16,
                )
            )
        elif cap.type == "ProbeSurface":
            probe_actions.append(
                Action(
                    action="Hover",
                    semantic_target=target,
                    rationale=f"probe latent surface affordances on {target}",
                    expected_predicate="SurfaceRevealed",
                    action_family="probe_focus",
                    score=0.14,
                    prior_score=0.04,
                    value_delta=0.05,
                    evidence_score=0.08,
                    reversible=True,
                    target_entity_id=entity.id,
                    capability_type="ProbeSurface",
                    frontier_label="probe surface",
                    frontier_score=0.14,
                )
            )
    return probe_actions


def enumerate_candidates(
    goal: Goal,
    world: WorldModel,
    features: StateFeatures,
    overlay: AppOverlay,
) -> List[Action]:
    contact = goal.contact or ""
    screen_kind = _screen_kind(features)
    in_conversation_surface = goal.kind == "whatsapp_voice_call" and screen_kind == "conversation"
    out: List[Action] = []
    world_explore = bool(features.extras.get("world_exploration_needed"))
    actuation_weak = bool(features.extras.get("actuation_weak"))

    out.append(
        Action(
            action="Observe",
            rationale=(
                "re-perceive current world (actuation/world uncertainty)"
                if (world_explore or actuation_weak)
                else "wait / re-perceive"
            ),
            expected_predicate="",
            action_family="observe",
        )
    )
    # Identical-Observe suppression (forward binding repair)
    ft0 = features.extras.get("forward_task") or {}
    if isinstance(ft0, dict) and ft0.get("suppress_observe"):
        out = [a for a in out if a.action_family != "observe"]
        features.extras["binding_repair"] = True
        features.extras["world_exploration_needed"] = True


    dialogs = list(features.extras.get("dialogs") or [])
    storage_pressure = bool(features.extras.get("storage_pressure") or features.extras.get("system_warnings"))
    from plugin.agent.apps.whatsapp_targets import exact_label_visible

    # Only emit dismiss for labels that are actually visible (no Always-on Later spam)
    dismiss_pool = list(dialogs)
    for lab in _DISMISS_LABELS:
        if exact_label_visible(world, lab):
            dismiss_pool.append(lab)
    seen_dismiss = set()
    emitted_dismiss = False
    for label in dismiss_pool:
        if storage_pressure:
            break
        if not label:
            continue
        low = str(label).lower()
        if low in seen_dismiss:
            continue
        seen_dismiss.add(low)
        emitted_dismiss = True
        out.append(
            Action(
                action="Click",
                semantic_target=str(label),
                rationale=f"dismiss dialog via {label}",
                expected_predicate="NoUnexpectedDialog",
                action_family="dismiss",
            )
        )
    if not emitted_dismiss and bool(features.has_dialog) and not storage_pressure:
        perception_summary = features.extras.get("perception_summary") or {}
        target = str(perception_summary.get("likely_next_target") or "").strip()
        if not target:
            target = "dialog dismiss"
        out.append(
            Action(
                action="Click",
                semantic_target=target,
                rationale="dismiss dialog inferred from perception summary",
                expected_predicate="NoUnexpectedDialog",
                action_family="dismiss",
            )
        )
    active_surface = str(features.extras.get("active_surface") or "").strip().lower()
    if active_surface == "menu" and not bool(features.has_dialog):
        menu_targets = ("Clear Menu", "Close", "Dismiss")
        target = None
        for lab in menu_targets:
            if exact_label_visible(world, lab):
                target = lab
                break
        if target is None:
            target = "Dismiss"
        out.append(
            Action(
                action="Dismiss",
                semantic_target=target,
                rationale="escape stale menu overlay",
                expected_predicate="NoUnexpectedDialog",
                action_family="dismiss",
            )
        )

    from plugin.agent.apps.whatsapp_targets import exact_label_visible
    from plugin.worldmodel.pragmatic_role import (
        UiPragmaticRole,
        get_pragmatic_role,
        infer_pragmatic_role_stage2,
    )

    if features.leftover_call:
        emitted = False
        for lab in _END_LABELS:
            if not exact_label_visible(world, lab):
                continue
            for e in world.entities.values():
                if not e.visible:
                    continue
                if get_pragmatic_role(e) == UiPragmaticRole.UNKNOWN:
                    infer_pragmatic_role_stage2(e)
                if (
                    _clean_label(e.label or "").lower() == lab.lower()
                    and get_pragmatic_role(e) == UiPragmaticRole.CTA
                ):
                    out.append(
                        Action(
                            action="Click",
                            semantic_target=lab,
                            rationale="end leftover call — CTA visible in world",
                            expected_predicate="CallStateIs(idle)",
                            action_family="end_call",
                        )
                    )
                    emitted = True
                    break
        if not emitted:
            out.append(
                Action(
                    action="Observe",
                    rationale="leftover_call without CTA End Call — re-perceive",
                    expected_predicate="",
                    action_family="observe",
                )
            )
    elif (
        (exact_label_visible(world, "End Call") or exact_label_visible(world, "End call"))
        and (bool(features.extras.get("call_ringing")) or bool(features.leftover_call))
    ):
        out.append(
            Action(
                action="Click",
                semantic_target="End Call",
                rationale="end call control visible in world",
                expected_predicate="CallStateIs(idle)",
                action_family="end_call",
            )
        )

    # Type: keep intent fixed; skip escaping to re-search when exploring open-chat call chrome
    is_forward = goal.kind == "whatsapp_forward_message"
    forward_phase = str(features.extras.get("forward_phase") or "")
    allow_source_search = (not is_forward) or forward_phase == "OPEN_SOURCE"
    if is_forward and forward_phase in {"PRECLEAR", "FIND_LINK", "OPEN_FORWARD", "PICK_DEST", "DONE"}:
        allow_source_search = False
    voice_call_surface_ready = goal.kind == "whatsapp_voice_call" and (
        features.conversation_open
        or bool(features.extras.get("voice_call_available"))
        or bool(features.extras.get("call_available"))
        or bool(features.extras.get("call_ringing"))
    )
    search_ready = False

    if contact and allow_source_search and not voice_call_surface_ready and not (
        features.conversation_open
        and (world_explore or actuation_weak)
        and features.query_matches_goal
    ):
        search_ready = bool(
            (not is_forward)
            or bool(features.extras.get("search_visible"))
            or features.search_focused
            or features.extras.get("result_surface_visible")
            or _screen_kind(features) in {"list", "search", "detail", "input"}
        )
        hyp_i = int(features.extras.get("search_hypothesis_index") or 0)
        search_text = str(features.extras.get("active_search_hypothesis") or "").strip()
        if not search_ready:
            search_text = ""
        elif not search_text:
            search_text = goal.search_text(hyp_i) if hasattr(goal, "search_text") else contact
        if search_text:
            out.append(
                Action(
                    action="Type",
                    semantic_target="Search",
                    text=search_text,
                    rationale=f"type search hypothesis[{hyp_i}]={search_text!r} (raw={contact!r})",
                    expected_predicate=f"SearchQueryEquals({search_text})",
                    action_family="type_query",
                )
            )

    source_rows = [str(row) for row in (features.extras.get("source_conversation_rows") or []) if str(row).strip()]
    source_rows_visible = bool(source_rows)
    search_rows = _visible_search_result_rows(features)
    if allow_source_search and contact and source_rows and not in_conversation_surface:
        if voice_call_surface_ready:
            source_rows = []
        seen_rows = set()
        for row in source_rows:
            row_l = row.lower()
            if row_l in seen_rows:
                continue
            seen_rows.add(row_l)
            out.append(
                Action(
                    action="Click",
                    semantic_target=row,
                    rationale=f"open visible source conversation row: {row}",
                    expected_predicate=f"ConversationOpen({contact})",
                    action_family="open_contact",
                )
            )

    if (
        allow_source_search
        and search_ready
        and _entity_mentions(world, "Search")
        and not (
            is_forward
            and forward_phase == "OPEN_SOURCE"
            and bool(features.extras.get("result_surface_visible"))
        )
    ):
        out.append(
            Action(
                action="Click",
                semantic_target="Search",
                rationale="focus search chrome",
                expected_predicate="SearchInputFocused",
                action_family="open_search",
            )
        )

    policy = str(features.extras.get("resolution_policy") or "")
    if (
        allow_source_search
        and contact
        and policy == "auto"
        and features.extras.get("resolved_contact")
        and (source_rows_visible or bool(search_rows) or bool(features.extras.get("result_surface_visible")))
        and not voice_call_surface_ready
        and not in_conversation_surface
    ):
        resolved = features.extras.get("resolved_contact") or contact
        conf = features.extras.get("resolution_confidence")
        out.append(
            Action(
                action="Click",
                semantic_target=str(resolved),
                rationale=f"open contact {resolved} (confidence={conf})",
                expected_predicate=f"ConversationOpen({contact})",
                action_family="open_contact",
            )
        )
    elif allow_source_search and contact and policy in {"observe", "ask"} and not voice_call_surface_ready and not in_conversation_surface:
        cands = features.extras.get("contact_candidates") or []
        names = ", ".join(str(c.get("name")) for c in cands[:4])
        preferred = features.extras.get("preferred_contact")
        out.append(
            Action(
                action="Observe",
                rationale=(
                    f"low confidence ({features.extras.get('resolution_confidence')}) "
                    f"preferred={preferred!r} among: {names}"
                ),
                expected_predicate=f"ContactResultVisible({contact})",
                action_family="observe",
            )
        )

    if allow_source_search and contact and search_rows and not voice_call_surface_ready and not in_conversation_surface:
        for row in search_rows:
            out.append(
                Action(
                    action="Click",
                    semantic_target=row,
                    rationale=f"select visible search result row: {row}",
                    expected_predicate=f"ConversationOpen({contact})",
                    action_family="open_contact",
                )
            )

    # Goal constraint voice_communication → enumerate visible affordances (search, not retry)
    if goal.kind == "whatsapp_voice_call":
        # Prefer opening the call dropdown before bare Voice
        for lab in (
            "Open call dropdown menu",
            "Open call dropdown menu with Now…",
        ):
            if _entity_mentions(world, lab) or _entity_mentions_prefix(world, "open call dropdown"):
                # Prefer any visible dropdown control
                for e in world.entities.values():
                    if not e.visible:
                        continue
                    blob = f"{e.label} {e.semantic_role}".lower()
                    if "open call dropdown" in blob:
                        out.append(
                            Action(
                                action="Click",
                                semantic_target=_clean_label(e.label or e.semantic_role or lab),
                                rationale=f"open call dropdown: {e.label}",
                                expected_predicate="",
                                action_family="explore_chrome",
                            )
                        )
                        break
                break

        for lab in _VOICE_AFFORDANCES:
            if _entity_mentions_positive_voice_affordance(world, lab) or (
                lab in {"Call", "Voice", "Voice call", "Voice Call"}
                and (
                    features.call_available
                    or features.conversation_open
                    or features.extras.get("latent_conversation_open")
                    or features.extras.get("branch_active")
                )
            ):
                out.append(
                    Action(
                        action="Click",
                        semantic_target=lab if lab != "Call" else "Call",
                        rationale=f"voice affordance from world: {lab}",
                        expected_predicate="",
                        action_family="start_call",
                    )
                )
        if world_explore or actuation_weak or features.conversation_open:
            for lab in _EXPLORE_CHROME:
                if _entity_mentions(world, lab) or _entity_mentions_prefix(world, lab.lower()):
                    out.append(
                        Action(
                            action="Click",
                            semantic_target=lab,
                            rationale=f"explore chrome for voice path: {lab}",
                            expected_predicate="",
                            action_family="explore_chrome",
                        )
                    )
            for e in world.entities.values():
                if not e.visible:
                    continue
                lab = _clean_label(e.label or e.semantic_role or "")
                low = lab.lower()
                if "call" in low and ("menu" in low or "dropdown" in low or "more" in low):
                    out.append(
                        Action(
                            action="Click",
                            semantic_target=lab,
                            rationale=f"explore call menu affordance: {lab}",
                            expected_predicate="",
                            action_family="explore_chrome",
                        )
                    )

    if goal.kind == "whatsapp_forward_message":
        out.extend(_forward_candidates(goal, world, features))
        out = _scrub_forward_search_types(goal, features, out)

    if world_explore or actuation_weak or bool(features.extras.get("branch_active")):
        out.extend(_latent_probe_candidates(goal, world, features))

    seen = set()
    uniq: List[Action] = []
    for a in out:
        key = (a.action.lower(), (a.semantic_target or "").lower(), a.text or "", a.action_family)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(a)
    return uniq


def _scrub_forward_search_types(
    goal: Goal, features: StateFeatures, actions: List[Action]
) -> List[Action]:
    """Search bar is for contacts only — never type link_query into it."""
    query = (goal.link_query or "").strip().lower()
    source = (goal.contact or "").strip().lower()
    dest = (goal.target_contact or "").strip().lower()
    phase = str(features.extras.get("forward_phase") or "")
    cleaned: List[Action] = []
    for a in actions:
        if a.action_family != "type_query" and a.action.lower() != "type":
            cleaned.append(a)
            continue
        typed = (a.text or "").strip().lower()
        if not typed:
            cleaned.append(a)
            continue
        # Ban content/link strings in Search
        if query and (
            typed == query
            or query in typed
            or typed in query
            or (len(query) >= 5 and typed.startswith(query[:5]))
        ):
            continue
        # Phase-legal contact strings only
        if phase == "OPEN_SOURCE":
            if source and (typed == source or source in typed or typed in source):
                cleaned.append(a)
            continue
        if phase == "PICK_DEST":
            if dest and (typed == dest or dest in typed or typed in dest):
                cleaned.append(a)
            continue
        # FIND_LINK / OPEN_FORWARD / PRECLEAR / DONE: no Type into Search
        continue
    return cleaned


_FORWARD_CHROME = (
    "Forward",
    "Forward message",
    "Forward messages",
    "Send to",
)


def _forward_candidates(goal: Goal, world: WorldModel, features: StateFeatures) -> List[Action]:
    """Binding-gated find→forward→select-destination actions."""
    out: List[Action] = []
    source = (goal.contact or "").strip()
    dest = (goal.target_contact or "").strip()
    query = (goal.link_query or "").strip()
    phase = str(features.extras.get("forward_phase") or "OPEN_SOURCE")
    open_c = str(features.extras.get("open_conversation") or "").lower()
    ft = features.extras.get("forward_task") or {}
    preds = (ft.get("predicates") if isinstance(ft, dict) else None) or {}
    bindings = (ft.get("bindings") if isinstance(ft, dict) else None) or {}
    src_obj = bindings.get("source_object") if isinstance(bindings, dict) else {}
    src_status = str((src_obj or {}).get("status") or "unresolved")
    src_eid = (src_obj or {}).get("resolved_entity_id")
    picker = bool(preds.get("destination_picker_visible"))
    obj_selected = bool(preds.get("source_object_selected") or src_status in {"provisional", "confirmed"})
    world_id = str(getattr(world, "world_id", "") or features.extras.get("world_id") or "w0")

    on_source = bool(source) and (
        source.lower() in open_c
        or any(tok in open_c for tok in source.lower().split() if len(tok) > 2)
    )
    on_dest = bool(dest) and (
        dest.lower() in open_c
        or any(tok in open_c for tok in dest.lower().split() if len(tok) > 2)
    )
    conversation_resolved = bool(
        features.conversation_open
        or features.extras.get("latent_conversation_open")
        or features.extras.get("source_conversation_visible")
        or features.extras.get("source_conversation_open")
        or str(features.extras.get("open_conversation") or "").strip()
    )

    if phase == "PRECLEAR":
        return out

    if phase == "OPEN_SOURCE":
        if source and not on_source:
            search_ready = bool(
                features.search_focused
                or features.extras.get("result_surface_visible")
                or str(features.extras.get("wa_screen") or "").upper() in {"LIST", "CONVERSATION", "SEARCH", "SEARCH_RESULTS"}
            )
            if search_ready:
                out.append(
                    Action(
                        action="Type",
                        semantic_target="Search",
                        text=source,
                        rationale=f"search source chat {source}",
                        expected_predicate=f"SearchQueryEquals({source})",
                        action_family="type_query",
                    )
                )
            if (
                search_ready
                and _entity_mentions(world, "Search")
                and not bool(features.search_focused)
                and not bool(features.extras.get("search_query"))
                and not bool(features.extras.get("result_surface_visible"))
                and not bool(features.extras.get("source_conversation_rows"))
            ):
                out.append(
                    Action(
                        action="Click",
                        semantic_target="Search",
                        rationale="focus search for source",
                        expected_predicate="SearchInputFocused",
                        action_family="open_search",
                    )
                )
        return out

    if phase in {"FIND_LINK", "OPEN_FORWARD"}:
        # Object resolution frontier — bind by entity_id; never naked More
        if query and src_status in {"unresolved", "ambiguous", "provisional", "confirmed"}:
            from plugin.agent.apps.whatsapp_targets import in_sidebar_band
            from plugin.agent.task_binding import find_query_entities

            ents = [e for e in world.entities.values() if e.visible]
            allowed_types = []
            if isinstance(src_obj, dict):
                allowed_types = [str(t) for t in (src_obj.get("types") or []) if str(t)]
            hits = find_query_entities(
                ents,
                query,
                in_sidebar_fn=in_sidebar_band,
                allowed_entity_types=allowed_types,
            )
            # Prefer resolved id first
            ordered = []
            if src_eid is not None:
                for e in hits:
                    if e.id == int(src_eid):
                        ordered.append(e)
                        break
            for e in hits:
                if e not in ordered:
                    ordered.append(e)
            if phase == "OPEN_FORWARD" and bool(preds.get("source_object_selected")) and src_eid is not None:
                ordered = [e for e in ordered if e.id != int(src_eid)]
            for e in ordered[:4]:
                if e.entity_type in {"window", "group", "scroll"}:
                    continue
                lab = _clean_label(e.label or e.semantic_role or "") or query
                out.append(
                    Action(
                        action="Click",
                        semantic_target=lab,
                        rationale=f"select source object matching {query!r} entity_id={e.id}",
                        expected_predicate="SourceObjectSelected",
                        action_family="select_content",
                        target_entity_id=int(e.id),
                        observed_in_world=world_id,
                        grounding_reason="timeline_query_match",
                        grounding_confidence=0.8 if src_status != "ambiguous" else 0.5,
                    )
                )
            # NEVER Type(link_query) into Search — that field is global chat find
            # ("Search or start new chat"). Content binding is timeline select only.

        conv_rel = features.extras.get("conversation_message_relevance") or {}
        likely_ids = []
        if isinstance(conv_rel, dict):
            likely_ids = [int(x) for x in (conv_rel.get("likely_source_message_ids") or []) if str(x).strip()]
        if likely_ids:
            for eid in likely_ids[:4]:
                ent = world.entities.get(int(eid))
                if ent is None or not ent.visible:
                    continue
                lab = _clean_label(ent.label or ent.semantic_role or "") or query or "conversation message"
                out.append(
                    Action(
                        action="Click",
                        semantic_target=lab,
                        rationale=f"LLM-ranked source message candidate entity_id={eid}",
                        expected_predicate="SourceObjectVisible",
                        action_family="select_content",
                        target_entity_id=int(eid),
                        observed_in_world=world_id,
                        grounding_reason="llm_message_relevance",
                        grounding_confidence=max(
                            0.72,
                            float(conv_rel.get("confidence", 0.0) or 0.0),
                        ),
                    )
                )

        if conversation_resolved and src_status in {"unresolved", "ambiguous", "provisional"}:
            out.append(
                Action(
                    action="Scroll",
                    semantic_target="Conversation timeline",
                    rationale="explore conversation timeline for unresolved source object",
                    expected_predicate="",
                    action_family="scroll_content",
                    scroll_direction=_preferred_scroll_direction(goal, features),
                    scroll_amount=_preferred_scroll_amount(goal, features),
                )
            )
        if exact_label_visible(world, "Go to most recent message"):
            out.append(
                Action(
                    action="Click",
                    semantic_target="Go to most recent message",
                    rationale="jump to the latest visible conversation state",
                    expected_predicate="",
                    action_family="explore_chrome",
                )
            )

        # Forward chrome only when object is grounded (provisional+) — never unscoped More
        if src_status in {"provisional", "confirmed"} or obj_selected:
            for lab in _FORWARD_CHROME:
                if _entity_mentions(world, lab) or _entity_mentions_prefix(world, lab.lower()):
                    tid = _matching_entity_id(world, lab)
                    out.append(
                        Action(
                            action="Click",
                            semantic_target=lab,
                            rationale=f"forward chrome on bound object: {lab}",
                            expected_predicate="DestinationPickerVisible",
                            action_family="forward_message",
                            target_entity_id=tid if tid is not None else (int(src_eid) if src_eid is not None else None),
                            observed_in_world=world_id,
                            grounding_reason="acts_on_forward_control" if tid is not None else "acts_on_source_object",
                            grounding_confidence=0.9 if tid is not None else 0.7,
                        )
                    )
            # If the forward chrome is still hidden, the generic next move is
            # to reveal message actions on the already-selected source row.
            # This stays app-agnostic: any timeline row that hides actions on
            # hover/context-menu should surface a grounded probe before we
            # fall back to another observe cycle.
            if src_eid is not None and not any(
                _entity_mentions(world, lab) or _entity_mentions_prefix(world, lab.lower())
                for lab in _FORWARD_CHROME
            ):
                src_ent = world.entities.get(int(src_eid))
                if src_ent is not None and src_ent.visible:
                    lab = _clean_label(src_ent.label or src_ent.semantic_role or "") or query or source or "selected message"
                    out.append(
                        Action(
                            action="Hover",
                            semantic_target=lab,
                            rationale=f"reveal hidden message actions on selected source object: {lab}",
                            expected_predicate="LatentActionsRevealed",
                            action_family="probe_hover",
                            target_entity_id=int(src_ent.id),
                            observed_in_world=world_id,
                            grounding_reason="selected_source_object",
                            grounding_confidence=0.85,
                            capability_type="RevealHiddenActions",
                            frontier_label="reveal hidden message actions",
                        )
                    )
                    out.append(
                        Action(
                            action="ContextClick",
                            semantic_target=lab,
                            rationale=f"open context menu to reveal hidden message actions on {lab}",
                            expected_predicate="LatentActionsRevealed",
                            action_family="probe_context_menu",
                            target_entity_id=int(src_ent.id),
                            observed_in_world=world_id,
                            grounding_reason="selected_source_object",
                            grounding_confidence=0.82,
                            capability_type="RevealHiddenActions",
                            frontier_label="reveal hidden message actions",
                        )
                    )
        # Explicitly do NOT emit More / Menu / More options (header More is unscoped)
        return out

    if phase == "PICK_DEST":
        # Illegal without picker evidence — candidates still gated; value bans reinforce
        if not picker and not (
            bool(preds.get("forward_surface_open")) and obj_selected
        ):
            return out
        if dest and not on_dest:
            if _entity_mentions(world, dest):
                out.append(
                    Action(
                        action="Click",
                        semantic_target=dest,
                        rationale=f"select forward destination {dest}",
                        expected_predicate=f"ConversationOpen({dest})",
                        action_family="select_forward_target",
                    )
                )
            out.append(
                Action(
                    action="Type",
                    semantic_target="Search",
                    text=dest,
                    rationale=f"search forward destination {dest}",
                    expected_predicate=f"SearchQueryEquals({dest})",
                    action_family="type_query",
                )
            )
        return out

    return out


def _entity_mentions(world: WorldModel, needle: str) -> bool:
    n = _clean_label(needle).lower()
    if not n:
        return False
    for e in world.entities.values():
        if not e.visible:
            continue
        blob = f"{e.label} {e.semantic_role} {e.attributes.get('description', '')}".lower()
        if n in blob:
            return True
    return False


def _entity_mentions_positive_voice_affordance(world: WorldModel, needle: str) -> bool:
    n = _clean_label(needle).lower()
    if not n:
        return False
    for e in world.entities.values():
        if not e.visible:
            continue
        label = _clean_label(e.label or "").lower()
        desc = _clean_label(e.attributes.get("description", "")).lower()
        blob = f"{label} {e.semantic_role} {desc}"
        if n not in blob:
            continue
        if label in _VOICE_NEGATIVE_LABELS:
            continue
        if label.startswith("end call") or "decline" in label or "hang up" in label:
            continue
        return True
    return False


def _entity_mentions_prefix(world: WorldModel, needle: str) -> bool:
    n = (needle or "").lower()
    if len(n) < 3:
        return False
    for e in world.entities.values():
        if not e.visible:
            continue
        lab = _clean_label(e.label or "").lower()
        if lab.startswith(n) or n in lab:
            return True
    return False


def _matching_entity_id(world: WorldModel, needle: str) -> int | None:
    n = _clean_label(needle or "").lower()
    if not n:
        return None
    for e in world.entities.values():
        if not e.visible:
            continue
        blob = _clean_label(f"{e.label} {e.semantic_role} {e.attributes.get('description', '')}").lower()
        if n == blob or n in blob or blob in n:
            return int(e.id)
    return None
