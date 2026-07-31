"""Cloudflare Workers AI provider profile.

Cloudflare Workers AI uses an account-specific OpenAI-compatible base URL:
``https://api.cloudflare.com/client/v4/accounts/<ACCOUNT_ID>/ai/v1``.
Hermes accepts either a full ``CLOUDFLARE_BASE_URL`` override or the
standard ``CLOUDFLARE_ACCOUNT_ID`` + ``CLOUDFLARE_API_TOKEN`` pair.
"""

from __future__ import annotations

import os

from providers import register_provider
from providers.base import ProviderProfile


class CloudflareWorkersAIProfile(ProviderProfile):
    """Workers AI needs account-aware base URL resolution."""

    def _resolved_base_url(self, base_url: str | None = None) -> str:
        explicit = str(base_url or "").strip().rstrip("/")
        if explicit:
            return explicit
        env_url = os.getenv("CLOUDFLARE_BASE_URL", "").strip().rstrip("/")
        if env_url:
            return env_url
        account_id = (
            os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
            or os.getenv("CF_ACCOUNT_ID", "").strip()
        )
        if account_id:
            return f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1"
        return self.base_url.rstrip("/")

    def fetch_models(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 8.0,
    ) -> list[str] | None:
        resolved_base = self._resolved_base_url(base_url)
        if not resolved_base or "{account_id}" in resolved_base:
            return None
        return super().fetch_models(api_key=api_key, base_url=resolved_base, timeout=timeout)


cloudflare_workers_ai = CloudflareWorkersAIProfile(
    name="cloudflare-workers-ai",
    aliases=("cf-workers", "workers-ai", "cloudflare-workers"),
    display_name="Cloudflare Workers AI",
    description="Cloudflare Workers AI — free-tier account-based inference",
    signup_url="https://dash.cloudflare.com/",
    env_vars=(
        "CLOUDFLARE_API_TOKEN",
        "CLOUDFLARE_ACCOUNT_ID",
        "CLOUDFLARE_BASE_URL",
        "CF_API_TOKEN",
        "CF_ACCOUNT_ID",
    ),
    base_url="https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1",
    auth_type="api_key",
    supports_vision=True,
    default_aux_model="@cf/openai/gpt-oss-120b",
    fallback_models=(
        "@cf/openai/gpt-oss-120b",
        "@cf/nvidia/nemotron-3-super-120b-a12b",
    ),
)

register_provider(cloudflare_workers_ai)
