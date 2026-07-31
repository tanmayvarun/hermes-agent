"""LLM7.io free model gateway / router.

Zero-friction OpenAI-compatible gateway with a free anonymous tier
(no registration required for basic access). Optional ``LLM7_API_KEY``
raises rate limits. Catalog spans open and proprietary models.

See https://github.com/mnfst/awesome-free-llm-apis and https://token.llm7.io
"""

from providers import register_provider
from providers.base import ProviderProfile


llm7 = ProviderProfile(
    name="llm7",
    aliases=("llm7.io", "llm7io"),
    display_name="LLM7",
    description="LLM7 — free OpenAI-compatible model gateway (no key required for basic access)",
    signup_url="https://token.llm7.io",
    env_vars=("LLM7_API_KEY", "LLM7_BASE_URL"),
    base_url="https://api.llm7.io/v1",
    auth_type="api_key",
    allows_no_api_key=True,
    strict_vision_tool_schema=True,
    default_aux_model="gpt-oss:20b",
    fallback_models=(
        "gpt-oss:20b",
        "codestral-latest",
        "minimax-m2.7",
        "deepseek-v4-flash",
        "mistral-small-3.1-24b",
        "qwen2.5-coder-32b",
    ),
)

register_provider(llm7)
