from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from hermes_cli.model_routing import (
    get_task_profile,
    rank_task_models,
    select_task_model_ids,
    select_task_model_subset,
)


def test_task_profile_aliases_normalize():
    assert get_task_profile("chat").name == "chat_runtime"
    assert get_task_profile("gui").name == "computer_use"
    assert get_task_profile("perception").name == "perception"
    assert get_task_profile("vision").name == "screen_understanding"


def test_chat_runtime_prefers_large_models_and_drops_known_small_ones():
    rows = [
        {
            "slug": "openrouter",
            "models": ["gpt-oss:120b", "qwen2.5:32b"],
            "source": "built-in",
            "is_current": False,
        },
        {
            "slug": "ollama-remote",
            "models": ["qwen3:235b", "deepseek-r1:32b"],
            "source": "plugin",
            "is_current": True,
        },
    ]

    with patch("hermes_cli.model_routing.list_providers", return_value=[]):
        ranked = rank_task_models("chat_runtime", rows=rows)
    ids = [(c.provider, c.model) for c in ranked]

    assert ("openrouter", "gpt-oss:120b") in ids
    assert ("ollama-remote", "qwen3:235b") not in ids
    assert all(not model.endswith(":32b") for _, model in ids)
    assert ids[0] == ("openrouter", "gpt-oss:120b")


def test_chat_runtime_skips_hosted_ollama_by_default(monkeypatch):
    rows = [
        {
            "slug": "ollama-remote",
            "models": ["qwen3:235b"],
            "source": "plugin",
            "is_current": True,
        },
        {
            "slug": "openrouter",
            "models": ["gpt-oss:120b"],
            "source": "built-in",
            "is_current": False,
        },
    ]

    monkeypatch.delenv("HERMES_ALLOW_OLLAMA_REMOTE_CHAT", raising=False)
    ranked = rank_task_models("chat_runtime", rows=rows)

    ids = [(c.provider, c.model) for c in ranked]
    assert ("ollama-remote", "qwen3:235b") not in ids
    assert ids[0] == ("openrouter", "gpt-oss:120b")


def test_chat_runtime_can_opt_in_to_hosted_ollama(monkeypatch):
    rows = [
        {
            "slug": "ollama-remote",
            "models": ["qwen3:235b"],
            "source": "plugin",
            "is_current": True,
        },
        {
            "slug": "openrouter",
            "models": ["gpt-oss:120b"],
            "source": "built-in",
            "is_current": False,
        },
    ]

    monkeypatch.setenv("HERMES_ALLOW_OLLAMA_REMOTE_CHAT", "1")
    ranked = rank_task_models("chat_runtime", rows=rows)

    ids = [(c.provider, c.model) for c in ranked]
    assert ("ollama-remote", "qwen3:235b") in ids


def test_computer_use_prefers_small_iterative_models():
    rows = [
        {
            "slug": "ollama-remote",
            "models": ["deepseek-r1:14b", "qwen2.5:32b", "deepseek-r1:70b"],
            "source": "plugin",
            "is_current": True,
        },
        {
            "slug": "openrouter",
            "models": ["gpt-oss:120b"],
            "source": "built-in",
            "is_current": False,
        },
    ]

    ranked = rank_task_models("computer_use", rows=rows)
    ids = [(c.provider, c.model) for c in ranked]

    assert ids[0] == ("ollama-remote", "deepseek-r1:14b")
    assert ("ollama-remote", "qwen2.5:32b") in ids
    assert all(model.endswith(("14b", "32b")) for _, model in ids)


def test_perception_prefers_structured_small_models():
    rows = [
        {
            "slug": "ollama-remote",
            "models": ["qwen2.5:32b", "gpt-oss:120b"],
            "source": "plugin",
            "is_current": True,
        },
        {
            "slug": "openrouter",
            "models": ["openai/gpt-oss-120b", "qwen3:235b"],
            "source": "built-in",
            "is_current": False,
        },
    ]

    ranked = rank_task_models("perception", rows=rows)
    ids = [(c.provider, c.model) for c in ranked]

    assert ids[0] == ("ollama-remote", "qwen2.5:32b")
    assert ("openrouter", "openai/gpt-oss-120b") not in ids[:1]


def test_screen_understanding_prefers_curated_vision_chain():
    """Preferred vision models lead; kimi-k3 (text/extra-usage) stays out of top."""
    rows = [
        {
            "slug": "ollama-cloud",
            "models": ["qwen3.5:cloud", "kimi-k3:cloud", "gemma4:cloud", "qwen2.5:32b"],
            "source": "plugin",
            "is_current": True,
        },
        {
            "slug": "openrouter",
            "models": ["openai/gpt-oss-120b", "qwen3:235b"],
            "source": "built-in",
            "is_current": False,
        },
    ]

    class _Info:
        def __init__(self, vision: bool) -> None:
            self.tool_call = True
            self.reasoning = True
            self.structured_output = True
            self.context_window = 256000
            self._vision = vision

        def supports_vision(self) -> bool:
            return self._vision

    def fake_get_model_info(provider: str, model: str):  # noqa: ANN001
        return _Info(model in {"qwen3.5:cloud", "kimi-k3:cloud", "gemma4:cloud"})

    with patch("hermes_cli.model_routing.get_model_info", side_effect=fake_get_model_info):
        ranked = rank_task_models("screen_understanding", rows=rows)

    ids = [(c.provider, c.model) for c in ranked]
    assert ids[0] == ("ollama-cloud", "qwen3.5:cloud")
    assert ("ollama-cloud", "gemma4:cloud") in ids[:3]
    assert ("ollama-cloud", "kimi-k3:cloud") not in ids[:2]
    assert ("openrouter", "openai/gpt-oss-120b") not in ids[:3]


def test_plugin_provider_is_added_when_not_present_in_authenticated_rows():
    profile = SimpleNamespace(
        name="ollama-remote",
        display_name="Remote Ollama",
        fallback_models=("qwen2.5:32b",),
        base_url="http://157.20.215.33:11434/v1",
    )

    with (
        patch("hermes_cli.model_routing.list_authenticated_providers", return_value=[]),
        patch("hermes_cli.model_routing.list_providers", return_value=[profile]),
        patch("hermes_cli.model_routing.is_provider_explicitly_configured", return_value=True),
        patch("hermes_cli.model_routing.provider_model_ids", return_value=["qwen2.5:32b"]),
    ):
        ranked = rank_task_models("computer_use", rows=[])

    assert [(c.provider, c.model) for c in ranked] == [("ollama-remote", "qwen2.5:32b")]


def test_task_subset_groups_by_provider():
    rows = [
        {
            "slug": "ollama-remote",
            "models": ["deepseek-r1:14b", "qwen2.5:32b", "deepseek-r1:70b"],
            "source": "plugin",
            "is_current": True,
        },
        {
            "slug": "openrouter",
            "models": ["gpt-oss:120b", "qwen3:235b"],
            "source": "built-in",
            "is_current": False,
        },
    ]

    subset = select_task_model_subset(
        "computer_use",
        rows=rows,
        per_provider_limit=2,
        total_limit=3,
    )
    assert subset["ollama-remote"] == ["deepseek-r1:14b", "qwen2.5:32b"]
    assert "openrouter" not in subset or subset["openrouter"] == []

    ids = select_task_model_ids("computer_use", rows=rows, limit=2)
    assert ids[0] == "ollama-remote/deepseek-r1:14b"
