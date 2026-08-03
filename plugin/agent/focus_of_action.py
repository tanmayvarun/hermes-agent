"""The perceptor's awareness of *where the action is*, and whether it may act.

The perceptor is the agent's eyes; the brain equates to a human operator. Two
faculties live here, both about staying anchored to the task instead of merely
narrating whatever pixels are on screen:

* Foreground awareness (:func:`foreground_app_name`,
  :func:`foreground_matches_task`). A human operator interrupted mid-task — a
  call comes in, someone switches to YouTube — does not keep clicking blindly;
  they wait until they are back in the right window. These helpers give the brain
  that awareness so it can hold, persist its goal, and resume, rather than act on
  the wrong surface (where keystrokes would land in the foreign app anyway).

* Focus-of-action hierarchy (:class:`FocusOfAction`, added in a later pass): the
  structured ``app → layer → region → focus object`` reading with object
  permanence, plus a human-readable audit summary.
"""

from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence


def foreground_gate_enabled() -> bool:
    """Whether the brain should hold while a foreign app is frontmost.

    Opt-in, like the other live faculties (unified cognition, layered
    perception, meta-perception): the live launcher turns it on, while offline
    tests that drive the control loop headlessly (whose frontmost app is the
    test runner, never the task app) leave it off so the gate never engages.
    """
    raw = os.getenv("HERMES_FOREGROUND_GATE", "0").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def clean_app_display(name: Any) -> str:
    """App name with invisible format marks dropped but original case kept."""
    text = str(name or "")
    cleaned = "".join(ch for ch in text if unicodedata.category(ch) != "Cf")
    return " ".join(cleaned.strip().split())


def normalize_app_name(name: Any) -> str:
    """App name with invisible Unicode format marks dropped, lowercased.

    macOS reports some apps with leading bidi/format marks — WhatsApp appears as
    ``"\u200eWhatsApp"`` — so raw string equality silently misses them. Dropping
    Unicode ``Cf`` (format) characters and collapsing whitespace makes the
    comparison robust.
    """
    text = str(name or "")
    cleaned = "".join(ch for ch in text if unicodedata.category(ch) != "Cf")
    return " ".join(cleaned.strip().lower().split())


def task_anchor_app(goal: Any) -> str:
    """The application the task is anchored to (its home surface)."""
    return str(getattr(goal, "app", "") or "").strip()


def foreground_app_name() -> str:
    """Name of the frontmost application, or "" when it cannot be determined.

    Uses ``NSWorkspace`` (no special permission). Returning "" on any failure
    lets the caller fail open — treat the task app as in front — so a missing
    signal never wedges the agent in a permanent wait.
    """
    try:
        from AppKit import NSWorkspace  # type: ignore
    except Exception:
        return ""
    try:
        workspace = NSWorkspace.sharedWorkspace()
        app = workspace.frontmostApplication() if workspace is not None else None
        return str(app.localizedName() or "") if app is not None else ""
    except Exception:
        return ""


def foreground_matches_task(goal: Any, *, foreground: Optional[str] = None) -> bool:
    """Whether the foreground app is the task's app.

    Fails open: an unknown task app or an undeterminable foreground both count as
    a match, so the persistence gate only *holds* on positive evidence that a
    foreign app is in front — never on missing information.
    """
    task = normalize_app_name(task_anchor_app(goal))
    if not task:
        return True
    fg = normalize_app_name(foreground if foreground is not None else foreground_app_name())
    if not fg:
        return True
    return task in fg or fg in task


# --- Focus of action: the perceptor's high-level "where the action is" -------
#
# A human does not read a screen as a flat list of pixels; they perceive a stack
# of surfaces (a menu floating over a chat), attend to a region within the top
# one, and centre on the single object the action is about — all while keeping
# object permanence (the chat is still there under the menu). The eyes also know
# *which application* they are looking at, so they notice when the surface they
# were working on has vanished. FocusOfAction is that reading, so a developer
# auditing the log sees what the eyes actually attended to, not a bare surface
# label.

# Presence of the task surface in what the eyes see.
PRESENT = "present"      # the task app's surface is what we are looking at
OCCLUDED = "occluded"    # a foreign window covers it, but it is still there
ABSENT = "absent"        # the task app is not on screen at all

_STOPWORDS = frozenset(
    {"the", "a", "an", "to", "from", "for", "of", "on", "in", "and", "with", "link", "message", "chat"}
)


def _goal_tokens(goal: Any) -> List[str]:
    """Significant lowercase tokens the focus object should match against."""
    raw = " ".join(
        str(getattr(goal, attr, "") or "")
        for attr in ("link_query", "contact", "target_contact")
    )
    out: List[str] = []
    for tok in re.split(r"[^a-z0-9]+", raw.lower()):
        if len(tok) > 2 and tok not in _STOPWORDS and tok not in out:
            out.append(tok)
    return out


def _label_matches_goal(label: str, tokens: Sequence[str]) -> bool:
    low = str(label or "").lower()
    return bool(low) and any(tok in low for tok in tokens)


@dataclass
class FocusRegion:
    """The region within the active layer that the action is happening in."""

    kind: str = ""   # e.g. timeline, conversation, floating_menu, sidebar
    layer_role: str = ""

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        if self.kind:
            out["kind"] = self.kind
        if self.layer_role:
            out["layer_role"] = self.layer_role
        return out


@dataclass
class FocusObject:
    """The single object the action centres on, with its permanence status."""

    label: str = ""
    object_id: str = ""
    bounds: Optional[List[int]] = None
    layer_role: str = ""
    matches_goal: bool = False
    # live: seen in this frame. carried_forward: remembered across the frame from
    # the prior stack (object permanence). occluded: on a layer beneath an overlay.
    permanence: str = "live"

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"matches_goal": bool(self.matches_goal), "permanence": self.permanence}
        if self.label:
            out["label"] = self.label[:120]
        if self.object_id:
            out["object_id"] = self.object_id
        if self.bounds:
            out["bounds"] = list(self.bounds)
        if self.layer_role:
            out["layer_role"] = self.layer_role
        return out


@dataclass
class FocusOfAction:
    """The perceptor's high-level focus hierarchy: app -> layer -> region -> object.

    Carries the object-permanence anchor (``belongs_to_task``/``presence``) so the
    executive can tell "still on the task surface" from "the surface vanished and
    I'm now looking at a foreign app", and a thorough human-readable ``summary``
    for developer audits.
    """

    app: str = ""            # application the eyes actually see in the pixels
    task_app: str = ""       # application the task is anchored to
    belongs_to_task: bool = True
    presence: str = PRESENT
    active_layer_role: str = ""
    active_layer_name: str = ""
    region: FocusRegion = field(default_factory=FocusRegion)
    focus_object: Optional[FocusObject] = None
    layers: List[Dict[str, Any]] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "app": self.app,
            "task_app": self.task_app,
            "belongs_to_task": bool(self.belongs_to_task),
            "presence": self.presence,
        }
        if self.active_layer_role:
            out["active_layer_role"] = self.active_layer_role
        if self.active_layer_name:
            out["active_layer_name"] = self.active_layer_name
        region = self.region.to_dict()
        if region:
            out["region"] = region
        if self.focus_object is not None:
            out["focus_object"] = self.focus_object.to_dict()
        if self.layers:
            out["layers"] = self.layers
        if self.summary:
            out["summary"] = self.summary
        return out


def _presence(belongs_to_task: bool, *, app: str, task_app: str) -> str:
    """Where the task surface is relative to what the eyes see.

    Fails open to ``present`` when the perceived app is unknown, so a missing
    signal never fabricates a vanished surface. When a foreign app is clearly in
    view, the task app is treated as merely occluded (still running behind it,
    which window-scoped capture confirms) rather than gone for good.
    """
    if belongs_to_task:
        return PRESENT
    if not normalize_app_name(app):
        return PRESENT
    if not normalize_app_name(task_app):
        return PRESENT
    return OCCLUDED


def compute_focus_of_action(
    *,
    goal: Any,
    application: str = "",
    layers: Optional[Sequence[Dict[str, Any]]] = None,
    region_kind: str = "",
    focus_label: str = "",
    focus_object_id: str = "",
    focus_bounds: Optional[Sequence[int]] = None,
    focus_layer_role: str = "",
    focus_permanence: str = "live",
) -> FocusOfAction:
    """Assemble the focus hierarchy from already-extracted perception pieces.

    Pure and app-agnostic: the caller pulls the layer stack, attention region,
    and focus candidate out of whatever perception path produced them and passes
    them here. Everything degrades gracefully — an empty stack, an unknown app,
    or no focus candidate each just drops that part of the reading.
    """
    task_app = task_anchor_app(goal)
    app = clean_app_display(application)
    belongs = foreground_matches_task(goal, foreground=app) if app else True
    presence = _presence(belongs, app=app or task_app, task_app=task_app)

    stack = [dict(l) for l in (layers or []) if isinstance(l, dict)]
    active_role = ""
    active_name = ""
    for layer in stack:  # topmost active layer wins
        if str(layer.get("state") or "active") == "active":
            active_role = str(layer.get("role") or "")
            active_name = str(layer.get("name") or "")
    if not active_role and stack:
        active_role = str(stack[-1].get("role") or "")
        active_name = str(stack[-1].get("name") or "")

    focus_object: Optional[FocusObject] = None
    if str(focus_label or "").strip() or str(focus_object_id or "").strip():
        focus_object = FocusObject(
            label=str(focus_label or "").strip(),
            object_id=str(focus_object_id or "").strip(),
            bounds=[int(v) for v in focus_bounds] if focus_bounds else None,
            layer_role=str(focus_layer_role or active_role or "").strip(),
            matches_goal=_label_matches_goal(focus_label, _goal_tokens(goal)),
            permanence=str(focus_permanence or "live"),
        )

    foa = FocusOfAction(
        app=app or task_app,
        task_app=task_app,
        belongs_to_task=belongs,
        presence=presence,
        active_layer_role=active_role,
        active_layer_name=active_name,
        region=FocusRegion(kind=str(region_kind or "").strip(), layer_role=active_role),
        focus_object=focus_object,
        layers=stack,
    )
    foa.summary = render_focus_of_action(foa)
    return foa


def render_focus_of_action(foa: FocusOfAction, *, layers_prose: str = "") -> str:
    """A thorough, human-readable reading of the focus for developer audits."""
    lines: List[str] = []
    anchor = (
        f"Focus of action[app={foa.app or 'unknown'}, "
        f"belongs_to_task={'yes' if foa.belongs_to_task else 'no'}, "
        f"presence={foa.presence}]"
    )
    if not foa.belongs_to_task:
        anchor += (
            f" — the eyes are on {foa.app or 'another app'}, not the task app "
            f"{foa.task_app or '?'}; the task surface is {foa.presence}"
        )
    lines.append(anchor)

    if layers_prose.strip():
        lines.append(layers_prose.strip())
    elif foa.layers:
        rendered = []
        for layer in foa.layers:
            role = str(layer.get("role") or "?")
            name = str(layer.get("name") or "").strip()
            state = str(layer.get("state") or "active")
            n_obj = len(layer.get("objects") or [])
            label = f"{role}" + (f' "{name}"' if name else "")
            rendered.append(f"{label} [{state}, {n_obj} objects]")
        if rendered:
            lines.append("Layers (bottom→top): " + " · ".join(rendered))
    if foa.active_layer_role:
        active = foa.active_layer_role + (f' "{foa.active_layer_name}"' if foa.active_layer_name else "")
        lines.append(f"Active layer: {active}")
    if foa.region.kind:
        lines.append(f"Active region: {foa.region.kind}")
    if foa.focus_object is not None:
        fo = foa.focus_object
        bits = [f'Focus object: "{fo.label or "?"}"']
        if fo.object_id:
            bits.append(f"(id {fo.object_id})")
        if fo.layer_role:
            bits.append(f"on {fo.layer_role}")
        bits.append("— matches goal ✓" if fo.matches_goal else "— does not match goal")
        if fo.permanence and fo.permanence != "live":
            bits.append(f"[{fo.permanence}]")
        lines.append(" ".join(bits))
    else:
        lines.append("Focus object: none identified this frame")
    return "\n".join(lines)


def focus_of_action_from_perception(
    *,
    goal: Any,
    world: Any = None,
    view: Optional[Dict[str, Any]] = None,
    execution_state: Any = None,
    application: str = "",
    focus_label: str = "",
) -> FocusOfAction:
    """Adapter that pulls the focus pieces out of the live perception state.

    Reads the layer stack from the persisted unified world document (falling back
    to a one-layer stack built from the flat view), the attended region kind from
    the world's scene graph, and the app the eyes saw from the perceptor. Every
    lookup is defensive so a partially-populated runtime still yields a reading.
    """
    view = view if isinstance(view, dict) else {}

    # Layer stack: prefer the permanence-merged stack the unified path persists.
    layers: List[Dict[str, Any]] = []
    doc = getattr(execution_state, "unified_world_document", None)
    if isinstance(doc, dict) and isinstance(doc.get("layers"), list):
        layers = [l for l in doc["layers"] if isinstance(l, dict)]
    if not layers:
        try:
            from plugin.agent.scene_layers import layers_from_flat, layers_to_dicts

            layers = layers_to_dicts(
                layers_from_flat(
                    view.get("surface") or view.get("screen"),
                    view.get("open_conversation"),
                    view.get("objects"),
                )
            )
        except Exception:
            layers = []

    # App the eyes saw: perceptor's pixel reading, else the world's active app.
    app = str(application or getattr(world, "active_app", "") or "").strip()

    # Attended region kind from the scene graph's attention block.
    region_kind = ""
    scene = getattr(world, "last_scene_graph", None)
    if isinstance(scene, dict):
        attn = scene.get("attention") or {}
        want = list(attn.get("region_ids") or [])
        regions = scene.get("regions") or []
        if want and isinstance(regions, list):
            for reg in regions:
                if isinstance(reg, dict) and str(reg.get("id")) in {str(w) for w in want}:
                    region_kind = str(reg.get("kind") or "")
                    break

    # Focus object: the goal-relevant target the eyes settled on.
    label = str(focus_label or view.get("target_object_label") or view.get("likely_next_target") or "").strip()
    object_id = str(view.get("target_object_id") or "").strip()

    return compute_focus_of_action(
        goal=goal,
        application=app,
        layers=layers,
        region_kind=region_kind,
        focus_label=label,
        focus_object_id=object_id,
    )
