from __future__ import annotations

from types import SimpleNamespace

from agent.auxiliary_client import _get_provider_chain
from hermes_cli.auth import resolve_provider
from providers import get_provider_profile


def test_remote_ollama_provider_is_registered_and_anonymous():
    profile = get_provider_profile("ollama-remote")
    assert profile is not None
    assert profile.allows_no_api_key is True
    assert profile.omit_auth_header is True
    assert profile.default_aux_model == "qwen2.5:32b"
    assert profile.base_url == "http://157.20.215.33:11434/v1"
    assert "OLLAMA_REMOTE_BASE_URL" in profile.env_vars
    assert "OLLAMA_REMOTE_API_KEY" in profile.env_vars
    assert resolve_provider("ollama-remote") == "ollama-remote"


def test_ranked_provider_chain_can_surface_ollama_cloud_first(monkeypatch):
    def fake_rank_task_models(*args, **kwargs):  # noqa: ANN001,ARG001
        return [
            SimpleNamespace(
                provider="ollama-cloud",
                model="gpt-oss:120b",
                base_url="https://ollama.com/v1",
            ),
            SimpleNamespace(
                provider="openrouter",
                model="qwen2.5:32b",
                base_url="https://openrouter.ai/api/v1",
            ),
        ]

    monkeypatch.setattr("agent.auxiliary_client.rank_task_models", fake_rank_task_models)
    chain = _get_provider_chain(main_runtime={"provider": "anthropic", "model": "claude-3.5-sonnet"})
    assert [label for label, _ in chain] == [
        "ollama-cloud/gpt-oss:120b",
        "openrouter/qwen2.5:32b",
    ]
