"""Tests for free-tier model gateway providers."""

from __future__ import annotations

import pytest

from hermes_cli.auth import resolve_api_key_provider_credentials, resolve_provider
from hermes_cli.models import CANONICAL_PROVIDERS, normalize_provider
from providers import get_provider_profile
from providers.base import OMIT_AUTH_API_KEY


@pytest.fixture(autouse=True)
def _clear_provider_env(monkeypatch):
    for key in (
        "AION_API_KEY",
        "AION_BASE_URL",
        "COHERE_API_KEY",
        "COHERE_BASE_URL",
        "CLOUDFLARE_API_TOKEN",
        "CLOUDFLARE_ACCOUNT_ID",
        "CLOUDFLARE_BASE_URL",
        "CF_API_TOKEN",
        "CF_ACCOUNT_ID",
        "GITHUB_TOKEN",
        "GH_TOKEN",
        "GITHUB_MODELS_BASE_URL",
        "MISTRAL_API_KEY",
        "MISTRAL_BASE_URL",
        "POLLINATIONS_API_KEY",
        "POLLINATIONS_BASE_URL",
        "LLM7_API_KEY",
        "LLM7_BASE_URL",
        "GROQ_API_KEY",
        "GROQ_BASE_URL",
        "CEREBRAS_API_KEY",
        "CEREBRAS_BASE_URL",
        "OVHCLOUD_API_KEY",
        "OVHCLOUD_BASE_URL",
        "SILICONFLOW_API_KEY",
        "SILICONFLOW_BASE_URL",
        "SAMBANOVA_API_KEY",
        "SAMBANOVA_BASE_URL",
        "OPENROUTER_API_KEY",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)


class TestLlm7Provider:
    def test_profile_registered(self):
        p = get_provider_profile("llm7")
        assert p is not None
        assert p.name == "llm7"
        assert p.allows_no_api_key is True
        assert p.omit_auth_header is False
        assert "api.llm7.io" in p.base_url
        assert p.fallback_models

    @pytest.mark.parametrize("alias", ["llm7", "llm7.io", "llm7io"])
    def test_aliases(self, alias):
        assert get_provider_profile(alias).name == "llm7"
        assert normalize_provider(alias) == "llm7"

    def test_in_canonical_providers(self):
        assert any(p.slug == "llm7" for p in CANONICAL_PROVIDERS)

    def test_anonymous_credentials_use_placeholder(self):
        creds = resolve_api_key_provider_credentials("llm7")
        assert creds["provider"] == "llm7"
        assert creds["api_key"] == "no-key-required"
        assert "api.llm7.io" in creds["base_url"]

    def test_explicit_key_preferred(self, monkeypatch):
        monkeypatch.setenv("LLM7_API_KEY", "llm7-real-key")
        creds = resolve_api_key_provider_credentials("llm7")
        assert creds["api_key"] == "llm7-real-key"

    def test_resolve_provider_with_key(self, monkeypatch):
        monkeypatch.setenv("LLM7_API_KEY", "llm7-real-key")
        assert resolve_provider("llm7") == "llm7"


class TestAionProvider:
    def test_profile_registered(self):
        p = get_provider_profile("aion")
        assert p is not None
        assert p.name == "aion"
        assert "aionlabs.ai" in p.base_url
        assert p.default_aux_model == "aion-labs/aion-3.0-mini"

    @pytest.mark.parametrize("alias", ["aion", "aionlabs", "aion-labs"])
    def test_aliases(self, alias):
        assert get_provider_profile(alias).name == "aion"
        assert normalize_provider(alias) == "aion"

    def test_in_canonical_providers(self):
        assert any(p.slug == "aion" for p in CANONICAL_PROVIDERS)


class TestGithubModelsProvider:
    def test_profile_registered(self):
        p = get_provider_profile("gh-models")
        assert p is not None
        assert p.name == "github-models-api"
        assert "models.github.ai/inference" in p.base_url
        assert "models.github.ai/catalog/models" in p.models_url
        assert p.default_headers["Accept"] == "application/vnd.github+json"

    def test_in_canonical_providers(self):
        assert any(p.slug == "github-models-api" for p in CANONICAL_PROVIDERS)

    def test_credentials_with_token(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
        creds = resolve_api_key_provider_credentials("gh-models")
        assert creds["api_key"] == "ghp_test"
        assert creds["base_url"] == "https://models.github.ai/inference"


class TestMistralProvider:
    def test_profile_registered(self):
        p = get_provider_profile("mistral")
        assert p is not None
        assert p.name == "mistral"
        assert "api.mistral.ai" in p.base_url
        assert p.default_aux_model == "mistral-small-latest"

    def test_in_canonical_providers(self):
        assert any(p.slug == "mistral" for p in CANONICAL_PROVIDERS)

    def test_credentials_with_key(self, monkeypatch):
        monkeypatch.setenv("MISTRAL_API_KEY", "mistral-test")
        creds = resolve_api_key_provider_credentials("mistral")
        assert creds["api_key"] == "mistral-test"


class TestPollinationsProvider:
    def test_profile_registered(self):
        p = get_provider_profile("pollinations")
        assert p is not None
        assert p.name == "pollinations"
        assert "gen.pollinations.ai" in p.base_url
        assert p.supports_vision is True

    def test_in_canonical_providers(self):
        assert any(p.slug == "pollinations" for p in CANONICAL_PROVIDERS)

    def test_credentials_with_key(self, monkeypatch):
        monkeypatch.setenv("POLLINATIONS_API_KEY", "sk_test_pollinations")
        creds = resolve_api_key_provider_credentials("pollinations")
        assert creds["api_key"] == "sk_test_pollinations"


class TestCloudflareWorkersAIProvider:
    def test_profile_registered(self):
        p = get_provider_profile("cloudflare-workers-ai")
        assert p is not None
        assert p.name == "cloudflare-workers-ai"
        assert "cloudflare.com/client/v4/accounts" in p.base_url
        assert p.default_aux_model == "@cf/openai/gpt-oss-120b"
        assert all("120b" in m.lower() for m in p.fallback_models)

    @pytest.mark.parametrize("alias", ["cloudflare-workers-ai", "cf-workers", "workers-ai"])
    def test_aliases(self, alias):
        assert get_provider_profile(alias).name == "cloudflare-workers-ai"
        assert normalize_provider(alias) == "cloudflare-workers-ai"

    def test_in_canonical_providers(self):
        assert any(p.slug == "cloudflare-workers-ai" for p in CANONICAL_PROVIDERS)

    def test_credentials_with_token_and_account(self, monkeypatch):
        monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "cf-token")
        monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct-123")
        creds = resolve_api_key_provider_credentials("cloudflare-workers-ai")
        assert creds["api_key"] == "cf-token"
        assert creds["base_url"] == (
            "https://api.cloudflare.com/client/v4/accounts/acct-123/ai/v1"
        )

    def test_resolve_provider_requires_account_context(self, monkeypatch):
        monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "cf-token")
        assert resolve_provider("auto") != "cloudflare-workers-ai"
        monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct-123")
        assert resolve_provider("auto") == "cloudflare-workers-ai"


class TestCohereProvider:
    def test_profile_registered(self):
        p = get_provider_profile("cohere")
        assert p is not None
        assert p.name == "cohere"
        assert "api.cohere.ai/compatibility/v1" in p.base_url
        assert p.default_aux_model == "command-a-plus-05-2026"
        assert all("command-a" in m for m in p.fallback_models)

    @pytest.mark.parametrize("alias", ["cohere", "cohere-compat", "cohere-ai"])
    def test_aliases(self, alias):
        assert get_provider_profile(alias).name == "cohere"
        assert normalize_provider(alias) == "cohere"

    def test_in_canonical_providers(self):
        assert any(p.slug == "cohere" for p in CANONICAL_PROVIDERS)

    def test_credentials_with_key(self, monkeypatch):
        monkeypatch.setenv("COHERE_API_KEY", "cohere-test")
        creds = resolve_api_key_provider_credentials("cohere")
        assert creds["api_key"] == "cohere-test"
        assert creds["base_url"] == "https://api.cohere.ai/compatibility/v1"


class TestOvhcloudProvider:
    def test_profile_registered(self):
        p = get_provider_profile("ovhcloud")
        assert p is not None
        assert p.allows_no_api_key is True
        assert p.omit_auth_header is True
        assert "kepler.ai.cloud.ovh.net" in p.base_url

    @pytest.mark.parametrize("alias", ["ovhcloud", "ovh", "ovh-cloud"])
    def test_aliases(self, alias):
        assert get_provider_profile(alias).name == "ovhcloud"
        assert normalize_provider(alias) == "ovhcloud"

    def test_anonymous_credentials_omit_auth_sentinel(self):
        creds = resolve_api_key_provider_credentials("ovhcloud")
        assert creds["api_key"] == OMIT_AUTH_API_KEY

    def test_in_canonical_providers(self):
        assert any(p.slug == "ovhcloud" for p in CANONICAL_PROVIDERS)


class TestGroqProvider:
    def test_profile_registered(self):
        p = get_provider_profile("groq")
        assert p is not None
        assert p.name == "groq"
        assert p.allows_no_api_key is False
        assert "api.groq.com" in p.base_url
        assert "llama-3.3-70b-versatile" in p.fallback_models

    @pytest.mark.parametrize("alias", ["groq", "groq-cloud"])
    def test_aliases(self, alias):
        assert get_provider_profile(alias).name == "groq"
        assert normalize_provider(alias) == "groq"

    def test_in_canonical_providers(self):
        assert any(p.slug == "groq" for p in CANONICAL_PROVIDERS)

    def test_credentials_require_key(self):
        creds = resolve_api_key_provider_credentials("groq")
        assert creds["api_key"] == ""

    def test_credentials_with_key(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "gsk-test-key")
        creds = resolve_api_key_provider_credentials("groq")
        assert creds["api_key"] == "gsk-test-key"
        assert creds["base_url"].endswith("/openai/v1")

    def test_resolve_provider(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "gsk-test-key")
        assert resolve_provider("groq") == "groq"


class TestCerebrasProvider:
    def test_profile_registered(self):
        p = get_provider_profile("cerebras")
        assert p is not None
        assert p.name == "cerebras"
        assert "api.cerebras.ai" in p.base_url
        assert "gpt-oss-120b" in p.fallback_models

    @pytest.mark.parametrize("alias", ["cerebras", "cerebras-cloud"])
    def test_aliases(self, alias):
        assert get_provider_profile(alias).name == "cerebras"
        assert normalize_provider(alias) == "cerebras"

    def test_in_canonical_providers(self):
        assert any(p.slug == "cerebras" for p in CANONICAL_PROVIDERS)

    def test_credentials_with_key(self, monkeypatch):
        monkeypatch.setenv("CEREBRAS_API_KEY", "csk-test-key")
        creds = resolve_api_key_provider_credentials("cerebras")
        assert creds["api_key"] == "csk-test-key"
        assert "api.cerebras.ai" in creds["base_url"]


class TestSiliconflowProvider:
    def test_profile_registered(self):
        p = get_provider_profile("siliconflow")
        assert p is not None
        assert "siliconflow" in p.base_url
        assert normalize_provider("sf") == "siliconflow"

    def test_in_canonical_providers(self):
        assert any(p.slug == "siliconflow" for p in CANONICAL_PROVIDERS)


class TestSambanovaProvider:
    def test_profile_registered(self):
        p = get_provider_profile("sambanova")
        assert p is not None
        assert "sambanova" in p.base_url
        assert normalize_provider("samba") == "sambanova"

    def test_in_canonical_providers(self):
        assert any(p.slug == "sambanova" for p in CANONICAL_PROVIDERS)
