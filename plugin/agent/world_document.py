"""The world document: state the multimodal model owns and the runtime carries.

The runtime used to recompute the world from accessibility on every cycle,
which meant a belief the model asserted with full confidence was gone before
the next step could use it. Here the previous document is passed back into the
model as an identity path and the model returns the updated one, so integrating
new evidence is done by the thing that can actually see.

The runtime does not decide what is true. It bounds the document so it cannot
grow without limit, stamps provenance so a stale claim is visible as stale, and
otherwise carries it verbatim.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# Bounds exist to stop the document becoming the context-bloat problem in a new
# costume, not to censor the model's reading.
MAX_OBJECTS = 12
MAX_BELIEFS = 12
MAX_ATTEMPTS = 8
MAX_EXHAUSTED = 6
MAX_TEXT = 80
MAX_EVIDENCE_ITEMS = 3


def empty_document() -> Dict[str, Any]:
    """The document handed to the model on the first frame of a run."""
    return {
        "frame": 0,
        "surface": "",
        "open_conversation": "",
        "focused_field_role": "",
        "objects": [],
        # Layered scene (bottom -> top); empty until layered perception is on.
        # See plugin/agent/scene_layers.py.
        "layers": [],
        "beliefs": [],
        "progress": {"phase": "", "objective": "", "notes": ""},
        "attempts": [],
        "exhausted": [],
    }


def _text(value: Any, limit: int = MAX_TEXT) -> str:
    return str(value or "").strip()[:limit]


def _point(value: Any) -> Optional[List[int]]:
    try:
        x, y = value[0], value[1]
        return [int(x), int(y)]
    except (TypeError, ValueError, IndexError, KeyError):
        return None


def _confidence(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _normalize_objects(raw: Any, frame: int) -> List[Dict[str, Any]]:
    objects: List[Dict[str, Any]] = []
    if not isinstance(raw, (list, tuple)):
        return objects
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        text = _text(item.get("text"))
        if not text:
            continue
        entry: Dict[str, Any] = {
            "id": _text(item.get("id"), 24) or f"o{index + 1}",
            "kind": _text(item.get("kind"), 24) or "object",
            "text": text,
            "matches_goal": bool(item.get("matches_goal")),
            "seen_on_frame": _int(item.get("seen_on_frame"), frame),
        }
        point = _point(item.get("point") or item.get("target_point"))
        if point:
            entry["point"] = point
        objects.append(entry)
    return objects[:MAX_OBJECTS]


def _normalize_layers(raw: Any) -> List[Dict[str, Any]]:
    """Coerce a model-emitted ``layers`` list into a bounded, valid stack.

    Delegates to scene_layers so the schema has one definition; imported lazily
    to keep this module dependency-light.
    """
    if not isinstance(raw, (list, tuple)) or not raw:
        return []
    try:
        from plugin.agent.scene_layers import layers_to_dicts, normalize_layers

        return layers_to_dicts(normalize_layers(raw))
    except Exception:
        return []


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_beliefs(raw: Any, frame: int) -> List[Dict[str, Any]]:
    """Beliefs must carry their evidence and when they were last confirmed.

    That provenance is what lets the model retract its own stale claim on a
    later frame instead of the runtime having to police it.
    """
    beliefs: List[Dict[str, Any]] = []
    if not isinstance(raw, (list, tuple)):
        return beliefs
    for item in raw:
        if not isinstance(item, dict):
            continue
        predicate = _text(item.get("predicate"), 60)
        if not predicate:
            continue
        evidence = [
            _text(e, 120)
            for e in (item.get("evidence") or [])
            if _text(e, 120)
        ][:MAX_EVIDENCE_ITEMS]
        beliefs.append(
            {
                "predicate": predicate,
                "value": bool(item.get("value")),
                "confidence": _confidence(item.get("confidence")),
                "evidence": evidence,
                "confirmed_on_frame": _int(item.get("confirmed_on_frame"), frame),
            }
        )
    # Keep the most recently confirmed when the model overruns the bound.
    beliefs.sort(key=lambda b: b["confirmed_on_frame"], reverse=True)
    return beliefs[:MAX_BELIEFS]


def _normalize_attempts(raw: Any) -> List[Dict[str, Any]]:
    attempts: List[Dict[str, Any]] = []
    if not isinstance(raw, (list, tuple)):
        return attempts
    for item in raw:
        if isinstance(item, str):
            attempts.append({"action": _text(item, 120)})
            continue
        if not isinstance(item, dict):
            continue
        action = _text(item.get("action"), 40)
        if not action:
            continue
        attempts.append(
            {
                "frame": _int(item.get("frame")),
                "action": action,
                "target": _text(item.get("target"), 60),
                "result": _text(item.get("result"), 120),
            }
        )
    return attempts[-MAX_ATTEMPTS:]


def normalize_document(raw: Any, *, frame: int) -> Dict[str, Any]:
    """Coerce and bound whatever the model returned into a usable document."""
    if not isinstance(raw, dict):
        return empty_document()

    progress_raw = raw.get("progress")
    progress = progress_raw if isinstance(progress_raw, dict) else {}
    exhausted = [
        _text(item, 120) for item in (raw.get("exhausted") or []) if _text(item, 120)
    ]

    return {
        "frame": frame,
        "surface": _text(raw.get("surface"), 40),
        "open_conversation": _text(raw.get("open_conversation"), 80),
        "focused_field_role": _text(raw.get("focused_field_role"), 40),
        "objects": _normalize_objects(raw.get("objects"), frame),
        "layers": _normalize_layers(raw.get("layers")),
        "beliefs": _normalize_beliefs(raw.get("beliefs"), frame),
        "progress": {
            "phase": _text(progress.get("phase"), 40),
            "objective": _text(progress.get("objective"), 120),
            "notes": _text(progress.get("notes"), 200),
        },
        "attempts": _normalize_attempts(raw.get("attempts")),
        "exhausted": exhausted[:MAX_EXHAUSTED],
    }


def record_attempt(
    document: Dict[str, Any],
    *,
    frame: int,
    action: str,
    target: str = "",
    result: str = "",
) -> Dict[str, Any]:
    """Append what the runtime actually did, so the next call sees the outcome.

    The model proposes attempts, but only the runtime knows what was really
    executed and what came back, so that fact is written in rather than left
    for the model to assume.
    """
    if not isinstance(document, dict):
        document = empty_document()
    attempts = list(document.get("attempts") or [])
    attempts.append(
        {
            "frame": int(frame),
            "action": _text(action, 40),
            "target": _text(target, 60),
            "result": _text(result, 120),
        }
    )
    document["attempts"] = attempts[-MAX_ATTEMPTS:]
    return document


def stale_beliefs(document: Dict[str, Any], *, frame: int, older_than: int = 5) -> List[str]:
    """Predicates not reconfirmed recently, surfaced to the model as a prompt.

    This is information, not enforcement: the model decides whether to
    reconfirm or retract each one.
    """
    out: List[str] = []
    for belief in document.get("beliefs") or []:
        if not isinstance(belief, dict):
            continue
        age = frame - _int(belief.get("confirmed_on_frame"), frame)
        if age >= older_than:
            out.append(f"{belief.get('predicate')} (last confirmed {age} frames ago)")
    return out[:MAX_BELIEFS]


def document_summary(document: Dict[str, Any]) -> str:
    """One line for logs."""
    if not isinstance(document, dict):
        return "no world document"
    progress = document.get("progress") or {}
    return (
        f"surface={document.get('surface') or '?'} "
        f"conv={document.get('open_conversation') or '-'} "
        f"objects={len(document.get('objects') or [])} "
        f"beliefs={len(document.get('beliefs') or [])} "
        f"phase={progress.get('phase') or '-'}"
    )
