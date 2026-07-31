"""Tests for startup provider API prewarm gating."""

from __future__ import annotations

from unittest.mock import patch

import pytest

import agent.agent_init as ai


def _reset_gate() -> None:
    ai._provider_startup_prewarm_done.clear()


def test_startup_prewarm_passes_once_three_providers_answer(monkeypatch):
    _reset_gate()
    monkeypatch.setenv("HERMES_PROVIDER_STARTUP_MIN_SUCCESS", "3")
    rows = [
        {"slug": "groq"},
        {"slug": "mistral"},
        {"slug": "cerebras"},
        {"slug": "pollinations"},
    ]

    with patch("hermes_cli.model_switch.list_authenticated_providers", return_value=rows), patch(
        "hermes_cli.models.cached_provider_model_ids", side_effect=[
            ["groq-model"],
            ["mistral-model"],
            ["cerebras-model"],
        ],
    ) as mock_cached:
        result = ai._prewarm_provider_apis_at_startup(
            current_provider="groq",
            current_base_url="https://api.groq.com/openai/v1",
            user_providers={},
            custom_providers=[],
        )

    assert result["status"] == "ok"
    assert result["successes"] == ["groq", "mistral", "cerebras"]
    assert mock_cached.call_count == 3
    assert ai._provider_startup_prewarm_done.is_set()

    with patch("hermes_cli.model_switch.list_authenticated_providers") as mock_list, patch(
        "hermes_cli.models.cached_provider_model_ids"
    ) as mock_cached_again:
        skipped = ai._prewarm_provider_apis_at_startup(
            current_provider="groq",
            current_base_url="https://api.groq.com/openai/v1",
        )

    assert skipped["status"] == "skipped"
    mock_list.assert_not_called()
    mock_cached_again.assert_not_called()


def test_startup_prewarm_raises_when_fewer_than_three_providers_answer(monkeypatch):
    _reset_gate()
    monkeypatch.setenv("HERMES_PROVIDER_STARTUP_MIN_SUCCESS", "3")
    rows = [{"slug": "groq"}, {"slug": "mistral"}, {"slug": "cerebras"}]

    with patch("hermes_cli.model_switch.list_authenticated_providers", return_value=rows), patch(
        "hermes_cli.models.cached_provider_model_ids", side_effect=[["groq-model"], [], []]
    ):
        with pytest.raises(RuntimeError, match="need at least 3"):
            ai._prewarm_provider_apis_at_startup(
                current_provider="groq",
                current_base_url="https://api.groq.com/openai/v1",
            )

    assert not ai._provider_startup_prewarm_done.is_set()


def test_runtime_inventory_prewarm_records_models_and_warms_ollama(monkeypatch):
    _reset_gate()
    monkeypatch.setenv("HERMES_PROVIDER_STARTUP_MIN_SUCCESS", "1")
    rows = [{"slug": "ollama"}]

    with patch("hermes_cli.model_switch.list_authenticated_providers", return_value=rows), patch(
        "hermes_cli.models.cached_provider_model_ids", return_value=["qwen2.5:32b", "gpt-oss:120b"]
    ) as mock_cached, patch(
        "agent.agent_init.warm_ollama_model_keepalive", return_value=True
    ) as mock_warm:
        result = ai._prewarm_runtime_model_inventory_at_startup(
            current_provider="ollama",
            current_base_url="http://127.0.0.1:11434/v1",
            current_model="qwen2.5:32b",
            user_providers={},
            custom_providers=[],
        )

    assert result["status"] == "ok"
    assert result["inventory_by_provider"]["ollama"] == ["qwen2.5:32b", "gpt-oss:120b"]
    assert result["current_provider_models"] == ["qwen2.5:32b", "gpt-oss:120b"]
    assert result["ollama_warmed"] is True
    mock_cached.assert_called_once_with("ollama", force_refresh=True)
    mock_warm.assert_called_once_with(
        "qwen2.5:32b",
        "http://127.0.0.1:11434/v1",
        keep_alive=-1,
        timeout=5.0,
    )
