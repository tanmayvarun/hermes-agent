"""Actor: execute a complete motor brief — never re-choose the target.

Human analogue:

    perceptor (eyes) → brain (decide) → actor (hands)

Hard rule — no inventing UI grounding
-------------------------------------
The actor has no license to synthesise geometry, field identity, or host
shortcuts (Cmd+F, global AX "Search" hunt, first-matching kind). Missing
GroundedUiTarget details mean ``incomplete_brief`` — never a guessed rectangle.
Perception (and the brain packing that perception) is the only source of UI
truth; the actor is hands only.

The brain must hand the actor a closed brief: gesture + geometry and/or typed
text + field role. The actor lands that brief and reports motor outcome.

Transactional commit (perception confirm → act)
-----------------------------------------------
Perception is tens of seconds old by the time a brief lands. For every
geometry-bound gesture the actor owns a single transaction:

  1. finalise the rectangle from the brief (point → bounds if needed)
  2. call the cheap **perception confirm** API (not a full stage1 re-perceive)
  3. only then invoke the motor

Confirm asks whether the named rectangle is still valid. If the world moved
(user interrupt, call overlay, notification, list scroll), confirm returns
invalid and the actor refuses with ``status=stale_precondition`` /
``perception_invalid`` — no write. The executive forces a re-look; the brain
re-perceives and may re-decide. Because nothing reached the app, that recovery
cycle is idempotent.

The actor never re-perceives or invents a new target itself.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Sequence, Tuple, runtime_checkable

logger = logging.getLogger(__name__)

# Surfaced on ActorResult.status and mapped to ExecResult.backend so the
# controller's stale-precondition re-look path still fires through actor.
STALE_PRECONDITION = "stale_precondition"

# Gestures that commit against a read rectangle — must pass the freshness gate.
_COMMIT_GESTURES = frozenset({"click", "ax_press", "context_click", "hover", "type"})

# Boxes synthesised around a point (not measured AX). Same sizes as ax_action.
_SYNTHETIC_BOX_SIZES = (24.0, 48.0)

FIELD_ROLES = frozenset(
    {
        "none",
        "sidebar_search",
        "destination_filter",
        "in_chat_find",
        "composer",
        "dialog_field",
    }
)

GESTURES = frozenset(
    {
        "click",
        "context_click",
        "hover",
        "type",
        "press_escape",
        "scroll",
        "ax_press",
    }
)

# Capabilities the brain names → motor gesture the actor runs.
CAPABILITY_GESTURE: Dict[str, str] = {
    "open_entity": "click",
    # resolve_entity is judgment (rank → SearchResult.chosen), not a click.
    # Motor open is open_entity under meta ACT after the episode completes.
    "select_content": "click",
    "reveal_actions": "context_click",
    "invoke_affordance": "click",
    "commit_irreversible": "click",
    "type_query": "type",
    "compose_search_query": "type",
    "locate_content": "type",
    "dismiss_transient": "press_escape",
    "dismiss": "press_escape",
    "scroll": "scroll",
    "scroll_content": "scroll",
}

# Surfaces that must never open the global/sidebar search motor.
_NO_SIDEBAR_SURFACES = frozenset(
    {"forward_picker", "context_menu", "selection_mode", "dialog"}
)

_FILTER_KINDS = frozenset(
    {"text_field", "search_field", "search_input", "search_bar", "field"}
)
_CONTENT_KINDS = frozenset(
    {
        "message",
        "message_bubble",
        "message_link_preview",
        "link",
        "attachment",
        "media",
        "image",
        "video",
        "audio",
        "document",
    }
)
_CONTACT_KINDS = frozenset({"contact_row", "contact", "entity", "chat_row", "row"})


@dataclass
class ActorBrief:
    """Closed instruction for the actor. Incomplete briefs are refused."""

    gesture: str
    app: str = ""
    point: Optional[Tuple[float, float]] = None
    bounds: Optional[Tuple[float, float, float, float]] = None
    label: str = ""
    text: str = ""
    field_role: str = "none"
    open_search_ui: bool = False
    capability: str = ""
    target_id: str = ""
    # Perceived object kind at the bound site (action-area gate).
    target_kind: str = ""
    scroll_direction: str = "down"
    scroll_amount: int = 3
    # When set (from stamped task_surface), execute_actor refuses clicks outside.
    task_window_bounds: Optional[Tuple[float, float, float, float]] = None
    # Pre-click geometry audit (source frame → window → global desktop).
    geometry_audit: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if self.point is not None:
            d["point"] = [self.point[0], self.point[1]]
        if self.bounds is not None:
            d["bounds"] = list(self.bounds)
        if self.task_window_bounds is not None:
            d["task_window_bounds"] = list(self.task_window_bounds)
        if self.geometry_audit:
            d["geometry_audit"] = dict(self.geometry_audit)
        return d


@dataclass
class ActorResult:
    ok: bool
    status: str  # executed | incomplete_brief | motor_fail | unsupported_gesture
    message: str = ""
    brief: Optional[Dict[str, Any]] = None
    evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "message": self.message,
            "brief": self.brief,
            "evidence": dict(self.evidence),
        }


@runtime_checkable
class ActorMotor(Protocol):
    """Host motor. Implementations must not choose a different target."""

    def click(
        self, app: str, *, label: str, bounds: Optional[Tuple[float, float, float, float]]
    ) -> Tuple[bool, str]: ...

    def context_click(
        self, app: str, *, label: str, bounds: Optional[Tuple[float, float, float, float]]
    ) -> Tuple[bool, str]: ...

    def hover(
        self, app: str, *, label: str, bounds: Optional[Tuple[float, float, float, float]]
    ) -> Tuple[bool, str]: ...

    def type_text(
        self,
        app: str,
        text: str,
        *,
        bounds: Optional[Tuple[float, float, float, float]],
        open_search_ui: bool,
        into: str,
    ) -> Tuple[bool, str]: ...

    def press_escape(self, app: str) -> Tuple[bool, str]: ...

    def scroll(
        self, app: str, direction: str, amount: int
    ) -> Tuple[bool, str]: ...


@dataclass
class RecordingMotor:
    """Eval / unit-test motor: records calls, never touches the host."""

    calls: List[Dict[str, Any]] = field(default_factory=list)
    succeed: bool = True

    def click(self, app, *, label, bounds):
        self.calls.append({"op": "click", "app": app, "label": label, "bounds": bounds})
        return self.succeed, f"record click {label!r}"

    def context_click(self, app, *, label, bounds):
        self.calls.append(
            {"op": "context_click", "app": app, "label": label, "bounds": bounds}
        )
        return self.succeed, f"record context_click {label!r}"

    def hover(self, app, *, label, bounds):
        self.calls.append({"op": "hover", "app": app, "label": label, "bounds": bounds})
        return self.succeed, f"record hover {label!r}"

    def type_text(self, app, text, *, bounds, open_search_ui, into):
        self.calls.append(
            {
                "op": "type",
                "app": app,
                "text": text,
                "bounds": bounds,
                "open_search_ui": open_search_ui,
                "into": into,
            }
        )
        return self.succeed, f"record type {text!r} open_search_ui={open_search_ui}"

    def press_escape(self, app):
        self.calls.append({"op": "press_escape", "app": app})
        return self.succeed, "record escape"

    def scroll(self, app, direction, amount):
        self.calls.append(
            {"op": "scroll", "app": app, "direction": direction, "amount": amount}
        )
        return self.succeed, f"record scroll {direction}"


@dataclass
class MacActorMotor:
    """Thin adapter over ax_* — geometry first, no target re-choice."""

    def click(self, app, *, label, bounds):
        from plugin.executor.ax_action import ax_click

        r = ax_click(app, label or "target", bounds=bounds)
        return bool(r.ok), str(r.message or "")

    def context_click(self, app, *, label, bounds):
        from plugin.executor.ax_action import ax_context_click

        r = ax_context_click(app, label or "target", bounds=bounds)
        return bool(r.ok), str(r.message or "")

    def hover(self, app, *, label, bounds):
        from plugin.executor.ax_action import ax_hover

        r = ax_hover(app, label or "target", bounds=bounds)
        return bool(r.ok), str(r.message or "")

    def type_text(self, app, text, *, bounds, open_search_ui, into):
        from plugin.executor.ax_action import ax_type

        # Never invent a field name or Cmd+F path. Bounds come from the brief.
        if open_search_ui:
            logger.warning(
                "actor refused open_search_ui invent path; typing uses grounded bounds only"
            )
        r = ax_type(
            app,
            text,
            into=into or "",
            submit=False,
            search_bounds=bounds,
            open_search_ui=False,
        )
        return bool(r.ok), str(r.message or "")

    def press_escape(self, app):
        from plugin.executor.ax_action import ax_press_escape

        r = ax_press_escape(app)
        return bool(r.ok), str(r.message or "")

    def scroll(self, app, direction, amount):
        from plugin.executor.ghost import get_executor

        r = get_executor(dry_run=False, app=app).scroll(direction, amount=amount)
        return bool(getattr(r, "ok", False)), str(getattr(r, "message", "") or "")


def _point_bounds(
    point: Optional[Sequence[Any]], *, size: float = 24.0
) -> Optional[Tuple[float, float, float, float]]:
    if not point or len(point) < 2:
        return None
    try:
        x, y = float(point[0]), float(point[1])
    except (TypeError, ValueError):
        return None
    half = size / 2.0
    return (x - half, y - half, size, size)


def _as_point(raw: Any) -> Optional[Tuple[float, float]]:
    if not isinstance(raw, (list, tuple)) or len(raw) < 2:
        return None
    try:
        return (float(raw[0]), float(raw[1]))
    except (TypeError, ValueError):
        return None


def _as_bounds(raw: Any) -> Optional[Tuple[float, float, float, float]]:
    if not isinstance(raw, (list, tuple)) or len(raw) < 4:
        return None
    try:
        return (float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3]))
    except (TypeError, ValueError):
        return None


# Same pad as open_entity.resolve_addressable — AX label fragment vs row click.
_POINT_BOUNDS_AGREE_PAD = 96.0


def _bounds_center(
    bounds: Optional[Tuple[float, float, float, float]],
) -> Optional[Tuple[float, float]]:
    if bounds is None or len(bounds) < 4:
        return None
    try:
        return (
            float(bounds[0]) + float(bounds[2]) / 2.0,
            float(bounds[1]) + float(bounds[3]) / 2.0,
        )
    except (TypeError, ValueError):
        return None


def _point_in_rect(
    point: Sequence[Any],
    bounds: Sequence[Any],
    *,
    pad: float = 0.0,
) -> bool:
    if point is None or bounds is None or len(point) < 2 or len(bounds) < 4:
        return False
    try:
        x, y = float(point[0]), float(point[1])
        bx, by, bw, bh = (
            float(bounds[0]),
            float(bounds[1]),
            float(bounds[2]),
            float(bounds[3]),
        )
    except (TypeError, ValueError):
        return False
    return (bx - pad) <= x <= (bx + bw + pad) and (by - pad) <= y <= (by + bh + pad)


def _points_agree(
    a: Optional[Tuple[float, float]],
    b: Optional[Tuple[float, float]],
    *,
    pad: float = _POINT_BOUNDS_AGREE_PAD,
) -> bool:
    if a is None or b is None:
        return False
    try:
        return abs(float(a[0]) - float(b[0])) <= pad and abs(float(a[1]) - float(b[1])) <= pad
    except (TypeError, ValueError):
        return False


# Open/resolve CTAs: the brain's target_point is the intentional click. Inventory
# row points can land on the Calls rail (012852: obj [130,140] vs CTA [270,143]).
_CTA_POINT_WINS = frozenset(
    {"open_entity", "open_contact", "resolve_entity"}
)
# Content selection: inventory point beats a conflicting CTA (sidebar preview echo).
_INVENTORY_POINT_WINS = frozenset({"reveal_actions", "select_content", "invoke_affordance"})
# Search/type: inventory Search field beats a contact-row CTA point (live 095344).
_FILTER_POINT_WINS = frozenset(
    {"compose_search_query", "type_query", "locate_content", "open_search"}
)


def _task_surface_from_doc(doc: Dict[str, Any], app: str = "") -> Any:
    """Read stamped topology only — never live-probe during brief construction.

    Live ``build_task_surface`` belongs in execute_actor / packet stamp. Probing
    here would rewrite offline fixture geometry against whatever display the
    host currently has.
    """
    raw = doc.get("task_surface") if isinstance(doc, dict) else None
    if not isinstance(raw, dict) or not raw.get("window_bounds"):
        return None
    try:
        from plugin.perception.display_topology import TaskSurface

        wb = raw.get("window_bounds")
        origin = raw.get("capture_origin") or [0.0, 0.0]
        return TaskSurface(
            app=str(raw.get("app") or app or ""),
            window_bounds=tuple(float(v) for v in wb[:4]),
            window_id=raw.get("window_id"),
            display_index=raw.get("display_index"),
            display_count=int(raw.get("display_count") or 0),
            capture_origin=(float(origin[0]), float(origin[1])),
            capture_scale=float(raw.get("capture_scale") or 1.0),
            point_scale=float(raw.get("point_scale") or 1.0),
        )
    except Exception:
        return None


def _normalize_to_screen(
    point: Optional[Tuple[float, float]],
    bounds: Optional[Tuple[float, float, float, float]],
    *,
    coordinate_space: str,
    surface: Any,
    frame_id: str = "",
    graph: Any = None,
    grounding_capture_id: str = "",
    allow_legacy_geometry: bool = False,
) -> Tuple[
    Optional[Tuple[float, float]],
    Optional[Tuple[float, float, float, float]],
    Dict[str, Any],
]:
    """Map image-space geometry onto global desktop points via FrameGraph.

    Authoritative path: Grounding + FrameGraph.transform only.
    Tagged ``coordinate_space=screen`` passes through unchanged.
    Missing/stale frames fail closed (``grounding_uncertain`` audit) — never
    ``looks_like_image_point`` / legacy heuristic conversion on act path.

    Production default: naked ``[x,y]`` with no space/frame → uncertain.
    Legacy goldens/corpus may pass ``allow_legacy_geometry=True`` (or stamp
    ``legacy_geometry_provenance`` at the ingestion boundary) to opt into
    historical screen-absolute / identity-image adapters.
    """
    from plugin.perception.coordinate_frame import (
        FrameGraph,
        GroundingUncertain,
        StaleCoordinateFrame,
        UnknownCoordinateFrame,
        build_frame_graph,
        ensure_screen_space,
        frame_graph_from_task_surface,
    )

    audit: Dict[str, Any] = {}
    active_graph = graph
    if isinstance(active_graph, dict):
        active_graph = FrameGraph.from_dict(active_graph)
    if active_graph is None and surface is not None:
        raw = None
        if isinstance(surface, dict):
            raw = surface.get("frame_graph")
        else:
            raw = getattr(surface, "frame_graph", None)
        if isinstance(raw, FrameGraph):
            active_graph = raw
        elif isinstance(raw, dict):
            active_graph = FrameGraph.from_dict(raw)

    # ONE ingestion adapter: TaskSurface / identity capture → FrameGraph, then
    # ONLY transform(). Never looks_like_image_point / to_screen_point.
    adapter_used = False
    if active_graph is None and surface is not None:
        try:
            active_graph = frame_graph_from_task_surface(surface)
            adapter_used = True
        except Exception:
            active_graph = None

    space = str(coordinate_space or "").strip().lower()
    # TaskSurface adapter convention: untagged points are image-space.
    if adapter_used and not space and not frame_id:
        space = "image"
    # Explicit legacy marker only — never infer screen from absence of info.
    elif (
        allow_legacy_geometry
        and active_graph is None
        and not space
        and not frame_id
        and (point is not None or bounds is not None)
    ):
        space = "screen"
        audit["legacy_screen_assumption"] = True
        audit["legacy_geometry_provenance"] = "legacy_inventory_v1"
    # Identity image→screen only when legacy mode is explicitly enabled.
    elif (
        allow_legacy_geometry
        and active_graph is None
        and space == "image"
        and not frame_id
    ):
        active_graph = build_frame_graph(
            image_size=(0.0, 0.0),
            window_origin_in_screen=(0.0, 0.0),
            image_origin_in_window=(0.0, 0.0),
            point_scale=1.0,
            capture_scale=1.0,
            capture_id="legacy_identity",
        )
        adapter_used = True
        audit["legacy_identity_adapter"] = True

    # Naked geometry with no topology in production → fail closed.
    if (
        active_graph is None
        and not space
        and not frame_id
        and (point is not None or bounds is not None)
    ):
        return None, None, {
            "grounding_uncertain": True,
            "attempt_validity": "inconclusive_grounding",
            "error": "naked geometry without frame/space — re-ground",
            "error_code": "grounding_uncertain",
            "source_frame_id": frame_id or "",
            "source_space": space,
            "legacy_heuristic_refused": True,
        }

    # Window/image with unresolved frame_id and no graph → fail closed.
    if active_graph is None and space not in {"", "screen"}:
        return None, None, {
            "grounding_uncertain": True,
            "attempt_validity": "inconclusive_grounding",
            "error": "no FrameGraph for non-screen geometry",
            "error_code": "grounding_uncertain",
            "source_frame_id": frame_id or "",
            "source_space": space,
            "legacy_heuristic_refused": True,
        }
    if active_graph is None and space not in {"screen"}:
        return None, None, {
            "grounding_uncertain": True,
            "attempt_validity": "inconclusive_grounding",
            "error": "no FrameGraph and no TaskSurface topology to adapt",
            "error_code": "grounding_uncertain",
            "source_frame_id": frame_id or "",
            "source_space": space,
            "legacy_heuristic_refused": True,
        }

    try:
        pt, bd, norm_audit = ensure_screen_space(
            point,
            bounds,
            coordinate_space=space,
            frame_id=frame_id,
            graph=active_graph,
            surface=None,
            fail_closed=True,
            grounding_capture_id=grounding_capture_id,
        )
        merged = dict(audit)
        merged.update(dict(norm_audit or {}))
        if adapter_used:
            merged["task_surface_frame_adapter"] = True
        return pt, bd, merged
    except (UnknownCoordinateFrame, StaleCoordinateFrame, GroundingUncertain) as exc:
        return None, None, {
            "grounding_uncertain": True,
            "attempt_validity": "inconclusive_grounding",
            "error": str(exc),
            "error_code": getattr(exc, "code", "grounding_uncertain"),
            "source_frame_id": frame_id or "",
            "source_space": coordinate_space or "",
            "legacy_heuristic_refused": True,
        }
    except Exception as exc:
        return None, None, {
            "grounding_uncertain": True,
            "attempt_validity": "inconclusive_grounding",
            "error": str(exc),
            "legacy_heuristic_refused": True,
        }


def _reconcile_click_geometry(
    *,
    brain_point: Optional[Tuple[float, float]],
    obj_point: Optional[Tuple[float, float]],
    obj_bounds: Optional[Tuple[float, float, float, float]],
    gesture: str,
    capability: str = "",
    brain_space: str = "",
    obj_space: str = "",
    task_surface: Any = None,
) -> Tuple[Optional[Tuple[float, float]], Optional[Tuple[float, float, float, float]]]:
    """Click geometry ownership for the actor brief.

    - open_entity / open_contact: explicit CTA point beats a disagreeing inventory
      point (VLM often stamps the chat row on the left nav / Calls icon).
    - reveal_actions / select_content: inventory point beats a conflicting CTA
      (sidebar message-preview echo), *unless* the CTA is screen-global on the
      task window and the inventory point is still image-local (014321).
    - Never let *bounds center* override a good point (AX label fragment 011539).
    """
    from plugin.perception.display_topology import point_in_bounds

    cap = str(capability or "").strip().lower().replace("-", "_")
    b_space = str(brain_space or "").strip().lower()
    o_space = str(obj_space or "").strip().lower()

    def _on_task_window(pt: Optional[Tuple[float, float]]) -> bool:
        if pt is None or task_surface is None:
            return False
        return point_in_bounds(pt, getattr(task_surface, "window_bounds", None), pad=48.0)

    def _is_image(_pt: Optional[Tuple[float, float]], space: str) -> bool:
        # Authoritative: only explicit coordinate_space tags — never heuristic.
        return space == "image"

    if brain_point is not None and obj_point is not None and not _points_agree(
        brain_point, obj_point
    ):
        if cap in _FILTER_POINT_WINS:
            # Named Search field geometry over a mid-list / contact latch.
            point = obj_point
        elif cap in _CTA_POINT_WINS:
            point = brain_point
        elif cap in _INVENTORY_POINT_WINS:
            # Explicit screen CTA on the task window beats an image inventory
            # mispoint (multi-display: image [790,500] vs screen [3417,947]).
            if (b_space == "screen" or _on_task_window(brain_point)) and _is_image(
                obj_point, o_space
            ):
                point = brain_point
            else:
                point = obj_point
        else:
            point = brain_point
    elif obj_point is not None:
        point = obj_point
    else:
        point = brain_point
    bounds = obj_bounds
    center = _bounds_center(bounds)
    if (
        point is not None
        and center is not None
        and (
            (b_space == "screen" and point == brain_point and _is_image(center, o_space))
            or (
                task_surface is not None
                and _on_task_window(point)
                and _is_image(center, o_space)
            )
        )
    ):
        bounds = _point_bounds(point, size=120.0 if gesture == "type" else 24.0)
    elif point is not None and center is not None and not _points_agree(point, center):
        bounds = _point_bounds(point, size=120.0 if gesture == "type" else 24.0)
    elif bounds is None and point is not None:
        bounds = _point_bounds(point, size=120.0 if gesture == "type" else 24.0)
    return point, bounds


def validate_brief(brief: ActorBrief) -> Tuple[bool, str]:
    """Return (ok, why). Incomplete briefs must not reach the host."""
    gesture = str(brief.gesture or "").strip().lower()
    if gesture not in GESTURES:
        return False, f"unsupported_gesture:{gesture!r}"
    role = str(brief.field_role or "none").strip().lower() or "none"
    if role not in FIELD_ROLES:
        return False, f"unknown_field_role:{role!r}"

    if gesture in {"click", "context_click", "hover", "ax_press"}:
        if brief.bounds is None and brief.point is None:
            return False, "pointer_gesture_without_geometry"
    if gesture == "type":
        if not str(brief.text or "").strip():
            return False, "type_without_text"
        # Typing without a grounded rectangle is inventing a field. Refuse.
        if brief.bounds is None and brief.point is None:
            cap = str(brief.capability or "").strip().lower() or "type"
            return False, f"{cap}_without_geometry"
        # open_search_ui is a legacy Cmd+F invent flag. With grounded geometry
        # it is ignored (motor forces False). Without geometry the check above
        # already refused — never use the flag as a substitute for a rectangle.
    if gesture == "scroll":
        if not str(brief.scroll_direction or "").strip():
            return False, "scroll_without_direction"
    # High-cost wrong-area latch: refuse before the motor (095344 composer mistype).
    from plugin.agent.capabilities.action_area import validate_actuation_grounding

    area_ok, area_why = validate_actuation_grounding(
        capability=str(brief.capability or ""),
        field_role=str(brief.field_role or ""),
        label=str(brief.label or ""),
        target_kind=str(brief.target_kind or ""),
    )
    if not area_ok:
        return False, area_why
    return True, "ok"


def infer_field_role(surface: str, capability: str = "") -> str:
    surf = str(surface or "").strip().lower()
    cap = str(capability or "").strip().lower()
    if surf in _NO_SIDEBAR_SURFACES or surf == "forward_picker":
        return "destination_filter"
    if cap in {"locate_content"} and surf == "conversation":
        return "in_chat_find"
    # compose/type need the sidebar Search even when surface reads as
    # conversation (open chat leftover while reach_source still searches).
    if cap in {"type_query", "compose_search_query", "open_search"}:
        return "sidebar_search"
    if surf == "search":
        return "sidebar_search"
    return "none"


def _type_into_label(brief: "ActorBrief") -> str:
    """Field name for AX type — never a contact/query token (live 095344)."""
    from plugin.agent.capabilities.action_area import (
        contract_for,
        label_looks_like_filter,
    )

    label = str(brief.label or "").strip()
    role = str(brief.field_role or "").strip().lower()
    cap = str(brief.capability or "").strip().lower()
    contract = contract_for(cap)
    filterish = bool(contract and contract.area.value == "filter_input") or role in {
        "sidebar_search",
        "destination_filter",
        "in_chat_find",
    }
    if not filterish:
        return label
    if label_looks_like_filter(label):
        return label
    return (contract.canonical_label if contract else "") or "Search"


def _object_by_id(objects: Sequence[Any], target_id: str) -> Optional[Dict[str, Any]]:
    tid = str(target_id or "").strip()
    if not tid:
        return None
    for obj in objects:
        if not isinstance(obj, dict):
            continue
        if str(obj.get("id") or "").strip() == tid:
            return obj
    return None


def _resolve_named_object(
    objects: Sequence[Any],
    *,
    capability: str,
    surface: str,
    target_id: str,
    target_label: str,
) -> Optional[Dict[str, Any]]:
    """Resolve geometry only for a name the brain already chose.

    Look up by ``target_id``, else by label match against kind-appropriate
    objects. Never pick "first search_field" / matches_goal — that invents a
    latch the brain did not name.
    """
    typed = [o for o in objects if isinstance(o, dict)]
    cap = str(capability or "").strip().lower()
    surf = str(surface or "").strip().lower()

    def kind(o: Dict[str, Any]) -> str:
        return str(o.get("kind") or "").strip().lower()

    def blob(o: Dict[str, Any]) -> str:
        return " ".join(str(o.get(k) or "") for k in ("text", "label", "id", "kind")).lower()

    prefer: Optional[set] = None
    want_filter = False
    if cap in {"type_query", "compose_search_query", "locate_content", "open_search"}:
        prefer = set(_FILTER_KINDS)
        want_filter = True
    elif surf == "forward_picker" and cap in {"type_query", "compose_search_query"}:
        prefer = set(_FILTER_KINDS)
        want_filter = True
    elif cap in {"reveal_actions", "select_content"} and surf == "conversation":
        prefer = set(_CONTENT_KINDS)
    elif cap in {"resolve_entity", "open_entity"} and surf in {
        "forward_picker",
        "search",
        "search_results",
        "chat_list",
    }:
        prefer = set(_CONTACT_KINDS)

    def preferred(o: Dict[str, Any]) -> bool:
        if prefer is None:
            return True
        k = kind(o)
        if k in prefer:
            return True
        return want_filter and "search" in blob(o)

    by_id = _object_by_id(typed, target_id)
    if by_id is not None:
        # Contact/message ids must not satisfy compose/type (live 095344).
        if want_filter and not preferred(by_id):
            by_id = None
        else:
            return by_id

    label = str(target_label or "").strip().lower()
    if not label:
        return None

    matches = [o for o in typed if label in blob(o) and preferred(o)]
    if len(matches) == 1:
        return matches[0]
    # Ambiguous label → do not invent a winner.
    return None


def brief_from_brain_choice(
    next_action: Optional[Dict[str, Any]],
    world_document: Optional[Dict[str, Any]] = None,
    *,
    app: str = "",
    capability: str = "",
    allow_legacy_geometry: bool = False,
) -> ActorBrief:
    """Build an ActorBrief from the brain's next_action + accepted world.

    This is the handoff. Missing geometry/text stays missing — validate_brief
    refuses rather than inventing a motor path. World lookup only materialises
    geometry the brain already named (target_id / target_label / target_point).

    ``allow_legacy_geometry`` is for golden/corpus ingestion only. Production
    callers must leave it False so naked / unstamped image geometry fails closed.
    """
    action = dict(next_action or {})
    doc = dict(world_document or {})
    if action.get("allow_legacy_screen_geometry") or action.get(
        "legacy_geometry_provenance"
    ):
        allow_legacy_geometry = True
    objects = [o for o in (doc.get("objects") or []) if isinstance(o, dict)]
    surface = str(doc.get("surface") or "").strip().lower()
    cap = (
        str(capability or action.get("family") or action.get("capability") or "")
        .strip()
        .lower()
        .replace("-", "_")
    )
    gesture = CAPABILITY_GESTURE.get(cap, str(action.get("gesture") or "").strip().lower())
    if not gesture and cap in GESTURES:
        gesture = cap
    # Live 153213: after incomplete reveal, consultation/state rotates probe
    # gesture (context_click → hover). Catalog claims both motors; do not ignore
    # an explicit override when the capability is reveal_actions.
    override = str(action.get("gesture") or "").strip().lower()
    if cap in {"reveal_actions", "revealactions", "right_click", "context_click"}:
        if override in {"context_click", "hover"}:
            gesture = override
        else:
            mode = str(action.get("reveal_probe_mode") or "").strip().lower()
            if mode in {"context_click", "hover"}:
                gesture = mode

    from plugin.agent.capabilities.action_area import (
        contract_for,
        exclusive_area,
        is_high_cost,
        label_looks_like_filter,
        object_matches_area,
    )

    area_contract = contract_for(cap)
    target_id = str(action.get("target_id") or "").strip()
    label = str(
        action.get("target_label") or action.get("label") or ""
    ).strip()
    text = str(action.get("text") or "").strip()
    target_kind = str(action.get("target_kind") or "").strip().lower()

    # Strip a prior wrong-area latch before resolve (high-cost exclusive areas).
    wrong_obj = _object_by_id(objects, target_id) if target_id else None
    if (
        wrong_obj is not None
        and area_contract is not None
        and exclusive_area(cap)
        and not object_matches_area(wrong_obj, area_contract)
    ):
        wrong_pt = _as_point(wrong_obj.get("point"))
        brain_pt_early = _as_point(action.get("target_point") or action.get("point"))
        if (
            brain_pt_early is not None
            and wrong_pt is not None
            and _points_agree(brain_pt_early, wrong_pt)
        ):
            action = dict(action)
            action.pop("target_point", None)
            action.pop("point", None)
        target_id = ""
        target_kind = ""

    if area_contract is not None and area_contract.area.value == "filter_input":
        # Query/contact tokens are not field names — retarget to the filter
        # control. Empty label stays empty (no invented latch).
        label_for_field = str(action.get("target_label") or "").strip()
        if label_for_field:
            if label_looks_like_filter(label_for_field):
                label = label_for_field
            else:
                label = area_contract.canonical_label or "Search"

    brain_point = _as_point(action.get("target_point") or action.get("point"))
    bounds = _as_bounds(action.get("bounds"))
    point = brain_point
    task_surface = _task_surface_from_doc(doc, app=str(app or ""))
    brain_space = str(action.get("coordinate_space") or "").strip().lower()
    # Positive provenance only: AX/OCR geometry is screen-absolute on macOS.
    # Do not infer screen from absence of space/frame (that is the fail-open hole).
    if not brain_space:
        geo_src = str(action.get("geometry_source") or "").strip().lower()
        if geo_src.startswith("ax") or geo_src.startswith("ocr"):
            brain_space = "screen"

    # Only resolve named objects. Anonymous kind-picks invent a Search rect.
    obj = _resolve_named_object(
        objects,
        capability=cap,
        surface=surface,
        target_id=target_id,
        target_label=label,
    )
    obj_point = None
    obj_bounds = None
    obj_space = ""
    if obj is not None:
        # Resolved object wins identity — including when a contact id was
        # rejected and Search matched by label (live 095344).
        resolved_id = str(obj.get("id") or "").strip()
        if resolved_id:
            target_id = resolved_id
        if not label:
            label = str(obj.get("text") or obj.get("label") or "").strip()
        target_kind = str(obj.get("kind") or "").strip().lower() or target_kind
        obj_space = str(obj.get("coordinate_space") or "").strip().lower()
        obj_point = _as_point(obj.get("point"))
        # Untagged inventory: only assume image-local when the point *looks*
        # image-relative. Screen/OCR/AX points that already sit inside the task
        # window must stay screen — re-tagging them as image double-transforms
        # (live 171216: Forward ~[1380,217] → 2751 via capture_origin+scale).
        if not obj_space and task_surface is not None and obj_point is not None:
            try:
                from plugin.perception.display_topology import looks_like_image_point

                if looks_like_image_point(obj_point, task_surface):
                    obj_space = "image"
                else:
                    obj_space = "screen"
            except Exception:
                obj_space = ""
        obj_bounds = _as_bounds(obj.get("bounds")) or bounds
    elif (
        is_high_cost(cap)
        and exclusive_area(cap)
        and brain_point is not None
        and area_contract is not None
    ):
        # High error-cost + no named in-area bind: either promote an in-area
        # object under the CTA, or drop geometry that sits on a forbidden site
        # / when the inventory has no legal landing site at all.
        promoted: Optional[Dict[str, Any]] = None
        hit_forbidden = False
        for o in objects:
            op = _as_point(o.get("point"))
            if op is None or not _points_agree(brain_point, op, pad=96.0):
                continue
            if object_matches_area(o, area_contract):
                promoted = o
                break
            hit_forbidden = True
            break
        if promoted is not None:
            obj = promoted
            target_id = str(obj.get("id") or "").strip()
            target_kind = str(obj.get("kind") or "").strip().lower()
            if not label:
                label = str(obj.get("text") or obj.get("label") or "").strip()
            obj_space = str(obj.get("coordinate_space") or "").strip().lower()
            obj_point = _as_point(obj.get("point"))
            if not obj_space and task_surface is not None and obj_point is not None:
                try:
                    from plugin.perception.display_topology import looks_like_image_point

                    obj_space = (
                        "image"
                        if looks_like_image_point(obj_point, task_surface)
                        else "screen"
                    )
                except Exception:
                    obj_space = ""
            obj_bounds = _as_bounds(obj.get("bounds")) or bounds
        elif hit_forbidden:
            # Nearby inventory row under the CTA (Search sits ~80px above the
            # first chat_row — live 215556). Keep filter chrome from AX/OCR /
            # Search labels; only drop unmarked points that look like a row.
            geo_src = str(action.get("geometry_source") or "").strip().lower()
            keep_filter = (
                geo_src.startswith("ax")
                or geo_src.startswith("ocr")
                or label_looks_like_filter(label)
            )
            if not keep_filter:
                brain_point = None
                point = None
                bounds = None
        elif objects and not any(
            object_matches_area(o, area_contract) for o in objects
        ):
            # Inventory has only out-of-area objects (e.g. chat_rows). Keep the
            # brain point when it is already filter chrome from AX/OCR — VLM
            # often omits Search (live 123746). Drop unmarked geometry so we
            # never invent a type site on a contact row (095344).
            geo_src = str(action.get("geometry_source") or "").strip().lower()
            keep_filter = (
                geo_src.startswith("ax")
                or geo_src.startswith("ocr")
                or label_looks_like_filter(label)
            )
            if not keep_filter:
                brain_point = None
                point = None
                bounds = None
        # Empty inventory: keep brain geometry (objects may be omitted upstream).

    # Reconcile in native spaces first (so screen CTA beats image inventory),
    # then project the winner into global desktop points.
    point, bounds = _reconcile_click_geometry(
        brain_point=brain_point,
        obj_point=obj_point,
        obj_bounds=obj_bounds if obj_bounds is not None else bounds,
        gesture=gesture or "",
        capability=cap,
        brain_space=brain_space,
        obj_space=obj_space,
        task_surface=task_surface,
    )
    # Prefer an explicit screen brain/OCR space when native points already agree.
    # Never let an untagged-or-mis-tagged inventory "image" label force a second
    # image→screen transform onto geometry that is already screen-absolute.
    winner_space = brain_space
    if point is not None and obj_point is not None and _points_agree(point, obj_point):
        if (brain_space or "").lower() == "screen":
            winner_space = "screen"
        elif (obj_space or "").lower() == "screen":
            winner_space = "screen"
        else:
            winner_space = obj_space or brain_space
    elif point is not None and brain_point is not None and _points_agree(point, brain_point):
        winner_space = brain_space or "screen"
    elif obj_space:
        winner_space = obj_space
    frame_id = str(
        action.get("coordinate_frame_id")
        or action.get("frame_id")
        or (obj or {}).get("coordinate_frame_id")
        or (obj or {}).get("frame_id")
        or ""
    )
    stamped_graph = None
    if isinstance(doc, dict):
        stamped_graph = doc.get("frame_graph")
    if stamped_graph is None and task_surface is not None:
        stamped_graph = getattr(task_surface, "frame_graph", None)
    obj_grounding = (obj or {}).get("grounding") if isinstance(obj, dict) else None
    obj_g_cid = ""
    if isinstance(obj_grounding, dict):
        obj_g_cid = str(obj_grounding.get("capture_id") or "")
    grounding_capture_id = str(
        action.get("capture_id")
        or action.get("grounding_capture_id")
        or (obj or {}).get("capture_id")
        or obj_g_cid
        or ""
    )
    point, bounds, geometry_audit = _normalize_to_screen(
        point,
        bounds,
        coordinate_space=winner_space,
        surface=task_surface,
        frame_id=frame_id,
        graph=stamped_graph,
        grounding_capture_id=grounding_capture_id,
        allow_legacy_geometry=allow_legacy_geometry,
    )
    geometry_audit = dict(geometry_audit or {})
    geometry_audit.setdefault(
        "geometry_source",
        str(action.get("geometry_source") or winner_space or ""),
    )
    if geometry_audit.get("grounding_uncertain"):
        # Fail closed: do not emit a clickable brief with invented coordinates.
        point = None
        bounds = None

    role = str(action.get("field_role") or "").strip().lower()
    if not role or role == "none":
        role = infer_field_role(surface, cap)

    # Cmd+F invent path is closed. Always False regardless of callers.
    open_search = False

    # locate_content / type_query: text is the query argument
    if cap in {"locate_content", "type_query"} and not text:
        text = str(action.get("text") or action.get("target") or "").strip()

    window_bounds = None
    if task_surface is not None and getattr(task_surface, "window_bounds", None):
        try:
            window_bounds = tuple(float(v) for v in task_surface.window_bounds[:4])
        except (TypeError, ValueError):
            window_bounds = None

    return ActorBrief(
        gesture=gesture or "",
        app=str(app or "").strip(),
        point=point,
        bounds=bounds,
        label=label,
        text=text,
        field_role=role,
        open_search_ui=open_search,
        capability=cap,
        target_id=target_id,
        target_kind=target_kind,
        scroll_direction=str(action.get("direction") or action.get("scroll_direction") or "down"),
        scroll_amount=int(action.get("amount") or action.get("scroll_amount") or 3),
        geometry_audit=geometry_audit,
        task_window_bounds=window_bounds,  # type: ignore[arg-type]
    )


def brief_from_plan_step(
    step: Any,
    world_document: Optional[Dict[str, Any]] = None,
    *,
    app: str = "",
    execution_state: Any = None,
) -> ActorBrief:
    """Bridge PlanStep / Action into an ActorBrief."""
    from plugin.agent.capabilities.action_area import label_looks_like_filter

    fam = str(getattr(step, "action_family", "") or "").strip().lower()
    act = str(getattr(step, "action", "") or "").strip().lower()
    next_action = {
        "family": fam or act,
        "text": str(getattr(step, "text", "") or ""),
        "target_label": str(getattr(step, "semantic_target", "") or ""),
        "target_id": str(getattr(step, "target_entity_id", "") or ""),
        "target_point": getattr(step, "target_point", None),
        "bounds": getattr(step, "bounds", None),
        "coordinate_space": getattr(step, "coordinate_space", None) or "screen",
        "geometry_source": getattr(step, "geometry_source", None),
        "direction": getattr(step, "scroll_direction", None),
        "amount": getattr(step, "scroll_amount", None),
    }
    # Live 153213: honor rotated reveal probe mode from execution_state so the
    # actor path does not hardcode context_click after a failed incomplete reveal.
    if (fam or act) in {
        "reveal_actions",
        "revealactions",
        "right_click",
        "context_click",
    }:
        mode = ""
        try:
            from plugin.agent.capabilities.reveal_actions import (
                current_reveal_probe_mode,
            )

            if execution_state is not None:
                mode = current_reveal_probe_mode(execution_state)
        except Exception:
            mode = str(getattr(execution_state, "reveal_probe_mode", "") or "")
        if mode in {"context_click", "hover"}:
            next_action["gesture"] = mode
            next_action["reveal_probe_mode"] = mode
    # PlanStep may not carry geometry_source; Q Search / Search labels still mark
    # exclusive filter chrome so actor keeps the AX point over chat_row inventory.
    if not next_action.get("geometry_source") and label_looks_like_filter(
        str(next_action.get("target_label") or "")
    ):
        next_action["geometry_source"] = "ax_plan_step"
    return brief_from_brain_choice(
        next_action, world_document, app=app, capability=fam or act
    )


def _is_estimated_box(bounds: Optional[Tuple[float, float, float, float]]) -> bool:
    if not bounds or len(bounds) < 4:
        return False
    try:
        w, h = float(bounds[2]), float(bounds[3])
    except (TypeError, ValueError):
        return False
    return w == h and w in _SYNTHETIC_BOX_SIZES


def _commit_perception_confirm(
    brief: ActorBrief,
    bounds: Optional[Tuple[float, float, float, float]],
) -> Optional[ActorResult]:
    """Perception-confirm step immediately before motor actuation.

    Returns an ActorResult refusal when confirm says the perception is invalid;
    ``None`` means the commit may proceed (valid, skipped/fail-open, or no
    geometry to confirm).
    """
    if str(brief.gesture or "") not in _COMMIT_GESTURES:
        return None
    if bounds is None:
        return None
    from plugin.agent.capabilities.invoke_affordance import is_irreversible_affordance
    from plugin.perception.confirm import confirm_perception

    label = str(brief.label or brief.text or "target").strip() or "target"
    confirm = confirm_perception(
        brief.app,
        label,
        bounds,
        irreversible=is_irreversible_affordance(label),
        estimated=_is_estimated_box(bounds),
    )
    if confirm.valid:
        return None
    reason = confirm.reason or "target no longer matches"
    return ActorResult(
        ok=False,
        status=STALE_PRECONDITION,
        message=f"perception_invalid: refused stale click on {label!r}: {reason}",
        brief=brief.to_dict(),
        evidence={
            "perception_confirm": confirm.to_dict(),
            "continuity_state": confirm.state,
            "reason": reason,
            "may_commit": False,
            "bounds": list(bounds),
            "label": label,
        },
    )


def exec_backend_for_actor_result(result: ActorResult) -> str:
    """Map actor status onto ExecResult.backend for the executive loop."""
    status = str(getattr(result, "status", "") or "")
    if status in {STALE_PRECONDITION, "off_task_window"}:
        return STALE_PRECONDITION
    msg = str(getattr(result, "message", "") or "").lower()
    if (
        "refused stale click" in msg
        or "stale_precondition" in msg
        or "perception_invalid" in msg
        or "off_task_window" in msg
        or "outside task window" in msg
    ):
        return STALE_PRECONDITION
    return "actor"


def execute_actor(
    brief: ActorBrief,
    motor: Optional[ActorMotor] = None,
) -> ActorResult:
    """Validate, perception-confirm, then land the brief. Never invent a target."""
    ok, why = validate_brief(brief)
    payload = brief.to_dict()
    if not ok:
        return ActorResult(
            ok=False,
            status="incomplete_brief",
            message=why,
            brief=payload,
            evidence={"validation": why},
        )

    host = motor or MacActorMotor()
    gesture = brief.gesture
    bounds = brief.bounds
    if bounds is None and brief.point is not None:
        bounds = _point_bounds(
            brief.point, size=120.0 if gesture == "type" else 24.0
        )

    # Multi-display guard: when topology was stamped on the brief, refuse a
    # click whose center is not on that task window (primary-display miss while
    # WhatsApp lives on display 2). Live-refresh bounds when possible.
    if (
        gesture in _COMMIT_GESTURES
        and bounds is not None
        and brief.app
        and getattr(brief, "task_window_bounds", None)
    ):
        try:
            from plugin.perception.display_topology import (
                build_task_surface,
                point_in_bounds,
            )

            window = brief.task_window_bounds
            display_index = None
            display_count = None
            try:
                live = build_task_surface(brief.app)
                if live.window_bounds is not None:
                    window = live.window_bounds
                    display_index = live.display_index
                    display_count = live.display_count
            except Exception:
                pass
            center = _bounds_center(bounds)
            if (
                window is not None
                and center is not None
                and not point_in_bounds(center, window, pad=64.0)
            ):
                return ActorResult(
                    ok=False,
                    status="off_task_window",
                    message=(
                        f"refused click outside task window on multi-display desktop: "
                        f"center={center} window={window} "
                        f"display_index={display_index}"
                    ),
                    brief=payload,
                    evidence={
                        "center": list(center),
                        "window_bounds": list(window),
                        "display_index": display_index,
                        "display_count": display_count,
                    },
                )
        except Exception:
            pass

    # Scope fidelity: brief.point and brief.bounds must describe one target.
    # Cross-pane packs (point in conversation, bounds on list) are refused here.
    # Search/type fields often retarget AX centers — only refuse large pane misses.
    _filter_roles = {
        "sidebar_search",
        "destination_filter",
        "filter_input",
        "search",
    }
    _filter_caps = {
        "compose_search_query",
        "type_query",
        "open_search",
    }
    _overlay_caps = {"invoke_affordance", "reveal_actions", "select_content"}
    _overlay_roles_blob = str(brief.field_role or "").strip().lower()
    overlay_like = (
        str(brief.capability or "") in _overlay_caps
        or _overlay_roles_blob
        in {"none", "menu", "toolbar", "overlay", "context_menu", "selection_mode"}
        or str(getattr(brief, "surface", "") or "").strip().lower()
        in {
            "context_menu",
            "action_menu",
            "selection_mode",
            "forward_picker",
            "dialog",
        }
    )
    filter_like = (
        gesture == "type"
        or str(brief.field_role or "") in _filter_roles
        or str(brief.capability or "") in _filter_caps
    ) and not overlay_like
    if (
        gesture in _COMMIT_GESTURES
        and bounds is not None
        and brief.point is not None
        and not _point_in_rect(brief.point, bounds, pad=96.0)
    ):
        center = _bounds_center(bounds)
        cross_pane = False
        if center is not None:
            try:
                cross_pane = abs(float(brief.point[0]) - float(center[0])) >= 200.0
            except (TypeError, ValueError):
                cross_pane = True
        if cross_pane or not filter_like:
            return ActorResult(
                ok=False,
                status="geometry_mismatch",
                message=(
                    f"geometry_mismatch: brief.point={list(brief.point)} "
                    f"outside brief.bounds={list(bounds)}"
                ),
                brief=payload,
                evidence={
                    "geometry_mismatch": True,
                    "point": list(brief.point),
                    "bounds": list(bounds),
                },
            )

    # Transaction boundary: perception confirm on the final rectangle, then motor.
    refused = _commit_perception_confirm(brief, bounds)
    if refused is not None:
        return refused

    # Capture freshness: Grounding must match the active FrameGraph before motor.
    if gesture in _COMMIT_GESTURES and (
        brief.point is not None or brief.bounds is not None
    ):
        ga = dict(getattr(brief, "geometry_audit", None) or {})
        g_cid = str(ga.get("grounding_capture_id") or "").strip()
        graph_cid = str(ga.get("capture_id") or "").strip()
        if g_cid and graph_cid and g_cid != graph_cid:
            return ActorResult(
                ok=False,
                status="inconclusive_grounding",
                message=(
                    f"stale grounding capture_id={g_cid!r} vs active "
                    f"FrameGraph capture_id={graph_cid!r} — re-ground"
                ),
                brief=payload,
                evidence={
                    "grounding_uncertain": True,
                    "attempt_validity": "inconclusive_grounding",
                    "error_code": "stale_coordinate_frame",
                    "geometry_audit": ga,
                    "motor_event_emitted": False,
                },
            )

    try:
        if gesture == "click" or gesture == "ax_press":
            landed, msg = host.click(brief.app, label=brief.label, bounds=bounds)
        elif gesture == "context_click":
            landed, msg = host.context_click(brief.app, label=brief.label, bounds=bounds)
        elif gesture == "hover":
            landed, msg = host.hover(brief.app, label=brief.label, bounds=bounds)
        elif gesture == "type":
            landed, msg = host.type_text(
                brief.app,
                brief.text,
                bounds=bounds,
                open_search_ui=False,
                into=_type_into_label(brief),
            )
        elif gesture == "press_escape":
            landed, msg = host.press_escape(brief.app)
        elif gesture == "scroll":
            landed, msg = host.scroll(
                brief.app, brief.scroll_direction or "down", int(brief.scroll_amount or 3)
            )
        else:
            return ActorResult(
                ok=False,
                status="unsupported_gesture",
                message=f"unsupported_gesture:{gesture}",
                brief=payload,
            )
    except Exception as exc:
        logger.warning("actor motor failed: %s", exc)
        return ActorResult(
            ok=False,
            status="motor_fail",
            message=str(exc)[:300],
            brief=payload,
        )

    # Normalize legacy ax_* refusals that slipped past (defense in depth).
    status = "executed" if landed else "motor_fail"
    lower_msg = str(msg or "").lower()
    if not landed and (
        "refused stale click" in lower_msg or "perception_invalid" in lower_msg
    ):
        status = STALE_PRECONDITION

    evidence: Dict[str, Any] = {
        "gesture": gesture,
        "field_role": brief.field_role,
        "open_search_ui": brief.open_search_ui,
        "had_geometry": bounds is not None,
        "target_id": brief.target_id,
        "perception_confirm": "passed" if bounds is not None else "ungrounded",
    }
    # Pre-click chain from brief; completed with motor landing below.
    try:
        from plugin.perception.coordinate_frame import build_geometry_audit

        pre = dict(getattr(brief, "geometry_audit", None) or {})
        evidence["geometry_audit"] = build_geometry_audit(
            source_point=pre.get("source_point"),
            source_bbox=pre.get("source_bbox"),
            source_space=str(pre.get("source_space") or ""),
            source_frame_id=str(pre.get("source_frame_id") or ""),
            geometry_source=str(pre.get("geometry_source") or ""),
            global_desktop_point=pre.get("global_desktop_point")
            or (list(brief.point) if brief.point else None),
            window_frame_point=pre.get("window_frame_point"),
            extra={"double_transform_refused": pre.get("double_transform_refused")},
        )
    except Exception:
        if getattr(brief, "geometry_audit", None):
            evidence["geometry_audit"] = dict(brief.geometry_audit)
    # Geometry fidelity: motor center must stay in the brief's bound scope.
    # Landing in another pane (list vs content) is not an ok act.
    # Motor landing updates attempt evidence only — never object grounding.
    if landed and gesture in _COMMIT_GESTURES and bounds is not None:
        try:
            from plugin.agent.transition.attribution import parse_motor_landed_point

            landed_pt = parse_motor_landed_point(msg)
            intended = brief.point
            if intended is None:
                intended = _bounds_center(bounds)
            if landed_pt is not None:
                evidence["motor_landed_point"] = list(landed_pt)
                ga = evidence.get("geometry_audit")
                if isinstance(ga, dict):
                    ga["motor_event_point"] = list(landed_pt)
                if intended is not None:
                    dx = float(intended[0]) - float(landed_pt[0])
                    dy = float(intended[1]) - float(landed_pt[1])
                    dist = (dx * dx + dy * dy) ** 0.5
                    evidence["intended_vs_landed_distance_px"] = round(dist, 1)
                    if isinstance(ga, dict):
                        ga["intended_vs_landed_px"] = round(dist, 1)
                    in_bounds = _point_in_rect(landed_pt, bounds, pad=48.0)
                    # Host AX often rebinds search-field centers (~100–150px).
                    # Content clicks across panes (~200px+ x) remain hard fails.
                    soft = filter_like or gesture == "type"
                    limit = 200.0 if soft else 80.0
                    hard_miss = dist >= limit or (
                        not soft and not in_bounds
                    )
                    if hard_miss and (not soft or abs(dx) >= 200.0):
                        evidence["geometry_mismatch"] = True
                        evidence["attempt_validity"] = "inconclusive_grounding"
                        return ActorResult(
                            ok=False,
                            status="geometry_mismatch",
                            message=(
                                f"geometry_mismatch: intended={list(intended)} "
                                f"landed={list(landed_pt)} dist_px={dist:.0f} "
                                f"in_bounds={in_bounds}"
                            ),
                            brief=payload,
                            evidence=evidence,
                        )
        except Exception:
            pass

    return ActorResult(
        ok=bool(landed),
        status=status,
        message=msg,
        brief=payload,
        evidence=evidence,
    )
