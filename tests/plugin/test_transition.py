"""Transition monitor / progress / experience — no scripted next-screen gates."""

from __future__ import annotations

from plugin.agent.action import Action
from plugin.agent.goal import Goal
from plugin.agent.transition import (
    StateExperience,
    TransitionEvaluator,
    TransitionOutcome,
    assess_progress,
    compare_fingerprints,
    world_fingerprint,
)
from plugin.agent.transition.context import detect_latent_affordances, update_interaction_context
from plugin.agent.transition.types import ActionPrediction, InteractionContext, TransitionResult
from plugin.agent.transition.experience import action_experience_key
from plugin.worldmodel.entities.entity import Entity
from plugin.worldmodel.model import WorldModel


def _entity(eid: int, name: str) -> Entity:
    return Entity(
        id=eid,
        entity_type="button",
        semantic_role=name,
        label=name,
        role="AXButton",
        actions=["click"],
        attributes={"description": name},
        visible=True,
    )


def _world(names: list[str], *, open_conversation: str = "", call_state: str = "") -> WorldModel:
    wm = WorldModel()
    wm.active_app = "WhatsApp"
    ents = [_entity(i + 1, n) for i, n in enumerate(names)]
    wm.entities = {e.id: e for e in ents}
    wm.tracker._entities = dict(wm.entities)
    wm.tracker._next_id = len(ents) + 1
    if open_conversation:
        wm.overlay_hints["open_conversation"] = open_conversation
    if call_state:
        wm.overlay_hints["call_state"] = call_state
    return wm


def test_compare_fingerprints_detects_entity_change():
    before = {
        "labels": {"now…", "pallavi", "search"},
        "signature": "LIST||",
        "screen": "LIST",
        "search_query": "",
        "open_conversation": "",
        "call_state": "",
        "dialogs": (),
        "entity_count": 3,
    }
    after = {
        "labels": {"now…", "pallavi", "search", "voice call"},
        "signature": "CONVERSATION||now",
        "screen": "CONVERSATION",
        "search_query": "Now",
        "open_conversation": "now… messages",
        "call_state": "",
        "dialogs": (),
        "entity_count": 4,
    }
    tr = compare_fingerprints(before, after)
    assert tr.changed
    assert tr.change_score >= 0.12
    assert "open_conversation_changed" in tr.reasons or "screen_bucket_changed" in tr.reasons


def test_identical_world_is_no_effect_change():
    fp = {
        "labels": {"a", "b"},
        "signature": "X",
        "screen": "LIST",
        "search_query": "",
        "open_conversation": "",
        "call_state": "",
        "dialogs": (),
        "entity_count": 2,
    }
    tr = compare_fingerprints(fp, dict(fp))
    assert tr.change_score < 0.08
    assert not tr.changed


def test_progress_search_to_open_stem():
    goal = Goal(kind="whatsapp_voice_call", contact="now group")
    before = {
        "screen": "SEARCH_RESULTS",
        "search_query": "Now",
        "open_conversation": "",
        "call_state": "",
        "unexpected_dialogs": [],
        "voice_call_available": False,
    }
    after = {
        "screen": "CONVERSATION",
        "search_query": "Now",
        "open_conversation": "now… messages in chat with now…",
        "call_state": "",
        "unexpected_dialogs": [],
        "voice_call_available": True,
    }
    assessment = assess_progress(
        goal=goal,
        before_view=before,
        after_view=after,
        before_features={"has_named_entity": True, "query_matches_goal": True, "call_available": False},
        after_features={"has_named_entity": True, "query_matches_goal": True, "call_available": True},
    )
    assert assessment.progress_delta > 0.08
    assert "target_focus_gained" in assessment.notes or assessment.target_resolution_delta > 0


def test_no_effect_identical_views():
    goal = Goal(kind="whatsapp_voice_call", contact="now group")
    view = {
        "screen": "CONVERSATION",
        "search_query": "",
        "open_conversation": "now…",
        "call_state": "",
        "unexpected_dialogs": [],
        "voice_call_available": True,
    }
    feats = {"has_named_entity": True, "call_available": True, "call_ringing": False, "mean_belief": 0.8}
    from plugin.agent.transition.types import TransitionResult

    tr = TransitionResult(changed=False, stabilized=True, change_score=0.0, reasons=[])
    attempt = TransitionEvaluator().evaluate(
        goal=goal,
        before_world=_world(["Now…", "Call"]),
        after_world=_world(["Now…", "Call"]),
        action=Action(action="Click", semantic_target="Call", action_family="start_call"),
        before_view=view,
        after_view=view,
        before_features=feats,
        after_features=feats,
        transition=tr,
        before_world_id="w1",
        after_world_id="w1",
    )
    assert attempt.outcome == TransitionOutcome.NO_EFFECT.value


def test_hover_reveal_labels_surface_hidden_message_actions():
    view = {
        "screen": "CONVERSATION",
        "open_conversation": "Kulvinder Ji",
        "visible_contacts": ["Kulvinder Ji"],
        "conversation_messages": [
            {"label": "Forward"},
            {"label": "Reply"},
            {"label": "Info"},
        ],
    }

    latent = detect_latent_affordances(view)

    assert "probe_hover" in latent
    assert "probe_context_menu" in latent
    assert "reveal_message_actions" in latent
    assert "forward_message" in latent
    assert "reply_message" in latent


def test_scroll_no_effect_is_promising_unresolved():
    from plugin.agent.transition.types import TransitionResult

    goal = Goal(kind="whatsapp_forward_message", contact="Kulvinder", target_contact="Pallavi", link_query="zaroortwala")
    before = {
        "screen": "CONVERSATION",
        "search_query": "",
        "open_conversation": "Messages in chat with Kulvinder",
        "call_state": "",
        "unexpected_dialogs": [],
        "voice_call_available": False,
    }
    after = dict(before)
    attempt = TransitionEvaluator().evaluate(
        goal=goal,
        before_world=_world(["Kulvinder", "zaroortwala"]),
        after_world=_world(["Kulvinder", "zaroortwala"]),
        action=Action(action="Scroll", semantic_target="", action_family="scroll_content"),
        before_view=before,
        after_view=after,
        before_features={"resolution_confidence": 0.9, "mean_belief": 0.95},
        after_features={"resolution_confidence": 0.9, "mean_belief": 0.95},
        transition=TransitionResult(changed=False, stabilized=True, change_score=0.0, reasons=[]),
        before_world_id="w1",
        after_world_id="w1",
        execution={"ok": True, "backend": "pyautogui", "message": "scroll down"},
    )
    assert attempt.outcome == TransitionOutcome.PROMISING_UNRESOLVED.value


def test_select_content_no_visible_repaint_is_promising_unresolved():
    from plugin.agent.transition.types import TransitionResult

    goal = Goal(kind="whatsapp_forward_message", contact="Kulvinder", target_contact="Pallavi", link_query="zarooratwala")
    before = {
        "screen": "CONVERSATION",
        "search_query": "",
        "open_conversation": "Messages in chat with Kulvinder Ji",
        "call_state": "",
        "unexpected_dialogs": [],
        "voice_call_available": False,
    }
    after = dict(before)
    attempt = TransitionEvaluator().evaluate(
        goal=goal,
        before_world=_world(["Kulvinder Ji", "Zarooratwala"]),
        after_world=_world(["Kulvinder Ji", "Zarooratwala"]),
        action=Action(action="Click", semantic_target="Your message, Zarooratwala", action_family="select_content"),
        before_view=before,
        after_view=after,
        before_features={"resolution_confidence": 0.9, "mean_belief": 0.95, "has_named_entity": True},
        after_features={"resolution_confidence": 0.9, "mean_belief": 0.95, "has_named_entity": True},
        transition=TransitionResult(changed=False, stabilized=True, change_score=0.0, reasons=[]),
        before_world_id="w1",
        after_world_id="w1",
        execution={"ok": True, "backend": "ax", "message": "click row"},
    )
    assert attempt.outcome == TransitionOutcome.PROMISING_UNRESOLVED.value


def test_state_experience_suppresses_ineffective():
    exp = StateExperience()
    action = Action(action="Click", semantic_target="Call", action_family="start_call")
    exp.record_outcome("SIG", action, TransitionOutcome.NO_EFFECT)
    assert exp.is_suppressed("SIG", action)
    alts = [
        action,
        Action(action="Type", semantic_target="Search", text="Now Group", action_family="type_query"),
        Action(action="Observe", action_family="observe"),
    ]
    kept = exp.filter_actions("SIG", alts)
    assert all(a.action_family != "start_call" or a.semantic_target != "Call" for a in kept)
    assert any(a.action_family == "type_query" for a in kept)


def test_action_experience_key_stable():
    a = Action(action="Click", semantic_target="Call", action_family="start_call")
    assert action_experience_key(a) == "start_call:call:"


def test_call_dropdown_is_promising_unresolved_not_regression():
    """Opening call picker occludes header but reveals Voice — not regression."""
    goal = Goal(kind="whatsapp_voice_call", contact="now group")
    before = {
        "screen": "CONVERSATION",
        "search_query": "",
        "open_conversation": "now… messages in chat with now…",
        "call_state": "",
        "unexpected_dialogs": [],
        "voice_call_available": True,
        "visible_contacts": ["Now…", "Open call dropdown menu with Now…", "Pallavi"],
    }
    after = {
        "screen": "LIST",
        "search_query": "",
        "open_conversation": None,
        "call_state": "",
        "unexpected_dialogs": [],
        "voice_call_available": False,
        "visible_contacts": ["Now…, Select people", "Video", "Voice"],
    }
    ctx = InteractionContext()
    update_interaction_context(
        ctx,
        goal=goal,
        view=before,
        features={"resolution_confidence": 0.9, "has_named_entity": True, "call_available": True},
        world_id="w0",
    )
    tr = TransitionResult(
        changed=True,
        stabilized=True,
        change_score=1.0,
        reasons=["open_conversation_changed", "entity_set_changed"],
    )
    attempt = TransitionEvaluator().evaluate(
        goal=goal,
        before_world=_world(["Now…", "Call"], open_conversation="now…"),
        after_world=_world(["Voice", "Video", "Select people"]),
        action=Action(action="Click", semantic_target="Call", action_family="start_call"),
        before_view=before,
        after_view=after,
        before_features={
            "has_named_entity": True,
            "call_available": True,
            "resolution_confidence": 0.9,
            "mean_belief": 0.97,
        },
        after_features={
            "has_named_entity": False,
            "call_available": False,
            "resolution_confidence": 0.0,
            "mean_belief": 0.98,
        },
        transition=tr,
        before_world_id="w0",
        after_world_id="w1",
        execution={"ok": True, "backend": "ax", "message": "click dropdown"},
        interaction_context=ctx,
    )
    assert attempt.outcome == TransitionOutcome.PROMISING_UNRESOLVED.value
    assert "initiate_voice" in (attempt.assessment or {}).get("newly_relevant_affordances", [])
    assert "target_occluded_not_lost" in (attempt.assessment or {}).get("occlusion_notes", [])
    assert attempt.attribution.get("likely_failure_domain") in {"none", None, ""}


def test_transition_attempt_carries_prediction_and_prediction_error():
    goal = Goal(kind="whatsapp_forward_message", contact="Kulvinder", target_contact="Pallavi", link_query="zarooratwala")
    before = {
        "screen": "SEARCH_RESULTS",
        "search_query": "Kulvinder",
        "open_conversation": "",
        "call_state": "",
        "unexpected_dialogs": [],
        "voice_call_available": False,
    }
    after = dict(before)
    action = Action(
        action="Type",
        semantic_target="Search",
        text="Kulvinder",
        action_family="type_query",
        prediction=ActionPrediction(
            action_key="type_query:Search:Kulvinder",
            action_family="type_query",
            semantic_target="Search",
            strategy="local",
            expected_surface="SEARCH_RESULTS",
            expected_progress=0.3,
            expected_affordances=["conversation_open"],
            expected_non_changes=["goal_reference_should_remain"],
            predicted_outcome="progress",
            reversible=True,
            confidence=0.8,
            rationale="search source conversation",
        ),
    )
    attempt = TransitionEvaluator().evaluate(
        goal=goal,
        before_world=_world(["Kulvinder"]),
        after_world=_world(["Kulvinder"]),
        action=action,
        before_view=before,
        after_view=after,
        before_features={"resolution_confidence": 0.9, "mean_belief": 0.95},
        after_features={"resolution_confidence": 0.9, "mean_belief": 0.95},
        transition=TransitionResult(changed=False, stabilized=True, change_score=0.0, reasons=[]),
        before_world_id="w1",
        after_world_id="w1",
    )
    assert attempt.prediction["predicted_outcome"] == "progress"
    assert attempt.prediction_error["outcome"]["predicted"] == "progress"
    assert attempt.prediction_error["outcome"]["observed"] == TransitionOutcome.NO_EFFECT.value


def test_selected_object_persists_while_header_is_occluded():
    goal = Goal(kind="whatsapp_forward_message", contact="Kulvinder", target_contact="Pallavi", link_query="zarooratwala")
    ctx = InteractionContext()
    update_interaction_context(
        ctx,
        goal=goal,
        view={"open_conversation": "Messages in chat with Kulvinder Ji"},
        features={
            "selected_object_label": "Your message, ZarooratWala – Fresh Groceries Delivered",
            "selected_object_confidence": 0.9,
            "selected_object_visible": True,
            "selected_object_observability": "confirmed_true",
        },
        world_id="w0",
    )
    assert ctx.selected_object.effective
    assert "zarooratwala" in ctx.selected_object_label.lower()

    update_interaction_context(
        ctx,
        goal=goal,
        view={"open_conversation": ""},
        features={},
        world_id="w1",
    )
    assert ctx.selected_object.effective
    assert ctx.selected_object.observability == "not_currently_observable"


def test_wrong_target_visible_is_clear_regression():
    goal = Goal(kind="whatsapp_voice_call", contact="now group")
    before = {
        "screen": "CONVERSATION",
        "open_conversation": "now… messages",
        "call_state": "",
        "unexpected_dialogs": [],
        "visible_contacts": ["Now…"],
        "voice_call_available": True,
    }
    after = {
        "screen": "CONVERSATION",
        "open_conversation": "Pallavi messages in chat with Pallavi",
        "call_state": "",
        "unexpected_dialogs": [],
        "visible_contacts": ["Pallavi"],
        "voice_call_available": True,
    }
    from plugin.agent.transition.types import TransitionResult

    tr = TransitionResult(changed=True, change_score=0.8, reasons=["open_conversation_changed"])
    attempt = TransitionEvaluator().evaluate(
        goal=goal,
        before_world=_world(["Now…"], open_conversation="now…"),
        after_world=_world(["Pallavi"], open_conversation="Pallavi"),
        action=Action(action="Click", semantic_target="Pallavi", action_family="open_contact"),
        before_view=before,
        after_view=after,
        before_features={"has_named_entity": True, "resolution_confidence": 0.9},
        after_features={"has_named_entity": True, "resolution_confidence": 0.9},
        transition=tr,
        execution={"ok": True, "message": "clicked"},
    )
    assert attempt.outcome == TransitionOutcome.REGRESSION.value
    assert "wrong_target_visible" in (attempt.assessment or {}).get("contradiction_evidence", [])


def test_branch_budget_waits_for_stagnation_not_depth_alone():
    from plugin.agent.transition.types import ExplorationBranch, FrontierAction
    from plugin.agent.controller import _frontier_backtrack_hint

    branch = ExplorationBranch(
        active=True,
        depth=3,
        current_state="picker",
        active_surface="call_picker",
        newly_relevant_affordances=["initiate_voice"],
    )
    branch.policy.max_depth = 3
    branch.policy.max_stagnant_steps = 2
    branch.policy.max_surface_rotations = 3
    branch.set_frontier(
        [FrontierAction(state_signature="picker", action_family="start_call", semantic_target="Voice", score=0.9)]
    )

    assert not branch.budget_exhausted()
    assert branch.best_non_observe_frontier(only_untried=True) is not None
    assert _frontier_backtrack_hint(branch, fallback="observe") == "start_call"

    branch.stagnant_steps = 2
    branch.frontier = []

    assert branch.budget_exhausted()
