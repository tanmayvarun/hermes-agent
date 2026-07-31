"""Stage 5–7 — generic region-conditioned affordances + goal attention.

No app-specific vocabulary. Uses region kinds, entity actions/roles, and
coarse goal-kind tokens (call / message / search / …) only.
"""

from __future__ import annotations

import math
import re
from typing import Dict, List, Optional, Sequence, Set, Tuple

from plugin.agent.goal import Goal
from plugin.worldmodel.entities.entity import Entity
from plugin.worldmodel.entities.normalize import _clean_label
from plugin.worldmodel.scene.reconstruct import (
    region_id_for_entity,
    region_ids_for_entity,
    region_kind_for_entity,
    region_kinds_for_entity,
)
from plugin.worldmodel.scene.types import (
    AffordanceDistribution,
    AffordanceHypothesis,
    AttentionSubgraph,
    RegionKind,
    WorldGraph,
)

# Region → capability families (generic UI, not product names)
_REGION_CAPABILITIES: Dict[RegionKind, Tuple[str, ...]] = {
    RegionKind.COMPOSER: ("compose_text", "attach_media", "send_message"),
    RegionKind.FLOATING_MENU: ("choose_option", "initiate_session"),
    RegionKind.MODAL: ("choose_option", "confirm", "dismiss"),
    RegionKind.HEADER: ("navigate", "open_menu", "initiate_session"),
    RegionKind.SIDEBAR: ("select_item", "navigate", "search"),
    RegionKind.TIMELINE: ("select_item", "scroll_content"),
    RegionKind.TOOLBAR: ("navigate", "open_menu"),
    RegionKind.NAVIGATION: ("navigate",),
    RegionKind.STATUS_BAR: ("status_read",),
    RegionKind.CONVERSATION: ("navigate",),
    RegionKind.UNKNOWN: ("unknown",),
}

# Goal-kind token → preferred region kinds (order = attention priority)
_GOAL_REGION_PRIORITIES: List[Tuple[re.Pattern[str], Tuple[RegionKind, ...]]] = [
    (
        re.compile(r"call|voice_call|video_call|phone|ring", re.I),
        (
            RegionKind.FLOATING_MENU,
            RegionKind.MODAL,
            RegionKind.HEADER,
            RegionKind.TOOLBAR,
        ),
    ),
    (
        re.compile(r"message|chat|compose|send|reply|mail", re.I),
        (RegionKind.COMPOSER, RegionKind.TIMELINE, RegionKind.HEADER),
    ),
    (
        re.compile(r"search|find|lookup", re.I),
        (RegionKind.SIDEBAR, RegionKind.HEADER, RegionKind.TOOLBAR),
    ),
    (
        re.compile(r"settings|pref|config", re.I),
        (RegionKind.NAVIGATION, RegionKind.SIDEBAR, RegionKind.MODAL),
    ),
]


def preferred_regions_for_goal(goal_kind: str) -> Tuple[RegionKind, ...]:
    kind = goal_kind or ""
    for pat, regions in _GOAL_REGION_PRIORITIES:
        if pat.search(kind):
            return regions
    # Default: menus/header before composer (safer than external side effects)
    return (
        RegionKind.FLOATING_MENU,
        RegionKind.MODAL,
        RegionKind.HEADER,
        RegionKind.SIDEBAR,
        RegionKind.COMPOSER,
        RegionKind.TIMELINE,
    )


def _entity_by_id(entities: Sequence[Entity]) -> Dict[int, Entity]:
    return {e.id: e for e in entities}


def _tokens(text: str) -> Set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", (text or "").lower()) if len(t) >= 2}


def _entropy(ps: Sequence[float]) -> float:
    total = sum(max(0.0, p) for p in ps)
    if total <= 1e-9:
        return 1.0
    h = 0.0
    for p in ps:
        q = max(0.0, p) / total
        if q > 1e-12:
            h -= q * math.log(q + 1e-12)
    # Normalize by log(|support|) rough upper bound
    return float(min(1.0, h / max(1e-9, math.log(max(2, len(ps))))))


def build_affordance_distribution(
    graph: WorldGraph,
    entities: Sequence[Entity],
) -> AffordanceDistribution:
    """Stage 5–7: P(capability | entity, region) without app labels."""
    by_entity: Dict[int, List[AffordanceHypothesis]] = {}

    for e in entities:
        if not e.visible:
            continue
        region_ids = region_ids_for_entity(graph, e.id)
        region_kinds = region_kinds_for_entity(graph, e.id)
        if not region_kinds:
            by_entity[e.id] = [
                AffordanceHypothesis(
                    id="unknown",
                    p=1.0,
                    region_id=None,
                    entity_id=e.id,
                    evidence={"reason": "no_region"},
                )
            ]
            continue

        hyps: List[AffordanceHypothesis] = []
        for idx, kind in enumerate(region_kinds[:3]):
            rid = region_ids[idx] if idx < len(region_ids) else region_ids[0]
            caps = list(_REGION_CAPABILITIES.get(kind, ("unknown",)))
            # Interactive controls in composer: demote initiate_session hard
            weights = {c: 1.0 / len(caps) for c in caps}
            if kind is RegionKind.COMPOSER:
                for c in caps:
                    if c == "initiate_session":
                        weights[c] = 0.02
                    elif c in {"send_message", "attach_media", "compose_text"}:
                        weights[c] = 0.9 / max(1, len(caps) - 1)
            if kind is RegionKind.FLOATING_MENU:
                for c in caps:
                    if c == "initiate_session":
                        weights[c] = 0.55
                    elif c == "choose_option":
                        weights[c] = 0.45
            if kind is RegionKind.HEADER and "click" in (e.actions or ["click"]):
                weights["initiate_session"] = max(weights.get("initiate_session", 0.2), 0.35)
            if kind is RegionKind.SIDEBAR:
                for c in caps:
                    if c == "search":
                        weights[c] = max(weights.get(c, 0.25), 0.4)
            if kind is RegionKind.TIMELINE and _is_clickable(e):
                for c in caps:
                    if c == "select_item":
                        weights[c] = max(weights.get(c, 0.33), 0.55)

            # Region-membership-specific hypotheses stay separate so downstream
            # layers can keep alternate surfaces alive.
            hyps.extend(
                AffordanceHypothesis(
                    id=cap,
                    p=round(float(weights.get(cap, 0.0)), 4),
                    region_id=rid,
                    entity_id=e.id,
                    evidence={
                        "region_kind": kind.value,
                        "region_id": rid,
                        "entity_type": e.entity_type,
                    },
                )
                for cap in caps
            )

        # Latent reveal affordances: some rows/cards only disclose actions on hover,
        # focus, or context menu. Keep them as low-probability hypotheses so the
        # controller can probe instead of thrashing Observe.
        if any(_looks_like_probe_target(e, kind) for kind in region_kinds[:3]):
            latent_weight = 0.16 if kind in {RegionKind.TIMELINE, RegionKind.CONVERSATION} else 0.12
            hyps.extend(
                [
                    AffordanceHypothesis(
                        id="probe_hover",
                        p=latent_weight,
                        region_id=rid,
                        entity_id=e.id,
                        evidence={
                            "region_kind": kind.value,
                            "region_id": rid,
                            "entity_type": e.entity_type,
                            "latent": True,
                            "probe": "hover",
                        },
                    ),
                    AffordanceHypothesis(
                        id="probe_context_menu",
                        p=max(0.08, latent_weight - 0.04),
                        region_id=rid,
                        entity_id=e.id,
                        evidence={
                            "region_kind": kind.value,
                            "region_id": rid,
                            "entity_type": e.entity_type,
                            "latent": True,
                            "probe": "context_menu",
                        },
                    ),
                ]
            )
        by_entity[e.id] = hyps

    return AffordanceDistribution(by_entity=by_entity)


def build_attention_subgraph(
    graph: WorldGraph,
    goal: Goal,
    entities: Sequence[Entity],
) -> AttentionSubgraph:
    """Stage 6: goal → preferred regions present on screen → entity set."""
    preferred = preferred_regions_for_goal(goal.kind)
    present_kinds = {r.kind for r in graph.regions}
    chosen_kinds: List[RegionKind] = [k for k in preferred if k in present_kinds]
    if not chosen_kinds:
        # Fall back to any non-unknown region
        chosen_kinds = [r.kind for r in graph.regions if r.kind != RegionKind.UNKNOWN][:3]

    region_ids = [r.id for r in graph.regions if r.kind in chosen_kinds]
    entity_ids: List[int] = []
    for r in graph.regions:
        if r.id in region_ids:
            entity_ids.extend(r.entity_ids)

    # Soft lexical pull: entities whose labels overlap goal contact tokens,
    # but only if already in a preferred region (does not resurrect composer mic).
    contact_toks = _tokens(goal.contact or "")
    if contact_toks:
        by_id = _entity_by_id(entities)
        for eid in list(entity_ids):
            e = by_id.get(eid)
            if e is None:
                continue
            if _tokens(f"{e.label} {e.semantic_role}") & contact_toks:
                pass  # already included
        for e in entities:
            if not e.visible or e.id in entity_ids:
                continue
            if not set(region_kinds_for_entity(graph, e.id)) & set(chosen_kinds):
                continue
            if _tokens(f"{e.label} {e.semantic_role}") & contact_toks:
                entity_ids.append(e.id)

    # Residual: fraction of interactive entities outside attention
    interactive = [e for e in entities if e.visible and _is_clickable(e)]
    outside = sum(1 for e in interactive if e.id not in set(entity_ids))
    residual = outside / max(1, len(interactive))

    return AttentionSubgraph(
        region_ids=region_ids,
        entity_ids=sorted(set(entity_ids)),
        goal_kind=goal.kind,
        residual_mass=round(residual, 4),
    )


def _is_clickable(e: Entity) -> bool:
    if e.entity_type == "button":
        return True
    if "click" in (e.actions or []):
        return True
    return "button" in (e.role or "").lower()


def _looks_like_probe_target(e: Entity, kind: RegionKind) -> bool:
    if not e.visible:
        return False
    if kind not in {
        RegionKind.TIMELINE,
        RegionKind.CONVERSATION,
        RegionKind.SIDEBAR,
        RegionKind.HEADER,
        RegionKind.TOOLBAR,
    }:
        return False
    if not _is_clickable(e):
        return False
    blob = _tokens(f"{e.label} {e.semantic_role}")
    if not blob:
        return False
    if {"search", "call", "menu", "settings", "compose", "send"} & blob:
        return False
    return True


def enrich_world_graph(
    graph: WorldGraph,
    entities: Sequence[Entity],
    goal: Optional[Goal] = None,
) -> WorldGraph:
    """Fill affordances + optional attention; update report entropy."""
    graph.affordances = build_affordance_distribution(graph, entities)
    all_ps: List[float] = []
    for hyps in graph.affordances.by_entity.values():
        all_ps.extend(h.p for h in hyps)
    graph.report.affordance_entropy = round(_entropy(all_ps) if all_ps else 1.0, 4)

    if goal is not None:
        graph.attention = build_attention_subgraph(graph, goal, entities)
    return graph


def attention_score_delta(
    graph: WorldGraph,
    *,
    semantic_target: str,
    entities: Sequence[Entity],
) -> float:
    """
    Generic decision bias from scene attention.

    Positive when target resolves inside the attention subgraph.
    Strong negative when a lexical peer exists inside attention but this
    target resolves outside (classic same-label / different-region trap).
    """
    if graph.attention is None or not graph.attention.entity_ids:
        return 0.0
    attended = set(graph.attention.entity_ids)
    target = _clean_label(semantic_target or "").lower()
    if not target:
        return 0.0

    matches = [
        e
        for e in entities
        if e.visible
        and target in _clean_label(f"{e.label} {e.semantic_role}").lower()
    ]
    if not matches:
        # Fuzzy: token overlap
        ttoks = _tokens(target)
        matches = [
            e
            for e in entities
            if e.visible and (ttoks & _tokens(f"{e.label} {e.semantic_role}"))
        ]
    if not matches:
        return 0.0

    inside = [e for e in matches if e.id in attended]
    outside = [e for e in matches if e.id not in attended]

    # Prefer matches whose dominant affordance aligns with attended regions
    if inside and not outside:
        return 0.22
    if inside and outside:
        # Target may match both a short control and a longer sibling label
        # (e.g. "Save" vs "Save draft") across regions — prefer attended exact.
        exact_inside = [
            e for e in inside if _clean_label(e.label or "").lower() == target
        ]
        exact_outside = [
            e for e in outside if _clean_label(e.label or "").lower() == target
        ]
        if exact_inside:
            return 0.28
        if exact_outside and not exact_inside:
            return -0.55
        # Prefix collision: shorter label inside vs longer outside
        return 0.2
    if outside and not inside:
        # No attended peer with this label — mild penalty if region is deprioritized
        kinds = region_kinds_for_entity(graph, outside[0].id)
        preferred = preferred_regions_for_goal(graph.attention.goal_kind)
        if kinds and all(kind not in preferred[:3] for kind in kinds):
            return -0.4
        return -0.15
    return 0.0
