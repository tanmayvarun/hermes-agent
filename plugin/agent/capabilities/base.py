"""Shared contract for general capabilities.

A capability is a named operation over a typed representation substrate, not a
host-specific click script. Perception arrives at the representation; the
capability executes general computation on it; the agent decides whether the
outcome is the right object or branch.

See docs/design/representation-capability-substrate.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


class CapabilityStatus(str, Enum):
    """How far a catalog entry has been built out."""

    REALIZED = "realized"  # at least one realization can run
    CONTRACT = "contract"  # named and documented; motor verbs still approximate it


class Substrate(str, Enum):
    """Thin views of the world document / host that capabilities consume."""

    SEARCHABLE_SURFACE = "searchable_surface"
    ADDRESSABLE_ENTITY = "addressable_entity"
    AFFORDANCE_SET = "affordance_set"
    TRANSIENT_CHROME = "transient_chrome"
    GATED_TARGET = "gated_target"
    # Goal cues + world document + prior search attempts — not a UI surface.
    TASK_EVIDENCE = "task_evidence"
    # Visible rows / contacts to disambiguate against a goal referent.
    CANDIDATE_SET = "candidate_set"
    # Recent forward-leg acts + world deltas for overloaded revert/rollback.
    EFFECT_TRACE = "effect_trace"


@dataclass(frozen=True)
class CapabilitySpec:
    """Catalog entry: the abstract contract, independent of any host app."""

    name: str
    substrate: Substrate
    # What the model may put in next_action.family / allowed_actions.
    verb: str
    description: str
    reversible: bool
    # Argument the model must supply (judgment). Empty means none required.
    required_arg: str = ""
    status: CapabilityStatus = CapabilityStatus.CONTRACT
    # Motor verbs that approximate this capability until it is realized.
    motor_approximation: tuple[str, ...] = ()
    # True when actuation writes to a named rectangle on screen. The brain→actor
    # handoff is illegal without a GroundedUiTarget (point and/or bounds).
    requires_geometry: bool = False


@dataclass(frozen=True)
class GroundedUiTarget:
    """Screen / image geometry for any capability that actuates the UI.

    The perceptor binds identity + geometry; the brain chooses *which*
    capability; the actor lands this rectangle. Without point or bounds the
    input contract is incomplete — the actor must refuse, not invent a site.
    """

    label: str = ""
    target_id: str = ""
    point: Optional[tuple[float, float]] = None
    bounds: Optional[tuple[float, float, float, float]] = None
    # "image" = window-relative model coords (need scale+origin).
    # "screen" = already in pointer/screen points (do not re-transform).
    coordinate_space: str = "image"
    geometry_source: str = ""

    def has_geometry(self) -> bool:
        return self.point is not None or self.bounds is not None

    def as_next_action_fields(self) -> Dict[str, Any]:
        """Fields the brain packs onto next_action for the actor."""
        out: Dict[str, Any] = {}
        if self.label:
            out["target_label"] = self.label
        if self.target_id:
            out["target_id"] = self.target_id
        if self.point is not None:
            out["target_point"] = [float(self.point[0]), float(self.point[1])]
        if self.bounds is not None:
            out["bounds"] = [float(x) for x in self.bounds[:4]]
        if self.coordinate_space:
            out["coordinate_space"] = self.coordinate_space
        if self.geometry_source:
            out["geometry_source"] = self.geometry_source
        return out


@dataclass
class CapabilityRequest:
    """What the agent asked a capability to do."""

    name: str
    app: str
    # Model-supplied judgment (query text, entity label, affordance name, …).
    arg: str = ""
    surface: str = ""
    extras: Dict[str, Any] = field(default_factory=dict)
    # Required when the capability's spec.requires_geometry is True.
    target: Optional[GroundedUiTarget] = None


@dataclass
class GroundedCapabilityRequest(CapabilityRequest):
    """Base request for the family of capabilities that actuate UI geometry.

    compose_search_query, type_query, open_entity, and peers inherit this
    contract: judgment args are free, the click/type site is not.
    """

    def __post_init__(self) -> None:
        if self.target is None:
            self.target = GroundedUiTarget()

    def assert_grounded(self) -> None:
        if self.target is None or not self.target.has_geometry():
            raise ValueError(
                f"{self.name} requires GroundedUiTarget geometry "
                "(point and/or bounds); got none"
            )


@dataclass
class CapabilityOutcome:
    """Evidence returned to the model after a capability runs.

    Outcomes report facts the runtime can know (reachable, exhausted, opened).
    They never claim task relevance — that judgment stays with the model.
    """

    ok: bool
    capability: str
    realization: str = ""
    message: str = ""
    evidence: Dict[str, Any] = field(default_factory=dict)

    def as_exec_message(self) -> str:
        flags = " ".join(f"{k}={v}" for k, v in self.evidence.items())
        body = f"{flags}; {self.message}" if flags else self.message
        return body.strip("; ").strip()


@runtime_checkable
class CapabilityHandler(Protocol):
    """One executable general capability."""

    spec: CapabilitySpec

    def available(self, request: CapabilityRequest, overlay: Any) -> bool:
        """Whether this host can run the capability right now."""

    def execute(self, request: CapabilityRequest, overlay: Any) -> CapabilityOutcome:
        """Run the capability; return evidence for the next model call."""


@dataclass(frozen=True)
class SearchableSurface:
    """Representation substrate for locate_content.

    Built from the open surface plus host declarations. The perceptor decides
    we are on a searchable body of content; the overlay declares how find works
    on this host. Neither invents the query.
    """

    app: str
    surface: str = ""
    find_declared: bool = False
    scoped_to_surface: bool = True


@dataclass(frozen=True)
class AddressableEntity:
    """Representation substrate for open_entity / reveal_actions.

    Perception (or AX resolution) names something that can be targeted. The
    capability opens or reveals it; it does not decide which entity matters.
    Geometry is a GroundedUiTarget — same contract as every other UI actuation.
    """

    app: str
    label: str = ""
    entity_id: Optional[int] = None
    point: Optional[tuple[float, float]] = None
    bounds: Optional[tuple[float, float, float, float]] = None
    coordinate_space: str = "screen"
    geometry_source: str = ""

    def grounded_target(self) -> GroundedUiTarget:
        return GroundedUiTarget(
            label=self.label,
            target_id=str(self.entity_id) if self.entity_id is not None else "",
            point=self.point,
            bounds=self.bounds,
            coordinate_space=self.coordinate_space,
            geometry_source=self.geometry_source,
        )


@dataclass(frozen=True)
class TransientChrome:
    """Representation substrate for dismiss_transient.

    Perception decided an overlay/menu is in the way. The capability clears it
    with the host's dismiss chord; it does not decide whether clearing was wise.
    """

    app: str
    surface: str = ""
