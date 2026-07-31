"""Proactive vision-tool schema adaptation.

Some gateways (e.g. LLM7) reject the *entire* chat request when vision-related
tools appear in the ``tools`` array for a text-only model — even with no image
content in messages. Hermes historically discovered this only after a 400 and
printed a scary warning. These helpers detect unsupported vision up front and
strip the tools quietly at agent init.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

# Same set as the reactive strip path in conversation_loop.py.
VISION_SCHEMA_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "vision_analyze",
        "browser_vision",
        "browser_get_images",
        "video_analyze",
        "image_generate",
    }
)


def _provider_strict_vision_tool_schema(provider: str) -> bool:
    try:
        from providers import get_provider_profile

        profile = get_provider_profile(str(provider or "").strip())
        return bool(
            profile is not None
            and getattr(profile, "strict_vision_tool_schema", False)
        )
    except Exception:
        return False


def should_strip_vision_tools(
    provider: str | None,
    model: str | None,
    *,
    cfg: Optional[Dict[str, Any]] = None,
) -> bool:
    """Return True when vision tools must be removed from the tools schema.

    Policy (see plan):
      - supports_vision False  → strip
      - supports_vision True   → keep
      - unknown (None)         → strip only if provider.strict_vision_tool_schema
    """
    provider = str(provider or "").strip()
    model = str(model or "").strip()
    if not provider and not model:
        return False

    if cfg is None:
        try:
            from hermes_cli.config import load_config

            cfg = load_config()
        except Exception:
            cfg = None

    try:
        from agent.image_routing import _lookup_supports_vision

        supports = _lookup_supports_vision(provider, model, cfg)
    except Exception:
        supports = None

    if supports is False:
        return True
    if supports is True:
        return False
    # Unknown — fail closed only for strict gateways.
    return _provider_strict_vision_tool_schema(provider)


def strip_vision_tools(
    tools: Sequence[Dict[str, Any]] | None,
) -> Tuple[List[Dict[str, Any]], int]:
    """Filter vision tools from an OpenAI-format tools list.

    Returns ``(filtered_tools, removed_count)``.
    """
    if not tools:
        return [], 0
    kept: List[Dict[str, Any]] = []
    removed = 0
    for tool in tools:
        if not isinstance(tool, dict):
            kept.append(tool)  # type: ignore[arg-type]
            continue
        name = str((tool.get("function") or {}).get("name") or tool.get("name") or "")
        if name in VISION_SCHEMA_TOOL_NAMES:
            removed += 1
            continue
        kept.append(tool)
    return kept, removed


def apply_vision_tool_adaptation(
    agent: Any,
    *,
    quiet: bool = False,
) -> int:
    """Strip vision tools on *agent* when the main model cannot use them.

    Sets ``agent._vision_supported = False`` and ``agent._vision_tools_stripped``
    when tools are removed. Returns the number of tools removed.
    """
    provider = getattr(agent, "provider", None) or ""
    model = getattr(agent, "model", None) or ""
    if not should_strip_vision_tools(provider, model):
        agent._vision_tools_stripped = False
        return 0

    tools = getattr(agent, "tools", None) or []
    filtered, removed = strip_vision_tools(tools)
    if removed:
        agent.tools = filtered
        if hasattr(agent, "valid_tool_names"):
            agent.valid_tool_names = {
                t["function"]["name"]
                for t in filtered
                if isinstance(t, dict) and isinstance(t.get("function"), dict)
                and t["function"].get("name")
            }
        logger.info(
            "Vision unsupported for %s/%s — removed %d vision tool(s) from schema",
            provider,
            model,
            removed,
        )
        if not quiet and not getattr(agent, "quiet_mode", False):
            # Calm startup note (not the scary server-rejection warning).
            print("Vision: unsupported")
            print("Removing vision tools...")

    agent._vision_supported = False
    agent._vision_tools_stripped = True
    agent._vision_adaptation_note = (
        "Vision: unsupported\nRemoving vision tools..."
        if removed
        else "Vision: unsupported"
    )
    return removed
