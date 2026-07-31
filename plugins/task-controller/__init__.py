"""task-controller plugin — universal multi-tool budgets + capability dispatch.

Owns execution discipline shared by domain controllers (research,
filesystem, coding, …):

* ``pre_llm_call`` — reset per-turn counters; inject Task schema + remaining budgets;
  for clear locate-file intents, auto-dispatch ``LocateFileCapability`` and inject
  the structured ``CapabilityResult`` (strategy lives in the capability, not the LLM)
* ``pre_tool_call`` — block tools that exceed per-tool or global ``tool_calls`` caps
* ``post_tool_call`` — increment per-tool and global counters

Defaults (per user turn)::

    web_search: 5
    web_extract: 4
    locate_file: 2
    search_files: 15
    read_file: 40
    write_file: 20
    patch: 20
    terminal: 30
    browser_navigate: 8
    tool_calls: 60   # global backstop (any tool)

Config::

    plugins:
      entries:
        task-controller:
          budgets:
            web_search: 5
            read_file: 40
            tool_calls: 60
          auto_dispatch_locate: true   # default true

Legacy flat keys ``max_web_search`` / ``max_web_extract`` still work.

Env::

* ``TASK_CONTROLLER_MAX_WEB_SEARCH``
* ``TASK_CONTROLLER_MAX_WEB_EXTRACT``
* ``TASK_CONTROLLER_MAX_TOOL_CALLS``
* ``TASK_CONTROLLER_DISABLE=1``
* ``TASK_CONTROLLER_AUTO_LOCATE=0`` — disable locate capability auto-dispatch
"""

from __future__ import annotations

import logging
import os
import re
import threading
from typing import Any, Dict, List, Optional, Tuple

from agent.decision_tracking import DecisionComponent, decision_tracker

logger = logging.getLogger(__name__)

_DEFAULT_BUDGETS: Dict[str, int] = {
    "web_search": 5,
    "web_extract": 4,
    "locate_file": 2,
    "search_files": 15,
    "read_file": 40,
    "write_file": 20,
    "patch": 20,
    "terminal": 30,
    "browser_navigate": 8,
    "tool_calls": 60,
}

_GLOBAL_KEY = "tool_calls"

# Per-session turn counters. Keyed by session/task id.
_lock = threading.Lock()
_counts: Dict[str, Dict[str, int]] = {}
_caps: Dict[str, Dict[str, int]] = {}
_task_types: Dict[str, str] = {}

class _LlmTaskClassifier(DecisionComponent):
    component_name = "task_controller.llm_classifier"


_llm_classifier = _LlmTaskClassifier()


def _plugin_disabled() -> bool:
    return os.environ.get("TASK_CONTROLLER_DISABLE", "").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _auto_locate_enabled() -> bool:
    env = os.environ.get("TASK_CONTROLLER_AUTO_LOCATE", "").strip().lower()
    if env in {"0", "false", "no", "off"}:
        return False
    if env in {"1", "true", "yes", "on"}:
        return True
    try:
        from hermes_cli.config import load_config

        cfg = load_config() or {}
        entry = (
            ((cfg.get("plugins") or {}).get("entries") or {}).get("task-controller")
            or {}
        )
        if isinstance(entry, dict) and "auto_dispatch_locate" in entry:
            return bool(entry.get("auto_dispatch_locate"))
    except Exception:
        logger.debug("task-controller: auto_locate config unavailable", exc_info=True)
    return True


def _read_int_env(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(0, value)


def _llm_task_classification_enabled() -> bool:
    env = (os.environ.get("TASK_CONTROLLER_LLM_CLASSIFY") or "").strip().lower()
    if env in {"0", "false", "no", "off"}:
        return False
    if env in {"1", "true", "yes", "on"}:
        return True
    return True


def _llm_task_classification_timeout() -> float:
    raw = (os.environ.get("TASK_CONTROLLER_LLM_CLASSIFY_TIMEOUT") or "").strip()
    if not raw:
        return 8.0
    try:
        value = float(raw)
    except ValueError:
        return 8.0
    return max(1.0, value)


def _parse_llm_task_label(content: str) -> Optional[str]:
    text = (content or "").strip().lower()
    for label in ("research", "filesystem", "coding", "general"):
        if re.search(rf"\b{label}\b", text):
            return label
    return None


def _llm_classify_task_type(user_message: str) -> Tuple[Optional[str], Optional[str]]:
    if not _llm_task_classification_enabled():
        return None, None
    text = (user_message or "").strip()
    if not text:
        return None, None
    try:
        from agent.auxiliary_client import call_llm

        resp = call_llm(
            task="mcp",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Classify the user's request into exactly one label: "
                        "research, filesystem, coding, or general. "
                        "Reply with the label only."
                    ),
                },
                {"role": "user", "content": text},
            ],
            temperature=0,
            max_tokens=8,
            timeout=_llm_task_classification_timeout(),
        )
        content = (
            resp.choices[0].message.content
            if resp and getattr(resp, "choices", None)
            else ""
        )
        label = _parse_llm_task_label(content)
        if not label:
            return None, None
        decision_id = _llm_classifier.record_decision(
            label,
            context={"message": text},
            metadata={"source": "llm"},
        )
        return label, decision_id
    except Exception:
        logger.debug("task-controller: llm task classification unavailable", exc_info=True)
        return None, None


def _config_caps() -> Dict[str, int]:
    """Resolve caps from config.yaml, then env, then defaults."""
    caps = dict(_DEFAULT_BUDGETS)
    try:
        from hermes_cli.config import load_config

        cfg = load_config() or {}
        plugins_cfg = cfg.get("plugins") or {}
        entries = plugins_cfg.get("entries") or {}
        entry = entries.get("task-controller") or entries.get("task_controller") or {}
        if isinstance(entry, dict):
            budgets = entry.get("budgets")
            if isinstance(budgets, dict):
                for key, value in budgets.items():
                    try:
                        caps[str(key)] = max(0, int(value))
                    except (TypeError, ValueError):
                        continue
            # Legacy flat keys
            if "max_web_search" in entry:
                caps["web_search"] = max(0, int(entry["max_web_search"]))
            if "max_web_extract" in entry:
                caps["web_extract"] = max(0, int(entry["max_web_extract"]))
    except Exception:
        logger.debug("task-controller: config caps unavailable", exc_info=True)

    caps["web_search"] = _read_int_env(
        "TASK_CONTROLLER_MAX_WEB_SEARCH", caps["web_search"]
    )
    caps["web_extract"] = _read_int_env(
        "TASK_CONTROLLER_MAX_WEB_EXTRACT", caps["web_extract"]
    )
    caps[_GLOBAL_KEY] = _read_int_env(
        "TASK_CONTROLLER_MAX_TOOL_CALLS", caps[_GLOBAL_KEY]
    )
    return caps


def detect_task_type(user_message: str = "") -> str:
    """Task hint for controller guidance; LLM-only classification."""
    text = user_message or ""
    if not text.strip():
        return "general"
    llm_label, llm_id = _llm_classify_task_type(text)
    if llm_label and llm_id:
        _llm_classifier.adjudicate_decision(
            llm_id,
            outcome=llm_label,
        )
        return llm_label
    return "general"


def get_decision_metrics() -> Dict[str, Dict[str, Any]]:
    """Expose decision-component reliability summaries for inspection/tests."""
    return decision_tracker.all_stats()


def _checklist_hint(task_type: str) -> str:
    if task_type == "research":
        return (
            "Domain: Research Controller — emit Research Plan first; use todo; "
            "prefer official sources; build entity→URL source graph; stop when done."
        )
    if task_type == "filesystem":
        return (
            "Domain: Filesystem Controller — reason in capabilities, not raw search loops. "
            "Find intents: LocateFileCapability (tool locate_file / auto-dispatched). "
            "If tool choice is ambiguous, inspect describe_capability or tool_search once "
            "before falling back to raw tools. "
            "Then open with read_file. Only use raw search_files if locate failed and "
            "user asks to dig deeper. Escalate path cwd → ~/Downloads|Desktop|Documents "
            "→ ~ → / only if needed; list path artifacts; stop when done."
        )
    if task_type == "coding":
        return (
            "Domain: Coding Controller — plan → read → edit → test → fix → done; "
            "use todo; if unsure which tool chain fits, use describe_capability or "
            "tool_search before branching; stop when verification passes or budget exhausted."
        )
    return (
        "Domain: general — commit a short plan and todo checklist before heavy "
        "tool use; stop when checklist is done or budget is exhausted."
    )


def _needs_recency_guardrail(task_type: str, user_message: str = "") -> bool:
    if task_type != "research":
        return False
    text = (user_message or "").lower()
    if not text:
        return False
    recency_cues = ("latest", "most recent", "newest", "recent", "today", "current")
    media_cues = ("youtube", "podcast", "interview", "episode", "video", "link")
    return any(cue in text for cue in recency_cues) and any(
        cue in text for cue in media_cues
    )


def _recency_guardrail(task_type: str, user_message: str = "") -> str:
    if not _needs_recency_guardrail(task_type, user_message):
        return ""
    return (
        "Recency guardrail: for latest/current media requests, verify the item's own "
        "publication date before answering. Do not trust playlist/channel/search "
        "snippet 'updated' dates. Prefer the episode/watch page over playlists or "
        "channel hubs, compare multiple candidates, and report the exact published date."
    )


def _session_key(session_id: str = "", task_id: str = "") -> str:
    return (session_id or task_id or "default").strip() or "default"


def reset_session(session_id: str = "", task_id: str = "") -> None:
    """Clear counters for a session (also used by tests)."""
    key = _session_key(session_id, task_id)
    with _lock:
        _counts.pop(key, None)
        _caps.pop(key, None)
        _task_types.pop(key, None)


def reset_decision_metrics() -> None:
    """Clear tracked reliability metrics (primarily for tests)."""
    decision_tracker.reset()


def get_counts(session_id: str = "", task_id: str = "") -> Dict[str, int]:
    key = _session_key(session_id, task_id)
    with _lock:
        return dict(_counts.get(key) or {})


def get_caps(session_id: str = "", task_id: str = "") -> Dict[str, int]:
    key = _session_key(session_id, task_id)
    with _lock:
        if key in _caps:
            return dict(_caps[key])
    return _config_caps()


def _empty_counts(caps: Dict[str, int]) -> Dict[str, int]:
    return {name: 0 for name in caps}


def _ensure_turn(session_id: str, task_id: str = "", user_message: str = "") -> str:
    """Reset counters at the start of a user turn and store caps."""
    key = _session_key(session_id, task_id)
    caps = _config_caps()
    task_type = detect_task_type(user_message)
    with _lock:
        _counts[key] = _empty_counts(caps)
        _caps[key] = caps
        _task_types[key] = task_type
    return key


def _budget_lines(caps: Dict[str, int], counts: Dict[str, int]) -> List[str]:
    # Stable order: defaults first, then any extras, tool_calls last.
    ordered = [k for k in _DEFAULT_BUDGETS if k in caps]
    for k in caps:
        if k not in ordered:
            ordered.append(k)
    lines = []
    for name in ordered:
        cap = caps.get(name, 0)
        used = counts.get(name, 0)
        left = max(0, cap - used)
        lines.append(f"  {name}: {left}/{cap}")
    return lines


def _budget_context(key: str, user_message: str = "") -> str:
    caps = get_caps(session_id=key)
    counts = get_counts(session_id=key)
    with _lock:
        task_type = _task_types.get(key) or detect_task_type(user_message)
    objective = (user_message or "").strip().replace("\n", " ")
    if len(objective) > 200:
        objective = objective[:197] + "..."
    lines = _budget_lines(caps, counts)
    recency_guardrail = _recency_guardrail(task_type, user_message)
    return (
        "[Task Controller]\n"
        "Task:\n"
        f"  type: {task_type}\n"
        f"  objective: {objective or '(from user message)'}\n"
        "  plan: required before heavy tool use\n"
        "  checklist: via todo tool\n"
        "  completion: checklist_done OR budget_exhausted OR user_abort\n"
        "  layering: Task Controller → Capability → Tools "
        "(prefer capabilities over raw tool loops)\n"
        "budget remaining:\n"
        + "\n".join(lines)
        + "\n"
        + _checklist_hint(task_type)
        + (f"\n{recency_guardrail}" if recency_guardrail else "")
        + "\n"
        "If the checklist is complete OR a required budget hits 0, stop exploring "
        "and synthesize/verify from what you already have."
    )


def _charge_tool(key: str, tool_name: str) -> None:
    """Count a capability dispatch against the tool budget."""
    with _lock:
        counts = _counts.setdefault(key, {})
        counts[_GLOBAL_KEY] = counts.get(_GLOBAL_KEY, 0) + 1
        if tool_name in (_caps.get(key) or {}) and tool_name != _GLOBAL_KEY:
            counts[tool_name] = counts.get(tool_name, 0) + 1


def _dispatch_locate_capability(
    key: str, user_message: str, *, search_fn: Any = None
) -> str:
    """Run LocateFileCapability for clear find intents; return context block or ''."""
    if not _auto_locate_enabled():
        return ""
    try:
        from agent.capabilities.locate_file import (
            LocateFileCapability,
            is_locate_intent,
        )
    except Exception:
        logger.debug("task-controller: capabilities unavailable", exc_info=True)
        return ""

    if not is_locate_intent(user_message):
        return ""

    caps = get_caps(session_id=key)
    counts = get_counts(session_id=key)
    locate_cap = caps.get("locate_file", 0)
    locate_used = counts.get("locate_file", 0)
    if locate_cap > 0 and locate_used >= locate_cap:
        return ""

    extras: Dict[str, Any] = {}
    if search_fn is not None:
        extras["search_fn"] = search_fn

    try:
        result = LocateFileCapability().execute_objective(
            user_message,
            session_id=key,
            # Share engine cache with the locate_file tool (default task_id).
            task_id="default",
            budget={"locate_file": max(0, locate_cap - locate_used)},
            **extras,
        )
    except Exception:
        logger.debug("task-controller: locate capability failed", exc_info=True)
        return ""

    _charge_tool(key, "locate_file")

    return result.format_context_block()


def _dispatch_latest_media_capability(
    key: str, user_message: str, *, search_fn: Any = None
) -> str:
    """Run latest-media capability for clear latest media link intents."""
    try:
        from agent.capabilities.latest_media import (
            ResolveLatestMediaCapability,
            is_latest_media_intent,
        )
    except Exception:
        logger.debug("task-controller: latest-media capability unavailable", exc_info=True)
        return ""

    if not is_latest_media_intent(user_message):
        return ""

    extras: Dict[str, Any] = {}
    if search_fn is not None:
        extras["search_fn"] = search_fn

    try:
        result = ResolveLatestMediaCapability().execute_objective(
            user_message,
            session_id=key,
            task_id="default",
            budget={"web_search": max(0, get_caps(session_id=key).get("web_search", 0) - get_counts(session_id=key).get("web_search", 0))},
            **extras,
        )
    except Exception:
        logger.debug("task-controller: latest-media capability failed", exc_info=True)
        return ""

    _charge_tool(key, "web_search")
    return result.format_context_block()


def _block_message(tool_name: str, cap: int, *, global_cap: bool = False) -> Dict[str, str]:
    kind = "Global tool_calls" if global_cap else f"{tool_name}"
    return {
        "action": "block",
        "message": (
            f"Budget exhausted — synthesize/verify and stop. "
            f"({kind} cap is {cap} per turn; raise via "
            f"plugins.entries.task-controller.budgets or "
            f"TASK_CONTROLLER_MAX_* env vars.)"
        ),
    }


def on_pre_llm_call(
    session_id: str = "",
    user_message: str = "",
    conversation_history: Any = None,
    is_first_turn: bool = False,
    model: str = "",
    platform: str = "",
    **_: Any,
) -> Optional[Dict[str, str]]:
    """Reset per-turn budget and inject Task schema + remaining quotas."""
    if _plugin_disabled():
        return None
    key = _ensure_turn(session_id, user_message=user_message or "")
    # Clear locate_file stage cache for this session on each user turn.
    try:
        from tools.locate_file import reset_locate_state

        reset_locate_state(session_id or key)
        reset_locate_state("default")
    except Exception:
        logger.debug("task-controller: locate_file reset skipped", exc_info=True)

    parts = [_budget_context(key, user_message=user_message or "")]
    latest_media_block = _dispatch_latest_media_capability(key, user_message or "")
    if latest_media_block:
        parts[0] = _budget_context(key, user_message=user_message or "")
        parts.append(latest_media_block)
    locate_block = _dispatch_locate_capability(key, user_message or "")
    if locate_block:
        # Refresh budget lines after charging locate_file
        parts[0] = _budget_context(key, user_message=user_message or "")
        parts.append(locate_block)
    return {"context": "\n\n".join(parts)}


def _init_if_needed(key: str) -> None:
    with _lock:
        if key not in _counts:
            caps = _config_caps()
            _counts[key] = _empty_counts(caps)
            _caps[key] = caps
            _task_types.setdefault(key, "general")


def on_pre_tool_call(
    tool_name: str = "",
    args: Any = None,
    task_id: str = "",
    session_id: str = "",
    **_: Any,
) -> Optional[Dict[str, str]]:
    """Block when per-tool or global tool_calls budget is exhausted."""
    if _plugin_disabled():
        return None
    if not tool_name:
        return None

    key = _session_key(session_id, task_id)
    _init_if_needed(key)

    with _lock:
        caps = _caps.get(key) or _config_caps()
        counts = _counts.get(key) or {}
        global_used = counts.get(_GLOBAL_KEY, 0)
        global_cap = caps.get(_GLOBAL_KEY, 0)

    if global_cap > 0 and global_used >= global_cap:
        return _block_message(tool_name, global_cap, global_cap=True)

    # Tools without an explicit per-tool cap still count toward tool_calls only.
    if tool_name in caps and tool_name != _GLOBAL_KEY:
        used = counts.get(tool_name, 0)
        cap = caps.get(tool_name, 0)
        if cap > 0 and used >= cap:
            return _block_message(tool_name, cap, global_cap=False)

    return None


def on_post_tool_call(
    tool_name: str = "",
    args: Any = None,
    result: Any = None,
    task_id: str = "",
    session_id: str = "",
    duration_ms: int = 0,
    **_: Any,
) -> None:
    """Increment per-tool (if budgeted) and global tool_calls counters."""
    if _plugin_disabled():
        return
    if not tool_name:
        return
    key = _session_key(session_id, task_id)
    _init_if_needed(key)
    with _lock:
        counts = _counts.setdefault(key, {})
        counts[_GLOBAL_KEY] = counts.get(_GLOBAL_KEY, 0) + 1
        if tool_name in (_caps.get(key) or {}) and tool_name != _GLOBAL_KEY:
            counts[tool_name] = counts.get(tool_name, 0) + 1


def register(ctx) -> None:
    ctx.register_hook("pre_llm_call", on_pre_llm_call)
    ctx.register_hook("pre_tool_call", on_pre_tool_call)
    ctx.register_hook("post_tool_call", on_post_tool_call)
