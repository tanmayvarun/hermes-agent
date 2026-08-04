"""The agent is told how long it has been stuck and what it has already tried.

A live run spent thirteen minutes reissuing one right-click. The runtime knew:
it logged seven no-progress replans and four semantic repeats, and every event
carried elapsed time. None of it reached the model, which is the party that picks
the next move -- it sees a single frame and its own previous document, so it has
neither a clock nor any memory of the loop it is in. Each attempt therefore
arrived looking like the first.

The consecutive-repeat counter did not help, because a stuck agent rarely repeats
a move twice running: the failure prompts a different move, which fails too and
leads back. right_click -> resolve_entity -> right_click held that counter at 1
throughout.
"""

from __future__ import annotations

from plugin.agent.features import StateFeatures
from plugin.agent.goal import Goal
from plugin.agent.runtime.state import MAX_TRACKED_ATTEMPTS, ExecutionState
from plugin.agent.unified_cognition import _stuck_report, build_decision_packet
from plugin.worldmodel.model import WorldModel


def _goal() -> Goal:
    return Goal(kind="whatsapp_forward_message", contact="Pallavi", target_contact="Kulvinder")


# --- the ledger counts what the consecutive counter cannot -------------------


def test_the_same_move_twice_running_is_counted():
    state = ExecutionState()
    state.note_attempt(family="reveal_actions", target="msg", surface="conversation")
    entry = state.note_attempt(family="reveal_actions", target="msg", surface="conversation")
    assert entry["attempts"] == 2


def test_an_alternating_loop_is_counted_too():
    """The live shape: A, B, A, B. Nothing repeats consecutively."""
    state = ExecutionState()
    for _ in range(3):
        state.note_attempt(family="reveal_actions", target="msg", surface="conversation")
        state.note_attempt(family="resolve_entity", target="msg", surface="conversation")
    assert state.attempts_for(family="reveal_actions", target="msg", surface="conversation") == 3
    assert state.attempts_for(family="resolve_entity", target="msg", surface="conversation") == 3


def test_the_same_move_on_a_different_target_is_a_different_move():
    state = ExecutionState()
    state.note_attempt(family="open_entity", target="Kulvinder", surface="search")
    state.note_attempt(family="open_entity", target="Pallavi", surface="search")
    assert state.attempts_for(family="open_entity", target="Kulvinder", surface="search") == 1
    assert state.attempts_for(family="open_entity", target="Pallavi", surface="search") == 1


def test_the_same_move_on_a_different_surface_is_a_different_move():
    """Right-clicking a row in a picker is not the move that failed in a chat."""
    state = ExecutionState()
    state.note_attempt(family="reveal_actions", target="msg", surface="conversation")
    state.note_attempt(family="reveal_actions", target="msg", surface="forward_picker")
    assert state.attempts_for(family="reveal_actions", target="msg", surface="conversation") == 1


def test_targets_are_compared_case_and_space_insensitively():
    """OCR and AX disagree on casing and spacing for the same control."""
    state = ExecutionState()
    state.note_attempt(family="Open_Entity", target="Kulvinder  Ji", surface="Search")
    assert state.attempts_for(family="open_entity", target="kulvinder ji", surface="search") == 1


def test_what_came_of_each_attempt_is_kept():
    state = ExecutionState()
    state.note_attempt(family="reveal_actions", target="msg", effect="no_transition")
    entry = state.note_attempt(family="reveal_actions", target="msg", effect="no_transition")
    assert entry["effects"] == ["no_transition", "no_transition"]


def test_a_move_without_a_family_is_not_ledgered():
    state = ExecutionState()
    assert state.note_attempt(family="", target="msg") == {}
    assert state.action_attempts == {}


def test_the_ledger_is_bounded():
    """A long run must not turn its own history into unbounded context."""
    state = ExecutionState()
    for i in range(MAX_TRACKED_ATTEMPTS + 25):
        state.note_attempt(family="click", target=f"thing-{i}", iteration=i)
    assert len(state.action_attempts) <= MAX_TRACKED_ATTEMPTS


def test_the_oldest_entries_are_the_ones_dropped():
    state = ExecutionState()
    state.note_attempt(family="click", target="first", iteration=1)
    for i in range(MAX_TRACKED_ATTEMPTS + 5):
        state.note_attempt(family="click", target=f"later-{i}", iteration=100 + i)
    assert state.attempts_for(family="click", target="first") == 0


# --- the clock and the ledger reach the model -------------------------------


def test_time_without_progress_is_reported():
    state = ExecutionState()
    state.seconds_since_progress = 651.9
    state.no_progress_budget_s = 45.0
    report = _stuck_report(state)
    assert report["seconds_since_anything_advanced"] == 651.9
    assert report["stalled"] is True


def test_being_within_the_budget_is_reported_as_not_stalled():
    state = ExecutionState()
    state.seconds_since_progress = 12.0
    state.no_progress_budget_s = 45.0
    assert _stuck_report(state)["stalled"] is False


def test_a_fresh_run_reports_nothing_to_worry_about():
    assert _stuck_report(ExecutionState()) == {}


def test_repeated_moves_are_listed_with_their_outcomes():
    state = ExecutionState()
    for _ in range(3):
        state.note_attempt(family="reveal_actions", target="msg", effect="no_transition")
    listed = _stuck_report(state)["moves_already_tried_more_than_once"]
    assert listed[0]["family"] == "reveal_actions"
    assert listed[0]["attempts"] == 3
    assert "no_transition" in listed[0]["effects"]


def test_a_move_tried_once_is_not_held_against_the_model():
    state = ExecutionState()
    state.note_attempt(family="open_entity", target="Kulvinder")
    assert "moves_already_tried_more_than_once" not in _stuck_report(state)


def test_the_most_repeated_move_is_listed_first():
    state = ExecutionState()
    for _ in range(2):
        state.note_attempt(family="scroll", target="history")
    for _ in range(5):
        state.note_attempt(family="reveal_actions", target="msg")
    listed = _stuck_report(state)["moves_already_tried_more_than_once"]
    assert listed[0]["family"] == "reveal_actions"


def test_the_packet_carries_the_stuck_signals():
    state = ExecutionState()
    state.seconds_since_progress = 400.0
    state.no_progress_budget_s = 45.0
    for _ in range(3):
        state.note_attempt(family="reveal_actions", target="msg", effect="no_transition")

    packet = build_decision_packet(_goal(), WorldModel(), StateFeatures(app="WhatsApp"), state)

    signals = packet["stuck_signals"]
    assert signals["seconds_since_anything_advanced"] == 400.0
    assert signals["moves_already_tried_more_than_once"][0]["attempts"] == 3


def test_a_healthy_packet_does_not_carry_stuck_signals():
    packet = build_decision_packet(
        _goal(), WorldModel(), StateFeatures(app="WhatsApp"), ExecutionState()
    )
    assert "stuck_signals" not in packet


def test_the_protocol_explains_what_the_signals_mean():
    from plugin.agent.unified_cognition import _SYSTEM_PROMPT

    assert "stuck_signals" in _SYSTEM_PROMPT
    assert "seconds_since_anything_advanced" in _SYSTEM_PROMPT
    assert "moves_already_tried_more_than_once" in _SYSTEM_PROMPT


def test_the_total_count_is_reported_beside_the_consecutive_one():
    """times_repeated_in_a_row stayed at 1 through the live loop; this is the fix."""
    from plugin.agent.action import PlanStep

    state = ExecutionState()
    state.accepted_surface = "conversation"
    state.last_plan_step = PlanStep(
        action="ContextClick", action_family="reveal_actions", semantic_target="msg"
    )
    state.repeated_action_count = 1
    for _ in range(3):
        state.note_attempt(family="reveal_actions", target="msg", surface="conversation")

    packet = build_decision_packet(_goal(), WorldModel(), StateFeatures(app="WhatsApp"), state)

    last = packet["last_action"]
    assert "times_repeated_in_a_row" not in last, "it genuinely was not consecutive"
    assert last["times_tried_here_in_total"] == 3
