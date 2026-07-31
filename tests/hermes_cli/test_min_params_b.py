"""Tests for model.min_params_b filtering in fallback_config."""

from __future__ import annotations

from hermes_cli.fallback_config import (
    apply_min_params_b,
    estimate_model_params_b,
    get_fallback_chain,
    get_min_params_b,
    meets_min_params_b,
)


class TestEstimateModelParamsB:
    def test_colon_suffix(self):
        assert estimate_model_params_b("gpt-oss:120b") == 120.0

    def test_hyphen_suffix(self):
        assert estimate_model_params_b("gpt-oss-120b") == 120.0

    def test_moe_style_takes_largest(self):
        assert estimate_model_params_b("nvidia/nemotron-3-ultra-550b-a55b:free") == 550.0

    def test_ollama_large(self):
        assert estimate_model_params_b("mistral-large-3:675b") == 675.0

    def test_known_codestral(self):
        assert estimate_model_params_b("codestral-latest") == 22.0

    def test_unknown_returns_none(self):
        assert estimate_model_params_b("some-mystery-model") is None


class TestMinParamsFilter:
    def test_default_floor_applies_when_unset(self):
        cfg = {
            "fallback_providers": [
                {"provider": "llm7", "model": "codestral-latest"},
                {"provider": "ovhcloud", "model": "gpt-oss:120b"},
            ]
        }
        assert get_min_params_b(cfg) == 100.0
        assert [e["model"] for e in get_fallback_chain(cfg)] == ["gpt-oss:120b"]

    def test_drops_below_threshold_and_unknown(self):
        cfg = {
            "model": {"min_params_b": 100},
            "fallback_providers": [
                {"provider": "openrouter", "model": "nvidia/nemotron-3-ultra-550b-a55b:free"},
                {"provider": "ollama-cloud", "model": "nemotron-3-nano:30b"},
                {"provider": "llm7", "model": "codestral-latest"},
                {"provider": "llm7", "model": "mystery-model"},
                {"provider": "ollama-cloud", "model": "gpt-oss:120b"},
            ],
        }
        chain = get_fallback_chain(cfg)
        assert [e["model"] for e in chain] == [
            "nvidia/nemotron-3-ultra-550b-a55b:free",
            "gpt-oss:120b",
        ]

    def test_meets_helper(self):
        assert meets_min_params_b("gpt-oss:120b", 100)
        assert not meets_min_params_b("gpt-oss:20b", 100)
        assert not meets_min_params_b("codestral-latest", 100)
        assert not meets_min_params_b("codestral-latest", None)
        assert meets_min_params_b("gpt-oss:120b", None)

    def test_apply_promotes_primary(self):
        cfg = {
            "model": {
                "provider": "llm7",
                "default": "codestral-latest",
                "min_params_b": 100,
            },
            "fallback_providers": [
                {"provider": "ollama-cloud", "model": "nemotron-3-nano:30b"},
                {"provider": "ollama-cloud", "model": "gpt-oss:120b"},
                {"provider": "ovhcloud", "model": "gpt-oss-120b"},
            ],
        }
        apply_min_params_b(cfg)
        assert cfg["model"]["default"] == "gpt-oss:120b"
        assert cfg["model"]["provider"] == "ollama-cloud"
        assert [e["model"] for e in cfg["fallback_providers"]] == ["gpt-oss-120b"]

    def test_apply_keeps_large_primary(self):
        cfg = {
            "model": {
                "provider": "ollama-cloud",
                "default": "mistral-large-3:675b",
                "min_params_b": 100,
            },
            "fallback_providers": [
                {"provider": "llm7", "model": "codestral-latest"},
                {"provider": "ollama-cloud", "model": "gpt-oss:120b"},
            ],
        }
        apply_min_params_b(cfg)
        assert cfg["model"]["default"] == "mistral-large-3:675b"
        assert [e["model"] for e in cfg["fallback_providers"]] == ["gpt-oss:120b"]


class TestModelCatalogFloor:
    def test_list_provider_models_hides_small_and_unknown_models(self, monkeypatch):
        from agent import models_dev

        monkeypatch.setattr(
            models_dev,
            "_get_provider_models",
            lambda provider: {
                "tiny-20b": {"tool_call": True},
                "mystery-model": {"tool_call": True},
                "gpt-oss-120b": {"tool_call": True},
            },
        )
        assert models_dev.list_provider_models("openrouter") == ["gpt-oss-120b"]

    def test_list_agentic_models_hides_small_and_unknown_models(self, monkeypatch):
        from agent import models_dev

        monkeypatch.setattr(
            models_dev,
            "_get_provider_models",
            lambda provider: {
                "tiny-20b": {"tool_call": True},
                "mystery-model": {"tool_call": True},
                "gpt-oss-120b": {"tool_call": True},
                "notools-120b": {"tool_call": False},
            },
        )
        assert models_dev.list_agentic_models("openrouter") == ["gpt-oss-120b"]
