"""Cerebras free-tier inference provider.

Wafer-scale chip inference with an OpenAI-compatible endpoint. Free tier
(no credit card) caps context and daily tokens — see Cerebras Cloud docs.

See https://github.com/mnfst/awesome-free-llm-apis
"""

from providers import register_provider
from providers.base import ProviderProfile


cerebras = ProviderProfile(
    name="cerebras",
    aliases=("cerebras-cloud",),
    display_name="Cerebras",
    description="Cerebras — wafer-scale free-tier inference (OpenAI-compatible)",
    signup_url="https://cloud.cerebras.ai/",
    env_vars=("CEREBRAS_API_KEY", "CEREBRAS_BASE_URL"),
    base_url="https://api.cerebras.ai/v1",
    auth_type="api_key",
    default_aux_model="llama3.1-8b",
    fallback_models=(
        "gpt-oss-120b",
        "zai-glm-4.7",
        "llama-3.3-70b",
        "llama3.1-8b",
        "qwen-3-32b",
    ),
)

register_provider(cerebras)
