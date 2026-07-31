"""Shared reasoning-consultation boundary for semantic judgment tasks.

This module keeps the *consultation* contract narrow:

- the caller supplies a small, task-specific message list
- the helper invokes the existing auxiliary LLM chokepoint
- the helper parses JSON, preserves abstention, and surfaces a compact trace

It intentionally does not know about app-specific semantics. Callers own the
projection step; this module owns the shared consultation lifecycle.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if hasattr(value, "to_dict") and callable(value.to_dict):
        try:
            return _json_safe(value.to_dict())
        except Exception:
            pass
    return str(value)


def _extract_text(response: Any) -> str:
    if isinstance(response, str):
        return response.strip()
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()
    choices = getattr(response, "choices", None)
    if isinstance(choices, list) and choices:
        message = getattr(choices[0], "message", None)
        if message is not None:
            content = getattr(message, "content", None)
            if isinstance(content, str) and content.strip():
                return content.strip()
    if isinstance(response, dict):
        for key in ("output_text", "text", "content"):
            val = response.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return str(response).strip()


def _extract_json_block(text: str) -> Optional[Dict[str, Any]]:
    raw = (text or "").strip()
    if not raw:
        return None
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL | re.IGNORECASE)
    if fenced:
        raw = fenced.group(1).strip()
    if not raw.startswith("{"):
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            raw = raw[start : end + 1]
    try:
        parsed = json.loads(raw)
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


@dataclass
class ReasoningConsultationResult:
    task: str
    messages: List[Dict[str, Any]] = field(default_factory=list)
    raw_response: str = ""
    parsed: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    abstained: bool = False
    reason: str = ""
    timeout_s: float = 0.0
    max_tokens: int = 0
    provider: str = ""
    model: str = ""
    base_url: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task": self.task,
            "messages": _json_safe(self.messages),
            "raw_response": self.raw_response,
            "parsed": _json_safe(self.parsed),
            "confidence": round(float(self.confidence or 0.0), 4),
            "abstained": bool(self.abstained),
            "reason": self.reason,
            "timeout_s": round(float(self.timeout_s or 0.0), 4),
            "max_tokens": int(self.max_tokens or 0),
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
        }


def consult_reasoning(
    task: str,
    messages: Sequence[Dict[str, Any]],
    *,
    caller: Optional[Callable[..., Any]] = None,
    call_kwargs: Optional[Dict[str, Any]] = None,
    temperature: float = 0.0,
    max_tokens: int = 256,
) -> ReasoningConsultationResult:
    """Run one bounded reasoning consultation through the shared LLM router."""
    effective_call_kwargs = dict(call_kwargs or {})
    effective_call_kwargs.pop("task", None)
    materialized_messages = [dict(msg) for msg in messages]
    if caller is None:
        from agent.auxiliary_client import call_llm as caller

    timeout_s = float(effective_call_kwargs.get("timeout") or 0.0)
    logger.info(
        "Reasoning consultation: task=%s messages=%d timeout=%.0fs max_tokens=%d",
        task,
        len(materialized_messages),
        timeout_s,
        int(max_tokens or 0),
    )
    response = caller(
        task=task,
        messages=materialized_messages,
        temperature=temperature,
        max_tokens=max_tokens,
        **effective_call_kwargs,
    )
    raw_text = _extract_text(response)
    parsed = _extract_json_block(raw_text) or {}
    confidence = 0.0
    try:
        confidence = float(parsed.get("confidence") or 0.0)
    except Exception:
        confidence = 0.0
    abstained = bool(
        parsed.get("needs_followup_observe")
        or parsed.get("abstain")
        or parsed.get("abstained")
        or parsed.get("needs_more_context")
    )
    reason = str(parsed.get("reason") or "").strip()
    if not parsed:
        reason = reason or "non_json_response"
    elif abstained and not reason:
        reason = "consultation_abstained"
    return ReasoningConsultationResult(
        task=task,
        messages=materialized_messages,
        raw_response=raw_text,
        parsed=parsed,
        confidence=confidence,
        abstained=abstained,
        reason=reason,
        timeout_s=timeout_s,
        max_tokens=int(max_tokens or 0),
        provider=str(effective_call_kwargs.get("provider") or ""),
        model=str(effective_call_kwargs.get("model") or ""),
        base_url=str(effective_call_kwargs.get("base_url") or ""),
    )
