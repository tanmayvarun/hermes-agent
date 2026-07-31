"""Remote Ollama provider profile.

This profile targets an Ollama instance exposed on a remote machine with the
OpenAI-compatible `/v1` surface and the Ollama-native `/api/tags` catalog.
It is configured to allow anonymous access because the remote server is meant
to be exposed on a trusted network path.
"""

from __future__ import annotations

from typing import Any

from providers import register_provider
from providers.base import ProviderProfile


class RemoteOllamaProfile(ProviderProfile):
    """Remote Ollama server with anonymous access and native model listing."""

    def fetch_models(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 8.0,
    ) -> list[str] | None:
        effective_base = (base_url or self.base_url or "").strip().rstrip("/")
        if not effective_base:
            return None
        url = effective_base + "/api/tags"

        import json
        import urllib.request

        from hermes_cli.urllib_security import open_credentialed_url

        req = urllib.request.Request(url)
        req.add_header("Accept", "application/json")
        try:
            with open_credentialed_url(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode())
        except Exception:
            return None
        models = data.get("models") if isinstance(data, dict) else None
        if not isinstance(models, list):
            return None
        out: list[str] = []
        for item in models:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or item.get("model") or "").strip()
            if name:
                out.append(name)
        return out or None


ollama_remote = RemoteOllamaProfile(
    name="ollama-remote",
    aliases=("ollama_remote", "remote-ollama"),
    display_name="Remote Ollama",
    description="Remote Ollama server exposed over the network",
    signup_url="https://ollama.com/",
    env_vars=("OLLAMA_REMOTE_BASE_URL", "OLLAMA_REMOTE_API_KEY"),
    base_url="http://157.20.215.33:11434/v1",
    auth_type="api_key",
    allows_no_api_key=True,
    omit_auth_header=True,
    default_aux_model="qwen2.5:32b",
    fallback_models=(
        "qwen2.5:32b",
        "deepseek-r1:32b",
        "qwen3:235b",
        "qwen3:235b-instruct",
        "deepseek-r1:70b",
        "gpt-oss:120b",
        "llama3.1:70b",
    ),
)

register_provider(ollama_remote)
