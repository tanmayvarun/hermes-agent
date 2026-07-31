"""Pollinations provider profile.

OpenAI-compatible text API with permanent free keys (sk_/pk_). The service
also exposes multimodal endpoints, so we keep vision support enabled.
"""

from providers import register_provider
from providers.base import ProviderProfile


pollinations = ProviderProfile(
    name="pollinations",
    aliases=("pollinations-ai",),
    display_name="Pollinations",
    description="Pollinations — OpenAI-compatible API with permanent free tiers",
    signup_url="https://gen.pollinations.ai/docs",
    env_vars=("POLLINATIONS_API_KEY", "POLLINATIONS_BASE_URL"),
    base_url="https://gen.pollinations.ai/v1",
    auth_type="api_key",
    supports_vision=True,
    default_aux_model="openai",
    fallback_models=(
        "openai",
        "openai-large",
        "gpt-5.4",
        "mistral-small",
        "deepseek",
        "llama",
    ),
)

register_provider(pollinations)
