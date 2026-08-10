from __future__ import annotations

import json
from types import SimpleNamespace

from plugin.agent.reasoning_consultation import consult_reasoning


def _response(payload: dict[str, object]):
    message = SimpleNamespace(content=json.dumps(payload), tool_calls=[])
    choice = SimpleNamespace(message=message, finish_reason="stop")
    return SimpleNamespace(choices=[choice], usage=None, model="fake")


def test_reasoning_consultation_preserves_abstention(monkeypatch):
    from agent import auxiliary_client

    seen: dict[str, object] = {}

    def fake_call_llm(**kwargs):
        seen.update(kwargs)
        return _response(
            {
                "needs_followup_observe": True,
                "confidence": 0.12,
                "reason": "need more context",
            }
        )

    monkeypatch.setattr(auxiliary_client, "call_llm", fake_call_llm)

    result = consult_reasoning(
        "perception",
        [
            {"role": "system", "content": "Return JSON only."},
            {"role": "user", "content": "probe"},
        ],
        call_kwargs={
            "provider": "ollama-cloud",
            "model": "gpt-oss:120b",
            "timeout": 7,
        },
        temperature=0.0,
        max_tokens=64,
    )

    assert result.abstained is True
    assert result.reason == "need more context"
    assert result.parsed["needs_followup_observe"] is True
    # Text-only messages must not ride the vision perception pin.
    assert seen["task"] == "decision"
    assert result.task == "decision"
    assert seen["provider"] == "ollama-cloud"
    assert seen["model"] == "gpt-oss:120b"
    assert seen["timeout"] == 7
