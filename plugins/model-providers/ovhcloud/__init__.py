"""OVHcloud AI Endpoints — free anonymous OpenAI-compatible gateway.

Permanent free anonymous tier (no signup / no API key): 2 RPM per IP per
model. Higher limits require an OVHcloud Public Cloud API key.

Anonymous calls must omit the Authorization header entirely — any dummy
Bearer token is rejected with 403. See ProviderProfile.omit_auth_header.

See https://github.com/mnfst/awesome-free-llm-apis
"""

from providers import register_provider
from providers.base import ProviderProfile


ovhcloud = ProviderProfile(
    name="ovhcloud",
    aliases=("ovh", "ovh-cloud", "ovhcloud-ai"),
    display_name="OVHcloud AI Endpoints",
    description="OVHcloud — free anonymous EU OpenAI-compatible endpoints (2 RPM/IP)",
    signup_url="https://www.ovhcloud.com/en/public-cloud/ai-endpoints/",
    env_vars=("OVHCLOUD_API_KEY", "OVHCLOUD_BASE_URL"),
    base_url="https://oai.endpoints.kepler.ai.cloud.ovh.net/v1",
    auth_type="api_key",
    allows_no_api_key=True,
    omit_auth_header=True,
    default_aux_model="gpt-oss-20b",
    fallback_models=(
        "gpt-oss-20b",
        "gpt-oss-120b",
        "Qwen3-Coder-30B-A3B-Instruct",
        "Qwen3.6-27B",
        "Meta-Llama-3_3-70B-Instruct",
        "Mistral-Small-3.2-24B-Instruct-2506",
        "Llama-3.1-8B-Instruct",
    ),
)

register_provider(ovhcloud)
