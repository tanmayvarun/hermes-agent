"""The task-conditioned affordance frontier handed to the world model.

A world model that knows only which objects exist is not enough for agency.
To choose a move the model has to know what can be done *now*, what each move
is expected to reveal, and which moves only become available after a probe.
Until this module existed the packet carried objects and their direct AX
actions, so the model had to rediscover WhatsApp's interaction mechanics from
pixels on every frame -- and the richer candidate set only appeared later, in
the action selector, after the belief had already been formed without it.

Three classes of affordance are kept apart on purpose:

  observed  -- available right now, backed by AX or by something visible
  latent    -- not available now, expected to appear after a named trigger
  probe     -- unknown; an action worth taking for what it would reveal

Collapsing them is what makes an agent hallucinate a Forward button that is
not on screen. Every entry therefore carries its provenance and a confidence,
and latent entries are never produced by a family x object cross product --
the earlier capability graph did exactly that and attached voice calls to
messages. A latent action exists here only because an app overlay declared it,
a generic interaction prior covers the object kind, or the runtime watched the
transition happen before.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from plugin.agent.capabilities.invoke_affordance import is_irreversible_affordance

# Evidence sources, strongest first. The name travels with the affordance so a
# reader (model or human) can tell a fact from an expectation.
SOURCE_AX_ACTION = "ax_action"
SOURCE_AX_ROLE = "ax_role"
SOURCE_VISION_OBJECT = "vision_object"
SOURCE_OVERLAY_PRIOR = "overlay_prior"
SOURCE_INTERACTION_PRIOR = "interaction_prior"
SOURCE_SURFACE_GRAPH = "surface_graph"
SOURCE_TRANSITION_MEMORY = "transition_memory"

STATUS_OBSERVED = "observed"
STATUS_LATENT = "latent"
STATUS_PROBE = "probe"

MAX_OBSERVED = 14
MAX_LATENT = 8
MAX_PROBE = 4
MAX_EDGES = 8
MAX_EXCLUDED = 6


def affordance_frontier_enabled() -> bool:
    raw = os.getenv("HERMES_AFFORDANCE_FRONTIER", "1").strip().lower()
    return raw in {"1", "true", "yes", "on"}


@dataclass
class Evidence:
    source: str
    detail: str = ""

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"source": self.source}
        if self.detail:
            out["detail"] = self.detail[:120]
        return out


@dataclass
class PredictedOutcome:
    """What a move is expected to produce, stated so it can be falsified."""

    surface: str = ""
    predicates: Dict[str, Any] = field(default_factory=dict)
    probability: float = 0.0
    expected_information_gain: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"probability": round(float(self.probability), 2)}
        if self.surface:
            out["surface"] = self.surface
        if self.predicates:
            out["predicates"] = dict(self.predicates)
        if self.expected_information_gain:
            out["expected_information_gain"] = round(
                float(self.expected_information_gain), 2
            )
        return out


@dataclass
class LatentAffordance:
    """A control expected to appear once its trigger has been taken."""

    label: str
    family: str = ""
    probability: float = 0.0
    basis: str = ""

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "label": self.label,
            "probability": round(float(self.probability), 2),
        }
        if self.family:
            out["family"] = self.family
        if self.basis:
            out["basis"] = self.basis
        return out


@dataclass
class Affordance:
    id: str
    family: str
    status: str
    target_id: Optional[int] = None
    target_label: str = ""
    available_now: bool = True
    # For a latent affordance: the id of the action that is expected to reveal it.
    trigger_action: Optional[str] = None
    actuators: List[Dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0
    risk: float = 0.0
    reversible: bool = True
    expected_outcomes: List[PredictedOutcome] = field(default_factory=list)
    may_reveal: List[LatentAffordance] = field(default_factory=list)
    evidence: List[Evidence] = field(default_factory=list)
    expected_information_gain: float = 0.0
    # Producer-stamped geometry provenance — never invented by the publisher.
    coordinate_space: str = ""
    geometry_source: str = ""
    owner_surface: str = ""
    # Temporal provenance: WHEN the geometry was true (not current world time).
    capture_id: str = ""
    frame_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "id": self.id,
            "family": self.family,
            "status": self.status,
            "confidence": round(float(self.confidence), 2),
        }
        if self.target_id is not None:
            out["target_id"] = self.target_id
        if self.target_label:
            out["target_label"] = self.target_label[:80]
        if not self.available_now:
            out["available_now"] = False
        if self.trigger_action:
            out["available_after"] = self.trigger_action
        if self.actuators:
            out["actuators"] = self.actuators
        if self.risk:
            out["risk"] = round(float(self.risk), 2)
        if not self.reversible:
            out["reversible"] = False
        if self.expected_outcomes:
            out["expected_outcomes"] = [o.to_dict() for o in self.expected_outcomes]
        if self.may_reveal:
            out["may_reveal"] = [m.to_dict() for m in self.may_reveal]
        if self.expected_information_gain:
            out["expected_information_gain"] = round(
                float(self.expected_information_gain), 2
            )
        if self.evidence:
            out["evidence"] = [e.to_dict() for e in self.evidence]
        space = str(self.coordinate_space or "").strip().lower()
        if space in {"screen", "image"}:
            out["coordinate_space"] = space
        if self.geometry_source:
            out["geometry_source"] = str(self.geometry_source)[:40]
        if self.owner_surface:
            out["owner_surface"] = str(self.owner_surface)[:40]
        if self.capture_id:
            out["capture_id"] = str(self.capture_id)[:80]
        if self.frame_id:
            out["frame_id"] = str(self.frame_id)[:80]
        return out


@dataclass
class TransitionEdge:
    from_action: str
    to_surface: str
    probability: float
    enumeration_status: str = "predicted"
    possible_actions: List[str] = field(default_factory=list)
    basis: str = ""

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "from_action": self.from_action,
            "to_surface": self.to_surface,
            "probability": round(float(self.probability), 2),
            "enumeration_status": self.enumeration_status,
        }
        if self.possible_actions:
            out["possible_actions"] = list(self.possible_actions)
        if self.basis:
            out["basis"] = self.basis
        return out


@dataclass
class UnknownFrontier:
    """An honest "unknown beyond this edge": an object whose full action set is
    not yet known, the question that would resolve it, and the probes that would
    answer that question.

    This is distinct from a probe action (a concrete move to make) and from a
    latent action (a specific control we predict): a frontier marks the
    *epistemic hole* itself, so the executive can reason about topology it has
    not explored instead of assuming an object has no further actions. Once a
    probe grounds the object's actions, its frontier is resolved and dropped.
    """

    object_id: str = ""
    object_label: str = ""
    question: str = ""
    suggested_probes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"question": self.question}
        if self.object_id:
            out["object_id"] = self.object_id
        if self.object_label:
            out["object_label"] = self.object_label[:80]
        if self.suggested_probes:
            out["suggested_probes"] = list(self.suggested_probes)
        return out


@dataclass
class AffordanceFrontier:
    surface: str = ""
    observed_actions: List[Affordance] = field(default_factory=list)
    latent_actions: List[Affordance] = field(default_factory=list)
    probe_actions: List[Affordance] = field(default_factory=list)
    known_transition_edges: List[TransitionEdge] = field(default_factory=list)
    excluded_actions: List[Dict[str, str]] = field(default_factory=list)
    # Where the action topology is genuinely unexplored: objects whose reachable
    # actions we predict but have not observed. "unknown beyond this edge".
    unknown_frontiers: List[UnknownFrontier] = field(default_factory=list)

    def to_packet(self) -> Dict[str, Any]:
        return {
            "surface": self.surface,
            "observed_actions": [a.to_dict() for a in self.observed_actions[:MAX_OBSERVED]],
            "latent_actions": [a.to_dict() for a in self.latent_actions[:MAX_LATENT]],
            "probe_actions": [a.to_dict() for a in self.probe_actions[:MAX_PROBE]],
            "known_transition_edges": [
                e.to_dict() for e in self.known_transition_edges[:MAX_EDGES]
            ],
            "unknown_frontiers": [f.to_dict() for f in self.unknown_frontiers[:MAX_PROBE]],
            "excluded_actions": list(self.excluded_actions[:MAX_EXCLUDED]),
        }

    def index(self) -> Dict[str, Affordance]:
        return {
            a.id: a
            for a in list(self.observed_actions)
            + list(self.latent_actions)
            + list(self.probe_actions)
        }


# --- priors -----------------------------------------------------------------

# Generic, app-independent interaction priors keyed by object kind. These are
# the only source of a latent action besides an overlay declaration or a
# remembered transition, which is what keeps the graph honest.
_KIND_PRIORS: Dict[str, Dict[str, Any]] = {
    "message": {
        "select": ("select_content", "focus the message so its actions apply to it"),
        "probes": (
            (
                "context_click",
                ("Reply", "Forward", "Copy", "Delete"),
                0.8,
                "context_menu",
            ),
            ("hover", ("Reply", "React", "Forward"), 0.5, ""),
        ),
    },
    "row": {
        "open": ("open_entity", "open the conversation this row stands for"),
        "probes": (),
    },
    "contact": {
        "open": ("open_entity", "open the conversation this row stands for"),
        "probes": (),
    },
    "conversation": {
        "open": ("open_entity", "open the conversation this row stands for"),
        "probes": (),
    },
    "chat": {
        "open": ("open_entity", "open the conversation this row stands for"),
        "probes": (),
    },
}

# Roles that behave like a text input; typing into them is observed, not latent.
_INPUT_ROLES = {"axtextfield", "axsearchfield", "axtextarea", "axcombobox"}
_BUTTON_ROLES = {"axbutton", "axmenuitem", "axmenubutton", "axpopupbutton", "axcheckbox"}
_ROW_ROLES = {"axrow", "axcell", "axoutlinerow", "axlink"}

# Which families can advance which goal. Everything else on screen is real but
# irrelevant, and is reported as excluded rather than silently dropped so the
# model can see that the runtime considered and rejected it.
_GOAL_FAMILIES: Dict[str, Tuple[str, ...]] = {
    "forward_message": (
        "compose_search_query",
        "type_query",
        "resolve_entity",
        "open_entity",
        "locate_content",
        "select_content",
        "reveal_actions",
        "invoke_affordance",
        "commit_irreversible",
        "dismiss_transient",
        "scroll",
        "hover",
    ),
}

# Labels that are always out of scope for a messaging goal. Naming them keeps
# "voice call attached to a message" out of the frontier without pretending the
# control does not exist.
_OFF_TASK_LABELS = (
    "voice call",
    "video call",
    "start call",
    "call",
    "settings",
    "archive",
    "archived",
    "new chat",
    "status",
    "channels",
    "communities",
    "mute",
    "block",
    "report",
)


def _clean(text: Any, limit: int = 80) -> str:
    return str(text or "").strip()[:limit]


def _norm(text: Any) -> str:
    return str(text or "").strip().lower()


def _kind_of(role: str, label: str, declared_kind: str = "") -> str:
    kind = _norm(declared_kind)
    if kind in _KIND_PRIORS:
        return kind
    role_l = _norm(role)
    if role_l in _INPUT_ROLES:
        return "input"
    if role_l in _BUTTON_ROLES:
        return "button"
    if role_l in _ROW_ROLES:
        return "row"
    if kind:
        return kind
    return "static"


def _family_for(kind: str, role: str, label: str, *, description: str = "") -> str:
    if kind == "input":
        # Sidebar Search is contact-query authorship, not an in-picker type_query.
        blob = f"{label} {description}".strip().lower()
        if "search" in blob:
            return "compose_search_query"
        return "type_query"
    if kind == "button":
        return "commit_irreversible" if is_irreversible_affordance(label) else "invoke_affordance"
    if kind in {"row", "contact", "conversation", "chat"}:
        return "open_entity"
    if kind == "message":
        return "select_content"
    # WhatsApp Electron: sidebar Search is often AXStaticText ("• Search" / "Q Search").
    blob = f"{label} {description}".strip().lower()
    if blob in {"search", "q search", "• search", "search…", "search..."} or (
        "search" in blob and "result" not in blob and len(blob) < 48
    ):
        return "compose_search_query"
    return ""


def goal_profile(goal_kind: str) -> Tuple[str, ...]:
    """Families that can advance this goal, or empty when the goal is unknown.

    An unrecognised goal gets no filtering rather than the forwarding filter:
    silently scoping a frontier to the wrong task is worse than a wide one.
    """
    kind = _norm(goal_kind)
    for name, families in _GOAL_FAMILIES.items():
        if kind == name or name.split("_")[0] in kind:
            return families
    return ()


def _relevant(family: str, label: str, goal_kind: str) -> Tuple[bool, str]:
    allowed = goal_profile(goal_kind)
    if not allowed:
        return True, ""
    if family and family not in allowed:
        return False, f"{family} cannot advance {goal_kind}"
    low = _norm(label)
    if low and any(low == term or low.startswith(term + " ") for term in _OFF_TASK_LABELS):
        return False, f"{label!r} is off-task for {goal_kind}"
    return True, ""


def _actuators(entity_id: Optional[int], point: Optional[Sequence[float]], ax_actions: Sequence[str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    press = [a for a in ax_actions if "press" in _norm(a)]
    if press and entity_id is not None:
        out.append({"type": "ax_press", "target_id": entity_id, "confidence": 0.85})
    if point is not None:
        try:
            out.append(
                {
                    "type": "coordinate_click",
                    "point": [int(point[0]), int(point[1])],
                    "confidence": 0.9,
                }
            )
        except (TypeError, ValueError, IndexError):
            pass
    return out


def _center(bounds: Any) -> Optional[Tuple[int, int]]:
    try:
        x, y, w, h = bounds
    except (TypeError, ValueError):
        return None
    try:
        return int(float(x) + float(w) / 2.0), int(float(y) + float(h) / 2.0)
    except (TypeError, ValueError):
        return None


# --- observed ---------------------------------------------------------------


def _temporal_from_item(
    item: Optional[Dict[str, Any]],
    *,
    default_capture_id: str = "",
) -> Tuple[str, str]:
    """Producer capture/frame stamps — never invent current-world freshness.

    ``frame_id`` is returned raw; callers must resolve it against
    ``coordinate_space`` via :func:`resolve_frame_id_for_space`.
    """
    row = item if isinstance(item, dict) else {}
    cid = str(
        row.get("capture_id")
        or row.get("grounding_capture_id")
        or default_capture_id
        or ""
    ).strip()[:80]
    fid = str(
        row.get("frame_id") or row.get("coordinate_frame_id") or ""
    ).strip()[:80]
    return cid, fid


def _coerce_frame_graph(raw: Any) -> Any:
    if raw is None:
        return None
    try:
        from plugin.perception.coordinate_frame import FrameGraph

        if isinstance(raw, FrameGraph):
            return raw
        if isinstance(raw, dict):
            return FrameGraph.from_dict(raw)
    except Exception:
        return None
    return None


def observed_from_ax(
    ax_evidence: Iterable[Dict[str, Any]],
    *,
    goal_kind: str = "forward_message",
    capture_id: str = "",
    frame_graph: Any = None,
) -> Tuple[List[Affordance], List[Dict[str, str]]]:
    """Turn AX evidence into affordances that are true right now.

    ``capture_id`` / ``frame_graph`` are producer stamps for this observation.
    AX geometry is screen-space: ``frame_id`` is always the graph's screen
    frame (never a generic document frame / image frame).
    """
    from plugin.perception.coordinate_frame import resolve_frame_id_for_space

    graph = _coerce_frame_graph(frame_graph)
    found: List[Affordance] = []
    excluded: List[Dict[str, str]] = []
    for item in ax_evidence:
        if not isinstance(item, dict):
            continue
        label = _clean(item.get("label") or item.get("description"))
        description = _clean(item.get("description"))
        role = str(item.get("role") or "")
        actions = [str(a) for a in (item.get("actions") or [])]
        kind = _kind_of(role, label, "")
        family = _family_for(kind, role, label, description=description)
        if not family:
            continue
        if not label and kind != "input":
            continue
        ok, why = _relevant(family, label, goal_kind)
        if not ok:
            excluded.append({"target_label": label or role, "reason": why})
            continue
        entity_id = item.get("id")
        entity_id = int(entity_id) if isinstance(entity_id, int) else None
        point = _center(item.get("bounds"))
        actuators = _actuators(entity_id, point, actions)
        if not actuators:
            continue
        evidence = [Evidence(SOURCE_AX_ROLE, role)]
        if actions:
            evidence.insert(0, Evidence(SOURCE_AX_ACTION, ",".join(actions[:3])))
        reversible = family != "commit_irreversible"
        cid, raw_fid = _temporal_from_item(item, default_capture_id=capture_id)
        # Screen space only — never inherit an image/document frame id.
        fid = resolve_frame_id_for_space(
            frame_id=raw_fid,
            coordinate_space="screen",
            graph=graph,
        )
        found.append(
            Affordance(
                id=f"ax_{entity_id if entity_id is not None else len(found)}_{family}",
                family=family,
                status=STATUS_OBSERVED,
                target_id=entity_id,
                target_label=label,
                actuators=actuators,
                confidence=0.9 if actions else 0.7,
                risk=0.4 if not reversible else 0.05,
                reversible=reversible,
                evidence=evidence,
                # AX measured geometry is screen-space by producer contract.
                coordinate_space="screen",
                geometry_source="ax_action" if actions else "ax_role",
                owner_surface=str(item.get("owner_surface") or item.get("surface") or "")[
                    :40
                ],
                capture_id=cid,
                frame_id=fid,
            )
        )
    return found, excluded


def observed_from_objects(
    objects: Iterable[Dict[str, Any]],
    *,
    goal_kind: str = "forward_message",
    point_scale: float = 1.0,
    point_origin: Tuple[float, float] = (0.0, 0.0),
    frame_graph: Any = None,
) -> List[Affordance]:
    """Affordances on things only the model can see.

    WhatsApp publishes no AX content nodes for messages or chat rows, so
    without this the frontier would claim the only actionable things on a
    conversation are the window's chrome buttons.
    """
    from plugin.perception.coordinate_frame import resolve_frame_id_for_space

    graph = _coerce_frame_graph(frame_graph)
    found: List[Affordance] = []
    for index, item in enumerate(objects):
        if not isinstance(item, dict):
            continue
        text = _clean(item.get("text") or item.get("label"))
        if not text:
            continue
        kind = _kind_of("", text, str(item.get("kind") or ""))
        family = _family_for(kind, "", text)
        if not family:
            continue
        ok, _why = _relevant(family, text, goal_kind)
        if not ok:
            continue
        raw_point = item.get("point") or item.get("target_point")
        point = None
        if isinstance(raw_point, (list, tuple)) and len(raw_point) >= 2:
            try:
                space = str(item.get("coordinate_space") or "").strip().lower()
                rx, ry = float(raw_point[0]), float(raw_point[1])
                # Unknown space → not executable (missing location metadata).
                # Screen: pass through. Image: origin+scale via FrameGraph path.
                if space == "screen":
                    point = (int(rx), int(ry))
                elif space == "image":
                    point = (
                        int(float(point_origin[0]) + rx * float(point_scale)),
                        int(float(point_origin[1]) + ry * float(point_scale)),
                    )
                else:
                    point = None
            except (TypeError, ValueError):
                point = None
        actuators = _actuators(None, point, ())
        space = str(item.get("coordinate_space") or "").strip().lower()
        geo_src = str(item.get("geometry_source") or item.get("source") or "").strip()
        owner = str(item.get("owner_surface") or item.get("surface") or "").strip()
        # Keep untagged objects for probe/latent discovery. Executable publish
        # requires stamped coordinate_space — never invent it here.
        # matches_goal is recall-only; do not let it dominate affordance rank.
        cid, raw_fid = _temporal_from_item(item)
        fid = ""
        if space in {"screen", "image"}:
            fid = resolve_frame_id_for_space(
                frame_id=raw_fid,
                coordinate_space=space,
                graph=graph,
            )
        found.append(
            Affordance(
                id=f"obj_{index}_{family}",
                family=family,
                status=STATUS_OBSERVED,
                target_label=text,
                actuators=actuators,
                confidence=0.65 if item.get("matches_goal") else 0.6,
                evidence=[Evidence(SOURCE_VISION_OBJECT, f"kind={kind}")],
                expected_outcomes=[
                    PredictedOutcome(
                        predicates={"target_object_selected": True}
                        if family == "select_content"
                        else {"conversation_open": True},
                        probability=0.8,
                    )
                ],
                coordinate_space=space if space in {"screen", "image"} else "",
                geometry_source=geo_src[:40],
                owner_surface=owner[:40],
                capture_id=cid,
                frame_id=fid,
            )
        )
    return found


# --- latent and probe -------------------------------------------------------


def probes_for_object(
    affordance: Affordance,
    *,
    reveal_mode: str = "context_click",
) -> Tuple[List[Affordance], List[Affordance]]:
    """Probes and the latent actions they are expected to reveal.

    Both come from the same prior entry, so a latent Forward can never appear
    without the probe that would produce it, and neither is ever stated as an
    observed fact.
    """
    kind = "message" if affordance.family == "select_content" else ""
    prior = _KIND_PRIORS.get(kind or "", {})
    specs = prior.get("probes") or ()
    probes: List[Affordance] = []
    latents: List[Affordance] = []
    for trigger, reveals, probability, surface in specs:
        # The app overlay decides which gesture reveals object actions; a hover
        # probe on an app whose menu is context-click only is wasted motion.
        confidence = probability if trigger == reveal_mode else probability * 0.6
        probe_id = f"{trigger}_{affordance.target_label or affordance.id}"[:60]
        probe_actuator: Dict[str, Any] = {
            "type": trigger,
            "confidence": round(confidence, 2),
        }
        first = (affordance.actuators or [{}])[0]
        if first.get("point"):
            probe_actuator["point"] = first["point"]
        may_reveal = [
            LatentAffordance(
                label=name,
                family="commit_irreversible"
                if is_irreversible_affordance(name)
                else "invoke_affordance",
                probability=round(probability, 2),
                basis="message-object interaction prior",
            )
            for name in reveals
        ]
        probes.append(
            Affordance(
                id=probe_id,
                family="reveal_actions" if trigger == "context_click" else "hover",
                status=STATUS_PROBE,
                target_id=affordance.target_id,
                target_label=affordance.target_label,
                available_now=True,
                actuators=[probe_actuator],
                confidence=round(confidence, 2),
                expected_information_gain=round(probability, 2),
                may_reveal=may_reveal,
                evidence=[Evidence(SOURCE_INTERACTION_PRIOR, f"{kind} -> {trigger}")],
                expected_outcomes=[
                    PredictedOutcome(
                        surface=surface,
                        probability=round(confidence, 2),
                        expected_information_gain=round(probability, 2),
                    )
                ]
                if surface
                else [],
            )
        )
        for latent in may_reveal:
            latents.append(
                Affordance(
                    id=f"{latent.label.lower()}_via_{trigger}",
                    family=latent.family,
                    status=STATUS_LATENT,
                    target_label=latent.label,
                    available_now=False,
                    trigger_action=probe_id,
                    confidence=round(confidence * latent.probability, 2),
                    reversible=latent.family != "commit_irreversible",
                    evidence=[Evidence(SOURCE_INTERACTION_PRIOR, latent.basis)],
                )
            )
    return probes, latents


def overlay_latents(overlay: Any, surface: str) -> List[Affordance]:
    """Latent actions an app adapter declares for the current surface.

    Duck-typed on purpose: an overlay that says nothing contributes nothing,
    and the core never learns WhatsApp's menu tree.
    """
    declare = getattr(overlay, "affordance_priors", None)
    if not callable(declare):
        return []
    try:
        raw = declare(surface) or []
    except Exception:
        return []
    out: List[Affordance] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        label = _clean(item.get("label"))
        family = _clean(item.get("family"), 40)
        if not label or not family:
            continue
        out.append(
            Affordance(
                id=_clean(item.get("id"), 60) or f"overlay_{label.lower()}",
                family=family,
                status=STATUS_LATENT,
                target_label=label,
                available_now=False,
                trigger_action=_clean(item.get("available_after"), 60) or None,
                confidence=float(item.get("probability") or 0.6),
                reversible=family != "commit_irreversible"
                and not is_irreversible_affordance(label),
                risk=0.4 if family == "commit_irreversible" else 0.05,
                evidence=[Evidence(SOURCE_OVERLAY_PRIOR, _clean(item.get("basis"), 80))],
            )
        )
    return out


# --- transition edges -------------------------------------------------------

# Coarse structural priors. Deliberately blunt: their job is to tell the model
# which move reaches which surface, not to pretend at calibrated probability.
_STRUCTURAL_EDGE_PROBABILITY = 0.7

# How strongly an action causes a new surface rather than merely being legal on
# one. The critic's opener sets are unordered because it only asks "could this
# explain the jump"; the frontier has to answer "what gets me there", so the
# strongest cause is offered and the rest are dropped as noise.
_CAUSAL_RANK: Tuple[str, ...] = (
    "invoke_affordance",
    "reveal_actions",
    "commit_irreversible",
    "open_entity",
    "open_contact",
    "compose_search_query",
    "open_search",
    "type_query",
    "locate_content",
    "select_content",
)
_MAX_OPENERS_PER_SURFACE = 2


def structural_edges(surface: str, goal_kind: str = "forward_message") -> List[TransitionEdge]:
    from plugin.agent.world_critic import ACTION_OPENS_SURFACE, SURFACE_PARENTS

    allowed = set(goal_profile(goal_kind))
    edges: List[TransitionEdge] = []
    for target_surface, openers in ACTION_OPENS_SURFACE.items():
        parents = SURFACE_PARENTS.get(target_surface, set())
        if surface and parents and surface not in parents:
            continue
        ranked = sorted(
            (o for o in openers if not allowed or o in allowed),
            key=lambda o: (_CAUSAL_RANK.index(o) if o in _CAUSAL_RANK else len(_CAUSAL_RANK), o),
        )
        for opener in ranked[:_MAX_OPENERS_PER_SURFACE]:
            edges.append(
                TransitionEdge(
                    from_action=opener,
                    to_surface=target_surface,
                    probability=_STRUCTURAL_EDGE_PROBABILITY,
                    enumeration_status="predicted",
                    basis="surface graph",
                )
            )
    return edges


class TransitionMemory:
    """What actually happened, per (surface, action) pair, in this process.

    Prediction is only useful if it can be corrected. Once the runtime has
    watched context_click on a conversation produce a context menu a few
    times, that observation should outrank the structural guess.
    """

    def __init__(self) -> None:
        self._counts: Dict[Tuple[str, str], Dict[str, int]] = {}

    def record(self, from_surface: str, family: str, to_surface: str) -> None:
        from_surface = _norm(from_surface)
        family = _norm(family)
        to_surface = _norm(to_surface)
        if not family or not to_surface:
            return
        bucket = self._counts.setdefault((from_surface, family), {})
        bucket[to_surface] = bucket.get(to_surface, 0) + 1

    def edges(self, surface: str) -> List[TransitionEdge]:
        surface = _norm(surface)
        out: List[TransitionEdge] = []
        for (from_surface, family), bucket in self._counts.items():
            if from_surface != surface:
                continue
            total = sum(bucket.values()) or 1
            for to_surface, count in sorted(bucket.items(), key=lambda kv: -kv[1]):
                out.append(
                    TransitionEdge(
                        from_action=family,
                        to_surface=to_surface,
                        probability=round(count / total, 2),
                        enumeration_status="observed",
                        basis=f"seen {count}/{total} times this session",
                    )
                )
        return out

    def to_dict(self) -> Dict[str, Dict[str, int]]:
        return {f"{s}|{f}": dict(b) for (s, f), b in self._counts.items()}


def memory_for(execution_state: Any) -> TransitionMemory:
    """The per-run transition memory, created on first use."""
    memory = getattr(execution_state, "transition_memory", None)
    if isinstance(memory, TransitionMemory):
        return memory
    memory = TransitionMemory()
    try:
        execution_state.transition_memory = memory
    except Exception:
        pass
    return memory


def merge_edges(
    observed: Sequence[TransitionEdge], predicted: Sequence[TransitionEdge]
) -> List[TransitionEdge]:
    """Observation replaces prediction for the same (action, surface) pair."""
    seen = {(e.from_action, e.to_surface) for e in observed}
    return list(observed) + [
        e for e in predicted if (e.from_action, e.to_surface) not in seen
    ]


# --- assembly ---------------------------------------------------------------


def _best_per_label(latents: Sequence[Affordance]) -> List[Affordance]:
    """One row per control, attributed to its most likely trigger.

    Hover and context-click predict overlapping menus, so listing Forward once
    per gesture would spend context restating the same expectation.
    """
    best: Dict[Tuple[str, str], Affordance] = {}
    for item in latents:
        key = (_norm(item.target_label), item.family)
        current = best.get(key)
        if current is None or float(item.confidence) > float(current.confidence):
            best[key] = item
    return sorted(best.values(), key=lambda a: -float(a.confidence))


def _provenance_from_grounded(match: Any) -> Tuple[str, str, str, str, str]:
    """Copy producer stamps from a reveal Action target — never invent space/time."""
    from plugin.perception.coordinate_frame import resolve_frame_id_for_space

    target = getattr(match, "target", None) or {}
    if not isinstance(target, dict):
        target = {}
    space = str(target.get("coordinate_space") or "").strip().lower()
    if space not in {"screen", "image"}:
        space = ""
    geo = str(target.get("geometry_source") or "").strip()[:40]
    owner = str(target.get("owner_surface") or target.get("surface") or "").strip()[:40]
    cid, raw_fid = _temporal_from_item(target)
    fid = ""
    if space:
        fid = resolve_frame_id_for_space(
            frame_id=raw_fid,
            coordinate_space=space,
            graph=None,
        )
    return space, geo, owner, cid, fid


def _actuators_from_grounded(match: Any) -> Tuple[List[Dict[str, Any]], Optional[int]]:
    target = getattr(match, "target", None) or {}
    if not isinstance(target, dict):
        target = {}
    point = target.get("point")
    entity_id = target.get("entity_id")
    actuators: List[Dict[str, Any]] = []
    if entity_id is not None:
        try:
            actuators.append(
                {"type": "ax_press", "target_id": int(entity_id), "confidence": 0.85}
            )
        except (TypeError, ValueError):
            entity_id = None
    if point:
        actuators.append(
            {"type": "coordinate_click", "point": list(point), "confidence": 0.9}
        )
    eid: Optional[int] = None
    if entity_id is not None:
        try:
            eid = int(entity_id)
        except (TypeError, ValueError):
            eid = None
    return actuators, eid


def ground_revealed(frontier: AffordanceFrontier, reveal_result: Any) -> AffordanceFrontier:
    """Close the frontier's loop: move latent actions a probe revealed to observed.

    ``reveal_actions`` is the arm that performs a probe and grounds the controls
    it exposes. This consumes its :class:`RevealResult`: any latent affordance
    whose label the reveal grounded becomes an observed action carrying the real
    target, so the executive can invoke it directly instead of re-deriving it.
    Grounded menu items that were not pre-listed as latents are also ingested
    as observed invoke_affordance entries (complete affordance_set thoroughness).
    """
    actions = list(getattr(reveal_result, "actions", []) or [])
    grounded = {
        _norm(a.label): a
        for a in actions
        if getattr(a, "is_grounded", False)
    }
    if not grounded:
        return frontier

    still_latent: List[Affordance] = []
    promoted: List[Affordance] = []
    for latent in frontier.latent_actions:
        match = grounded.get(_norm(latent.target_label))
        if match is None:
            still_latent.append(latent)
            continue
        actuators, eid = _actuators_from_grounded(match)
        if not actuators:
            still_latent.append(latent)
            continue
        space, geo, owner, cid, fid = _provenance_from_grounded(match)
        promoted.append(
            Affordance(
                id=f"revealed_{_norm(latent.target_label)}",
                family=latent.family,
                status=STATUS_OBSERVED,
                target_id=eid,
                target_label=latent.target_label,
                available_now=True,
                actuators=actuators,
                confidence=max(float(latent.confidence), float(getattr(match, "confidence", 0.0))),
                risk=latent.risk,
                reversible=latent.reversible,
                evidence=[Evidence(SOURCE_TRANSITION_MEMORY, "grounded by reveal_actions")],
                coordinate_space=space,
                geometry_source=geo,
                owner_surface=owner,
                capture_id=cid,
                frame_id=fid,
            )
        )
        grounded.pop(_norm(latent.target_label), None)
    # Menu items seen in perception but not pre-declared as latents still belong
    # in the affordance_set so invoke_affordance has complete geometry.
    observed_labels = {_norm(a.target_label) for a in frontier.observed_actions + promoted}
    for key, match in list(grounded.items()):
        if key in observed_labels:
            continue
        actuators, eid = _actuators_from_grounded(match)
        if not actuators:
            continue
        label = str(getattr(match, "label", "") or key)
        irreversible = is_irreversible_affordance(label)
        space, geo, owner, cid, fid = _provenance_from_grounded(match)
        promoted.append(
            Affordance(
                id=f"revealed_{key}",
                family="commit_irreversible" if irreversible else "invoke_affordance",
                status=STATUS_OBSERVED,
                target_id=eid,
                target_label=label,
                available_now=True,
                actuators=actuators,
                confidence=float(getattr(match, "confidence", 0.85) or 0.85),
                reversible=not irreversible,
                evidence=[Evidence(SOURCE_VISION_OBJECT, "menu item grounded after reveal")],
                coordinate_space=space,
                geometry_source=geo,
                owner_surface=owner,
                capture_id=cid,
                frame_id=fid,
            )
        )
    frontier.observed_actions = frontier.observed_actions + promoted
    frontier.latent_actions = still_latent
    # A successful reveal grounds the probed object's actions, so its topology
    # hole is filled: the object's actions are now observed, not merely
    # predicted, and the unknown frontier that asked for them is resolved.
    if promoted:
        frontier.unknown_frontiers = []
    return frontier


def publish_grounded_affordance_set(
    execution_state: Any, frontier: Optional[AffordanceFrontier]
) -> List[Dict[str, Any]]:
    """Persist *currently executable* grounded controls.

    Frontier / historical observed rows may retain stale capture provenance.
    This set means controls executable **now**, so publication requires:

    * actionable actuators
    * known coordinate_space (screen|image)
    * known current capture
    * affordance.capture_id == current capture
    * authoritative FrameGraph
    * frame_id that resolves for that coordinate_space

    Unknown freshness / missing graph → fail closed (empty executable set).
    Never invents or restamps coordinate_space / owner_surface / capture_id /
    frame_id onto older geometry.
    """
    from plugin.perception.coordinate_frame import resolve_frame_id_for_space

    out: List[Dict[str, Any]] = []
    if frontier is None:
        if execution_state is not None:
            try:
                execution_state.last_grounded_affordance_set = []
            except Exception:
                pass
        return out
    active_cid = ""
    graph = None
    if execution_state is not None:
        try:
            from plugin.agent.grounding_validity import resolve_active_frame_graph

            graph, _, active_cid = resolve_active_frame_graph(execution_state)
        except Exception:
            graph, active_cid = None, ""
    # Cannot establish "now" → nothing is currently executable.
    if not active_cid or graph is None:
        if execution_state is not None:
            try:
                execution_state.last_grounded_affordance_set = []
            except Exception:
                pass
        return out
    for aff in frontier.observed_actions:
        if aff.family not in {"invoke_affordance", "commit_irreversible"}:
            continue
        if not aff.actuators:
            continue
        row = aff.to_dict()
        space = str(row.get("coordinate_space") or "").strip().lower()
        if space not in {"screen", "image"}:
            # Unknown provenance stays ungrounded — publisher never invents space.
            continue
        row_cid = str(row.get("capture_id") or "").strip()
        # Preserve stale evidence in the frontier; do not expose it as executable.
        if not row_cid or row_cid != active_cid:
            continue
        row_fid = str(row.get("frame_id") or "").strip()
        if not row_fid:
            continue
        resolved = resolve_frame_id_for_space(
            frame_id=row_fid,
            coordinate_space=space,
            graph=graph,
        )
        # Fail closed: do not restamp expected frame into the published row.
        if resolved != row_fid:
            continue
        out.append(row)
    if execution_state is not None:
        try:
            execution_state.last_grounded_affordance_set = list(out)
            if out:
                handoff = getattr(execution_state, "reveal_handoff", None)
                if isinstance(handoff, dict):
                    # Discovery complete: overlay ingested into affordance_set.
                    execution_state.reveal_handoff = None
        except Exception:
            pass
    return out


def grounded_affordance_set_of(execution_state: Any) -> List[Dict[str, Any]]:
    raw = getattr(execution_state, "last_grounded_affordance_set", None) if execution_state else None
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    return []


def finalize_reveal_handoff(
    execution_state: Any, frontier: Optional[AffordanceFrontier]
) -> Dict[str, Any]:
    """After a post-reveal perceive: publish affordance_set or count a failed look.

    Returns a small status dict for logging/tests. Clears handoff on success;
    after ``ttl`` unsuccessful looks marks ``failed_reveal``.
    """
    status: Dict[str, Any] = {"active": False}
    if execution_state is None:
        return status
    handoff = getattr(execution_state, "reveal_handoff", None)
    if not isinstance(handoff, dict) or not str(handoff.get("surface") or "").strip():
        publish_grounded_affordance_set(execution_state, frontier)
        status["grounded"] = len(grounded_affordance_set_of(execution_state))
        return status
    status["active"] = True
    grounded = publish_grounded_affordance_set(execution_state, frontier)
    if grounded:
        status["complete"] = True
        status["grounded"] = len(grounded)
        try:
            from plugin.agent.executive.intention_frame import (
                IntentionStatus,
                TerminationReason,
                active_intention_frame,
                evaluate_intention_success,
                pop_intention_frame,
            )

            iframe = active_intention_frame(execution_state)
            if iframe is not None and evaluate_intention_success(
                iframe,
                affordance_stance=str(
                    getattr(execution_state, "last_affordance_stance", "") or ""
                ),
                grounded_forward=True,
            ):
                iframe.status = IntentionStatus.ACHIEVED.value
                iframe.termination_reason = TerminationReason.SUCCESS.value
                iframe.pending_effect_verification = False
                status["intention_achieved"] = iframe.intention.id
                pop_intention_frame(execution_state)
        except Exception:
            pass
        return status
    looks = int(handoff.get("looks") or 0) + 1
    ttl = int(handoff.get("ttl") or 2)
    handoff = dict(handoff)
    handoff["looks"] = looks
    if looks >= ttl:
        # Method settle window expired without grounded affordances → rotate
        # method under the same EXPLORE intention. Episode is terminal only
        # when the IntentionFrame has no eligible methods left (architect).
        try:
            from plugin.agent.capabilities.reveal_actions import escalate_failed_reveal

            step = getattr(execution_state, "last_plan_step", None)
            esc = escalate_failed_reveal(
                execution_state,
                target=str(
                    handoff.get("target")
                    or getattr(step, "semantic_target", "")
                    or ""
                ),
                point=(
                    handoff.get("target_point")
                    if handoff.get("target_point") is not None
                    else (getattr(step, "target_point", None) if step is not None else None)
                ),
                last_gesture=str(
                    handoff.get("probe_gesture")
                    or getattr(execution_state, "reveal_probe_mode", "")
                    or "context_click"
                ),
            )
            status["escalation"] = esc
            handoff["escalation"] = esc
        except Exception as exc:
            status["escalation_error"] = str(exc)[:120]

        locally_exhausted = False
        intention_status = ""
        try:
            from plugin.agent.executive.intention_frame import (
                IntentionStatus,
                active_intention_frame,
                apply_derived_status,
                is_local_route_exhausted,
            )

            iframe = active_intention_frame(execution_state)
            if iframe is not None:
                iframe.pending_effect_verification = False
                apply_derived_status(iframe)
                locally_exhausted = is_local_route_exhausted(iframe) or iframe.status in {
                    IntentionStatus.EXHAUSTED.value,
                    IntentionStatus.BLOCKED.value,
                }
                intention_status = str(iframe.status or "")
                status["intention_id"] = iframe.intention.id
                status["intention_status"] = intention_status
                status["eligible_methods"] = list(
                    iframe.method_frontier.eligible_methods()
                )
        except Exception:
            # Legacy: no frame → treat escalate prefs as still having methods
            # until prefer select_content has also been attempted.
            prefer = str(
                getattr(execution_state, "reveal_prefer_capability", "") or ""
            ).strip()
            mode = str(getattr(execution_state, "reveal_probe_mode", "") or "")
            locally_exhausted = prefer == "select_content" and mode == "select_content"

        status["looks"] = looks
        status["ttl"] = ttl
        status["grounded"] = 0
        if locally_exhausted:
            handoff["failed_reveal"] = True
            handoff["status"] = "failed_reveal"
            handoff["incomplete_reveal"] = False
            status["failed_reveal"] = True
            status["episode_terminal"] = True
            try:
                execution_state.reveal_handoff = {
                    "status": "failed_reveal",
                    "failed_reveal": True,
                    "incomplete_reveal": False,
                    "surface": str(handoff.get("surface") or ""),
                    "target": handoff.get("target"),
                    "target_point": handoff.get("target_point"),
                    "escalation": handoff.get("escalation"),
                    "looks": looks,
                    "ttl": ttl,
                    "intention_status": intention_status,
                }
            except Exception:
                pass
            return status

        # Methods remain: close this method's settle look, keep intention open.
        handoff["failed_reveal"] = False
        handoff["incomplete_reveal"] = False
        handoff["looks"] = 0
        handoff["status"] = "method_ineffective_advance"
        status["method_advance"] = True
        status["failed_reveal"] = False
        try:
            execution_state.reveal_handoff = handoff
        except Exception:
            pass
        return status
    else:
        status["pending"] = True
    try:
        execution_state.reveal_handoff = handoff
    except Exception:
        pass
    status["looks"] = looks
    status["ttl"] = ttl
    status["grounded"] = 0
    return status


def build_affordance_frontier(
    *,
    surface: str,
    goal_kind: str = "forward_message",
    ax_evidence: Optional[Sequence[Dict[str, Any]]] = None,
    objects: Optional[Sequence[Dict[str, Any]]] = None,
    overlay: Any = None,
    memory: Optional[TransitionMemory] = None,
    point_scale: float = 1.0,
    point_origin: Tuple[float, float] = (0.0, 0.0),
    capture_id: str = "",
    frame_graph: Any = None,
) -> AffordanceFrontier:
    """Assemble the frontier for the active surface and one action beyond it.

    Scope is the point of the signature: the current surface, what is on it,
    and what one interaction reaches. Shipping the whole application's action
    space is what produced the polluted graphs this replaces.

    ``capture_id`` / ``frame_graph`` are producer stamps for this observation.
    Frame IDs are derived per ``coordinate_space`` from the graph — never from
    a generic document ``frame_id``.
    """
    surface = _norm(surface)
    graph = _coerce_frame_graph(frame_graph)
    ax_actions, excluded = observed_from_ax(
        ax_evidence or (),
        goal_kind=goal_kind,
        capture_id=capture_id,
        frame_graph=graph,
    )
    object_actions = observed_from_objects(
        objects or (),
        goal_kind=goal_kind,
        point_scale=point_scale,
        point_origin=point_origin,
        frame_graph=graph,
    )
    observed = object_actions + ax_actions

    reveal_mode = _norm(getattr(overlay, "reveal_mode", "") or "context_click")
    probes: List[Affordance] = []
    latents: List[Affordance] = []
    unknown: List[UnknownFrontier] = []
    for affordance in observed:
        if affordance.family != "select_content":
            continue
        new_probes, new_latents = probes_for_object(affordance, reveal_mode=reveal_mode)
        probes.extend(new_probes)
        latents.extend(new_latents)
        # This object has actions we predict but have not observed: mark the
        # hole so the executive knows the topology past it is unexplored, not
        # empty. Resolved once a probe grounds the object's actions.
        if new_probes:
            unknown.append(
                UnknownFrontier(
                    object_id=str(affordance.target_id) if affordance.target_id is not None else affordance.id,
                    object_label=affordance.target_label,
                    question=f"which actions does {affordance.target_label or 'this object'!r} expose?",
                    suggested_probes=[p.family for p in new_probes],
                )
            )
        # One object's probes are enough to describe the mechanic; repeating
        # them per message is noise the transformer has to wade through.
        break
    latents.extend(overlay_latents(overlay, surface))

    edges = merge_edges(
        memory.edges(surface) if memory is not None else [],
        structural_edges(surface, goal_kind),
    )

    observed.sort(key=lambda a: -float(a.confidence))
    probes.sort(key=lambda a: -float(a.expected_information_gain))
    latents = _best_per_label(latents)
    return AffordanceFrontier(
        surface=surface,
        observed_actions=observed[:MAX_OBSERVED],
        latent_actions=latents[:MAX_LATENT],
        probe_actions=probes[:MAX_PROBE],
        known_transition_edges=edges[:MAX_EDGES],
        unknown_frontiers=unknown[:MAX_PROBE],
        excluded_actions=excluded[:MAX_EXCLUDED],
    )
