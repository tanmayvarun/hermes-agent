"""Layered scene representation: the perceptor sees a *stack*, not one surface.

A human looking at a right-click menu over a chat perceives two things at once:
a menu floating *on top of* a conversation that is still open underneath. The
flat single-``surface`` world model could not express that -- the instant an
overlay appeared it reported only the overlay and dropped the conversation, so
every consumer downstream had to reconstruct object permanence from prior state
(the ``transfer_task`` stickiness patch was exactly that, in the wrong layer).

This module models the scene as a shallow **layer stack** scoped to the current
action subscene: bottom -> top, the topmost layer ``active`` and everything
beneath it ``occluded`` but still present. Object permanence becomes a property
of the representation -- an occluded ``container`` layer carries its objects
forward -- so the task binder can simply read the stack with no app rules and no
prior-state hacks.

Everything here is pure and app-agnostic. The only app-aware knowledge is the
:data:`SURFACE_ROLES` table (data, not branching), which collapses an app's
concrete surface names onto general roles.

See ``docs/design/layered-perception-and-affordance-discovery.md``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

# --- general layer roles -----------------------------------------------------
CONTAINER = "container"      # context that must be open to see the object
LIST = "list"                # navigational list on the way to the container
SEARCH = "search"            # search surface
ACTION_MENU = "action_menu"  # menu exposing Forward/Share/Move on the object
DESTINATION = "destination"  # picker/sheet to choose the transfer target
DIALOG = "dialog"            # modal confirm/alert
BLANK = "blank"              # empty / loading
UNKNOWN = "unknown"

KNOWN_ROLES = frozenset(
    {CONTAINER, LIST, SEARCH, ACTION_MENU, DESTINATION, DIALOG, BLANK, UNKNOWN}
)

# Roles that float *over* a base without replacing it. Their appearance must not
# erase the layer beneath -- that is the object-permanence invariant.
OVERLAY_ROLES = frozenset({ACTION_MENU, DESTINATION, DIALOG})

# Roles that constitute a "base" surface (the thing an overlay floats over).
BASE_ROLES = frozenset({CONTAINER, LIST, SEARCH, BLANK})

# Cap the stack within the action subscene (container <- dialog <- menu = 3).
MAX_LAYERS = 3

# App surface vocabulary -> general role. Data an overlay can extend, never
# branching logic. Moved here from transfer_task so the whole system shares one
# table; transfer_task re-exports these names for back-compat.
SURFACE_ROLES: Dict[str, str] = {
    # WhatsApp canonical surfaces (see unified_cognition.CANONICAL_SURFACES).
    "conversation": CONTAINER,
    "chat_list": LIST,
    "search": SEARCH,
    "context_menu": ACTION_MENU,
    "forward_picker": DESTINATION,
    "dialog": DIALOG,
    "blank": BLANK,
    # Role names themselves, so mapping is idempotent on already-general input.
    "container": CONTAINER,
    "list": LIST,
    "action_menu": ACTION_MENU,
    "destination": DESTINATION,
    "unknown": UNKNOWN,
    # Generic synonyms other apps' readings may use.
    "thread": CONTAINER,
    "folder": CONTAINER,
    "document": CONTAINER,
    "page": CONTAINER,
    "share_sheet": ACTION_MENU,
    "context menu": ACTION_MENU,
    "destination_picker": DESTINATION,
    "share_targets": DESTINATION,
    "picker": DESTINATION,
}

# General role -> a canonical surface name, for the flat back-compat fields many
# existing consumers still read. Uses the WhatsApp vocabulary because that is
# the only live state machine; other apps only need the role.
ROLE_TO_SURFACE: Dict[str, str] = {
    CONTAINER: "conversation",
    LIST: "chat_list",
    SEARCH: "search",
    ACTION_MENU: "context_menu",
    DESTINATION: "forward_picker",
    DIALOG: "dialog",
    BLANK: "blank",
    UNKNOWN: "blank",
}


def layered_perception_enabled() -> bool:
    """Opt-in while the layer stack is proven on live tasks.

    When off, the perceptor keeps its flat single-surface behaviour and the
    task binder falls back to its prior-state bridge; nothing downstream sees a
    ``layers`` key.
    """
    raw = os.getenv("HERMES_LAYERED_PERCEPTION", "0").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def surface_role(surface: str) -> str:
    """Map an app's concrete surface name onto a general role."""
    key = str(surface or "").strip().lower().replace("-", "_")
    if key in SURFACE_ROLES:
        return SURFACE_ROLES[key]
    key2 = key.replace("_", " ")
    return SURFACE_ROLES.get(key2, UNKNOWN)


@dataclass
class Layer:
    """One surface in the stack, with the objects that live on it."""

    role: str
    name: str = ""
    state: str = "active"  # "active" (topmost) | "occluded" (beneath an overlay)
    objects: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def is_overlay(self) -> bool:
        return self.role in OVERLAY_ROLES

    @property
    def is_base(self) -> bool:
        return self.role in BASE_ROLES

    @property
    def occluded(self) -> bool:
        return self.state == "occluded"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "name": self.name,
            "state": "occluded" if self.occluded else "active",
            "objects": [dict(o) for o in self.objects],
        }

    @classmethod
    def from_dict(cls, raw: Any) -> "Layer":
        raw = raw if isinstance(raw, dict) else {}
        role = str(raw.get("role") or raw.get("surface") or "").strip().lower()
        if role not in KNOWN_ROLES:
            role = surface_role(role)
        state = str(raw.get("state") or "active").strip().lower()
        state = "occluded" if state.startswith("occlud") else "active"
        objects = [o for o in (raw.get("objects") or []) if isinstance(o, dict)]
        return cls(role=role or UNKNOWN, name=str(raw.get("name") or "").strip(), state=state, objects=objects)


def _fix_states(layers: Sequence[Layer]) -> List[Layer]:
    """Enforce the invariant: exactly the topmost layer is active, rest occluded."""
    out = [Layer(role=l.role, name=l.name, state=l.state, objects=list(l.objects)) for l in layers]
    for i, layer in enumerate(out):
        layer.state = "active" if i == len(out) - 1 else "occluded"
    return out


def _cap_depth(layers: Sequence[Layer], max_depth: int) -> List[Layer]:
    """Keep the base plus the topmost overlays when the stack is too deep."""
    layers = list(layers)
    if len(layers) <= max_depth:
        return layers
    kept = [layers[0]] + layers[-(max_depth - 1):]
    # De-dup while preserving order (base could coincide with a kept top entry).
    seen: List[Layer] = []
    for layer in kept:
        if layer not in seen:
            seen.append(layer)
    return seen[:max_depth]


def normalize_layers(raw: Any, *, max_depth: int = MAX_LAYERS) -> List[Layer]:
    """Coerce a raw ``layers`` list into a bounded, invariant-obeying stack."""
    if not isinstance(raw, (list, tuple)):
        return []
    layers = [Layer.from_dict(item) for item in raw if isinstance(item, dict)]
    # Drop truly empty entries (no role signal, no name, no objects).
    layers = [l for l in layers if (l.role and l.role != UNKNOWN) or l.name or l.objects]
    if not layers:
        return []
    layers = _cap_depth(layers, max_depth)
    return _fix_states(layers)


def layers_from_flat(
    surface: Any, open_conversation: Any, objects: Any
) -> List[Layer]:
    """Build a one-layer stack from the flat single-surface reading.

    The flat model reports only the topmost surface, so this yields a single
    layer. If that layer is an overlay, the base beneath it is missing here --
    :func:`merge_permanence` restores it from the prior stack.
    """
    role = surface_role(surface)
    objs = [o for o in (objects or []) if isinstance(o, dict)]
    name = str(open_conversation or "").strip() if role == CONTAINER else ""
    return [Layer(role=role or BLANK, name=name, state="active", objects=objs)]


def base_layer(layers: Sequence[Layer]) -> Optional[Layer]:
    """The lowest non-overlay layer (the container/list/search beneath)."""
    for layer in layers:
        if not layer.is_overlay:
            return layer
    return None


def container_layer(layers: Sequence[Layer]) -> Optional[Layer]:
    for layer in layers:
        if layer.role == CONTAINER:
            return layer
    return None


def find_layer(layers: Sequence[Layer], role: str) -> Optional[Layer]:
    for layer in layers:
        if layer.role == role:
            return layer
    return None


def top_layer(layers: Sequence[Layer]) -> Optional[Layer]:
    return layers[-1] if layers else None


def merge_permanence(
    prior_layers: Sequence[Layer], new_layers: Sequence[Layer]
) -> List[Layer]:
    """Enforce object permanence across frames using the prior stack as memory.

    Two corrections, both semantic and app-agnostic:

    1. **Base carried under an overlay.** If the new reading's top layer is an
       overlay and it dropped the base beneath it, carry the prior base forward
       as ``occluded`` (with its objects). This is what a human does: the menu
       opened *over* the chat; the chat did not go anywhere.
    2. **Objects carried on an occluded base.** If the new reading kept the base
       but listed no objects on it (they are behind the overlay), and the prior
       base of the same role/name had objects, carry those objects forward, so
       the goal object does not blink out just because a menu covers it.
    """
    prior = list(prior_layers or [])
    new = [Layer(role=l.role, name=l.name, state=l.state, objects=list(l.objects)) for l in (new_layers or [])]
    if not new:
        return _fix_states(prior)

    top = new[-1]
    has_base = any(not l.is_overlay for l in new)
    prior_base = base_layer(prior)

    if top.is_overlay and not has_base and prior_base is not None:
        carried = Layer(
            role=prior_base.role,
            name=prior_base.name,
            state="occluded",
            objects=list(prior_base.objects),
        )
        new = [carried] + new
    else:
        # Base present but stripped of its objects behind the overlay -> refill
        # from the prior base if it is the same surface.
        nb = base_layer(new)
        if (
            nb is not None
            and not nb.objects
            and prior_base is not None
            and prior_base.role == nb.role
            and _same_name(prior_base.name, nb.name)
            and prior_base.objects
        ):
            nb.objects = list(prior_base.objects)

    return _cap_depth(_fix_states(new), MAX_LAYERS)


def _same_name(a: str, b: str) -> bool:
    a = str(a or "").strip().lower()
    b = str(b or "").strip().lower()
    if not a or not b:
        return True  # an unnamed container matches any (WhatsApp often omits it)
    return a in b or b in a


def derive_flat(layers: Sequence[Layer]) -> tuple[str, str]:
    """Back-compat flat fields: (top-layer surface, base container name)."""
    if not layers:
        return "", ""
    surface = ROLE_TO_SURFACE.get(layers[-1].role, "blank")
    base = base_layer(layers)
    name = base.name if base is not None and base.role == CONTAINER else ""
    return surface, name


def flat_objects(layers: Sequence[Layer]) -> List[Dict[str, Any]]:
    """Union of every layer's objects, for consumers that want one inventory.

    Menu items on the overlay and messages on the occluded container both need
    to become clickable, so the flat inventory carries the whole stack. Dedup on
    (text, point) preserving stack order (base first).
    """
    seen = set()
    out: List[Dict[str, Any]] = []
    for layer in layers:
        for obj in layer.objects:
            key = (str(obj.get("text") or ""), tuple(obj.get("point") or ()))
            if key in seen:
                continue
            seen.add(key)
            out.append(dict(obj))
    return out


def layers_to_dicts(layers: Sequence[Layer]) -> List[Dict[str, Any]]:
    return [l.to_dict() for l in layers]


def _short_object(obj: Dict[str, Any]) -> str:
    text = str(obj.get("text") or obj.get("label") or "").strip()
    text = text[:40] + ("…" if len(text) > 40 else "")
    flag = " *" if obj.get("matches_goal") else ""
    return f"{text}{flag}" if text else str(obj.get("kind") or "object")


def render_layers(layers: Sequence[Layer], *, task_context: str = "") -> str:
    """Human-readable enumeration of the stack, for developer verification.

    Lists every layer and overlay in the action subscene with role, name,
    active/occluded state and salient objects, so perception can be eyeballed
    against the screenshot. Optionally annotated with the executive's task
    context (perception describes the scene; the executive owns task topology,
    so the phase is an annotation, not part of the scene).
    """
    if not layers:
        return "Scene: (empty)."
    n = len(layers)
    head = f"Scene ({n} layer{'s' if n != 1 else ''}):"
    lines = [head]
    for i, layer in enumerate(layers):
        state = "active" if not layer.occluded else "occluded"
        piece = f"  L{i} {layer.role}"
        if layer.name:
            piece += f' "{layer.name}"'
        piece += f" ({state})"
        objs = layer.objects[:6]
        if objs:
            piece += " — " + ", ".join(_short_object(o) for o in objs)
        lines.append(piece)
    out = "\n".join(lines)
    if task_context:
        out += f"\nTask context: {task_context}"
    return out
