"""GitHub Models provider profile.

OpenAI-compatible inference endpoint backed by GitHub Models. Requires a
GitHub token with ``models: read`` scope. We use the catalog endpoint for
model discovery and the inference endpoint for completions.
"""

from providers import register_provider
from providers.base import ProviderProfile


github_models = ProviderProfile(
    name="github-models-api",
    aliases=("gh-models",),
    display_name="GitHub Models",
    description="GitHub Models — free prototyping via GitHub auth",
    signup_url="https://github.com/marketplace/models",
    env_vars=("GITHUB_TOKEN", "GH_TOKEN", "GITHUB_MODELS_BASE_URL"),
    base_url="https://models.github.ai/inference",
    models_url="https://models.github.ai/catalog/models",
    auth_type="api_key",
    supports_vision=True,
    default_headers={
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2026-03-10",
    },
    default_aux_model="openai/gpt-4.1-mini",
    fallback_models=(
        "openai/gpt-4.1-mini",
        "openai/gpt-4.1",
        "openai/gpt-4o",
        "DeepSeek-R1",
        "Meta-Llama-3.3-70B",
    ),
)

register_provider(github_models)
