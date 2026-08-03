"""The general capability catalog.

Entries are the verbs the agent can grow by realization, not by inventing
procedures. Motor primitives remain available separately; capabilities are
preferred when intent matches and a realization exists for the host.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from plugin.agent.capabilities.base import CapabilitySpec, CapabilityStatus, Substrate

# Motor primitives stay outside the catalog. They are muscle movements; the
# catalog names operations over representations.
MOTOR_PRIMITIVES: Tuple[str, ...] = (
    "click",
    "right_click",
    "hover",
    "type",
    "scroll",
    "press_escape",
    "observe",
    "request_more_evidence",
)

_CATALOG: Tuple[CapabilitySpec, ...] = (
    CapabilitySpec(
        name="compose_search_query",
        verb="compose_search_query",
        substrate=Substrate.TASK_EVIDENCE,
        description=(
            "Author a search-box query from goal evidence, world document, and "
            "prior search attempts. Does not type. Does not hardcode a query "
            "template — judgment chooses how to combine evidence tokens."
        ),
        reversible=True,
        required_arg="",
        status=CapabilityStatus.REALIZED,
        motor_approximation=("type",),
    ),
    CapabilitySpec(
        name="locate_content",
        verb="locate_content",
        substrate=Substrate.SEARCHABLE_SURFACE,
        description=(
            "Make content matching a query reachable on the current surface, "
            "or report that the surface is exhausted. Does not claim relevance."
        ),
        reversible=True,
        required_arg="text",
        status=CapabilityStatus.REALIZED,
        motor_approximation=("scroll",),
    ),
    CapabilitySpec(
        name="open_entity",
        verb="open_entity",
        substrate=Substrate.ADDRESSABLE_ENTITY,
        description="Navigate into a named entity (conversation, channel, thread).",
        reversible=True,
        required_arg="target",
        status=CapabilityStatus.REALIZED,
        motor_approximation=("click",),
    ),
    CapabilitySpec(
        name="resolve_entity",
        verb="resolve_entity",
        substrate=Substrate.CANDIDATE_SET,
        description=(
            "Choose which visible candidate matches a goal referent "
            "(destination/source/…). Semantic resolution over a candidate_set; "
            "does not click. Self markers like (you) are evidence, not a template."
        ),
        reversible=True,
        required_arg="",
        status=CapabilityStatus.REALIZED,
        motor_approximation=("click",),
    ),
    CapabilitySpec(
        name="select_content",
        verb="select_content",
        substrate=Substrate.ADDRESSABLE_ENTITY,
        description=(
            "Focus a content object inside an open surface (message, row, link) "
            "without navigating away."
        ),
        reversible=True,
        required_arg="target",
        status=CapabilityStatus.REALIZED,
        motor_approximation=("click",),
    ),
    CapabilitySpec(
        name="reveal_actions",
        verb="reveal_actions",
        substrate=Substrate.ADDRESSABLE_ENTITY,
        description="Expose the affordance set for an entity without committing.",
        reversible=True,
        required_arg="target",
        status=CapabilityStatus.REALIZED,
        motor_approximation=("hover", "right_click"),
    ),
    CapabilitySpec(
        name="invoke_affordance",
        verb="invoke_affordance",
        substrate=Substrate.AFFORDANCE_SET,
        description="Activate a named reversible affordance on a bound entity.",
        reversible=True,
        required_arg="text",
        status=CapabilityStatus.REALIZED,
        motor_approximation=("click",),
    ),
    CapabilitySpec(
        name="dismiss_transient",
        verb="dismiss_transient",
        substrate=Substrate.TRANSIENT_CHROME,
        description="Clear an overlay or menu that is not the task.",
        reversible=True,
        required_arg="",
        status=CapabilityStatus.REALIZED,
        motor_approximation=("press_escape",),
    ),
    CapabilitySpec(
        name="commit_irreversible",
        verb="commit_irreversible",
        substrate=Substrate.GATED_TARGET,
        description=(
            "Send, delete, or confirm. Always a gated primitive; never bundled "
            "inside another capability."
        ),
        reversible=False,
        required_arg="text",
        status=CapabilityStatus.REALIZED,
        motor_approximation=("click",),
    ),
)


def all_specs() -> Tuple[CapabilitySpec, ...]:
    return _CATALOG


def spec_by_name(name: str) -> Optional[CapabilitySpec]:
    key = str(name or "").strip().lower()
    for spec in _CATALOG:
        if spec.name == key or spec.verb == key:
            return spec
    return None


def realized_specs() -> List[CapabilitySpec]:
    return [s for s in _CATALOG if s.status == CapabilityStatus.REALIZED]


def realized_verbs() -> Tuple[str, ...]:
    return tuple(s.verb for s in realized_specs())


def model_allowed_actions() -> Tuple[str, ...]:
    """Vocabulary offered to the multimodal model.

    Motor primitives plus every *realized* capability. Contract-only entries
    stay out of the packet so the model cannot name a verb the runtime cannot
    execute; they grow into the vocabulary when a realization lands.
    """
    return MOTOR_PRIMITIVES + realized_verbs()


def catalog_index() -> Dict[str, CapabilitySpec]:
    return {s.name: s for s in _CATALOG}
