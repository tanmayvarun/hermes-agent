from __future__ import annotations

import json

from plugin.experiments.browser_relay_eval import (
    BrowserRelayCase,
    BrowserRelayCandidateSpec,
    _build_recorded_invoker,
    run_browser_relay_eval,
)


def test_browser_relay_eval_replays_multi_turn_conversation_and_scores_background_mode():
    candidate = BrowserRelayCandidateSpec(
        name="chatgpt-browser",
        service_name="chatgpt",
        transport_provider="browser-use",
        background_safe=True,
    )
    case = BrowserRelayCase(
        case_id="chatgpt_followup_clarification",
        service_name="chatgpt",
        objective="Hold a natural multi-turn conversation and ask a useful follow-up.",
        seed_prompt="I need a concise explanation of how to share a Google Drive file with view-only access.",
        expected_terms=["share", "drive", "view", "access"],
        max_turns=2,
    )

    def invoker(candidate, case, conversation):
        if len([msg for msg in conversation if msg["role"] == "assistant"]) == 0:
            return {
                "content": "Use the share button, choose view-only access, and send the link.",
                "used_background_mode": True,
                "foreground_focus_changes": 0,
                "requires_human_cta": False,
                "browser_service": "chatgpt",
                "transport_provider": "browser-use",
            }
        return {
            "content": "You can also revoke access later from the sharing dialog if needed.",
            "used_background_mode": True,
            "foreground_focus_changes": 0,
            "requires_human_cta": False,
            "browser_service": "chatgpt",
            "transport_provider": "browser-use",
        }

    followup_calls = []

    def followup_generator(candidate, case, conversation):
        followup_calls.append(len(conversation))
        if len(followup_calls) == 1:
            return {"question": "Can you explain how to revoke access later?", "stop": False, "reason": "advance"}
        return {"question": "", "stop": True, "reason": "enough"}

    report = run_browser_relay_eval(
        [candidate],
        cases=[case],
        invoker=invoker,
        followup_generator=followup_generator,
    )

    assert report.case_count == 1
    result = report.case_results[0]
    assert result.used_expected_service is True
    assert result.completed is True
    assert result.turn_count == 2
    assert result.background_safe_rate == 1.0
    assert result.foreground_focus_changes == 0
    assert result.mean_assistant_overlap > 0.0
    assert result.mean_followup_overlap > 0.0
    assert len(result.turn_results) == 2
    assert followup_calls == [2, 4]


def test_browser_relay_eval_can_replay_recorded_transcripts():
    transcript = {
        "candidates": {
            "chatgpt-browser": {
                "chatgpt_followup_clarification": [
                    {
                        "content": "Use the share button and choose view-only access.",
                        "used_background_mode": True,
                        "foreground_focus_changes": 0,
                        "requires_human_cta": False,
                    }
                ]
            }
        }
    }
    candidate = BrowserRelayCandidateSpec(
        name="chatgpt-browser",
        service_name="chatgpt",
        transport_provider="browser-use",
        background_safe=True,
    )
    case = BrowserRelayCase(
        case_id="chatgpt_followup_clarification",
        service_name="chatgpt",
        objective="Hold a natural multi-turn conversation and ask a useful follow-up.",
        seed_prompt="I need a concise explanation of how to share a Google Drive file with view-only access.",
        expected_terms=["share", "drive", "view", "access"],
        max_turns=1,
    )

    invoker = _build_recorded_invoker(transcript)

    report = run_browser_relay_eval(
        [candidate],
        cases=[case],
        invoker=invoker,
        followup_generator=lambda candidate, case, conversation: {"question": "", "stop": True, "reason": "done"},
    )

    result = report.case_results[0]
    assert result.final_assistant_response == "Use the share button and choose view-only access."
    assert result.background_safe_rate == 1.0
    assert result.human_cta_rate == 0.0
    assert json.loads(json.dumps(report.to_dict()))["case_results"][0]["final_assistant_response"]
