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
class AffordanceFrontier:
    surface: str = ""
    observed_actions: List[Affordance] = field(default_factory=list)
    latent_actions: List[Affordance] = field(default_factory=list)
    probe_actions: List[Affordance] = field(default_factory=list)
    known_transition_edges: List[TransitionEdge] = field(default_factory=list)
    excluded_actions: List[Dict[str, str]] = field(default_factory=list)

    def to_packet(self) -> Dict[str, Any]:
        return {
            "surface": self.surface,
            "observed_actions": [a.to_dict() for a in self.observed_actions[:MAX_OBSERVED]],
            "latent_actions": [a.to_dict() for a in self.latent_actions[:MAX_LATENT]],
            "probe_actions": [a.to_dict() for a in self.probe_actions[:MAX_PROBE]],
            "known_transition_edges": [
                e.to_dict() for e in self.known_transition_edges[:MAX_EDGES]
            ],
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


def _family_for(kind: str, role: str, label: str) -> str:
    if kind == "input":
        return "type_query"
    if kind == "button":
        return "commit_irreversible" if is_irreversible_affordance(label) else "invoke_affordance"
    if kind in {"row", "contact", "conversation", "chat"}:
        return "open_entity"
    if kind == "message":
        return "select_content"
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


def observed_from_ax(
    ax_evidence: Iterable[Dict[str, Any]],
    *,
    goal_kind: str = "forward_message",
) -> Tuple[List[Affordance], List[Dict[str, str]]]:
    """Turn AX evidence into affordances that are true right now."""
    found: List[Affordance] = []
    excluded: List[Dict[str, str]] = []
    for item in ax_evidence:
        if not isinstance(item, dict):
            continue
        label = _clean(item.get("label") or item.get("description"))
        role = str(item.get("role") or "")
        actions = [str(a) for a in (item.get("actions") or [])]
        kind = _kind_of(role, label, "")
        family = _family_for(kind, role, label)
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
            )
        )
    return found, excluded


def observed_from_objects(
    objects: Iterable[Dict[str, Any]],
    *,
    goal_kind: str = "forward_message",
    point_scale: float = 1.0,
) -> List[Affordance]:
    """Affordances on things only the model can see.

    WhatsApp publishes no AX content nodes for messages or chat rows, so
    without this the frontier would claim the only actionable things on a
    conversation are the window's chrome buttons.
    """
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
                point = (
                    int(float(raw_point[0]) * float(point_scale)),
                    int(float(raw_point[1]) * float(point_scale)),
                )
            except (TypeError, ValueError):
                point = None
        actuators = _actuators(None, point, ())
        if not actuators:
            continue
        found.append(
            Affordance(
                id=f"obj_{index}_{family}",
                family=family,
                status=STATUS_OBSERVED,
                target_label=text,
                actuators=actuators,
                confidence=0.75 if item.get("matches_goal") else 0.6,
                evidence=[Evidence(SOURCE_VISION_OBJECT, f"kind={kind}")],
                expected_outcomes=[
                    PredictedOutcome(
                        predicates={"target_object_selected": True}
                        if family == "select_content"
                        else {"conversation_open": True},
                        probability=0.8,
                    )
                ],
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


def ground_revealed(frontier: AffordanceFrontier, reveal_result: Any) -> AffordanceFrontier:
    """Close the frontier's loop: move latent actions a probe revealed to observed.

    ``reveal_actions`` is the arm that performs a probe and grounds the controls
    it exposes. This consumes its :class:`RevealResult`: any latent affordance
    whose label the reveal grounded becomes an observed action carrying the real
    target, so the executive can invoke it directly instead of re-deriving it.
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
        point = match.target.get("point")
        entity_id = match.target.get("entity_id")
        actuators: List[Dict[str, Any]] = []
        if entity_id is not None:
            actuators.append({"type": "ax_press", "target_id": int(entity_id), "confidence": 0.85})
        if point:
            actuators.append({"type": "coordinate_click", "point": list(point), "confidence": 0.9})
        promoted.append(
            Affordance(
                id=f"revealed_{_norm(latent.target_label)}",
                family=latent.family,
                status=STATUS_OBSERVED,
                target_id=int(entity_id) if entity_id is not None else None,
                target_label=latent.target_label,
                available_now=True,
                actuators=actuators,
                confidence=max(float(latent.confidence), float(getattr(match, "confidence", 0.0))),
                risk=latent.risk,
                reversible=latent.reversible,
                evidence=[Evidence(SOURCE_TRANSITION_MEMORY, "grounded by reveal_actions")],
            )
        )
    frontier.observed_actions = frontier.observed_actions + promoted
    frontier.latent_actions = still_latent
    return frontier


def build_affordance_frontier(
    *,
    surface: str,
    goal_kind: str = "forward_message",
    ax_evidence: Optional[Sequence[Dict[str, Any]]] = None,
    objects: Optional[Sequence[Dict[str, Any]]] = None,
    overlay: Any = None,
    memory: Optional[TransitionMemory] = None,
    point_scale: float = 1.0,
) -> AffordanceFrontier:
    """Assemble the frontier for the active surface and one action beyond it.

    Scope is the point of the signature: the current surface, what is on it,
    and what one interaction reaches. Shipping the whole application's action
    space is what produced the polluted graphs this replaces.
    """
    surface = _norm(surface)
    ax_actions, excluded = observed_from_ax(ax_evidence or (), goal_kind=goal_kind)
    object_actions = observed_from_objects(
        objects or (), goal_kind=goal_kind, point_scale=point_scale
    )
    observed = object_actions + ax_actions

    reveal_mode = _norm(getattr(overlay, "reveal_mode", "") or "context_click")
    probes: List[Affordance] = []
    latents: List[Affordance] = []
    for affordance in observed:
        if affordance.family != "select_content":
            continue
        new_probes, new_latents = probes_for_object(affordance, reveal_mode=reveal_mode)
        probes.extend(new_probes)
        latents.extend(new_latents)
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
        excluded_actions=excluded[:MAX_EXCLUDED],
    )
