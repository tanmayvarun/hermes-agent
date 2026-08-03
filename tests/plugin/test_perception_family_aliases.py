from plugin.agent.decision import DecisionEngine
from plugin.agent.features import StateFeatures
from plugin.agent.goal import Goal
from plugin.perception.representation import structured_perception_bridge
from plugin.worldmodel.model import WorldModel


def test_bridge_recovers_recommendation_from_world_when_features_rebuilt():
    """Feature builders make a fresh StateFeatures every cycle.

    The screen-understanding recommendation must survive that rebuild, or the
    decision engine never sees it and falls back to Observe forever.
    """
    world = WorldModel(active_app="WhatsApp")
    world.last_perception_synthesis = {
        "cache_key": "k",
        "summary": {
            "screen_type": "chat_list",
            "active_surface": "main_window",
            "likely_next_family": "chat_selection",
            "likely_next_target": "chat_item_pallavi",
            "likely_next_text": "Pallavi",
            "confidence": 0.95,
        },
    }
    bridged = structured_perception_bridge(features=StateFeatures(), world=world)
    assert bridged.get("likely_next_family") == "chat_selection"
    assert bridged.get("likely_next_text") == "Pallavi"
    assert bridged.get("confidence") == 0.95


def test_ax_content_starved_reads_worldview_components():
    starved = StateFeatures(extras={"worldview_score": {"components": {"app_content_node_count": 0}}})
    rich = StateFeatures(extras={"worldview_score": {"components": {"app_content_node_count": 12}}})
    assert DecisionEngine._ax_content_starved(starved) is True
    assert DecisionEngine._ax_content_starved(rich) is False
    # Absent evidence must not be read as "starved".
    assert DecisionEngine._ax_content_starved(StateFeatures()) is False


def test_normalize_search_with_text_becomes_type_query():
    goal = Goal(
        kind="whatsapp_forward_message",
        contact="Kulvinder",
        target_contact="Pallavi",
        link_query="zarooratwala",
    )
    summary = {
        "likely_next_family": "search",
        "likely_next_target": "search_input",
        "likely_next_text": "Kulvinder",
        "confidence": 0.95,
    }
    fam = DecisionEngine._normalize_perception_family("search", summary, goal)
    assert fam == "type_query"
    action, target, text = DecisionEngine._family_to_action("search", goal, summary)
    assert action == "Type"
    assert target == "Search"
    assert text == "Kulvinder"


def test_chat_selection_falls_back_to_search_when_ax_content_starved():
    goal = Goal(
        kind="whatsapp_forward_message",
        contact="Pallavi",
        target_contact="Tanmay",
        link_query="zarooratwala",
    )
    summary = {
        "likely_next_family": "chat_selection",
        "likely_next_target": "Pallavi",
        "likely_next_text": "Pallavi",
        "confidence": 0.95,
    }
    starved = StateFeatures(extras={"app_content_node_count": 0})
    rich = StateFeatures(extras={"app_content_node_count": 24})

    assert DecisionEngine._normalize_perception_family("chat_selection", summary, goal, starved) == "compose_search_query"
    assert DecisionEngine._normalize_perception_family("chat_selection", summary, goal, rich) == "open_contact"

    action, target, text = DecisionEngine._family_to_action("chat_selection", goal, summary, starved)
    assert action == "ComposeSearchQuery"


def test_open_entity_falls_back_to_compose_when_ax_content_starved():
    goal = Goal(
        kind="whatsapp_forward_message",
        contact="Pallavi",
        target_contact="Tanmay",
        link_query="zarooratwala",
    )
    summary = {"likely_next_target": "Pallavi", "likely_next_text": "Pallavi"}
    starved = StateFeatures(extras={"app_content_node_count": 0})
    rich = StateFeatures(extras={"app_content_node_count": 24})

    # Bare entity name → compose (author), not type_query("Pallavi").
    assert DecisionEngine._normalize_perception_family("open_entity", summary, goal, starved) == "compose_search_query"
    assert DecisionEngine._normalize_perception_family("open_entity", summary, goal, rich) == "open_entity"


def test_open_entity_stays_when_search_already_holds_contact():
    goal = Goal(
        kind="whatsapp_forward_message",
        contact="Pallavi",
        target_contact="Tanmay",
        link_query="zarooratwala",
    )
    summary = {"likely_next_target": "Pallavi", "likely_next_text": "Pallavi"}
    held = StateFeatures(
        extras={"app_content_node_count": 0, "search_query_hint": "Pallavi"},
    )
    assert DecisionEngine._normalize_perception_family("open_entity", summary, goal, held) == "open_entity"
    assert DecisionEngine._search_holds_query(held, "Pallavi") is True


def test_unseen_family_labels_resolve_by_intent():
    goal = Goal(
        kind="whatsapp_forward_message",
        contact="Pallavi",
        target_contact="Tanmay",
        link_query="zarooratwala",
    )
    summary = {"likely_next_target": "Pallavi", "likely_next_text": "Pallavi"}
    starved = StateFeatures(extras={"app_content_node_count": 0})
    rich = StateFeatures(extras={"app_content_node_count": 24})

    # Labels the perceptor has emitted across runs, none of them canonical.
    for label in ("chat_entry", "chat_row", "conversation-item", "recipient pick"):
        assert DecisionEngine._normalize_perception_family(label, summary, goal, starved) == "compose_search_query"
        assert DecisionEngine._normalize_perception_family(label, summary, goal, rich) == "open_contact"

    # Wholly unknown wording still yields a grounded action, never Observe.
    assert DecisionEngine._normalize_perception_family("pick_the_thing", summary, goal, starved) == "compose_search_query"

    # Window/focus chatter must stay an observation, not a fake click.
    assert DecisionEngine._normalize_perception_family("window_management", summary, goal, starved) == "observe"


def test_enumerated_search_candidate_gets_perception_grounding():
    """An enumerated search action carries no grounding of its own.

    Without endorsement the grounding filter drops it and only Observe
    survives, which is what stalled the live forward runs.
    """
    from plugin.agent.action import Action

    cand = Action(action="Type", semantic_target="Search", action_family="type_query")
    assert cand.grounding_confidence == 0.0

    endorsed = DecisionEngine._endorse_with_perception(
        [cand], "type_query", 0.95, {"likely_next_text": "Pallavi"}
    )
    assert endorsed == 1
    assert cand.grounding_confidence == 0.95
    assert cand.grounding_reason == "multimodal_perception"
    assert cand.text == "Pallavi"
    assert cand.grounding_confidence >= DecisionEngine().action_grounding_confidence_threshold()

    # Click-style families still require real entity grounding.
    click = Action(action="Click", semantic_target="Pallavi", action_family="open_contact")
    assert DecisionEngine._endorse_with_perception([click], "open_contact", 0.95, {}) == 0
    assert click.grounding_confidence == 0.0


def test_promote_perception_search_alias(monkeypatch):
    engine = DecisionEngine(selector_enabled=False)
    goal = Goal(
        kind="whatsapp_forward_message",
        contact="Kulvinder",
        target_contact="Pallavi",
        link_query="zarooratwala",
    )
    world = WorldModel(active_app="WhatsApp")
    features = StateFeatures(
        extras={
            "perception_summary": {
                "likely_next_family": "search",
                "likely_next_target": "search_input",
                "likely_next_text": "Kulvinder",
                "confidence": 0.95,
            }
        }
    )
    monkeypatch.setattr(
        "plugin.agent.decision.structured_perception_bridge",
        lambda **kwargs: dict(features.extras["perception_summary"]),
    )
    promoted = engine._promote_perception_candidate(goal, world, features, [])
    assert promoted is not None
    assert promoted.action_family == "type_query"
    assert promoted.action == "Type"
    assert promoted.text == "Kulvinder"
    assert promoted.semantic_target == "Search"
    assert promoted.grounding_confidence >= 0.9
