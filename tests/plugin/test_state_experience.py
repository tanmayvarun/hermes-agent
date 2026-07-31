from __future__ import annotations

from plugin.agent.action import Action
from plugin.agent.transition.experience import StateExperience
from plugin.agent.transition.types import TransitionOutcome


def _action(family: str, target: str = "", text: str = "") -> Action:
    return Action(action="Click", action_family=family, semantic_target=target, text=text)


def test_state_experience_backtracks_to_better_family_after_repeated_dead_ends():
    exp = StateExperience()
    sig = "screen|search"

    exp.record_outcome(sig, _action("open_contact", "Kulvinder"), TransitionOutcome.PROMISING_UNRESOLVED)
    exp.record_outcome(sig, _action("type_query", "Search", "Kulvinder"), TransitionOutcome.NO_EFFECT)
    exp.record_outcome(sig, _action("type_query", "Search", "Kulvinder"), TransitionOutcome.NO_EFFECT)
    exp.record_outcome(sig, _action("type_query", "Search", "Kulvinder"), TransitionOutcome.NO_EFFECT)

    assert exp.pending_backtrack_family == "open_contact"


def test_state_experience_suppresses_family_after_repeated_dead_ends():
    exp = StateExperience()
    sig = "screen|search"

    exp.record_outcome(sig, _action("type_query", "Search", "Kulvinder"), TransitionOutcome.NO_EFFECT)
    exp.record_outcome(sig, _action("type_query", "Search", "Kulvinder"), TransitionOutcome.NO_EFFECT)
    exp.record_outcome(sig, _action("type_query", "Search", "Kulvinder"), TransitionOutcome.NO_EFFECT)

    assert exp.is_suppressed(sig, _action("type_query", "Search", "Pallavi")) is True
    kept = exp.filter_actions(sig, [_action("type_query", "Search", "Pallavi"), _action("observe")])
    assert any(a.action_family == "observe" for a in kept)
    assert all(a.action_family != "type_query" for a in kept if a.action_family)


def test_state_experience_prefers_non_observe_backtrack_sibling_over_observe():
    exp = StateExperience()
    exp.pending_backtrack_family = "open_contact"
    sig = "screen|conversation"

    actions = [
        _action("observe"),
        _action("open_contact", "Kulvinder"),
        _action("type_query", "Search", "Kulvinder"),
    ]
    kept = exp.filter_actions(sig, actions)

    assert kept
    assert all(a.action_family != "observe" for a in kept)
    assert any(a.action_family == "open_contact" for a in kept)


def test_state_experience_observe_backtrack_does_not_blacklist_siblings():
    exp = StateExperience()
    exp.pending_backtrack_family = "observe"
    sig = "screen|conversation"

    actions = [
        _action("observe"),
        _action("open_contact", "Kulvinder"),
        _action("type_query", "Search", "Kulvinder"),
    ]
    kept = exp.filter_actions(sig, actions)

    assert kept
    assert any(a.action_family == "observe" for a in kept)
    assert any(a.action_family == "open_contact" for a in kept)
    assert any(a.action_family == "type_query" for a in kept)


def test_state_experience_links_search_tree_nodes():
    exp = StateExperience()
    sig = "screen|search"

    exp.record_outcome(sig, _action("open_contact", "Kulvinder"), TransitionOutcome.PROMISING_UNRESOLVED)
    exp.record_outcome(sig, _action("type_query", "Search", "Kulvinder"), TransitionOutcome.NO_EFFECT)

    assert len(exp.search_trace) == 2
    first, second = exp.search_trace
    assert first.node_id == 1
    assert first.parent_node_id == 0
    assert second.node_id == 2
    assert second.parent_node_id == 1
    assert 2 in first.children_node_ids
    assert exp.search_tree_root_id == 1
    assert exp.current_search_node_id == 2
