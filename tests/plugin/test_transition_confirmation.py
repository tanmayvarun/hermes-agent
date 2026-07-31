from __future__ import annotations

import json
from types import SimpleNamespace

from plugin.agent.action import Action
from plugin.agent.features import StateFeatures
from plugin.agent.goal import Goal
from plugin.agent.runtime.state import RuntimeState
from plugin.agent.transition.confirmation import (
    apply_transition_confirmation,
    confirm_transition_with_llm,
    TransitionConfirmation,
)
from plugin.agent.transition.types import TransitionAttempt, TransitionOutcome


def _response(payload: dict[str, object]):
    message = SimpleNamespace(content=json.dumps(payload), tool_calls=[])
    choice = SimpleNamespace(message=message, finish_reason="stop")
    return SimpleNamespace(choices=[choice], usage=None, model="fake")


def test_confirm_transition_with_llm_stamps_success_and_updates_forward_state(monkeypatch):
    from agent import auxiliary_client
    import plugin.agent.transition.confirmation as confirmation_mod

    seen = {"main_runtime": None}

    def fake_call_llm(**kwargs):
        assert kwargs["task"] == "transition_confirmation"
        seen["main_runtime"] = kwargs.get("main_runtime")
        return _response(
            {
                "confirmed": True,
                "confidence": 0.89,
                "confirmed_surface": "conversation",
                "confirmed_target": "Kulvinder Ji",
                "confirmed_open_conversation": "Messages in chat with Kulvinder Ji",
                "confirmed_source_object_selected": False,
                "needs_followup_observe": False,
                "reason": "conversation header and context confirm success",
            }
        )

    monkeypatch.setattr(auxiliary_client, "call_llm", fake_call_llm)
    monkeypatch.setattr(confirmation_mod, "_transition_confirmation_enabled", lambda: True)
    token = auxiliary_client.set_runtime_main(
        "ollama-remote",
        "qwen2.5:32b",
        base_url="http://ollama.test/v1",
    )

    try:
        goal = Goal(kind="whatsapp_forward_message", contact="Kulvinder", target_contact="Pallavi", link_query="zarooratwala")
        runtime = RuntimeState()
        runtime.world_model.active_app = "WhatsApp"
        runtime.execution_state.interaction_context.active_surface = "list"
        runtime.execution_state.interaction_context.selected_target = "Kulvinder"

        view = {
            "screen": "CONVERSATION",
            "open_conversation": "Messages in chat with Kulvinder Ji",
            "search_query": "",
            "visible_contacts": ["Kulvinder Ji"],
        }
        features = StateFeatures(
            screen_bucket="conversation",
            conversation_open=True,
            worldview_score=0.81,
            mean_belief=0.94,
            extras={"conversation_context_text": ["Sent to Kulvinder Ji: zarooratwala link"]},
        )
        action = Action(action="Click", semantic_target="Kulvinder Ji", action_family="open_contact", reversible=True)
        attempt = TransitionAttempt(
            before_world_id="w0",
            after_world_id="w1",
            action_family="open_contact",
            action_key="open_contact|Kulvinder Ji|",
            observed_change=True,
            progress_delta=0.4,
            outcome=TransitionOutcome.PROGRESS.value,
            change_score=0.6,
            reasons=["open_conversation_changed"],
            assessment={
                "state_understood": False,
                "goal_progress": "promising",
                "irreversible_risk_delta": 0.2,
            },
            attribution={"likely_failure_domain": "none"},
            effect_kind="open_conversation",
        )

        confirmation = confirm_transition_with_llm(
            goal,
            runtime.world_model,
            view,
            features,
            action,
            attempt,
            runtime.execution_state.interaction_context,
        )
        assert confirmation is not None
        assert confirmation.confirmed
        assert seen["main_runtime"] == {
            "provider": "ollama-remote",
            "model": "qwen2.5:32b",
            "base_url": "http://ollama.test/v1",
            "api_key": "",
            "api_mode": "",
            "auth_mode": "",
        }

        apply_transition_confirmation(
            runtime,
            goal=goal,
            action=action,
            attempt=attempt,
            confirmation=confirmation,
            after_view=view,
            after_features=features,
            world_id="w1",
        )

        ctx = runtime.execution_state.interaction_context
        assert ctx.open_conversation.effective
        assert ctx.active_surface == "conversation"
        assert runtime.world_model.overlay_hints["forward_task"]["predicates"]["source_conversation_open"] is True
        assert runtime.world_model.overlay_hints["forward_task"]["derived_phase"] != "OPEN_SOURCE"
        assert features.conversation_open is True
        assert features.extras["active_surface"] == "conversation"
        assert features.extras["transition_confirmation"]["confirmed"] is True
    finally:
        auxiliary_client.reset_runtime_main(token)


def test_apply_transition_confirmation_accepts_dict_features(monkeypatch):
    goal = Goal(kind="whatsapp_forward_message", contact="Kulvinder", target_contact="Pallavi", link_query="zarooratwala")
    runtime = RuntimeState()
    runtime.world_model.active_app = "WhatsApp"
    runtime.execution_state.interaction_context.active_surface = "list"

    view = {"screen": "CONVERSATION"}
    features = {
        "screen_bucket": "conversation",
        "conversation_open": True,
        "extras": {"active_surface": "conversation", "forward_task": {"derived_phase": "OPEN_SOURCE"}},
    }
    action = Action(action="Click", semantic_target="Kulvinder Ji", action_family="open_contact", reversible=True)
    attempt = TransitionAttempt(
        before_world_id="w0",
        after_world_id="w1",
        action_family="open_contact",
        action_key="open_contact|Kulvinder Ji|",
        observed_change=True,
        progress_delta=0.4,
        outcome=TransitionOutcome.PROGRESS.value,
        change_score=0.6,
        reasons=["open_conversation_changed"],
        assessment={"goal_progress": "promising"},
        attribution={"likely_failure_domain": "none"},
        effect_kind="open_conversation",
    )
    confirmation = TransitionConfirmation(
        confirmed=True,
        confidence=0.91,
        confirmed_surface="conversation",
        confirmed_target="Kulvinder Ji",
        confirmed_open_conversation="Messages in chat with Kulvinder Ji",
        confirmed_source_object_selected=False,
        needs_followup_observe=False,
        reason="ok",
    )

    apply_transition_confirmation(
        runtime,
        goal=goal,
        action=action,
        attempt=attempt,
        confirmation=confirmation,
        after_view=view,
        after_features=features,
        world_id="w1",
    )

    assert features["conversation_open"] is True
    assert features["extras"]["active_surface"] == "conversation"
    assert features["extras"]["transition_confirmation"]["confirmed"] is True
