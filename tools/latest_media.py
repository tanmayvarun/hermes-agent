"""Tool wrapper for ResolveLatestMediaCapability."""

from __future__ import annotations

import json

from tools.registry import registry


def latest_media_tool(query: str, task_id: str = "default") -> str:
    from agent.capabilities.latest_media import ResolveLatestMediaCapability

    cap = ResolveLatestMediaCapability()
    result = cap.execute_objective(
        query,
        task_id=task_id,
    )
    return json.dumps(cap.to_tool_payload(result), ensure_ascii=False, indent=2)


LATEST_MEDIA_SCHEMA = {
    "name": "latest_media",
    "description": (
        "Resolve a latest/newest/current media link request by issuing multiple "
        "web searches and preferring dated episode/watch pages over playlists, "
        "channels, and reposts."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Natural-language latest media request, for example: share the YouTube link to latest podcast of Jaya Kishori.",
            }
        },
        "required": ["query"],
        "additionalProperties": False,
    },
}


def _handle_latest_media(args, **kwargs):
    return latest_media_tool(
        str((args or {}).get("query") or ""),
        task_id=str(kwargs.get("task_id") or "default"),
    )


registry.register(
    name="latest_media",
    toolset="web",
    schema=LATEST_MEDIA_SCHEMA,
    handler=_handle_latest_media,
    emoji="🕒",
    max_result_size_chars=100_000,
)
