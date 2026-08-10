"""The general capability catalog.

Entries are the verbs the agent can grow by realization, not by inventing
procedures. Motor primitives remain available separately; capabilities are
preferred when intent matches and a realization exists for the host.
"""

from __future__ import annotations

from typing import Dict, FrozenSet, List, Optional, Tuple

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
        name="search",
        verb="search",
        substrate=Substrate.CANDIDATE_SET,
        description=(
            "Legacy catalog name for find-among-many. The executive owns this as "
            "MetaAction.SEARCH; brain chooses stage verbs "
            "(compose_search_query / resolve_entity) under that meta. Not an "
            "ACT capability."
        ),
        reversible=True,
        required_arg="",
        status=CapabilityStatus.CONTRACT,
        motor_approximation=(),
        requires_geometry=False,
    ),
    CapabilitySpec(
        name="compose_search_query",
        verb="compose_search_query",
        substrate=Substrate.TASK_EVIDENCE,
        description=(
            "Search stage: author a search-box query from goal evidence, world "
            "document, and prior attempts, then type it into the perceived "
            "search field. Does not complete search — ranking/resolve follows. "
            "Requires GroundedUiTarget geometry for that field."
        ),
        reversible=True,
        required_arg="",
        status=CapabilityStatus.REALIZED,
        motor_approximation=("type",),
        requires_geometry=True,
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
        requires_geometry=True,
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
        requires_geometry=True,
    ),
    CapabilitySpec(
        name="resolve_entity",
        verb="resolve_entity",
        substrate=Substrate.CANDIDATE_SET,
        description=(
            "Choose which visible candidate matches a goal referent "
            "(destination/source/…). Semantic resolution over a candidate_set; "
            "runtime turns the choice into a click, so geometry is required."
        ),
        reversible=True,
        required_arg="",
        status=CapabilityStatus.REALIZED,
        motor_approximation=("click",),
        requires_geometry=True,
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
        requires_geometry=True,
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
        requires_geometry=True,
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
        requires_geometry=True,
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
        requires_geometry=False,
    ),
    CapabilitySpec(
        name="revert_effects",
        verb="revert_effects",
        substrate=Substrate.EFFECT_TRACE,
        description=(
            "Backtrack / revert / rollback (same graph concept): analyze the "
            "forward leg + world, propose a plan, approve, then execute host "
            "realizations. Clears wrong branches — multi-select, Videos/Photos "
            "search filter, overlays — or undoes send/copy/edit via contracted "
            "realizations. Aliases: backtrack, revert, rollback."
        ),
        reversible=True,
        required_arg="",
        status=CapabilityStatus.REALIZED,
        motor_approximation=("press_escape",),
        requires_geometry=False,
    ),
    CapabilitySpec(
        name="relieve_host_storage",
        verb="relieve_host_storage",
        substrate=Substrate.TASK_EVIDENCE,
        description=(
            "Relieve host/app storage pressure by cleaning low-importance "
            "disposable destinations first and stopping once decent free-space "
            "headroom is available so the goal can resume."
        ),
        reversible=True,
        required_arg="",
        status=CapabilityStatus.REALIZED,
        motor_approximation=(),
        requires_geometry=False,
    ),
    CapabilitySpec(
        name="recover_blocked_app",
        verb="recover_blocked_app",
        substrate=Substrate.TRANSIENT_CHROME,
        description=(
            "Recover a blocked app UI (e.g. Exit CTA on a storage-full dialog) "
            "and relaunch/activate so the task surface is usable again."
        ),
        reversible=True,
        required_arg="",
        status=CapabilityStatus.REALIZED,
        motor_approximation=("click",),
        requires_geometry=False,
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
        requires_geometry=True,
    ),
)

# Motor/family names used beside the catalog that still actuate a UI rectangle.
_EXTRA_GEOMETRY_FAMILIES: Tuple[str, ...] = ("type_query", "open_search")


def geometry_required_capabilities() -> FrozenSet[str]:
    """Names of every capability/family whose actor brief needs geometry."""
    names = {s.name for s in _CATALOG if s.requires_geometry}
    names.update(_EXTRA_GEOMETRY_FAMILIES)
    return frozenset(names)


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
