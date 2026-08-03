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


@dataclass
class CapabilityRequest:
    """What the agent asked a capability to do."""

    name: str
    app: str
    # Model-supplied judgment (query text, entity label, affordance name, …).
    arg: str = ""
    surface: str = ""
    extras: Dict[str, Any] = field(default_factory=dict)


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
    """

    app: str
    label: str = ""
    entity_id: Optional[int] = None
    point: Optional[tuple[int, int]] = None
    bounds: Optional[tuple[float, float, float, float]] = None


@dataclass(frozen=True)
class TransientChrome:
    """Representation substrate for dismiss_transient.

    Perception decided an overlay/menu is in the way. The capability clears it
    with the host's dismiss chord; it does not decide whether clearing was wise.
    """

    app: str
    surface: str = ""
