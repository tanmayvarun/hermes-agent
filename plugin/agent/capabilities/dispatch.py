"""Dispatch a named capability through the catalog.

Call sites name the capability and the model-supplied argument. Realizations
come from the app overlay. This is the single place motor code must not grow
host-specific locate/open/dismiss forks.
"""

from __future__ import annotations

from typing import Any, Dict, FrozenSet

from plugin.agent.capabilities.base import (
    CapabilityOutcome,
    CapabilityRequest,
    CapabilityStatus,
    SearchableSurface,
    TransientChrome,
)
from plugin.agent.capabilities.catalog import spec_by_name
from plugin.agent.capabilities.commit_irreversible import commit_irreversible
from plugin.agent.capabilities.compose_search_query import (
    brief_from_context,
    compose_search_query,
)
from plugin.agent.capabilities.dismiss_transient import (
    MacDismissRuntime,
    dismiss_chord_for,
    dismiss_transient,
)
from plugin.agent.capabilities.recover_blocked_app import recover_blocked_app
from plugin.agent.capabilities.relieve_host_storage import relieve_host_storage
from plugin.agent.capabilities.invoke_affordance import invoke_affordance
from plugin.agent.capabilities.locate_content import (
    FindAffordance,
    LocateContent,
    LocateRequest,
    default_realizations,
)
from plugin.agent.capabilities.open_entity import open_entity, resolve_addressable
from plugin.agent.capabilities.pointer_runtime import MacPointerRuntime
from plugin.agent.capabilities.resolve_entity import (
    brief_from_context as resolve_brief_from_context,
    resolve_entity,
)
from plugin.agent.capabilities.reveal_actions import (
    reveal_actions,
    reveal_context_from_extras,
    reveal_mode_for,
)
from plugin.agent.capabilities.select_content import select_content
from plugin.agent.capabilities.revert_effects import (
    goal_referents_from_context,
    revert_effects,
)

_NAME_ALIASES = {
    "composesearchquery": "compose_search_query",
    "compose_query": "compose_search_query",
    "author_search_query": "compose_search_query",
    "locatecontent": "locate_content",
    "openentity": "open_entity",
    "resolveentity": "resolve_entity",
    "resolve_candidate": "resolve_entity",
    "select_candidate": "resolve_entity",
    "selectcontent": "select_content",
    "revealactions": "reveal_actions",
    "invokeaffordance": "invoke_affordance",
    "dismisstransient": "dismiss_transient",
    "commitirreversible": "commit_irreversible",
    "dismiss": "dismiss_transient",
    "press_escape": "dismiss_transient",
    "pressescape": "dismiss_transient",
    "relievehoststorage": "relieve_host_storage",
    "relieve_storage": "relieve_host_storage",
    "recoverblockedapp": "recover_blocked_app",
    "recover_app": "recover_blocked_app",
    "reverteffects": "revert_effects",
    "revert": "revert_effects",
    "rollback": "revert_effects",
    "rollback_effects": "revert_effects",
    # Graph nomenclature: backtrack ≡ revert ≡ rollback.
    "backtrack": "revert_effects",
    "back_track": "revert_effects",
    "right_click": "reveal_actions",
    "rightclick": "reveal_actions",
    "context_click": "reveal_actions",
    "contextclick": "reveal_actions",
}

_ENTITY_CAPABILITIES: FrozenSet[str] = frozenset(
    {"open_entity", "select_content", "reveal_actions"}
)


def searchable_surface(overlay: Any, *, app: str, surface: str = "") -> SearchableSurface:
    """Project host declarations into the substrate locate_content consumes."""
    affordance = getattr(overlay, "find_affordance", None)
    return SearchableSurface(
        app=app,
        surface=surface,
        find_declared=isinstance(affordance, FindAffordance),
        scoped_to_surface=bool(getattr(affordance, "scoped_to_surface", True))
        if isinstance(affordance, FindAffordance)
        else True,
    )


def locators_for_overlay(overlay: Any):
    """Cheapest-first locate realizations for a host overlay."""
    declared = getattr(overlay, "content_locators", None)
    if callable(declared):
        realizations = declared()
        if realizations:
            return list(realizations)
    affordance = getattr(overlay, "find_affordance", None)
    return default_realizations(affordance if isinstance(affordance, FindAffordance) else None)


def _execute_compose(request: CapabilityRequest, overlay: Any) -> CapabilityOutcome:
    extras = request.extras or {}
    goal = extras.get("goal")
    world = extras.get("world")
    features = extras.get("features")
    document = extras.get("world_document")
    exec_state = extras.get("execution_state")
    if document is None and world is not None:
        document = getattr(world, "overlay_hints", None) or {}
        # Prefer the model-owned unified document when present.
        if exec_state is not None:
            document = getattr(exec_state, "unified_world_document", None) or document
    if goal is None:
        return CapabilityOutcome(
            ok=False,
            capability="compose_search_query",
            message="compose_search_query needs goal evidence",
        )
    brief = brief_from_context(
        goal,
        world_document=document if isinstance(document, dict) else {},
        features=features,
        prior_queries=extras.get("prior_queries"),
    )
    # Optional model hint in arg is notes, not a forced template.
    if request.arg:
        brief.notes = (brief.notes + " " + request.arg).strip()
    outcome = compose_search_query(brief, author=extras.get("author"))
    if outcome.ok and exec_state is not None:
        try:
            from plugin.agent.capabilities.search_episode import start_search_episode

            authored = ""
            if isinstance(outcome.evidence, dict):
                authored = str(
                    outcome.evidence.get("chosen")
                    or outcome.evidence.get("query")
                    or outcome.evidence.get("authored_query")
                    or ""
                ).strip()
            start_search_episode(
                exec_state,
                role="source",
                referent=str(getattr(goal, "link_query", None) or getattr(goal, "contact", "") or ""),
                query=authored or str(request.arg or ""),
                evidence_tokens=[
                    t
                    for t in (
                        getattr(goal, "link_query", None),
                        getattr(goal, "contact", None),
                        authored,
                    )
                    if t
                ],
                space="ui_filter",
                reason="compose_search_query",
                status="retrieving" if authored else "querying",
            )
        except Exception:
            pass
    return outcome


def _execute_search(request: CapabilityRequest, overlay: Any) -> CapabilityOutcome:
    """Compound search: advance episode / resolve; never commit (open)."""
    extras = request.extras or {}
    exec_state = extras.get("execution_state")
    document = extras.get("world_document")
    if not isinstance(document, dict) and exec_state is not None:
        document = getattr(exec_state, "unified_world_document", None)
    if not isinstance(document, dict):
        document = {}
    from plugin.agent.capabilities.search_episode import (
        advance_search_with_candidates,
        candidates_from_world_document,
        complete_search_choice,
        search_episode_of,
        start_search_episode,
    )
    from plugin.agent.capabilities.resolve_entity import candidates_from_context

    goal = extras.get("goal")
    role = str(extras.get("role") or "source").strip() or "source"
    referent = (request.arg or "").strip()
    if not referent and goal is not None:
        if role == "destination":
            referent = str(getattr(goal, "target_contact", "") or "").strip()
        else:
            referent = str(
                getattr(goal, "link_query", None)
                or getattr(goal, "contact", None)
                or ""
            ).strip()
    cands = candidates_from_context(
        features=extras.get("features"),
        world_document=document,
        explicit=extras.get("candidates"),
    )
    if not cands:
        cands = candidates_from_world_document(document)
    ep = search_episode_of(exec_state)
    if not ep:
        start_search_episode(
            exec_state,
            role=role,
            referent=referent,
            query=str(extras.get("query") or ""),
            space=str(extras.get("space") or "ui_filter"),
            reason="search_capability",
            status="ranking" if cands else "querying",
        )
    ep = advance_search_with_candidates(
        exec_state,
        cands,
        referent=referent,
        query=str((search_episode_of(exec_state) or {}).get("query") or extras.get("query") or ""),
        evidence_tokens=extras.get("evidence_tokens"),
    )
    if str(ep.get("status") or "") == "complete" and ep.get("chosen_label"):
        return CapabilityOutcome(
            ok=True,
            capability="search",
            realization="unique_fit",
            message=f"search complete → {ep.get('chosen_label')!r}",
            evidence={"search_episode": ep, "chosen": ep.get("chosen_label")},
        )
    if not cands:
        return CapabilityOutcome(
            ok=False,
            capability="search",
            realization="awaiting_candidates",
            message="search has no candidates yet; compose or re-perceive",
            evidence={"search_episode": ep},
        )
    # Rank via resolve_entity (does not open — we stamp choice only).
    resolve_outcome = _execute_resolve(request, overlay)
    if resolve_outcome.ok and isinstance(resolve_outcome.evidence, dict):
        chosen = str(resolve_outcome.evidence.get("chosen") or "").strip()
        if chosen:
            complete_search_choice(
                exec_state,
                chosen_label=chosen,
                chosen_id=resolve_outcome.evidence.get("id"),
                scores=resolve_outcome.evidence.get("ranked"),
            )
            return CapabilityOutcome(
                ok=True,
                capability="search",
                realization="resolve_entity",
                message=f"search ranked → {chosen!r}",
                evidence={
                    "search_episode": search_episode_of(exec_state),
                    "chosen": chosen,
                    "point": resolve_outcome.evidence.get("point"),
                    "id": resolve_outcome.evidence.get("id"),
                    "ranked": resolve_outcome.evidence.get("ranked"),
                },
            )
    return CapabilityOutcome(
        ok=False,
        capability="search",
        realization=resolve_outcome.realization or "ranking",
        message=resolve_outcome.message or "search ranking incomplete",
        evidence={
            "search_episode": search_episode_of(exec_state),
            "resolve": dict(resolve_outcome.evidence or {}),
        },
    )


def _execute_resolve(request: CapabilityRequest, overlay: Any) -> CapabilityOutcome:
    extras = request.extras or {}
    goal = extras.get("goal")
    role = str(extras.get("role") or "destination").strip() or "destination"
    referent = (request.arg or "").strip()
    if not referent and goal is not None:
        referent = str(
            getattr(goal, "target_contact", None)
            if role == "destination"
            else getattr(goal, "contact", None)
            or getattr(goal, "target_contact", None)
            or ""
        ).strip()
    if goal is None and not referent and not extras.get("candidates"):
        return CapabilityOutcome(
            ok=False,
            capability="resolve_entity",
            message="resolve_entity needs a referent or goal evidence",
        )
    document = extras.get("world_document")
    if not isinstance(document, dict):
        exec_state = extras.get("execution_state")
        document = (
            getattr(exec_state, "unified_world_document", None) if exec_state is not None else None
        )
    if not isinstance(document, dict) and extras.get("world") is not None:
        document = getattr(extras.get("world"), "overlay_hints", None) or {}
    if not isinstance(document, dict):
        document = {}
    brief = resolve_brief_from_context(
        goal if goal is not None else object(),
        referent=referent,
        role=role,
        features=extras.get("features"),
        world_document=document,
        candidates=extras.get("candidates"),
    )
    if not brief.referent and referent:
        brief.referent = referent
    outcome = resolve_entity(
        brief,
        resolver=extras.get("resolver"),
        use_llm=bool(extras.get("use_llm")),
    )
    exec_state = extras.get("execution_state")
    if exec_state is not None:
        try:
            from plugin.agent.capabilities.search_episode import (
                complete_search_choice,
                fail_search_episode,
            )

            if outcome.ok and isinstance(outcome.evidence, dict):
                chosen = str(outcome.evidence.get("chosen") or "").strip()
                if chosen:
                    complete_search_choice(
                        exec_state,
                        chosen_label=chosen,
                        chosen_id=outcome.evidence.get("id"),
                        scores=outcome.evidence.get("ranked"),
                    )
                else:
                    # ok without a chosen stamp is still zero progress — fail.
                    fail_search_episode(
                        exec_state,
                        reason=str(outcome.message or "resolve_ok_without_choice")[:120],
                    )
            else:
                # Zero-progress find (empty set / no candidate relates). Always
                # arm retreat — do not require incomplete status (live 212533:
                # resolve failed but SEARCH re-entered with ranking still open).
                fail_search_episode(
                    exec_state,
                    reason=str(outcome.message or "resolve_no_match")[:120],
                )
        except Exception:
            pass
    return outcome


def _execute_locate(request: CapabilityRequest, overlay: Any) -> CapabilityOutcome:
    from plugin.agent.capabilities.macos_runtime import MacLocatorRuntime

    query = (request.arg or "").strip()
    if not query:
        return CapabilityOutcome(
            ok=False,
            capability="locate_content",
            message="locate_content without a query",
        )

    surface = searchable_surface(overlay, app=request.app, surface=request.surface)
    capability = LocateContent(realizations=locators_for_overlay(overlay))
    outcome = capability.locate(
        LocateRequest(query=query, app=request.app, surface=surface.surface),
        MacLocatorRuntime(request.app),
    )
    evidence = outcome.as_evidence()
    evidence["substrate"] = "searchable_surface"
    evidence["find_declared"] = surface.find_declared
    return CapabilityOutcome(
        ok=outcome.ok,
        capability="locate_content",
        realization=outcome.realization,
        message=outcome.message,
        evidence=evidence,
    )


def _entity_from(request: CapabilityRequest, overlay: Any):
    extras = dict(request.extras or {})
    return resolve_addressable(request.arg, extras, overlay, app=request.app)


def _execute_open(request: CapabilityRequest, overlay: Any) -> CapabilityOutcome:
    return open_entity(_entity_from(request, overlay), MacPointerRuntime())


def _execute_select(request: CapabilityRequest, overlay: Any) -> CapabilityOutcome:
    return select_content(_entity_from(request, overlay), MacPointerRuntime())


def _execute_reveal(request: CapabilityRequest, overlay: Any) -> CapabilityOutcome:
    extras = request.extras or {}
    context = reveal_context_from_extras(extras)
    return reveal_actions(
        _entity_from(request, overlay),
        MacPointerRuntime(),
        mode=reveal_mode_for(overlay),
        context=context,
        goal_action=str(extras.get("goal_action") or ""),
    ).to_outcome()


def _execute_invoke(request: CapabilityRequest, overlay: Any) -> CapabilityOutcome:
    extras = request.extras or {}
    return invoke_affordance(
        request.app,
        request.arg,
        MacPointerRuntime(),
        bounds=extras.get("bounds"),
        point=extras.get("point"),
    )


def _execute_dismiss(request: CapabilityRequest, overlay: Any) -> CapabilityOutcome:
    chrome = TransientChrome(app=request.app, surface=request.surface)
    return dismiss_transient(
        chrome,
        MacDismissRuntime(),
        chord=dismiss_chord_for(overlay),
    )


def _execute_relieve_storage(request: CapabilityRequest, overlay: Any) -> CapabilityOutcome:
    extras = dict(request.extras or {})
    return relieve_host_storage(
        app=request.app,
        view=extras.get("view") if isinstance(extras.get("view"), dict) else None,
        features=extras.get("features") if isinstance(extras.get("features"), dict) else extras,
        observation_texts=list(extras.get("observation_texts") or []),
        evidence=list(extras.get("evidence") or []),
        reason=str(extras.get("reason") or request.arg or "storage pressure"),
    )


def _execute_recover_app(request: CapabilityRequest, overlay: Any) -> CapabilityOutcome:
    extras = dict(request.extras or {})
    world = extras.get("world")
    if world is None:
        world = getattr(overlay, "world", None)
    return recover_blocked_app(
        app=request.app,
        world=world,
        dialogs=list(extras.get("dialogs") or []),
    )


def _execute_commit(request: CapabilityRequest, overlay: Any) -> CapabilityOutcome:
    extras = request.extras or {}
    return commit_irreversible(
        request.app,
        request.arg,
        MacPointerRuntime(),
        bounds=extras.get("bounds"),
        point=extras.get("point"),
    )


def _execute_revert(request: CapabilityRequest, overlay: Any) -> CapabilityOutcome:
    extras = dict(request.extras or {})
    exec_state = extras.get("execution_state")
    document = extras.get("world_document")
    if not isinstance(document, dict) and exec_state is not None:
        document = getattr(exec_state, "unified_world_document", None)
    if not isinstance(document, dict):
        document = {}
    effect_trace = extras.get("effect_trace")
    if not isinstance(effect_trace, list) and exec_state is not None:
        effect_trace = list(getattr(exec_state, "effect_trace", None) or [])
    sel = extras.get("selection_consistency")
    if not isinstance(sel, dict) and exec_state is not None:
        sel = getattr(exec_state, "last_selection_consistency", None)
    referents = goal_referents_from_context(
        execution_state=exec_state,
        goal=extras.get("goal"),
        extras=extras,
    )
    outcome = revert_effects(
        app=request.app,
        surface=request.surface,
        document=document,
        effect_trace=effect_trace if isinstance(effect_trace, list) else None,
        selection_consistency=sel if isinstance(sel, dict) else None,
        goal_referents=referents,
        semantic_target=str(extras.get("semantic_target") or ""),
        overlay=overlay,
        runtime=extras.get("runtime"),
        approve=bool(extras.get("approve", True)),
        force_approve=bool(extras.get("force_approve", False)),
        dry_run=bool(extras.get("dry_run", False)),
        user_intent=str(
            extras.get("user_intent") or request.arg or extras.get("reason") or ""
        ),
    )
    # After a successful revert, stash a follow-up so the next look re-selects
    # the goal content instead of advancing Forward on a cleared surface.
    if outcome.ok and exec_state is not None:
        try:
            exec_state.pending_repair_after_revert = {
                "capability": "select_content",
                "target_hint": (referents[0] if referents else "") or "goal content",
                "reason": "post_revert_reselect",
                "repair_kind": "re_ground_then_act",
            }
            exec_state.last_revert_plan = (
                (outcome.evidence or {}).get("plan")
                if isinstance(outcome.evidence, dict)
                else None
            )
        except Exception:
            pass
    return outcome


_HANDLERS = {
    # Compound ``search`` is MetaAction.SEARCH; stages dispatch below.
    "compose_search_query": _execute_compose,
    "locate_content": _execute_locate,
    "open_entity": _execute_open,
    "resolve_entity": _execute_resolve,
    "select_content": _execute_select,
    "reveal_actions": _execute_reveal,
    "invoke_affordance": _execute_invoke,
    "dismiss_transient": _execute_dismiss,
    "revert_effects": _execute_revert,
    "relieve_host_storage": _execute_relieve_storage,
    "recover_blocked_app": _execute_recover_app,
    "commit_irreversible": _execute_commit,
}


def can_dispatch(name: str) -> bool:
    resolved = _normalize_name(name)
    spec = spec_by_name(resolved)
    return bool(spec and spec.status == CapabilityStatus.REALIZED and spec.name in _HANDLERS)


def _normalize_name(name: str) -> str:
    key = str(name or "").strip().lower().replace("-", "_")
    compact = key.replace("_", "")
    if key in _NAME_ALIASES:
        return _NAME_ALIASES[key]
    if compact in _NAME_ALIASES:
        return _NAME_ALIASES[compact]
    return key


def _request_satisfied(spec, request: CapabilityRequest) -> bool:
    if not spec.required_arg:
        return True
    if (request.arg or "").strip():
        return True
    if spec.name in _ENTITY_CAPABILITIES:
        extras = request.extras or {}
        return bool(extras.get("point") or extras.get("bounds") or extras.get("entity_id"))
    return False


def dispatch(request: CapabilityRequest, overlay: Any) -> CapabilityOutcome:
    """Run a realized capability, or return a clear contract-only refusal."""
    name = _normalize_name(request.name)
    if name != request.name:
        request = CapabilityRequest(
            name=name,
            app=request.app,
            arg=request.arg,
            surface=request.surface,
            extras=request.extras,
        )
    spec = spec_by_name(request.name)
    if spec is None:
        return CapabilityOutcome(
            ok=False,
            capability=request.name,
            message=f"unknown capability: {request.name}",
        )
    if spec.status != CapabilityStatus.REALIZED:
        approx = ", ".join(spec.motor_approximation) or "motor primitives"
        return CapabilityOutcome(
            ok=False,
            capability=spec.name,
            message=(
                f"{spec.name} is contracted but not yet realized; "
                f"use motor approximation: {approx}"
            ),
            evidence={"status": spec.status.value},
        )
    handler = _HANDLERS.get(spec.name)
    if handler is None:
        return CapabilityOutcome(
            ok=False,
            capability=spec.name,
            message=f"{spec.name} is marked realized but has no handler",
        )
    if not _request_satisfied(spec, request):
        return CapabilityOutcome(
            ok=False,
            capability=spec.name,
            message=f"{spec.name} requires model argument {spec.required_arg!r}",
        )
    return handler(request, overlay)


def dispatch_from_step(
    step: Any,
    *,
    app: str,
    overlay: Any,
    world: Any = None,
    execution_state: Any = None,
    goal: Any = None,
) -> CapabilityOutcome:
    """Bridge PlanStep / Action fields into a CapabilityRequest."""
    fam = str(getattr(step, "action_family", "") or "").strip().lower()
    act = str(getattr(step, "action", "") or "").strip().lower()
    name = _normalize_name(fam or act)

    if name in _ENTITY_CAPABILITIES:
        arg = str(getattr(step, "semantic_target", "") or getattr(step, "text", "") or "")
    elif name in {
        "invoke_affordance",
        "commit_irreversible",
        "locate_content",
        "resolve_entity",
        "compose_search_query",
        "search",
    }:
        arg = str(getattr(step, "text", "") or getattr(step, "semantic_target", "") or "")
    else:
        arg = str(getattr(step, "text", "") or getattr(step, "semantic_target", "") or "")

    extras: Dict[str, Any] = {"app": app}
    if world is not None:
        extras["world"] = world
        doc = getattr(world, "overlay_hints", None)
        if isinstance(doc, dict) and "world_document" not in extras:
            # Prefer objects already mirrored onto overlay hints when present.
            extras.setdefault("world_document", doc.get("unified_world_document") or doc)
    if execution_state is not None:
        extras["execution_state"] = execution_state
        doc = getattr(execution_state, "unified_world_document", None)
        if isinstance(doc, dict):
            extras["world_document"] = doc
    if goal is not None:
        extras["goal"] = goal
        for attr in ("link_query", "content_query"):
            val = getattr(goal, attr, None)
            if val and attr not in extras:
                extras[attr] = val
    point = getattr(step, "target_point", None)
    if point:
        extras["point"] = point
    entity_id = getattr(step, "target_entity_id", None)
    if entity_id is not None:
        extras["entity_id"] = entity_id

    return dispatch(
        CapabilityRequest(name=name, app=app, arg=arg, extras=extras),
        overlay,
    )
