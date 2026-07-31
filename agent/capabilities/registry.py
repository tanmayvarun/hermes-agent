"""Simple in-process capability registry."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from agent.capabilities.base import Capability

_REGISTRY: Dict[str, Capability] = {}


def register_capability(capability: Capability) -> Capability:
    name = getattr(capability, "name", "") or capability.__class__.__name__
    _REGISTRY[name] = capability
    return capability


def get_capability(name: str) -> Optional[Capability]:
    return _REGISTRY.get(name)


def list_capabilities() -> List[str]:
    return sorted(_REGISTRY.keys())


def clear_capabilities() -> None:
    _REGISTRY.clear()


def describe_capability(name: str) -> Optional[Dict[str, Any]]:
    """Return capability metadata with required-tool registry status."""
    capability = get_capability(name)
    if capability is None:
        return None

    try:
        from tools.registry import registry as tool_registry
    except Exception:
        tool_registry = None

    required_tools: List[Dict[str, Any]] = []
    all_available = True
    for tool_name in list(getattr(capability, "required_tools", []) or []):
        entry = tool_registry.get_entry(tool_name) if tool_registry is not None else None
        available = False
        if entry is not None:
            try:
                available = bool(entry.check_fn()) if entry.check_fn else True
            except Exception:
                available = False
        all_available = all_available and available
        required_tools.append(
            {
                "name": tool_name,
                "registered": entry is not None,
                "toolset": entry.toolset if entry is not None else None,
                "available": available,
                "description": entry.description if entry is not None else "",
            }
        )

    return {
        "name": name,
        "description": getattr(capability, "description", "") or "",
        "required_tools": required_tools,
        "all_required_tools_available": all_available,
    }


def list_capability_specs() -> List[Dict[str, Any]]:
    """Return concise metadata for all registered capabilities."""
    specs: List[Dict[str, Any]] = []
    for name in list_capabilities():
        spec = describe_capability(name)
        if spec is not None:
            specs.append(spec)
    return specs


def ensure_builtins() -> None:
    """Register built-in capabilities (idempotent)."""
    from agent.capabilities.locate_file import LocateFileCapability
    from agent.capabilities.latest_media import ResolveLatestMediaCapability
    from agent.capabilities.pipedream_connect import PipedreamConnectCapability
    from agent.capabilities.prompt_benchmark import PromptBenchmarkCapability

    if "locate_file" not in _REGISTRY:
        register_capability(LocateFileCapability())
    if "latest_media" not in _REGISTRY:
        register_capability(ResolveLatestMediaCapability())
    if "pipedream_connect" not in _REGISTRY:
        register_capability(PipedreamConnectCapability())
    if "prompt_benchmark" not in _REGISTRY:
        register_capability(PromptBenchmarkCapability())
