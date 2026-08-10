"""General capabilities: operations over representation substrates.

Perception arrives at the representation; capabilities execute general
computation on it. See docs/design/representation-capability-substrate.md.

Forward-oriented composition (model-chosen, not a bundled plan):

    compose_search_query → type_query → resolve_entity(source)
      → open_entity(chosen) → locate_content → select_content
      → reveal_actions → invoke_affordance(Forward)
      → resolve_entity(dest) → open_entity(chosen) → commit_irreversible(Send)
"""

from plugin.agent.capabilities.base import (
    AddressableEntity,
    CapabilityOutcome,
    CapabilityRequest,
    CapabilitySpec,
    CapabilityStatus,
    GroundedCapabilityRequest,
    GroundedUiTarget,
    SearchableSurface,
    Substrate,
    TransientChrome,
)
from plugin.agent.capabilities.action_area import (
    ActionArea,
    ActionAreaContract,
    contract_for,
    validate_actuation_grounding,
)
from plugin.agent.capabilities.catalog import (
    MOTOR_PRIMITIVES,
    all_specs,
    geometry_required_capabilities,
    model_allowed_actions,
    realized_verbs,
    spec_by_name,
)
from plugin.agent.capabilities.dispatch import can_dispatch, dispatch, dispatch_from_step

__all__ = [
    "ActionArea",
    "ActionAreaContract",
    "AddressableEntity",
    "CapabilityOutcome",
    "CapabilityRequest",
    "CapabilitySpec",
    "CapabilityStatus",
    "GroundedCapabilityRequest",
    "GroundedUiTarget",
    "MOTOR_PRIMITIVES",
    "SearchableSurface",
    "Substrate",
    "TransientChrome",
    "all_specs",
    "can_dispatch",
    "contract_for",
    "dispatch",
    "dispatch_from_step",
    "geometry_required_capabilities",
    "model_allowed_actions",
    "realized_verbs",
    "spec_by_name",
    "validate_actuation_grounding",
]
