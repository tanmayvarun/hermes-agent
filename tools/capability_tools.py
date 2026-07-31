"""Capability registry tools.

Expose reusable capability metadata to the LLM so it can choose a capability
or inspect which primitive tools back that capability before acting.
"""

from __future__ import annotations

import json

from agent.capabilities import (
    describe_capability as _describe_capability,
    ensure_builtins,
    list_capability_specs,
)
from tools.registry import registry


LIST_CAPABILITIES_SCHEMA = {
    "name": "list_capabilities",
    "description": (
        "List reusable agent capabilities and the primitive tools they depend on. "
        "Use this when you are unsure which higher-level capability fits a task."
    ),
    "parameters": {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
}


DESCRIBE_CAPABILITY_SCHEMA = {
    "name": "describe_capability",
    "description": (
        "Inspect one capability in detail, including which concrete tools it uses "
        "and whether those tools are currently registered/available."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Capability name, for example locate_file.",
            }
        },
        "required": ["name"],
        "additionalProperties": False,
    },
}


def _handle_list_capabilities(args, **kwargs):
    ensure_builtins()
    return json.dumps(
        {
            "success": True,
            "capabilities": list_capability_specs(),
        },
        ensure_ascii=False,
        indent=2,
    )


def _handle_describe_capability(args, **kwargs):
    ensure_builtins()
    name = str((args or {}).get("name") or "").strip()
    if not name:
        return json.dumps(
            {"success": False, "error": "name is required"},
            ensure_ascii=False,
            indent=2,
        )
    spec = _describe_capability(name)
    if spec is None:
        return json.dumps(
            {"success": False, "error": f"Unknown capability: {name}"},
            ensure_ascii=False,
            indent=2,
        )
    return json.dumps(
        {
            "success": True,
            "capability": spec,
        },
        ensure_ascii=False,
        indent=2,
    )


registry.register(
    name="list_capabilities",
    toolset="capability",
    schema=LIST_CAPABILITIES_SCHEMA,
    handler=_handle_list_capabilities,
    emoji="🧭",
    max_result_size_chars=100_000,
)
registry.register(
    name="describe_capability",
    toolset="capability",
    schema=DESCRIBE_CAPABILITY_SCHEMA,
    handler=_handle_describe_capability,
    emoji="🧩",
    max_result_size_chars=100_000,
)
