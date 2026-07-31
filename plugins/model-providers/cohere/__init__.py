"""Cohere provider profile.

Cohere's compatibility API is OpenAI-compatible and offers a trial key
with free-but-limited usage. Hermes can route it like any other direct
API-key provider through ``https://api.cohere.ai/compatibility/v1``.
"""

from providers import register_provider
from providers.base import ProviderProfile


cohere = ProviderProfile(
    name="cohere",
    aliases=("cohere-compat", "cohere-ai"),
    display_name="Cohere",
    description="Cohere — trial/free-tier compatibility API (OpenAI-compatible)",
    signup_url="https://dashboard.cohere.com/api-keys",
    env_vars=("COHERE_API_KEY", "COHERE_BASE_URL"),
    base_url="https://api.cohere.ai/compatibility/v1",
    auth_type="api_key",
    default_aux_model="command-a-plus-05-2026",
    fallback_models=(
        "command-a-plus-05-2026",
        "command-a-reasoning-08-2025",
    ),
)

register_provider(cohere)
