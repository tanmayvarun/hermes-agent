"""Mistral provider profile.

Mistral Studio offers a free mode with an OpenAI-compatible API.
"""

from providers import register_provider
from providers.base import ProviderProfile


mistral = ProviderProfile(
    name="mistral",
    aliases=("mistralai", "mistral-ai"),
    display_name="Mistral",
    description="Mistral AI — free Studio API with OpenAI-compatible endpoints",
    signup_url="https://docs.mistral.ai/getting-started/quickstarts/studio/activate-and-generate-api-key",
    env_vars=("MISTRAL_API_KEY", "MISTRAL_BASE_URL"),
    base_url="https://api.mistral.ai/v1",
    auth_type="api_key",
    supports_vision=True,
    default_aux_model="mistral-small-latest",
    fallback_models=(
        "mistral-small-latest",
        "mistral-large-latest",
        "codestral-latest",
        "pixtral-large-latest",
    ),
)

register_provider(mistral)
