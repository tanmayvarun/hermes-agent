"""The perceptor eval must fail loudly on the ways a perceptor actually fails.

An eval that scores everything 100% is worse than no eval, so each test here
constructs a specific defect and asserts the corresponding check catches it.
"""

from plugin.agent.unified_cognition import ALLOWED_ACTIONS, UnifiedProposal, should_escalate
from plugin.agent.features import StateFeatures
from plugin.experiments.perceptor_eval import (
    canonical_surface,
    score_actionability,
    score_input_contract,
    score_scene_representation,
    score_summary,
    score_world_update,
)


def _packet(**overrides):
    packet = {
        "goal": {
            "operation": "whatsapp_forward_message",
            "source_conversation": "Pallavi",
            "source_query": "zarooratwala",
            "destination": "Tanmay",
        },
        "world_model": {
            "surface": "",
            "open_conversation": "",
            "objects": [],
            "beliefs": [],
            "progress": {"phase": "", "objective": "", "notes": ""},
            "attempts": [],
            "exhausted": [],
        },
        "observation": {
            "frame": 3,
            "app": "WhatsApp",
            "ax_node_count": 2,
            "ax_content_node_count": 0,
            "ax_evidence": [{"id": 2, "role": "AXWindow", "label": "WhatsApp", "bounds": [105, 25, 1710, 988]}],
        },
        # Mirrored from the runtime rather than restated, so widening the
        # vocabulary does not silently leave the eval scoring an older contract.
        "allowed_actions": list(ALLOWED_ACTIONS),
    }
    packet.update(overrides)
    return packet


def _good_image():
    return {"present": True, "size": [1920, 1080], "mean_luma": 226.0, "stddev_luma": 60.0, "bytes": 120000}


def _proposal(**overrides) -> UnifiedProposal:
    base = dict(
        observed_state={
            "surface": "chat_list",
            "open_conversation": "",
            "target_object_visible": False,
            "target_object_id": None,
        },
        belief_updates=[{"predicate": "source_conversation_open", "value": False,
                         "confidence": 0.9, "evidence": ["no conversation pane"]}],
        next_action={"family": "click", "target_id": None, "target_point": [193, 83], "confidence": 0.9},
        missing_evidence=["AX nodes for search bar"],
        scene_summary="WhatsApp is open showing the chat list. I will click the search bar to find Pallavi.",
        confidence=0.9,
    )
    base.update(overrides)
    return UnifiedProposal(**base)


def _names(checks):
    return {c.name: c.passed for c in checks}


# ---------------------------------------------------------------- input


def test_input_contract_passes_on_a_real_frame():
    checks = _names(score_input_contract(_packet(), _good_image()))
    assert all(checks.values()), [k for k, v in checks.items() if not v]


def test_black_screenshot_is_caught():
    """A locked screen produced exactly this and the agent kept going anyway."""
    blank = {"present": True, "size": [1920, 1080], "mean_luma": 0.4, "stddev_luma": 0.1, "bytes": 900}
    checks = _names(score_input_contract(_packet(), blank))
    assert checks["screenshot_not_blank"] is False
    assert checks["screenshot_has_detail"] is False


def test_missing_screenshot_is_caught():
    checks = _names(score_input_contract(_packet(), {"present": False}))
    assert checks["screenshot_present"] is False


def test_ax_evidence_without_ids_is_caught():
    packet = _packet()
    packet["observation"]["ax_evidence"] = [{"role": "AXButton", "label": "Search"}]
    checks = _names(score_input_contract(packet, _good_image()))
    assert checks["ax_evidence_entries_have_ids"] is False


def test_credentials_in_packet_are_caught():
    packet = _packet()
    packet["observation"]["api_key"] = "sk-secret"
    checks = _names(score_input_contract(packet, _good_image()))
    assert checks["no_credentials_in_packet"] is False


def test_a_runtime_computed_world_in_the_packet_is_caught():
    """Shipping the runtime's own guess is the defect this design removes.

    Recomputing predicates from accessibility each cycle both discarded the
    model's belief and, on surfaces AX cannot read, asserted the opposite of
    what was on screen.
    """
    packet = _packet()
    packet["task_state"] = {"phase": "OPEN_SOURCE", "source_conversation_open": False}
    checks = _names(score_input_contract(packet, _good_image()))
    assert checks["packet_has_no_runtime_task_state"] is False


def test_a_packet_without_the_prior_world_is_caught():
    """No identity path means the model starts from nothing every frame."""
    packet = _packet()
    packet.pop("world_model")
    checks = _names(score_input_contract(packet, _good_image()))
    assert checks["packet_carries_prior_world"] is False


# ------------------------------------------------------- scene representation


def test_scene_representation_passes_on_a_good_reading():
    checks = _names(score_scene_representation(_proposal(), _packet()))
    assert all(checks.values()), [k for k, v in checks.items() if not v]


def test_uncanonical_surface_label_is_caught():
    proposal = _proposal(observed_state={"surface": "some novel screen", "target_object_visible": False})
    checks = _names(score_scene_representation(proposal, _packet()))
    assert checks["surface_is_canonical"] is False


def test_ungrounded_pointer_action_is_caught():
    """A confident click naming no target is the silent failure mode."""
    proposal = _proposal(next_action={"family": "click", "target_id": None, "confidence": 0.95})
    checks = _names(score_scene_representation(proposal, _packet()))
    assert checks["pointer_action_is_grounded"] is False


def test_action_outside_allowed_set_is_caught():
    proposal = _proposal(next_action={"family": "teleport", "target_point": [1, 2], "confidence": 0.9})
    checks = _names(score_scene_representation(proposal, _packet()))
    assert checks["action_in_allowed_set"] is False


def test_forgetting_the_open_conversation_is_caught():
    """The amnesia that made the agent undo its own progress.

    Still reading the screen as a conversation while dropping which one is open
    sent the phase machine back to the chat list it had already left.
    """
    packet = _packet()
    packet["world_model"]["open_conversation"] = "Pallavi"
    proposal = _proposal(observed_state={"surface": "conversation", "open_conversation": "",
                                         "target_object_visible": True})
    checks = _names(score_scene_representation(proposal, packet))
    assert checks["open_conversation_not_silently_dropped"] is False


def test_moving_to_a_new_surface_is_not_forgetting():
    """Leaving a conversation legitimately clears it, and must not be flagged."""
    packet = _packet()
    packet["world_model"]["open_conversation"] = "Pallavi"
    proposal = _proposal(observed_state={"surface": "forward_picker", "open_conversation": "",
                                         "target_object_visible": True})
    checks = _names(score_scene_representation(proposal, packet))
    assert checks["open_conversation_not_silently_dropped"] is True


def test_surface_folding_covers_observed_label_drift():
    """These five labels all came from one static screen in one live run."""
    for raw in ("WhatsApp Main Window", "WhatsApp Chats List", "WhatsApp Chat List",
                "WhatsApp Main Chat List", "chat_list"):
        assert canonical_surface(raw) == "chat_list", raw
    assert canonical_surface("Forward to...") == "forward_picker"
    assert canonical_surface("") == ""


# ---------------------------------------------------------------- summary


def test_summary_quality_passes_on_real_prose():
    checks = _names(score_summary(_proposal()))
    assert all(checks.values()), [k for k, v in checks.items() if not v]


def test_missing_summary_is_caught():
    checks = _names(score_summary(_proposal(scene_summary="")))
    assert checks["summary_present"] is False
    assert checks["summary_long_enough"] is False


def test_summary_contradicting_structure_is_caught():
    """Prose and structure disagreeing is the boundary bug in miniature."""
    proposal = _proposal(
        observed_state={"surface": "chat_list", "open_conversation": "", "target_object_visible": False},
        scene_summary="The conversation with Pallavi is open and the link is visible on screen.",
    )
    checks = _names(score_summary(proposal))
    assert checks["summary_agrees_with_structure"] is False


def test_json_blob_is_not_accepted_as_a_summary():
    checks = _names(score_summary(_proposal(scene_summary='{"surface": "chat_list", "open": false}')))
    assert checks["summary_is_prose"] is False


# ------------------------------------------------------------- actionability


def test_actionability_passes_when_runtime_would_execute():
    checks = _names(score_actionability(_proposal(), _packet()))
    assert all(checks.values()), [k for k, v in checks.items() if not v]


def test_targetless_scroll_is_not_flagged_as_unexecutable():
    """Scroll runs against a computed anchor, so it needs no target."""
    proposal = _proposal(
        observed_state={"surface": "conversation", "open_conversation": "Pallavi",
                        "target_object_visible": False},
        next_action={"family": "scroll", "target_id": None, "target_point": None, "confidence": 0.85},
        confidence=0.85,
    )
    checks = _names(score_actionability(proposal, _packet()))
    assert checks["action_is_executable"] is True


def test_actionability_catches_readings_the_runtime_rejects():
    """The exact regression that made the agent loop on Observe.

    The perceptor was confident and coordinate-grounded, but every reading
    named an evidence gap and the gate treated that as a veto.
    """
    proposal = _proposal(next_action={"family": "click", "target_id": None, "confidence": 0.6},
                         confidence=0.6)
    checks = _names(score_actionability(proposal, _packet()))
    assert checks["reading_is_admissible"] is False
    assert checks["fast_path_accepts_reading"] is False


# -------------------------------------------------------------- world update


def _document(**overrides):
    document = {
        "surface": "conversation",
        "open_conversation": "Pallavi",
        "objects": [{"id": "o1", "kind": "message", "text": "zarooratwala.com",
                     "point": [900, 500], "matches_goal": True, "seen_on_frame": 3}],
        "beliefs": [{"predicate": "source_conversation_open", "value": True, "confidence": 0.95,
                     "evidence": ["header reads Pallavi"], "confirmed_on_frame": 3}],
        "progress": {"phase": "FIND_LINK", "objective": "locate the link", "notes": ""},
        "attempts": [{"frame": 2, "action": "scroll", "target": "", "result": "ok: new messages"}],
        "exhausted": [],
    }
    document.update(overrides)
    return document


def test_world_update_passes_on_a_well_formed_document():
    proposal = _proposal(world_model=_document())
    checks = _names(score_world_update(proposal, _packet()))
    assert all(checks.values()), [k for k, v in checks.items() if not v]


def test_a_belief_without_evidence_is_caught():
    """Unsourced beliefs are the ones that cannot be re-checked or retracted."""
    document = _document(beliefs=[{"predicate": "forward_dialog_open", "value": True,
                                   "confidence": 0.9, "evidence": [], "confirmed_on_frame": 3}])
    checks = _names(score_world_update(_proposal(world_model=document), _packet()))
    assert checks["beliefs_carry_evidence"] is False


def test_an_object_the_runtime_cannot_reach_is_caught():
    """An object with no point and no id can be described but never clicked."""
    document = _document(objects=[{"kind": "message", "text": "zarooratwala.com"}])
    checks = _names(score_world_update(_proposal(world_model=document), _packet()))
    assert checks["objects_are_addressable"] is False


def test_carrying_a_flagged_belief_forward_untouched_is_caught():
    """Confabulation lock-in: a claim that survives without being re-checked.

    The runtime flags it rather than deleting it, because only the model can
    look at the pixels and decide. What it may not do is ignore the flag.
    """
    packet = _packet()
    packet["unconfirmed_beliefs"] = ["forward_dialog_open (last confirmed 6 frames ago)"]
    document = _document(beliefs=[{"predicate": "forward_dialog_open", "value": True,
                                   "confidence": 0.9, "evidence": ["a dialog appeared"],
                                   "confirmed_on_frame": 1}])
    checks = _names(score_world_update(_proposal(world_model=document), packet))
    assert checks["stale_beliefs_reconfirmed_or_dropped"] is False


def test_reconfirming_a_flagged_belief_satisfies_the_check():
    packet = _packet()
    packet["unconfirmed_beliefs"] = ["source_conversation_open (last confirmed 6 frames ago)"]
    checks = _names(score_world_update(_proposal(world_model=_document()), packet))
    assert checks["stale_beliefs_reconfirmed_or_dropped"] is True


def test_a_document_that_lost_track_of_the_task_is_caught():
    document = _document(progress={"phase": "", "objective": "", "notes": ""})
    checks = _names(score_world_update(_proposal(world_model=document), _packet()))
    assert checks["progress_is_tracked"] is False


def test_packet_reports_what_the_runtime_actually_executed():
    """The model needs the raw outcome of its last proposal, unjudged.

    It cannot see what the executor did, so the runtime reports the action and
    the result verbatim and leaves the interpretation to the model.
    """
    from plugin.agent.unified_cognition import _last_action_report
    from plugin.agent.runtime.state import ExecutionState
    from plugin.agent.action import PlanStep

    state = ExecutionState()
    step = PlanStep(action="Click", semantic_target="search bar", text="")
    step.action_family = "open_search"
    state.record(step, {"ok": True, "message": "click 'target' center=(196.0, 83.0)"})

    report = _last_action_report(StateFeatures(extras={}), state)
    assert report["action"] == "Click"
    assert report["target"] == "search bar"
    assert report["result"]["ok"] is True


def test_executed_action_is_written_into_the_carried_document():
    """The search record must reflect reality, not the model's intention.

    An action can be rejected, rewritten or fail on the way to the executor, so
    what the runtime actually ran is appended to the document the model reads
    next call.
    """
    from plugin.agent.unified_cognition import UnifiedProposal, persist_world_document
    from plugin.agent.runtime.state import ExecutionState
    from plugin.agent.action import PlanStep

    state = ExecutionState()
    persist_world_document(
        state, UnifiedProposal(world_model={"surface": "conversation", "attempts": []})
    )

    step = PlanStep(action="Click", semantic_target="forward arrow", text="")
    step.action_family = "open_forward"
    state.record(step, {"ok": False, "message": "no clickable target"})

    attempts = state.unified_world_document["attempts"]
    assert attempts[-1]["action"] == "open_forward"
    assert attempts[-1]["target"] == "forward arrow"
    assert attempts[-1]["result"].startswith("failed:")


def test_repeated_readings_are_reported_as_a_count_not_a_verdict():
    """The runtime says how many identical frames it saw, nothing more.

    Declaring that the last action 'did not move the task forward' was the
    runtime interpreting the screen it cannot see. The model gets the fact and
    decides what it means.
    """
    from plugin.agent.unified_cognition import (
        UnifiedProposal,
        _remember_reading,
        repeated_readings,
    )
    from plugin.agent.runtime.state import ExecutionState

    state = ExecutionState()
    reading = UnifiedProposal(
        observed_state={"surface": "chat_list", "open_conversation": "", "target_object_visible": False},
    )
    _remember_reading(state, reading)
    assert repeated_readings(state) == 0

    _remember_reading(state, reading)
    assert repeated_readings(state) == 1


def test_scrolling_that_reveals_new_messages_is_not_a_repeat():
    """Hunting through history must not be mistaken for looping.

    While scrolling a conversation the surface name never changes, so a
    surface-only comparison would tell the model to stop doing the one thing
    that is actually searching the timeline.
    """
    from plugin.agent.unified_cognition import (
        UnifiedProposal,
        _remember_reading,
        repeated_readings,
    )
    from plugin.agent.runtime.state import ExecutionState

    state = ExecutionState()
    conversation = {"surface": "conversation", "open_conversation": "Pallavi"}
    _remember_reading(state, UnifiedProposal(
        observed_state=conversation,
        visible_objects=[{"text": "Don't share your OTP"}, {"text": "Lucky girl"}],
    ))
    _remember_reading(state, UnifiedProposal(
        observed_state=conversation,
        visible_objects=[{"text": "an older message"}, {"text": "another older one"}],
    ))

    assert repeated_readings(state) == 0


def test_scrolling_that_reveals_nothing_new_is_a_repeat():
    from plugin.agent.unified_cognition import _remember_reading, UnifiedProposal
    from plugin.agent.runtime.state import ExecutionState

    state = ExecutionState()
    stuck = UnifiedProposal(
        observed_state={"surface": "conversation", "open_conversation": "Pallavi"},
        visible_objects=[{"text": "Lucky girl"}],
    )
    _remember_reading(state, stuck)
    _remember_reading(state, stuck)
    assert state.unified_same_reading_count == 1


def test_progress_resets_the_repeat_signal():
    from plugin.agent.unified_cognition import (
        UnifiedProposal,
        _remember_reading,
        repeated_readings,
    )
    from plugin.agent.runtime.state import ExecutionState

    state = ExecutionState()
    _remember_reading(state, UnifiedProposal(observed_state={"surface": "chat_list", "open_conversation": ""}))
    _remember_reading(state, UnifiedProposal(observed_state={"surface": "chat_list", "open_conversation": ""}))
    _remember_reading(state, UnifiedProposal(observed_state={"surface": "conversation",
                                                             "open_conversation": "Pallavi"}))

    assert repeated_readings(state) == 0


def test_model_supplied_point_survives_to_a_clickable_center():
    """The point must reach the mouse, not be eaten by a bounds guard.

    A 2px box round-tripped as valid everywhere except the executor's
    degenerate-frame check, so every coordinate the perceptor produced was
    discarded at the last hop and the run failed with 'AX element not found'.
    """
    from plugin.executor.ax_action import _bounds_center
    from plugin.experiments.run_forward_message import _POINT_TARGET_SIZE

    class _Step:
        target_point = (193, 83)

    half = _POINT_TARGET_SIZE // 2
    bounds = (193 - half, 83 - half, _POINT_TARGET_SIZE, _POINT_TARGET_SIZE)
    center = _bounds_center(bounds)
    assert center == (193.0, 83.0), center


def test_evidence_gaps_alone_do_not_veto_a_confident_grounded_reading():
    proposal = _proposal(missing_evidence=["AX nodes for search bar", "chat rows"])
    features = StateFeatures(extras={})
    escalate, reason = should_escalate(proposal, features, admissible=True)
    assert escalate is False, reason
