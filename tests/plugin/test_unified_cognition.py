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


def test_keyboard_action_needs_no_entity_grounding():
    world = WorldModel(active_app="WhatsApp")
    action, reason = proposal_to_action(
        _proposal(family="type", text="Pallavi"), _goal(), world
    )
    assert reason == "admissible"
    assert action is not None
    assert action.action == "Type"
    assert action.text == "Pallavi"
    assert action.action_family == "type_query"


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
    """Visible search results should open the matching row, not re-search."""
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
    features = StateFeatures(
        app="WhatsApp",
        screen_bucket="search",
        query_matches_goal=True,
        has_named_entity=True,
        conversation_open=False,
        extras={
            "result_surface_visible": True,
            "search_query": "Pallavi",
            "search_result_rows": ["Pallavi Ji"],
            "visible_contacts": ["Pallavi Ji"],
        },
    )
    action = DecisionEngine().decide(Goal(kind="whatsapp_voice_call", contact="Pallavi"), world, ExecutionState())
    assert action is not None
    assert action.action_family == "open_contact"
    assert action.semantic_target == "Pallavi Ji"


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
    """Run the fast path against a fixed proposal, skipping the model call."""
    import plugin.agent.unified_cognition as uc
    from plugin.agent.decision import DecisionEngine

    monkeypatch.setenv("HERMES_UNIFIED_COGNITION", "1")
    monkeypatch.setattr(uc, "consult_unified_cognition", lambda *a, **k: proposal)

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


def test_ranked_next_actions_are_ordered_and_the_head_becomes_the_action():
    parsed = _parse_proposal(
        {
            "world_model": {"surface": "conversation"},
            "next_actions": [
                {"rank": 2, "family": "hover", "target_id": 42, "confidence": 0.7},
                {"rank": 1, "family": "reveal_actions", "target_id": 42, "confidence": 0.88,
                 "expected_progress": 0.79, "reason": "most likely to reveal Forward"},
            ],
        },
        frame=2,
    )

    assert [a["family"] for a in parsed.next_actions] == ["reveal_actions", "hover"]
    assert parsed.next_action["family"] == "reveal_actions"
    assert parsed.confidence == 0.88


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


def test_a_single_next_action_still_parses_as_a_one_move_frontier():
    parsed = _parse_proposal(
        {
            "world_model": {"surface": "conversation"},
            "next_action": {"family": "press_escape", "confidence": 0.8},
        },
        frame=3,
    )
    assert parsed.next_action["family"] == "press_escape"
    assert [a["family"] for a in parsed.next_actions] == ["press_escape"]


def test_the_consulted_head_stays_first_and_the_model_ranking_supplies_siblings():
    from plugin.agent.unified_cognition import ranked_action_candidates

    proposal = UnifiedProposal(
        next_action={"family": "resolve_entity", "text": "Pallavi", "confidence": 0.8},
        next_actions=[
            {"family": "resolve_entity", "text": "Pallavi", "confidence": 0.8},
            {"family": "locate_content", "text": "zarooratwala", "confidence": 0.7},
        ],
    )
    families = [a["family"] for a in ranked_action_candidates(proposal)]

    assert families == ["resolve_entity", "locate_content"]


def test_an_inadmissible_first_choice_falls_to_the_next_ranked_move(monkeypatch):
    """A considered alternative beats sending the run to the slow reasoner."""
    proposal = UnifiedProposal(
        observed_state={"surface": "conversation"},
        next_action={"family": "click", "confidence": 0.9},
        next_actions=[
            {"family": "click", "confidence": 0.9},
            {"family": "type", "text": "Pallavi", "confidence": 0.8, "expected_progress": 0.6},
        ],
        confidence=0.9,
    )

    action, features = _fast_path_with(monkeypatch, proposal, ExecutionState())

    assert action is not None
    assert action.action_family == "type_query"
    trace = features.extras["unified_cognition"]
    assert trace["action_rank"] == 1
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
