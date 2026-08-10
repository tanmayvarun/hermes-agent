"""Goal × world branch fitness — exploration_controller / trajectory signal.

This is *not* information_search (MetaAction.SEARCH). Branch fitness asks whether
the current *region of the action space* still admits progress — evidence for
BACKTRACK / INFORMATION_GATHERING. SEARCH asks which candidate matches criteria.

Judgment evidence for meta/reflect: does the current world admit progress toward
the goal? Blocking chrome is typed (filter_chip, selection chrome, overlays),
never a closed vocabulary of chip label strings in core.

Host overlays may *observe* filter chips (tag ``kind=filter_chip``); recovery
rules must not say ``if Videos then Escape``.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence

_SELECTION_COUNT_RE = re.compile(r"(\d+)\s*selected", re.I)

# Evidence kinds a forward-message / content hunt typically needs.
_MESSAGE_LINK_KINDS = frozenset(
    {
        "message",
        "message_bubble",
        "link",
        "content",
        "chat_row",
        "search_result_row",
        "conversation",
    }
)
_MEDIA_ONLY_KINDS = frozenset(
    {"media", "video", "image", "photo", "attachment", "sticker", "gif"}
)


def _norm(text: Any) -> str:
    return str(text or "").strip().lower()


def _objects(document: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not isinstance(document, dict):
        return []
    return [o for o in (document.get("objects") or []) if isinstance(o, dict)]


def needed_evidence_kinds_for_goal(goal: Any = None, *, goal_kind: str = "") -> List[str]:
    """Coarse evidence kinds the goal needs — not app-specific label strings."""
    if goal is not None and hasattr(goal, "needed_evidence_kinds"):
        try:
            kinds = goal.needed_evidence_kinds()
            if kinds:
                return [str(k) for k in kinds]
        except Exception:
            pass
    kind = _norm(goal_kind or getattr(goal, "kind", "") or "")
    link = str(getattr(goal, "link_query", "") or "").strip() if goal is not None else ""
    if kind in {"whatsapp_forward_message", "whatsapp_read_message"} or link:
        return [
            "message",
            "message_bubble",
            "link",
            "content",
            "chat_row",
            "search_result_row",
        ]
    if kind in {"whatsapp_voice_call", "whatsapp_video_call"}:
        return ["chat_row", "search_result_row", "conversation", "button"]
    return ["chat_row", "search_result_row", "conversation", "message", "message_bubble"]


def selection_count_from_document(document: Optional[Dict[str, Any]]) -> Optional[int]:
    for obj in _objects(document):
        blob = str(obj.get("text") or obj.get("label") or "")
        m = _SELECTION_COUNT_RE.search(blob)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                continue
    return None


def selection_chrome_present(document: Optional[Dict[str, Any]]) -> bool:
    if selection_count_from_document(document) is not None:
        return True
    blob = " ".join(
        str(o.get("text") or o.get("label") or "") for o in _objects(document)
    ).lower()
    return "selected" in blob


def blocking_chrome_from_document(document: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Typed blockers only — filter_chip / selection / transient surfaces."""
    doc = document if isinstance(document, dict) else {}
    blockers: List[Dict[str, Any]] = []
    surface = _norm(doc.get("surface"))

    for obj in _objects(doc):
        kind = _norm(obj.get("kind"))
        if kind == "filter_chip" or (
            kind == "chip" and _norm(obj.get("restricts")) in {"media", "filter"}
        ):
            blockers.append(
                {
                    "type": "filter_chip",
                    "text": str(obj.get("text") or obj.get("label") or "")[:80],
                    "restricts": str(obj.get("restricts") or "")[:40],
                    "clearable": "escape",
                }
            )

    if selection_chrome_present(doc):
        blockers.append(
            {
                "type": "selection_chrome",
                "selection_count": selection_count_from_document(doc),
                "clearable": "escape",
            }
        )

    if surface in {"context_menu", "action_menu", "dialog"}:
        blockers.append({"type": "transient_overlay", "surface": surface, "clearable": "escape"})
    if surface == "selection_mode":
        blockers.append(
            {"type": "selection_chrome", "surface": surface, "clearable": "escape"}
        )
    if surface in {"forward_picker", "destination_picker"}:
        blockers.append({"type": "picker", "surface": surface, "clearable": "escape"})

    return blockers


def _has_needed_evidence(
    document: Optional[Dict[str, Any]],
    needed_kinds: Sequence[str],
) -> bool:
    needed = {_norm(k) for k in needed_kinds if _norm(k)}
    if not needed:
        return True
    for obj in _objects(document):
        kind = _norm(obj.get("kind"))
        text = _norm(obj.get("text") or obj.get("label"))
        if obj.get("matches_goal"):
            return True
        if kind in needed:
            return True
        if "http" in text and ({"link", "message", "message_bubble", "content"} & needed):
            return True
    return False


def _evidence_is_media_only(document: Optional[Dict[str, Any]]) -> bool:
    objs = _objects(document)
    if not objs:
        return False
    kinds = {_norm(o.get("kind")) for o in objs}
    # Ignore chrome kinds when judging content grid.
    contentish = {
        k
        for k in kinds
        if k
        not in {
            "chip",
            "filter_chip",
            "button",
            "status_text",
            "header",
            "tab",
            "segment",
        }
    }
    if not contentish:
        return False
    return bool(contentish) and contentish <= _MEDIA_ONLY_KINDS


def compute_branch_fitness(
    document: Optional[Dict[str, Any]] = None,
    *,
    needed_kinds: Optional[Sequence[str]] = None,
    goal: Any = None,
    goal_referents: Optional[Sequence[str]] = None,
    selection_consistency: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Whether the current branch admits progress toward the goal.

    ``admissible=False`` is evidence for backtrack/revert — not a force rule.
    """
    doc = document if isinstance(document, dict) else {}
    kinds = list(needed_kinds or needed_evidence_kinds_for_goal(goal))
    blockers = blocking_chrome_from_document(doc)
    has_evidence = _has_needed_evidence(doc, kinds)
    needs_message_link = bool(set(kinds) & _MESSAGE_LINK_KINDS)

    reasons: List[str] = []
    admissible = True

    sel = selection_consistency if isinstance(selection_consistency, dict) else None
    if sel is not None and sel.get("consistent") is False:
        admissible = False
        reasons.append("selection_inconsistent_with_goal")

    filter_blockers = [b for b in blockers if b.get("type") == "filter_chip"]
    if filter_blockers and needs_message_link and not has_evidence:
        admissible = False
        reasons.append("filter_chip_blocks_needed_evidence")
    elif filter_blockers and needs_message_link and _evidence_is_media_only(doc):
        admissible = False
        reasons.append("filter_chip_with_media_only_results")

    # Barren search surface: no needed evidence and escape-clearable chrome.
    surface = _norm(doc.get("surface"))
    if (
        admissible
        and surface in {"search", ""}
        and needs_message_link
        and not has_evidence
        and any(b.get("clearable") == "escape" for b in blockers)
    ):
        admissible = False
        reasons.append("barren_search_with_clearable_chrome")

    # Generic empty find: a query was committed and the world shows no results /
    # no needed evidence — branch is unfit until retreat (no host ontology).
    search_empty = bool(doc.get("search_empty"))
    typed_query = bool(
        _norm(doc.get("search_query"))
        or _norm(doc.get("typed_query"))
        or (isinstance(doc.get("extras"), dict) and _norm(doc["extras"].get("search_query")))
    )
    if (
        admissible
        and needs_message_link
        and not has_evidence
        and search_empty
        and (typed_query or surface in {"search", "search_results", "chat_list", "calls"})
    ):
        admissible = False
        reasons.append("empty_find_no_goal_evidence")

    return {
        "admissible": admissible,
        "progress_admissible": admissible,
        "needed_kinds": kinds,
        "has_needed_evidence": has_evidence,
        "blockers": blockers,
        "reasons": reasons,
        "goal_referents": [str(t) for t in (goal_referents or []) if str(t).strip()][:6],
        "verdict": (
            "branch admits progress"
            if admissible
            else (
                "branch unfit: "
                + ("; ".join(reasons) if reasons else "no progress evidence")
            )
        ),
        # Compat shape for callers that still read last_branch_consistency.
        "consistent": admissible,
        "applicable": True,
        "needs_backtrack": not admissible,
    }
