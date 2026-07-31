"""Groq free-tier inference provider.

Ultra-fast LPU inference via an OpenAI-compatible endpoint. Free tier
requires an API key from https://console.groq.com/keys (no credit card).

``GROQ_API_KEY`` is also used by Hermes STT (Whisper); the same key works
for chat here.

See https://github.com/mnfst/awesome-free-llm-apis
"""

from providers import register_provider
from providers.base import ProviderProfile


groq = ProviderProfile(
    name="groq",
    aliases=("groq-cloud",),
    display_name="Groq",
    description="Groq — ultra-fast free-tier LPU inference (OpenAI-compatible)",
    signup_url="https://console.groq.com/keys",
    env_vars=("GROQ_API_KEY", "GROQ_BASE_URL"),
    base_url="https://api.groq.com/openai/v1",
    auth_type="api_key",
    default_aux_model="llama-3.1-8b-instant",
    fallback_models=(
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "llama-4-scout-17b-16e-instruct",
        "qwen3-32b",
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
    ),
)

register_provider(groq)
