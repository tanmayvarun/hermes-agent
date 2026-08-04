"""The model's account of the screen decides the target, not string similarity.

These cover one live failure with four separate causes, each of which was on its
own enough to send a click to the wrong control. WhatsApp exposes no accessibility
content, so on a search-results screen the perceptor reports two objects whose
text is near-identical: the chat row it wants ("Kulvinder Ji - Video call") and
the search field echoing what was typed ("Kulvinder"). Every mechanism that picks
between them by label prefers the field, because the echo matches the query
exactly and the row carries extra words. The model can tell them apart -- it
reports their kinds and flags which matches the goal -- so the runtime's job is
to carry that verdict through, not to re-derive it.
"""

from __future__ import annotations

import pytest

from plugin.agent.goal import Goal
from plugin.agent.unified_cognition import (
    UnifiedProposal,
    _goal_matched_object,
    _resolve_target_entity,
    materialize_vision_entities,
    proposal_to_action,
)
from plugin.worldmodel.model import WorldModel


def _search_results_proposal(**action: object) -> UnifiedProposal:
    """A search-results reading: the wanted row, and the field echoing the query."""
    proposal = UnifiedProposal()
    proposal.confidence = 0.9
    proposal.point_scale = 1.0
    proposal.point_origin = (0.0, 0.0)
    proposal.world_model = {
        "frame": 2,
        "surface": "search_results",
        "objects": [
            {
                "id": "kulvinder_ji_row",
                "kind": "chat_row",
                "text": "Kulvinder Ji - Video call",
                "point": [135, 155],
                "matches_goal": True,
            },
            {
                "id": "search_bar",
                "kind": "search_field",
                "text": "Kulvinder",
                "point": [150, 85],
                "matches_goal": False,
            },
        ],
    }
    proposal.observed_state = {"surface": "search_results"}
    proposal.next_action = dict(action)
    # A projection of the document's objects, as the parser builds it.
    proposal.visible_objects = list(proposal.world_model["objects"])
    return proposal


def _world_from(proposal: UnifiedProposal) -> WorldModel:
    world = WorldModel()
    assert materialize_vision_entities(world, proposal) == 2
    return world


def _entity_label(world: WorldModel, entity_id: object) -> str:
    entity = world.entities.get(int(entity_id))  # type: ignore[arg-type]
    return str(getattr(entity, "label", ""))


# --- the model's object id survives materialisation ---------------------------


def test_the_models_own_id_for_an_object_is_kept():
    """Entities are keyed by int; the model names its objects in words.

    Dropping the word-form id severed the only link from a cited target_id back
    to the object meant.
    """
    proposal = _search_results_proposal(family="open_entity")
    world = _world_from(proposal)
    ids = {
        str(e.attributes.get("vision_object_id"))
        for e in world.entities.values()
        if isinstance(getattr(e, "attributes", None), dict)
    }
    assert ids == {"kulvinder_ji_row", "search_bar"}


def test_a_cited_word_id_resolves_to_the_object_it_names():
    proposal = _search_results_proposal(family="open_entity")
    world = _world_from(proposal)
    entity = _resolve_target_entity(world, "kulvinder_ji_row")
    assert entity is not None
    assert entity.label == "Kulvinder Ji - Video call"


def test_a_cited_id_is_matched_regardless_of_case():
    proposal = _search_results_proposal(family="open_entity")
    world = _world_from(proposal)
    assert _resolve_target_entity(world, "Kulvinder_JI_Row") is not None


def test_an_id_naming_nothing_on_screen_resolves_to_nothing():
    proposal = _search_results_proposal(family="open_entity")
    world = _world_from(proposal)
    assert _resolve_target_entity(world, "compose_box") is None


def test_an_integer_key_still_resolves():
    """The word-form lookup is an addition, not a replacement."""
    proposal = _search_results_proposal(family="open_entity")
    world = _world_from(proposal)
    key = min(world.entities)
    assert _resolve_target_entity(world, key) is not None


# --- the relevance verdict outranks the label --------------------------------


def test_the_uniquely_goal_matched_object_is_found():
    proposal = _search_results_proposal(family="resolve_entity")
    world = _world_from(proposal)
    winner = _goal_matched_object(world)
    assert winner is not None
    assert winner.label == "Kulvinder Ji - Video call"


def test_two_claimed_matches_are_not_silently_resolved():
    """Two claimed matches is the ambiguity resolve_entity exists to settle.

    Picking one here would move the coin toss rather than remove it.
    """
    proposal = _search_results_proposal(family="resolve_entity")
    for obj in proposal.visible_objects:
        obj["matches_goal"] = True
    world = _world_from(proposal)
    assert _goal_matched_object(world) is None


def test_no_claimed_match_leaves_the_label_path_in_charge():
    proposal = _search_results_proposal(family="resolve_entity")
    for obj in proposal.visible_objects:
        obj["matches_goal"] = False
    world = _world_from(proposal)
    assert _goal_matched_object(world) is None


# --- end to end: which control does the decision aim at? ---------------------


def test_resolve_entity_aims_at_the_row_not_the_field_echoing_the_query():
    """The observed live failure, top to bottom.

    The model asked to resolve 'Kulvinder' among the candidates. Grounding by
    label picks the search field, whose text is the query exactly.
    """
    proposal = _search_results_proposal(
        family="resolve_entity", text="Kulvinder", confidence=0.88
    )
    world = _world_from(proposal)
    action, reason = proposal_to_action(proposal, Goal(kind="whatsapp_forward_message"), world)
    assert action is not None, reason
    assert action.target_entity_id is not None
    assert _entity_label(world, action.target_entity_id) == "Kulvinder Ji - Video call"


def test_resolve_entity_carries_geometry_at_all():
    """Before the fix this family threaded no target, so the click was re-derived."""
    proposal = _search_results_proposal(family="resolve_entity", text="Kulvinder")
    world = _world_from(proposal)
    action, reason = proposal_to_action(proposal, Goal(kind="whatsapp_forward_message"), world)
    assert action is not None, reason
    assert action.target_entity_id is not None, "resolve_entity must ground its choice"


def test_an_explicit_target_id_beats_the_relevance_flag():
    """A stated choice is not second-guessed, even against the flags."""
    proposal = _search_results_proposal(
        family="open_entity", target_id="search_bar", text="Kulvinder"
    )
    world = _world_from(proposal)
    action, reason = proposal_to_action(proposal, Goal(kind="whatsapp_forward_message"), world)
    assert action is not None, reason
    assert _entity_label(world, action.target_entity_id) == "Kulvinder"


def test_open_entity_without_any_id_uses_the_relevance_flag():
    proposal = _search_results_proposal(family="open_entity", text="Kulvinder")
    world = _world_from(proposal)
    action, reason = proposal_to_action(proposal, Goal(kind="whatsapp_forward_message"), world)
    assert action is not None, reason
    assert _entity_label(world, action.target_entity_id) == "Kulvinder Ji - Video call"


# --- the prompt asks for the id ----------------------------------------------


def test_the_protocol_asks_for_an_id_when_acting_on_something_visible():
    from plugin.agent.unified_cognition import _SYSTEM_PROMPT

    assert "target_id" in _SYSTEM_PROMPT
    assert "world_model.objects" in _SYSTEM_PROMPT


@pytest.mark.parametrize("family", ["open_entity", "resolve_entity", "reveal_actions"])
def test_every_family_that_points_at_something_grounds_it(family: str):
    from plugin.agent.unified_cognition import _GROUNDED_POINTER_FAMILIES

    assert family in _GROUNDED_POINTER_FAMILIES


# --- deliberating is a way of deciding, not a reason to stop looking ----------
#
# The executive raises force_deliberation for THINK and for a PROBE wanting a
# fresh reveal, meaning "do not just take the fast pick". Reading it as "skip the
# perceptor" also skipped what the perceptor call *does*: refresh the world
# document, run the critic, and materialise the geometry above. The deliberative
# path then reasoned over the previous frame -- in the live run, one taken before
# the query was even typed -- and the enumerate/score machinery acted on it.


def _deliberation_fixture(monkeypatch):
    from plugin.agent.decision import DecisionEngine
    from plugin.agent.features import StateFeatures
    from plugin.agent.runtime.state import ExecutionState

    monkeypatch.setenv("HERMES_UNIFIED_COGNITION", "1")
    proposal = _search_results_proposal(family="open_entity", text="Kulvinder")
    world = _world_from(proposal)

    calls: list[str] = []

    def _spy(goal, world_, features, execution_state=None):
        calls.append("consulted")
        return proposal

    monkeypatch.setattr("plugin.agent.unified_cognition.consult_unified_cognition", _spy)
    return DecisionEngine(), Goal(kind="whatsapp_forward_message"), world, StateFeatures(
        app="WhatsApp", extras={}
    ), ExecutionState(), calls


def test_a_forced_deliberation_frame_still_perceives(monkeypatch):
    engine, goal, world, features, state, calls = _deliberation_fixture(monkeypatch)
    state.force_deliberation = True

    engine._unified_fast_path(goal, world, features, state, [])

    assert calls == ["consulted"], "deliberation must not skip the look"


def test_a_forced_deliberation_frame_withholds_only_the_action(monkeypatch):
    engine, goal, world, features, state, _ = _deliberation_fixture(monkeypatch)
    state.force_deliberation = True

    action = engine._unified_fast_path(goal, world, features, state, [])

    assert action is None, "the executive asked to deliberate, so do not act on the fast pick"
    assert features.extras["unified_cognition"]["withheld_for_deliberation"] is True


def test_the_deliberation_request_is_consumed_once(monkeypatch):
    engine, goal, world, features, state, _ = _deliberation_fixture(monkeypatch)
    state.force_deliberation = True

    engine._unified_fast_path(goal, world, features, state, [])

    assert state.force_deliberation is False
    assert features.extras.get("forced_deliberation") is True


def test_an_ordinary_frame_acts_on_the_proposal(monkeypatch):
    engine, goal, world, features, state, _ = _deliberation_fixture(monkeypatch)

    action = engine._unified_fast_path(goal, world, features, state, [])

    assert action is not None
    assert features.extras["unified_cognition"]["withheld_for_deliberation"] is False


def test_the_perception_reaches_the_trace_even_when_the_action_is_withheld(monkeypatch):
    """A withheld frame must still be diagnosable: the reading is the evidence."""
    engine, goal, world, features, state, _ = _deliberation_fixture(monkeypatch)
    state.force_deliberation = True

    engine._unified_fast_path(goal, world, features, state, [])

    recorded = features.extras["unified_cognition"]
    assert recorded.get("world_model", {}).get("surface") == "search_results"
