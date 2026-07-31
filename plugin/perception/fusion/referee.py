"""LLM referee for ambiguous perception fusion.

The referee never invents UI structure. It can only choose among the
observed sources, accept the deterministic fusion, or request a fresh
re-observe when the evidence is too contradictory to trust.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from agent import auxiliary_client

logger = logging.getLogger(__name__)


@dataclass
class FusionSourceSummary:
    source_id: str
    node_count: int
    hypothesis_count: int
    coverage: float
    degraded: bool
    latency_ms: float
    top_labels: List[str] = field(default_factory=list)
    top_roles: List[str] = field(default_factory=list)
    sample_nodes: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FusionRefereeDecision:
    action: str = "accept"
    preferred_source_id: str = ""
    confidence: float = 0.0
    reason: str = ""
    should_reobserve: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class FusionReferee:
    """Ask the current main LLM to arbitrate ambiguous source fusion."""

    def __init__(self, *, task: str = "perception") -> None:
        self.task = task

    def decide(self, payload: Dict[str, Any]) -> FusionRefereeDecision:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a perception-fusion referee for a GUI agent. "
                    "You must NOT invent UI elements. You may only choose one of: "
                    "\"accept\" the deterministic fused result, \"prefer_source\" and name one "
                    "observed source_id, or \"reobserve\" when all sources are too ambiguous. "
                    "Prefer the source with the richest usable UI structure when deterministic "
                    "fusion has collapsed or the selected fusion is clearly too lossy. "
                    "Return strict JSON only."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "task": "fusion_referee",
                        "instruction": "Choose the safest fusion policy decision.",
                        "payload": payload,
                        "allowed_actions": ["accept", "prefer_source", "reobserve"],
                        "output_schema": {
                            "action": "accept|prefer_source|reobserve",
                            "preferred_source_id": "string",
                            "confidence": "number 0..1",
                            "reason": "string",
                            "should_reobserve": "boolean",
                        },
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            },
        ]

        try:
            response = auxiliary_client.call_llm(
                task=self.task,
                messages=messages,
                temperature=0.0,
                max_tokens=256,
                main_runtime=auxiliary_client.get_runtime_main_snapshot(),
                extra_body={"response_format": {"type": "json_object"}},
            )
            content = str(response.choices[0].message.content or "").strip()
            data = json.loads(content)
            return self._coerce_decision(data)
        except Exception as exc:
            logger.info("Fusion referee unavailable or invalid response; falling back to deterministic fusion: %s", exc)
            return FusionRefereeDecision(action="accept", reason=str(exc), confidence=0.0)

    @staticmethod
    def _coerce_decision(data: Any) -> FusionRefereeDecision:
        if not isinstance(data, dict):
            return FusionRefereeDecision(action="accept", reason="non-dict referee output", confidence=0.0)
        action = str(data.get("action") or "accept").strip().lower()
        if action not in {"accept", "prefer_source", "reobserve"}:
            action = "accept"
        preferred = str(data.get("preferred_source_id") or "").strip()
        confidence = data.get("confidence")
        try:
            confidence_f = float(confidence)
        except Exception:
            confidence_f = 0.0
        confidence_f = max(0.0, min(1.0, confidence_f))
        reason = str(data.get("reason") or "").strip()
        should_reobserve = bool(data.get("should_reobserve")) or action == "reobserve"
        if action != "prefer_source":
            preferred = ""
        if action == "accept":
            should_reobserve = False
        return FusionRefereeDecision(
            action=action,
            preferred_source_id=preferred,
            confidence=confidence_f,
            reason=reason,
            should_reobserve=should_reobserve,
        )


def summarize_ax_like_node(node: Any) -> Dict[str, Any]:
    """Compact node summary for referee prompts."""
    label = str(getattr(node, "name", "") or getattr(node, "description", "") or getattr(node, "value", "") or "")
    bbox = getattr(node, "bbox", (0.0, 0.0, 0.0, 0.0))
    try:
        bbox = [round(float(x), 2) for x in bbox]
    except Exception:
        bbox = [0.0, 0.0, 0.0, 0.0]
    return {
        "role": str(getattr(node, "role", "") or ""),
        "label": label[:120],
        "value": None if getattr(node, "value", None) is None else str(getattr(node, "value", ""))[:120],
        "enabled": bool(getattr(node, "enabled", True)),
        "bbox": bbox,
    }
