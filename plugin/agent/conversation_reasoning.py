"""Generic conversation relevance ranking backed by object discovery.

This module remains as a compatibility layer for the WhatsApp overlay and any
other callers that still want a message-row shaped result. The actual ranking
now lives in the generic object-discovery core.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any, Dict, List, Optional, Sequence

from plugin.agent.goal import Goal
from plugin.agent.object_discovery import DiscoveryContext, build_content_query, resolve_content_rows

_DEFAULT_RELEVANCE_THRESHOLD = 0.55


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


@dataclass
class ConversationMessageRelevance:
    summary: str = ""
    confidence: float = 0.0
    ranked_messages: List[Dict[str, Any]] = field(default_factory=list)
    likely_source_message_ids: List[int] = field(default_factory=list)
    likely_source_message_text: str = ""
    supporting_evidence: List[str] = field(default_factory=list)
    contradictions: List[str] = field(default_factory=list)
    needs_followup_observe: bool = False
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "summary": self.summary,
            "confidence": round(float(self.confidence or 0.0), 4),
            "ranked_messages": _json_safe(self.ranked_messages),
            "likely_source_message_ids": [int(x) for x in self.likely_source_message_ids],
            "likely_source_message_text": self.likely_source_message_text,
            "supporting_evidence": list(self.supporting_evidence),
            "contradictions": list(self.contradictions),
            "needs_followup_observe": bool(self.needs_followup_observe),
            "raw": _json_safe(self.raw),
        }


def should_run_conversation_relevance(goal: Goal, rows: Sequence[Dict[str, Any]]) -> bool:
    if not rows:
        return False
    kind = (goal.kind or "").strip().lower()
    if kind in {"whatsapp_forward_message", "whatsapp_read_message"}:
        return True
    if "message" in kind or "forward" in kind:
        return True
    return len(rows) >= 3


def _parse_resolution(goal: Goal, rows: Sequence[Dict[str, Any]], resolution: Any) -> ConversationMessageRelevance:
    ranked_rows: List[Dict[str, Any]] = []
    row_by_id = {int(row.get("entity_id") or 0): row for row in rows if int(row.get("entity_id") or 0)}
    for cand in getattr(resolution, "candidates", []) or []:
        obj = getattr(cand, "object", None)
        if obj is None:
            continue
        source_ids = list(getattr(obj, "source_entity_ids", None) or [])
        entity_id = source_ids[0] if source_ids else None
        if entity_id is None:
            try:
                entity_id = int(str(getattr(cand, "object_id", "")).split("_")[-1])
            except Exception:
                continue
        row = row_by_id.get(int(entity_id), {})
        ranked_rows.append(
            {
                "entity_id": int(entity_id),
                "score": max(0.0, min(1.0, float(getattr(cand, "score", 0.0) or 0.0))),
                "reason": " ".join(getattr(cand, "reasons", []) or []) or "object_discovery",
                "text": str(row.get("text") or getattr(obj, "text", "") or getattr(obj, "display_text", "") or ""),
                "label": str(row.get("label") or getattr(obj, "title", "") or ""),
                "description": str(row.get("description") or getattr(obj, "metadata", {}).get("description") or ""),
            }
        )

    status = str(getattr(resolution, "status", "") or "").strip().lower()
    selected_ids = [int(x) for x in (getattr(resolution, "selected_source_entity_ids", None) or []) if str(x).strip()]
    # High-precision: never fall back to "first visible row" when discovery
    # said not_found / binding blocked (live 214025 YouTube distractor).
    if status in {"not_found", "needs_more_context"} or bool(
        (getattr(resolution, "raw", {}) or {}).get("binding_blocked")
    ):
        selected_ids = []
    if not selected_ids and ranked_rows:
        top = [
            item
            for item in ranked_rows
            if float(item.get("score") or 0.0) >= _DEFAULT_RELEVANCE_THRESHOLD
            and "binding_ineligible" not in str(item.get("reason") or "").lower()
        ]
        selected_ids.extend([int(item["entity_id"]) for item in top[:3]])
    # Deliberately no unthresholded ranked_rows[0] fallback — that elevated
    # container+type-only distractors into source_object.

    likely_text = str(getattr(resolution, "selected_object_text", "") or "").strip()
    if not likely_text and selected_ids:
        row = row_by_id.get(selected_ids[0]) or {}
        likely_text = str(row.get("text") or row.get("label") or "").strip()

    raw = getattr(resolution, "raw", {}) or {}
    summary = str(raw.get("summary") or "").strip()
    evidence = list(getattr(resolution, "evidence", []) or [])
    contradictions = list(getattr(resolution, "contradictions", None) or [])
    if not contradictions and isinstance(raw, dict):
        contradictions = list(raw.get("contradictions") or [])
    if not summary and selected_ids:
        summary = f"Selected message entity_id={selected_ids[0]}"
    elif not summary and not selected_ids:
        summary = "No binding-eligible source message in visible window"

    return ConversationMessageRelevance(
        summary=summary,
        confidence=float(getattr(resolution, "confidence", 0.0) or 0.0) if selected_ids else 0.0,
        ranked_messages=ranked_rows,
        likely_source_message_ids=selected_ids[:5],
        likely_source_message_text=likely_text if selected_ids else "",
        supporting_evidence=[str(x) for x in evidence if str(x)],
        contradictions=[str(x) for x in contradictions if str(x)],
        needs_followup_observe=bool(getattr(resolution, "status", "") == "needs_more_context")
        or bool((getattr(resolution, "raw", {}) or {}).get("needs_followup_observe"))
        or (not selected_ids and bool(ranked_rows)),
        raw=_json_safe(getattr(resolution, "raw", {}) or {}),
    )


def rank_conversation_messages(
    goal: Goal,
    view: Dict[str, Any],
    rows: Sequence[Dict[str, Any]],
    *,
    world: Any = None,
    force: bool = False,
) -> Optional[ConversationMessageRelevance]:
    """Deterministic ranking of visible conversation rows.

    The compatibility wrapper converts rows into generic content objects and
    asks the core object-discovery engine to score them.

    The engine can escalate to a second model to arbitrate which row matches
    the goal, but that judgement belongs to unified cognition, which already
    reports ``matches_goal`` against the same rows. Consulting another model
    here produces a rival answer and, when the auxiliary route stalls, blocks
    the control loop for minutes behind a call whose result is discarded on
    failure anyway. The scores below stay as ranking evidence; relevance is
    decided upstream.
    """

    rows = [row for row in rows if isinstance(row, dict) and row.get("entity_id") is not None]
    if not rows:
        return None
    if not _conversation_surface_observed(view, rows):
        return None
    if not force and not should_run_conversation_relevance(goal, rows):
        return None

    window = max(1, min(500, int(view.get("conversation_context_window") or len(rows) or 1)))
    query = build_content_query(goal)
    context = DiscoveryContext(
        source_app=str(goal.app or view.get("app") or "WhatsApp"),
        container_id=str(view.get("open_conversation") or ""),
        container_type="conversation",
        window_name=str(view.get("window_name") or ""),
        conversation_window=window,
        visible_object_count=len(rows),
        use_llm=False,
        active_subgraph=dict(
            getattr(world, "last_active_subgraph", None) or view.get("active_cognitive_subgraph") or {}
        ),
    )
    resolution = resolve_content_rows(
        goal,
        rows,
        source_app=context.source_app,
        container_id=context.container_id,
        container_type=context.container_type,
        context=context,
        world=world,
        force_llm=False,
    )
    result = _parse_resolution(goal, rows, resolution)
    if world is not None:
        world.last_conversation_relevance = {
            "cache_key": getattr(world, "last_object_resolution", {}).get("cache_key")
            if isinstance(getattr(world, "last_object_resolution", None), dict)
            else "",
            "summary": result.to_dict(),
            "query": query.to_dict(),
        }
    return result


def _conversation_surface_observed(view: Dict[str, Any], rows: Sequence[Dict[str, Any]]) -> bool:
    screen = str(view.get("screen") or view.get("screen_kind") or view.get("wa_screen") or "").strip().upper()
    open_c = str(view.get("open_conversation") or "").strip()
    if not open_c:
        return False
    if screen not in {"LIST", "SEARCH", "SEARCH_RESULTS"}:
        return True
    # WhatsApp often leaves the sidebar in SEARCH_RESULTS while the main pane
    # is already the live conversation. In that state the row evidence is still
    # usable and should be ranked instead of discarded.
    return bool(rows) or bool(view.get("conversation_context_rows") or view.get("conversation_timeline") or view.get("conversation_messages"))
