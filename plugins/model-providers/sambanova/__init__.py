"""SambaNova Cloud — free-tier ultra-fast OpenAI-compatible inference.

Free tier (no credit card): ≈20 RPM / 20 RPD / 200K TPD per model, plus
starter credits. Requires a free API key.

See https://github.com/mnfst/awesome-free-llm-apis
"""

from providers import register_provider
from providers.base import ProviderProfile


sambanova = ProviderProfile(
    name="sambanova",
    aliases=("samba", "samba-nova", "snova"),
    display_name="SambaNova",
    description="SambaNova — free-tier ultra-fast RDU inference (OpenAI-compatible)",
    signup_url="https://cloud.sambanova.ai/apis",
    env_vars=("SAMBANOVA_API_KEY", "SAMBANOVA_BASE_URL"),
    base_url="https://api.sambanova.ai/v1",
    auth_type="api_key",
    default_aux_model="Meta-Llama-3.3-70B-Instruct",
    fallback_models=(
        "Meta-Llama-3.3-70B-Instruct",
        "DeepSeek-V3.1",
        "gpt-oss-120b",
        "MiniMax-M2.7",
        "gemma-4-31B-it",
    ),
)

register_provider(sambanova)
