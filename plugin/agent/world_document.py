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
        bounds = item.get("bounds")
        if isinstance(bounds, (list, tuple)) and len(bounds) >= 4:
            try:
                entry["bounds"] = [float(x) for x in bounds[:4]]
            except (TypeError, ValueError):
                pass
        space = str(item.get("coordinate_space") or "").strip().lower()
        if space in {"image", "screen"}:
            entry["coordinate_space"] = space
        elif entry.get("bounds") and not space:
            # Measured bounds (OCR/AX) are pointer/screen space by contract.
            entry["coordinate_space"] = "screen"
        elif entry.get("point") and not space:
            # Producer contracts: OCR/AX → screen; VLM → image. Unknown stays
            # untagged and is not executable downstream.
            geo_src = str(item.get("geometry_source") or item.get("source") or "").strip().lower()
            if geo_src.startswith("ax") or geo_src.startswith("ocr") or geo_src in {
                "accessibility",
                "screen",
            }:
                entry["coordinate_space"] = "screen"
            elif geo_src in {"vision", "vlm", "model", "image"}:
                entry["coordinate_space"] = "image"
        owner = _text(item.get("owner_surface") or item.get("surface"), 40)
        if owner:
            entry["owner_surface"] = owner
        if item.get("selected") is not None:
            entry["selected"] = bool(item.get("selected"))
        if item.get("enabled") is not None:
            entry["enabled"] = bool(item.get("enabled"))
        role = _text(item.get("semantic_role") or item.get("role"), 40)
        if role:
            entry["semantic_role"] = role
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


# Selection / destination claims must name their owning surface. Background
# conversation selection must never satisfy a destination-picker predicate.
_DESTINATION_SELECTION_PREDICATES = frozenset(
    {
        "destination_selected",
        "destination_selected_count",
        "recipient_selected",
        "recipient_selected_count",
        "destination_contact_selected",
    }
)
_SOURCE_SELECTION_PREDICATES = frozenset(
    {
        "source_object_selected",
        "source_message_selected",
        "source_message_selected_count",
        "source_selected_count",
    }
)
_DESTINATION_OWNER_SURFACES = frozenset(
    {
        "forward_picker",
        "destination",
        "destination_picker",
        "dialog",
    }
)
_SOURCE_OWNER_SURFACES = frozenset(
    {
        "conversation",
        "selection_mode",
        "container",
        "conversation_selection_bar",
        "chat_list",
    }
)


def _normalize_beliefs(raw: Any, frame: int) -> List[Dict[str, Any]]:
    """Beliefs must carry their evidence and when they were last confirmed.

    That provenance is what lets the model retract its own stale claim on a
    later frame instead of the runtime having to police it. Selection claims
    also carry ``owner_surface`` / ``semantic_role`` so cross-surface
    attribution can be scrubbed (architect: surface ownership).
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
        raw_val = item.get("value")
        if isinstance(raw_val, bool):
            coerced: Any = raw_val
        elif isinstance(raw_val, (int, float)) and not isinstance(raw_val, bool):
            coerced = int(raw_val)
        else:
            coerced = bool(raw_val)
        entry: Dict[str, Any] = {
            "predicate": predicate,
            "value": coerced,
            "confidence": _confidence(item.get("confidence")),
            "evidence": evidence,
            "confirmed_on_frame": _int(item.get("confirmed_on_frame"), frame),
        }
        owner = _text(item.get("owner_surface"), 40)
        if owner:
            entry["owner_surface"] = owner
        role = _text(item.get("semantic_role"), 40)
        if role:
            entry["semantic_role"] = role
        rejected = [
            e
            for e in (item.get("rejected_evidence") or [])
            if isinstance(e, dict) or _text(e, 120)
        ][:MAX_EVIDENCE_ITEMS]
        if rejected:
            entry["rejected_evidence"] = [
                (
                    {
                        "text": _text(e.get("text"), 80),
                        "reason": _text(e.get("reason"), 120),
                        "owner_surface": _text(e.get("owner_surface"), 40),
                    }
                    if isinstance(e, dict)
                    else _text(e, 120)
                )
                for e in rejected
            ]
        beliefs.append(entry)
    # Keep the most recently confirmed when the model overruns the bound.
    beliefs.sort(key=lambda b: b["confirmed_on_frame"], reverse=True)
    return beliefs[:MAX_BELIEFS]


def _inventory_destination_selected(objects: List[Dict[str, Any]]) -> bool:
    """True when a destination-owned inventory row is marked selected."""
    for obj in objects:
        if not isinstance(obj, dict):
            continue
        if not (bool(obj.get("selected")) or bool(obj.get("matches_goal"))):
            continue
        owner = str(obj.get("owner_surface") or "").strip().lower()
        role = str(obj.get("semantic_role") or obj.get("kind") or "").strip().lower()
        if owner in _DESTINATION_OWNER_SURFACES:
            return True
        if role in {
            "recipient",
            "contact_row",
            "destination",
            "destination_row",
            "checkbox",
        }:
            return True
        # On a flat forward_picker inventory, selected contact-like rows count
        # when they are not commit/status chrome.
        text = str(obj.get("text") or "").strip().lower()
        kind = str(obj.get("kind") or "").strip().lower()
        if kind in {"status", "chrome", "toolbar_status"}:
            continue
        if text in {
            "forward",
            "send",
            "share",
            "cancel",
            "search",
            "my status",
        }:
            continue
        if owner in {"", "forward_picker", "destination_picker"} and bool(
            obj.get("selected")
        ):
            return True
    return False


def scrub_cross_surface_selection_beliefs(
    document: Dict[str, Any],
) -> Dict[str, Any]:
    """Retract destination-selection claims owned by the wrong surface.

    Structural invariant (not string-specific): a destination_selected belief
    may only stand when its ``owner_surface`` is a destination surface *and*
    inventory corroborates a selected recipient (or the claim is explicitly
    false). Background source-selection ownership can never satisfy destination
    predicates.
    """
    if not isinstance(document, dict):
        return document
    beliefs = list(document.get("beliefs") or [])
    if not beliefs:
        return document
    objects = [
        o for o in (document.get("objects") or []) if isinstance(o, dict)
    ]
    inventory_dest = _inventory_destination_selected(objects)
    active = str(document.get("surface") or "").strip().lower()
    scrubbed: List[Dict[str, Any]] = []
    changed = False
    for belief in beliefs:
        if not isinstance(belief, dict):
            continue
        pred = str(belief.get("predicate") or "").strip().lower()
        owner = str(belief.get("owner_surface") or "").strip().lower()
        role = str(belief.get("semantic_role") or "").strip().lower()
        b = dict(belief)
        if pred in _DESTINATION_SELECTION_PREDICATES or pred.endswith(
            "destination_selected"
        ):
            owned_by_source = owner in _SOURCE_OWNER_SURFACES or role in {
                "source_message_selection",
                "source_selection",
            }
            owned_by_dest = owner in _DESTINATION_OWNER_SURFACES or role in {
                "destination_selection",
                "recipient_selection",
            }
            if bool(b.get("value")) and (
                owned_by_source
                or (not owned_by_dest and not inventory_dest)
                or (owned_by_dest and not inventory_dest and active in _DESTINATION_OWNER_SURFACES)
            ):
                b["value"] = False
                b["confidence"] = min(float(b.get("confidence") or 0.0), 0.25)
                rejected = list(b.get("rejected_evidence") or [])
                rejected.append(
                    {
                        "text": "cross_surface_or_uncorroborated_destination_selection",
                        "reason": (
                            "destination selection claims require destination-surface "
                            "ownership plus inventory-selected recipient; "
                            "source-surface selection state is a separate namespace"
                        ),
                        "owner_surface": owner or "unspecified",
                    }
                )
                b["rejected_evidence"] = rejected[:MAX_EVIDENCE_ITEMS]
                if not owner and active in _DESTINATION_OWNER_SURFACES:
                    b["owner_surface"] = active
                changed = True
        elif pred in _SOURCE_SELECTION_PREDICATES:
            if not owner and active in _SOURCE_OWNER_SURFACES | {"conversation"}:
                b["owner_surface"] = (
                    "selection_mode" if active == "selection_mode" else "conversation"
                )
                changed = True
        scrubbed.append(b)
    if changed:
        document = dict(document)
        document["beliefs"] = scrubbed
    return document


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

    out = {
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
    # Runtime-stamped multi-display topology — carry through normalize; never
    # invent from the model (it may omit or hallucinate display indices).
    ts = raw.get("task_surface")
    if isinstance(ts, dict) and ts:
        out["task_surface"] = ts
    return scrub_cross_surface_selection_beliefs(out)


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
