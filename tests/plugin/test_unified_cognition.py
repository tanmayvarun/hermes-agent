"""The model owns the world; the runtime decides only what is executable."""

from plugin.agent.features import StateFeatures
from plugin.agent.goal import Goal
from plugin.agent.runtime.state import ExecutionState
from plugin.agent.unified_cognition import (
    ALLOWED_ACTIONS,
    UnifiedProposal,
    _parse_proposal,
    build_decision_packet,
    persist_world_document,
    proposal_to_action,
    should_escalate,
)
from plugin.worldmodel.entities.entity import Entity
from plugin.worldmodel.model import WorldModel


def _goal() -> Goal:
    return Goal(
        kind="whatsapp_forward_message",
        contact="Pallavi",
        target_contact="Tanmay",
        link_query="zarooratwala",
    )


def _world_with_entity() -> tuple[WorldModel, Entity]:
    world = WorldModel(active_app="WhatsApp")
    entity = Entity(
        id=42,
        entity_type="message",
        semantic_role="message",
        role="AXStaticText",
        label="ZarooratWala - Fresh Groceries",
        bounds=(810, 421, 380, 160),
        visible=True,
    )
    world.entities[42] = entity
    return world, entity


def _proposal(**next_action) -> UnifiedProposal:
    payload = {"family": "click", "confidence": 0.9}
    payload.update(next_action)
    return UnifiedProposal(
        observed_state={"surface": "conversation"},
        next_action=payload,
        confidence=float(payload.get("confidence") or 0.0),
    )


def test_packet_carries_ax_ids_and_bounds_for_grounding():
    """Ids alone are not enough: the model must be able to point at pixels."""
    world, _ = _world_with_entity()
    features = StateFeatures(app="WhatsApp", extras={"forward_phase": "FIND_LINK"})
    packet = build_decision_packet(_goal(), world, features, None)

    evidence = packet["observation"]["ax_evidence"]
    assert evidence, "goal-relevant entity must be offered as evidence"
    assert evidence[0]["id"] == 42
    assert evidence[0]["bounds"] == [810, 421, 380, 160]
    assert packet["allowed_actions"] == list(ALLOWED_ACTIONS)
    assert packet["goal"]["destination"] == "Tanmay"


def test_packet_carries_the_executive_perception_objective():
    """A look is not a blank refresh: when the executive has a perception query,
    its questions/focus/depth reach the perceptor so the look is objective-driven."""
    world, _ = _world_with_entity()
    state = ExecutionState()
    state.last_perception_query = {
        "questions": ["is the target message below the fold?"],
        "focus": "conversation timeline",
        "depth": "deep",
        "objective": "locate the ZarooratWala link",
        "completion_condition": "target row visible",
    }
    packet = build_decision_packet(_goal(), world, StateFeatures(app="WhatsApp"), state)

    obj = packet.get("perception_objective")
    assert obj is not None, "the executive's perception query must reach the packet"
    assert obj["questions"] == ["is the target message below the fold?"]
    assert obj["focus"] == "conversation timeline"
    assert obj["depth"] == "deep"


def test_packet_omits_perception_objective_when_the_look_is_generic():
    """No query, no objective section — an empty query is a generic refresh."""
    world, _ = _world_with_entity()
    state = ExecutionState()
    state.last_perception_query = {"questions": [], "objective": ""}
    packet = build_decision_packet(_goal(), world, StateFeatures(app="WhatsApp"), state)

    assert "perception_objective" not in packet


def test_packet_carries_no_runtime_derived_task_state():
    """The runtime must not ship its own guess about the world.

    Recomputing predicates from accessibility every cycle is what discarded the
    model's belief between steps, and on a surface AX cannot read those
    predicates were confidently wrong.
    """
    world, _ = _world_with_entity()
    features = StateFeatures(
        app="WhatsApp",
        extras={
            "forward_phase": "OPEN_SOURCE",
            "forward_task": {"predicates": {"source_conversation_open": False}},
        },
    )
    packet = build_decision_packet(_goal(), world, features, None)

    assert "task_state" not in packet
    assert "world_model" in packet


def test_target_id_resolves_to_entity_and_grounds_the_action():
    world, _ = _world_with_entity()
    action, reason = proposal_to_action(
        _proposal(family="right_click", target_id=42), _goal(), world
    )
    assert reason == "admissible"
    assert action is not None
    assert action.action == "RevealActions"
    assert action.action_family == "reveal_actions"
    assert action.target_entity_id == 42
    assert action.semantic_target == "ZarooratWala - Fresh Groceries"
    assert action.grounding_reason == "unified_multimodal"
    assert action.grounding_confidence == 0.9


def test_pointer_action_falls_back_to_model_supplied_point():
    """AX often omits the control; the screenshot still located it."""
    world = WorldModel(active_app="WhatsApp")
    action, reason = proposal_to_action(
        _proposal(family="click", target_id=None, target_point=[1012, 501]),
        _goal(),
        world,
    )
    assert reason == "admissible"
    assert action is not None
    assert action.target_point == (1012, 501)


def test_pointer_action_without_any_target_is_rejected():
    world = WorldModel(active_app="WhatsApp")
    action, reason = proposal_to_action(_proposal(family="click"), _goal(), world)
    assert action is None
    assert reason == "pointer_action_without_target"


def test_unknown_family_is_rejected_not_guessed():
    world, _ = _world_with_entity()
    action, reason = proposal_to_action(
        _proposal(family="teleport", target_id=42), _goal(), world
    )
    assert action is None
    assert reason.startswith("unknown_family")


def test_type_without_text_is_rejected():
    world = WorldModel(active_app="WhatsApp")
    action, reason = proposal_to_action(_proposal(family="type", text=""), _goal(), world)
    assert action is None
    assert reason == "type_without_text"


def test_type_query_without_field_geometry_is_rejected():
    # Cmd+F invent is closed — typing requires a grounded search-field site.
    world = WorldModel(active_app="WhatsApp")
    action, reason = proposal_to_action(
        _proposal(family="type", text="Pallavi"), _goal(), world
    )
    assert action is None
    assert reason == "type_query_without_geometry"


def test_type_query_with_screen_point_is_admissible():
    world = WorldModel(active_app="WhatsApp")
    action, reason = proposal_to_action(
        _proposal(
            family="type",
            text="Pallavi",
            target_point=[223, 93],
            coordinate_space="screen",
        ),
        _goal(),
        world,
    )
    assert reason == "admissible"
    assert action is not None
    assert action.action == "Type"
    assert action.text == "Pallavi"
    assert action.action_family == "type_query"
    assert action.target_point == (223, 93)


def test_open_entity_kept_when_ax_starved_but_row_is_visible():
    """A row the model can see carries a click point; AX starvation must not
    turn open_entity into a search. Click what you see."""
    world = WorldModel(active_app="WhatsApp")
    starved = StateFeatures(extras={"app_content_node_count": 0})
    action, reason = proposal_to_action(
        _proposal(family="open_entity", text="Pallavi", target_point=[285, 480]),
        _goal(),
        world,
        starved,
    )
    assert reason == "admissible"
    assert action is not None
    assert action.action_family == "open_entity"
    assert action.action == "OpenEntity"
    assert action.grounding_reason == "unified_multimodal"


def test_open_entity_kept_when_ax_has_content_rows():
    world = WorldModel(active_app="WhatsApp")
    rich = StateFeatures(extras={"app_content_node_count": 24})
    action, reason = proposal_to_action(
        _proposal(family="open_entity", text="Pallavi", target_point=[285, 480]),
        _goal(),
        world,
        rich,
    )
    assert reason == "admissible"
    assert action is not None
    assert action.action_family == "open_entity"
    assert action.action == "OpenEntity"


def test_open_entity_is_not_hijacked_by_a_search_hint():
    """A hinted query in the sidebar does not rewrite the model's open_entity;
    the runtime executes the move the brain chose."""
    world = WorldModel(active_app="WhatsApp")
    held = StateFeatures(
        conversation_open=False,
        extras={"app_content_node_count": 0, "search_query_hint": "Pallavi"},
    )
    action, reason = proposal_to_action(
        _proposal(family="open_entity", text="Pallavi", target_point=[285, 480]),
        _goal(),
        world,
        held,
    )
    assert reason == "admissible"
    assert action is not None
    assert action.action_family == "open_entity"


def test_open_entity_allowed_after_typed_search_still_closed():
    """After a typed submit, allow clicking the result row."""
    world = WorldModel(active_app="WhatsApp")
    held = StateFeatures(
        conversation_open=False,
        extras={
            "app_content_node_count": 0,
            "search_query_hint": "Pallavi zarooratwala link",
            "search_attempt_log": [
                {"q": "Pallavi zarooratwala link", "outcome": "typed_submitted"},
            ],
        },
    )
    action, reason = proposal_to_action(
        _proposal(
            family="open_entity",
            text="Pallavi",
            target_point=[278, 682],
        ),
        _goal(),
        world,
        held,
    )
    assert reason == "admissible"
    assert action is not None
    assert action.action_family == "open_entity"


def test_search_results_visible_promote_open_result_row():
    """Promote-row short-circuit removed: without unified, decide Observes."""
    from plugin.agent.decision import DecisionEngine

    world = WorldModel(active_app="WhatsApp")
    world.entities = {
        1: Entity(
            id=1,
            entity_type="textfield",
            semantic_role="Search",
            label="Search",
            role="AXTextField",
            actions=["click", "type"],
            visible=True,
            attributes={"value": "Pallavi"},
        ),
        2: Entity(
            id=2,
            entity_type="button",
            semantic_role="chat",
            label="Pallavi Ji",
            role="AXButton",
            actions=["click"],
            visible=True,
            attributes={"description": "Pallavi Ji"},
        ),
    }
    world.tracker._entities = dict(world.entities)
    world.tracker._next_id = 3
    action = DecisionEngine().define_action_step(Goal(kind="whatsapp_voice_call", contact="Pallavi"), world, ExecutionState())
    assert action is not None
    assert action.action_family == "observe"
    assert "unified_declined_no_legacy_fallthrough" in (action.rationale or "")


def test_open_entity_is_not_hijacked_by_a_pending_compose():
    """A pending composed query does not override a visible-row open_entity."""
    world = WorldModel(active_app="WhatsApp")
    pending = StateFeatures(
        extras={
            "app_content_node_count": 0,
            "composed_query_pending": "authored query pending",
        },
    )
    action, reason = proposal_to_action(
        _proposal(family="open_entity", text="Pallavi", target_point=[285, 480]),
        _goal(),
        world,
        pending,
    )
    assert reason == "admissible"
    assert action is not None
    assert action.action_family == "open_entity"


def test_model_asking_for_more_evidence_is_not_an_action():
    world, _ = _world_with_entity()
    action, reason = proposal_to_action(
        _proposal(family="request_more_evidence"), _goal(), world
    )
    assert action is None
    assert reason == "model_requested_request_more_evidence"


def test_escalation_is_the_exception_not_the_fast_path():
    features = StateFeatures()
    confident = _proposal(confidence=0.9)
    assert should_escalate(confident, features, admissible=True) == (False, "")

    # Low confidence, contradictions, and dead branches all escalate.
    assert should_escalate(_proposal(confidence=0.1), features, admissible=True)[0]
    assert should_escalate(confident, features, admissible=False)[0]

    # Naming an evidence gap is not doubt. The perceptor routinely reports
    # "AX publishes no node for the search bar" while still locating that bar
    # in the pixels; vetoing on that alone stalled the whole fast path.
    noted_gaps = _proposal(confidence=0.9)
    noted_gaps.missing_evidence = ["AX nodes for search bar"]
    assert should_escalate(noted_gaps, features, admissible=True) == (False, "")

    # Gaps plus genuine uncertainty do escalate.
    unsure = _proposal(confidence=0.6)
    unsure.missing_evidence = ["cannot see the forward control"]
    assert should_escalate(unsure, features, admissible=True)[0]
    assert should_escalate(confident, features, admissible=False)[0]
    assert should_escalate(None, features, admissible=False)[0]

    stalled = StateFeatures(extras={"no_progress_replans": 4})
    assert should_escalate(confident, stalled, admissible=True)[0]


def test_the_model_call_is_a_pure_function_of_document_and_observation():
    """A document written on one step is the document read on the next.

    Statelessness is the whole point: if the runtime edited or re-derived it in
    between, the model would be reasoning against a world it did not write, and
    a step could not be replayed exactly.
    """
    world, _ = _world_with_entity()
    state = ExecutionState()

    returned = _parse_proposal(
        {
            "world_model": {
                "surface": "conversation",
                "open_conversation": "Pallavi",
                "objects": [
                    {"id": "o1", "kind": "message", "text": "ZarooratWala order",
                     "point": [900, 500], "matches_goal": True}
                ],
                "beliefs": [
                    {"predicate": "source_conversation_open", "value": True,
                     "confidence": 0.98, "evidence": ["header reads Pallavi"]}
                ],
                "progress": {"phase": "FIND_LINK", "objective": "locate the link"},
            },
            "next_action": {"family": "scroll", "confidence": 0.8},
        },
        frame=3,
    )
    persist_world_document(state, returned)

    packet = build_decision_packet(_goal(), world, StateFeatures(app="WhatsApp"), state)
    assert packet["world_model"] == returned.world_model
    assert packet["world_model"]["progress"]["phase"] == "FIND_LINK"
    assert packet["world_model"]["beliefs"][0]["confirmed_on_frame"] == 3


def test_a_belief_the_model_drops_does_not_come_back():
    """Retraction has to be possible or the world can only accumulate errors.

    The model returns the whole document, so omitting a belief is how it
    retracts one. Nothing in the runtime may resurrect it.
    """
    state = ExecutionState()
    persist_world_document(state, _parse_proposal(
        {"world_model": {"surface": "conversation", "beliefs": [
            {"predicate": "target_visible", "value": True, "confidence": 0.9,
             "evidence": ["saw the card"]}]}},
        frame=1,
    ))
    assert state.unified_world_document["beliefs"]

    persist_world_document(state, _parse_proposal(
        {"world_model": {"surface": "conversation", "beliefs": []}}, frame=2
    ))
    assert state.unified_world_document["beliefs"] == []


def test_beliefs_going_unconfirmed_are_raised_back_to_the_model():
    """A claim nobody re-checked is the confabulation risk in this design.

    The runtime does not overrule it — it points at the belief and lets the
    model reconfirm it against fresh pixels or drop it.
    """
    world, _ = _world_with_entity()
    state = ExecutionState()
    persist_world_document(state, _parse_proposal(
        {"world_model": {"surface": "conversation", "beliefs": [
            {"predicate": "forward_dialog_open", "value": True, "confidence": 0.9,
             "evidence": ["a dialog appeared"], "confirmed_on_frame": 1}]}},
        frame=1,
    ))
    state.unified_frame = 9

    packet = build_decision_packet(_goal(), world, StateFeatures(app="WhatsApp"), state)
    assert any("forward_dialog_open" in item for item in packet["unconfirmed_beliefs"])


def test_last_action_carries_the_runtime_verdict_for_reflection():
    """The brain must see what the last action actually did to the world -- not
    just that the executor fired -- so it can course-correct instead of looping.
    """
    from plugin.agent.action import Action

    world, _ = _world_with_entity()
    state = ExecutionState()
    state.last_plan_step = Action(
        action="OpenEntity", action_family="open_entity", semantic_target="Pallavi"
    )
    state.last_result = {"ok": True, "message": "clicked 'Pallavi' via entity bounds"}
    # Runtime measured that nothing moved: an ok click that opened nothing.
    state.last_attribution = {
        "effect_kind": "no_transition",
        "likely_failure_domain": "actuation",
        "evidence": {"change_score": 0.0, "open_before": "", "open_after": ""},
        "notes": ["no_transition_after_downstream_action"],
    }
    state.repeated_action_count = 3

    packet = build_decision_packet(_goal(), world, StateFeatures(app="WhatsApp"), state)
    last = packet["last_action"]
    assert last["result"]["ok"] is True
    assert last["effect"] == "no_transition"
    assert last["failure_domain"] == "actuation"
    assert last["world_change_score"] == 0.0
    assert last["times_repeated_in_a_row"] == 3
    assert last["diagnosis_hints"]


def test_last_action_omits_reflection_fields_when_the_move_worked():
    """A clean, non-repeated action should not carry failure noise."""
    from plugin.agent.action import Action

    world, _ = _world_with_entity()
    state = ExecutionState()
    state.last_plan_step = Action(
        action="OpenEntity", action_family="open_entity", semantic_target="Pallavi"
    )
    state.last_result = {"ok": True, "message": "opened Pallavi"}
    state.last_attribution = {
        "effect_kind": "progress",
        "likely_failure_domain": "none",
        "evidence": {"change_score": 0.8},
        "notes": [],
    }
    state.repeated_action_count = 1

    packet = build_decision_packet(_goal(), world, StateFeatures(app="WhatsApp"), state)
    last = packet["last_action"]
    assert last["effect"] == "progress"
    assert "failure_domain" not in last
    assert "times_repeated_in_a_row" not in last
    assert "diagnosis_hints" not in last


def test_the_document_cannot_grow_without_bound():
    """Carrying the world forward must not become context bloat in a new form."""
    from plugin.agent.world_document import MAX_OBJECTS

    parsed = _parse_proposal(
        {"world_model": {"objects": [
            {"id": f"o{i}", "kind": "message", "text": f"message {i}", "point": [10, i]}
            for i in range(40)
        ]}},
        frame=1,
    )
    assert len(parsed.world_model["objects"]) == MAX_OBJECTS


def _fast_path_with(monkeypatch, proposal, execution_state):
    """Run the fast path against a fixed proposal, skipping the model call.

    Brain is stubbed to keep the proposal's pre-filled ``next_action`` so tests
    can assert grounding / admissibility without a live decision LLM.
    """
    import plugin.agent.brain as brain
    import plugin.agent.unified_cognition as uc
    from plugin.agent.decision import DecisionEngine

    monkeypatch.setenv("HERMES_UNIFIED_COGNITION", "1")
    monkeypatch.setattr(uc, "consult_unified_cognition", lambda *a, **k: proposal)

    def _keep_action(p, *a, **k):
        return {"applied": bool((getattr(p, "next_action", None) or {}).get("family")), "stub": True}

    monkeypatch.setattr(brain, "choose_next_capability", _keep_action)

    world, _ = _world_with_entity()
    features = StateFeatures(app="WhatsApp", extras={})
    return DecisionEngine()._unified_fast_path(
        _goal(), world, features, execution_state, []
    ), features


def test_repeating_a_reversible_action_is_the_model_call(monkeypatch):
    """Hunting repeats an action on purpose, and only the model can tell.

    The runtime's cycle detector cannot distinguish scrolling a history to find
    a message from spinning in place, so it kept replacing the model's scroll
    with an observe and the search never finished. The repetition is reported
    to the model through the packet instead of vetoing the move.
    """
    proposal = _proposal(family="scroll", confidence=0.9)
    state = ExecutionState()
    from plugin.agent.action import PlanStep

    state.prohibited_actions[
        state.action_key(PlanStep(action="Scroll", semantic_target="", text=""))
    ] = 3

    action, features = _fast_path_with(monkeypatch, proposal, state)
    assert action is not None
    assert features.extras["unified_cognition"]["repeat_allowed"] is True


def test_repeating_an_irreversible_action_still_stops_in_the_runtime(monkeypatch):
    """A wrong repeat that cannot be undone is the runtime's to refuse."""
    proposal = _proposal(family="click", target_id=42, confidence=0.9)
    state = ExecutionState()
    from plugin.agent.action import PlanStep

    state.prohibited_actions[
        state.action_key(PlanStep(action="Click", semantic_target="ZarooratWala - Fresh Groceries", text=""))
    ] = 3

    import plugin.agent.unified_cognition as uc

    monkeypatch.setattr(
        uc, "proposal_to_action",
        lambda *a, **k: (_irreversible_click(), "admissible"),
    )
    action, features = _fast_path_with(monkeypatch, proposal, state)
    assert action is None
    assert features.extras["unified_cognition"]["admissibility"] == "prohibited"


def _irreversible_click():
    from plugin.agent.action import Action

    return Action(
        action="Click",
        semantic_target="ZarooratWala - Fresh Groceries",
        action_family="open_contact",
        reversible=False,
    )


def test_a_point_in_the_image_becomes_the_matching_point_on_screen():
    """The frame is downscaled before it is sent, so the units differ.

    Executing the model's numbers unconverted put every pointer action off by
    the downscale ratio, which on a 1920-wide screen shown at 1280 meant
    right-clicking a different message than the one that was chosen.
    """
    world = WorldModel(active_app="WhatsApp")
    proposal = _proposal(family="right_click", target_point=[680, 480])
    proposal.point_scale = 1920 / 1280

    action, reason = proposal_to_action(proposal, _goal(), world)
    assert reason == "admissible"
    assert action.target_point == (1020, 720)


def test_the_document_keeps_the_model_own_coordinates():
    """Rescaling the document would desync it from the images the model sees.

    It is handed back verbatim next call alongside a fresh screenshot in the
    same image space, so the stored points must stay in that space.
    """
    from plugin.agent.unified_cognition import materialize_vision_entities

    world = WorldModel(active_app="WhatsApp")
    proposal = _parse_proposal(
        {"world_model": {"surface": "conversation", "objects": [
            {"id": "o1", "kind": "message", "text": "zarooratwala.com", "point": [600, 400]}]}},
        frame=1,
    )
    proposal.point_scale = 1.5
    materialize_vision_entities(world, proposal)

    assert proposal.world_model["objects"][0]["point"] == [600, 400]
    entity = next(e for e in world.entities.values() if e.label == "zarooratwala.com")
    x, y, w, h = entity.bounds
    assert (x + w / 2, y + h / 2) == (900.0, 600.0)


def test_packet_carries_the_action_topology_not_just_the_objects():
    """Objects alone leave the model to rediscover the UI mechanics each frame."""
    world, _ = _world_with_entity()
    state = ExecutionState()
    persist_world_document(
        state,
        _parse_proposal(
            {
                "world_model": {
                    "surface": "conversation",
                    "objects": [
                        {"id": "o1", "kind": "message", "text": "zarooratwala.com", "point": [980, 510]}
                    ],
                }
            },
            frame=1,
        ),
    )

    packet = build_decision_packet(_goal(), world, StateFeatures(app="WhatsApp"), state)
    frontier = packet["affordance_frontier"]

    assert frontier["surface"] == "conversation"
    assert any(a["family"] == "select_content" for a in frontier["observed_actions"])
    revealed = {
        item["label"]
        for probe in frontier["probe_actions"]
        for item in probe.get("may_reveal", [])
    }
    assert "Forward" in revealed
    for latent in frontier["latent_actions"]:
        assert latent["status"] == "latent"
        assert latent["available_now"] is False


def test_suggested_actions_parse_with_why_and_do_not_fill_next_action():
    """Stage1 rankings are advisory; brain alone fills next_action."""
    parsed = _parse_proposal(
        {
            "world_model": {"surface": "conversation"},
            "confidence": 0.88,
            "suggested_actions": [
                {"rank": 2, "family": "hover", "target_id": 42, "confidence": 0.7, "why": "toolbar"},
                {
                    "rank": 1,
                    "family": "reveal_actions",
                    "target_id": 42,
                    "confidence": 0.88,
                    "why": "most likely to reveal Forward",
                },
            ],
        },
        frame=2,
    )

    assert [a["family"] for a in parsed.suggested_actions] == ["reveal_actions", "hover"]
    assert parsed.suggested_actions[0]["why"] == "most likely to reveal Forward"
    assert parsed.next_action == {}
    assert parsed.confidence == 0.88


def test_legacy_next_actions_map_into_suggested_actions():
    parsed = _parse_proposal(
        {
            "world_model": {"surface": "conversation"},
            "next_actions": [
                {"rank": 1, "family": "reveal_actions", "confidence": 0.9, "reason": "legacy"},
            ],
        },
        frame=2,
    )
    assert parsed.suggested_actions[0]["family"] == "reveal_actions"
    assert parsed.suggested_actions[0]["why"] == "legacy"
    assert parsed.next_action == {}


def test_an_unpromising_alternative_is_dropped_but_the_best_move_never_is():
    """Thresholds prune siblings; they must not leave the runtime with nothing."""
    from plugin.agent.unified_cognition import normalize_next_actions

    pruned = normalize_next_actions(
        [
            {"rank": 1, "family": "reveal_actions", "confidence": 0.9, "expected_progress": 0.8},
            {"rank": 2, "family": "scroll", "confidence": 0.2},
            {"rank": 3, "family": "hover", "confidence": 0.9, "expected_progress": 0.05},
        ]
    )
    assert [a["family"] for a in pruned] == ["reveal_actions"]

    weak_only = normalize_next_actions([{"family": "scroll", "confidence": 0.1}])
    assert [a["family"] for a in weak_only] == ["scroll"]


def test_a_single_legacy_next_action_is_advisory_not_executed_head():
    parsed = _parse_proposal(
        {
            "world_model": {"surface": "conversation"},
            "next_action": {"family": "press_escape", "confidence": 0.8},
        },
        frame=3,
    )
    assert parsed.next_action == {}
    assert [a["family"] for a in parsed.next_actions] == ["press_escape"]


def test_ranked_action_candidates_are_brain_head_only():
    from plugin.agent.unified_cognition import ranked_action_candidates

    proposal = UnifiedProposal(
        next_action={"family": "resolve_entity", "text": "Pallavi", "confidence": 0.8},
        next_actions=[
            {"family": "locate_content", "text": "zarooratwala", "confidence": 0.7},
        ],
        recommended_probe={"family": "hover", "target_id": 42, "reason": "reveal Forward"},
    )
    families = [a["family"] for a in ranked_action_candidates(proposal)]

    # Perception siblings / probes are not auto-executed; brain must choose.
    assert families == ["resolve_entity"]


def test_an_inadmissible_brain_head_falls_through_to_slow_path(monkeypatch):
    """Brain owns choice; an inadmissible head does not auto-run a probe."""
    proposal = UnifiedProposal(
        observed_state={"surface": "conversation"},
        next_action={"family": "click", "confidence": 0.9},
        recommended_probe={
            "family": "type",
            "text": "Pallavi",
            "reason": "type into focused field",
        },
        confidence=0.9,
    )

    action, features = _fast_path_with(monkeypatch, proposal, ExecutionState())

    assert action is None
    trace = features.extras["unified_cognition"]
    assert trace["rejected_siblings"] == ["click:pointer_action_without_target"]


def test_missing_affordance_information_survives_parsing():
    """What the frontier failed to mention is the signal that improves it."""
    parsed = _parse_proposal(
        {
            "world_model": {"surface": "conversation"},
            "next_actions": [{"family": "hover", "target_id": 42, "confidence": 0.6}],
            "missing_affordance_information": ["no control listed for the pinned banner"],
            "recommended_probe": {"family": "hover", "target_id": 42, "may_reveal": ["Forward"]},
        },
        frame=5,
    )

    assert parsed.missing_affordance_information == ["no control listed for the pinned banner"]
    assert parsed.recommended_probe["may_reveal"] == ["Forward"]


def test_the_model_may_abandon_a_branch():
    """Backtracking is the model's call, and it has to survive parsing."""
    parsed = _parse_proposal(
        {
            "world_model": {"surface": "conversation", "exhausted": ["scrolled to the top"]},
            "next_action": {"family": "press_escape", "confidence": 0.8},
            "backtrack": {"reason": "history exhausted", "to": "chat_list"},
        },
        frame=4,
    )
    assert parsed.backtrack["to"] == "chat_list"
    assert parsed.world_model["exhausted"] == ["scrolled to the top"]


def test_act_clear_rewrites_reveal_suggestion_on_open_menu():
    """When Forward is already inventoried on a menu, do not advise re-reveal."""
    from plugin.agent.unified_cognition import apply_affordance_stance

    proposal = _parse_proposal(
        {
            "world_model": {
                "surface": "context_menu",
                "objects": [
                    {
                        "id": "fwd",
                        "kind": "menu_item",
                        "text": "Forward",
                        "point": [1270, 332],
                    }
                ],
            },
            "suggested_actions": [
                {
                    "rank": 1,
                    "family": "reveal_actions",
                    "text": "Forward",
                    "confidence": 0.9,
                    "why": "explore",
                }
            ],
            "affordance_qc": {"expected_found": True, "missing": []},
            "affordance_stance": "explore_needed",
        },
        frame=9,
    )
    apply_affordance_stance(proposal, goal=_goal())
    assert proposal.affordance_stance == "act_clear"
    assert proposal.suggested_actions[0]["family"] == "invoke_affordance"
    assert proposal.suggested_actions[0].get("target_point") == [1270.0, 332.0]


def test_act_clear_attaches_geometry_when_suggestion_already_invoke():
    """Even if the model already chose invoke, stamp the control point (173658)."""
    from plugin.agent.unified_cognition import apply_affordance_stance

    proposal = _parse_proposal(
        {
            "world_model": {
                "surface": "context_menu",
                "objects": [
                    {
                        "id": "fwd",
                        "kind": "menu_item",
                        "text": "Forward",
                        "point": [1272, 279],
                    }
                ],
            },
            "suggested_actions": [
                {
                    "rank": 1,
                    "family": "invoke_affordance",
                    "text": "Click 'Forward'",
                    "confidence": 0.9,
                    "why": "menu open",
                }
            ],
            "affordance_qc": {"expected_found": True, "missing": []},
            "affordance_stance": "act_clear",
        },
        frame=11,
    )
    apply_affordance_stance(proposal, goal=_goal())
    assert proposal.affordance_stance == "act_clear"
    assert proposal.suggested_actions[0].get("target_point") == [1272.0, 279.0]
    assert proposal.suggested_actions[0].get("text") == "Forward"


def test_label_only_menu_verb_is_not_act_clear():
    """Verb text without point/bounds must not claim act_clear (live 171627)."""
    from plugin.agent.unified_cognition import apply_affordance_stance

    proposal = _parse_proposal(
        {
            "world_model": {
                "surface": "context_menu",
                "objects": [
                    {
                        "id": "fwd",
                        "kind": "menu_item",
                        "text": "Forward",
                    }
                ],
            },
            "suggested_actions": [
                {
                    "rank": 1,
                    "family": "invoke_affordance",
                    "text": "Forward",
                    "confidence": 0.9,
                }
            ],
            "affordance_qc": {"expected_found": True, "missing": []},
            "affordance_stance": "act_clear",
        },
        frame=10,
    )
    apply_affordance_stance(proposal, goal=_goal())
    assert proposal.affordance_stance != "act_clear"
    assert proposal.affordance_stance == "explore_needed"


def test_overlay_verb_invoke_does_not_rebind_to_content_url():
    """Menu Forward must ground to the control, not the source URL message."""
    world = WorldModel(active_app="WhatsApp")
    menu = Entity(
        id=7,
        entity_type="control",
        semantic_role="menu_item",
        role="AXMenuItem",
        label="Forward",
        bounds=(1200, 300, 140, 40),
        visible=True,
    )
    content = Entity(
        id=9,
        entity_type="message",
        semantic_role="message",
        role="AXStaticText",
        label="https://example.test/zarooratwala",
        bounds=(280, 320, 200, 40),
        visible=True,
    )
    world.entities[7] = menu
    world.entities[9] = content
    proposal = UnifiedProposal(
        observed_state={"surface": "context_menu"},
        world_model={"surface": "context_menu"},
        next_action={
            "family": "invoke_affordance",
            "text": "Forward",
            "confidence": 0.9,
        },
        confidence=0.9,
    )
    action, err = proposal_to_action(proposal, _goal(), world)
    assert action is not None, err
    assert getattr(action, "target_entity_id", None) != 9
    assert getattr(action, "target_entity_id", None) == 7 or getattr(
        action, "target_point", None
    ) is not None


def test_overlay_verb_without_geometry_is_refused():
    """Overlay invoke must not click the content URL when menu geometry is missing."""
    world = WorldModel(active_app="WhatsApp")
    content = Entity(
        id=9,
        entity_type="message",
        semantic_role="message",
        role="AXStaticText",
        label="https://example.test/zarooratwala",
        bounds=(280, 320, 200, 40),
        visible=True,
    )
    world.entities[9] = content
    proposal = UnifiedProposal(
        observed_state={"surface": "context_menu"},
        world_model={
            "surface": "context_menu",
            "objects": [
                {"id": "fwd", "kind": "menu_item", "text": "Forward"},
                {
                    "id": "url",
                    "kind": "message",
                    "text": "https://example.test/zarooratwala",
                    "point": [310, 340],
                },
            ],
        },
        next_action={
            "family": "invoke_affordance",
            "text": "Forward",
            "confidence": 0.9,
        },
        confidence=0.9,
    )
    action, err = proposal_to_action(proposal, _goal(), world)
    assert action is None
    assert err == "overlay_verb_without_geometry"
