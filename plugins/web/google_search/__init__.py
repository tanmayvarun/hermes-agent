"""Google Search web provider plugin."""

from __future__ import annotations

from .provider import GoogleSearchWebSearchProvider


def register(ctx) -> None:
    ctx.register_web_search_provider(GoogleSearchWebSearchProvider())
