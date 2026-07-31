"""Aion Labs provider profile.

OpenAI-compatible API with a free tier and no card required. Use
``AION_API_KEY`` for auth.
"""

from providers import register_provider
from providers.base import ProviderProfile


aion = ProviderProfile(
    name="aion",
    aliases=("aionlabs", "aion-labs"),
    display_name="Aion Labs",
    description="Aion Labs — OpenAI-compatible API with a free tier",
    signup_url="https://www.aionlabs.ai/docs/quickstart/",
    env_vars=("AION_API_KEY", "AION_BASE_URL"),
    base_url="https://api.aionlabs.ai/v1",
    auth_type="api_key",
    supports_vision=False,
    default_aux_model="aion-labs/aion-3.0-mini",
    fallback_models=(
        "aion-labs/aion-3.0-mini",
        "aion-labs/aion-2.5",
        "aion-labs/aion-2.0",
        "aion-labs/aion-rp-llama-3.1-8b",
    ),
)

register_provider(aion)
