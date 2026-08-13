"""Action — one executable decision (no multi-step plan)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Action:
    """Exactly one next action from DecisionEngine."""

    action: str  # Click | Hover | ContextClick | Type | Observe | Dismiss | Press
    semantic_target: str = ""
    text: str = ""
    rationale: str = ""
    expected_predicate: str = ""  # logging / evidence only — not a control gate
    action_family: str = (
        ""  # type_query | open_contact | start_call | dismiss | end_call | observe | open_search | probe_hover | probe_context_menu | probe_focus
    )
    score: float = 0.0
    prior_score: float = 0.0
    value_delta: float = 0.0
    evidence_score: float = 0.0
    scroll_direction: str = ""
    scroll_amount: int = 0
    # Bound to world version when chosen; stale targets must be re-resolved
    observed_in_world: str = ""
    target_entity_id: int | None = None
    # A model-supplied screen point (x, y) for actions grounded on pixels rather
    # than an AX entity. The runtime turns it into a small clickable box so the
    # point survives to the mouse instead of being lost when no entity resolves.
    target_point: tuple[float, float] | None = None
    capability_id: str = ""
    capability_type: str = ""
    reversible: bool = True
    grounding_reason: str = ""
    grounding_confidence: float = 0.0
    frontier_label: str = ""
    frontier_score: float = 0.0
    prediction: dict = field(default_factory=dict)
    # Navigation / role-effect semantics (survive decision → execution).
    target_kind: str = ""
    establishes_roles: list = field(default_factory=list)
    action_is_navigation: bool = False
    # Immutable attempt identity for effect verification (not ambient runtime).
    attempt_id: str = ""
    # True when open semantics were reconstructed without authoritative typing.
    # Legacy opens must not use the typed navigation establish/bypass path.
    legacy_semantics: bool = False
    # locate_content MethodFrontier preference (native_find / scroll_scan).
    prefer_realization: str = ""
    # Typed navigation: required container after settle (content hit ≠ container).
    expected_container: str = ""


# Backward-compatible alias for one release
PlanStep = Action
