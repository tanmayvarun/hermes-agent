"""SiliconFlow — free-tier OpenAI-compatible inference (CN/global).

Permanently free models with relatively generous free-tier RPM (≈30 RPM /
60K TPM on free chat models). Requires a free API key from the console.

See https://github.com/mnfst/awesome-free-llm-apis
"""

from providers import register_provider
from providers.base import ProviderProfile


siliconflow = ProviderProfile(
    name="siliconflow",
    aliases=("silicon-flow", "sf", "siliconcloud"),
    display_name="SiliconFlow",
    description="SiliconFlow — free-tier OpenAI-compatible models (≈30 RPM)",
    signup_url="https://cloud.siliconflow.cn/account/ak",
    env_vars=("SILICONFLOW_API_KEY", "SILICONFLOW_BASE_URL"),
    base_url="https://api.siliconflow.cn/v1",
    auth_type="api_key",
    default_aux_model="Qwen/Qwen3-8B",
    fallback_models=(
        "Qwen/Qwen3-8B",
        "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
        "Qwen/Qwen2.5-7B-Instruct",
        "THUDM/glm-4-9b-chat",
    ),
)

register_provider(siliconflow)
