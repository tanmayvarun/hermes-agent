"""Stage 3+4 — generic geometry/AX layout reconstruction + contains graph.

App-agnostic: region kinds come from spatial structure (bands, density, clusters),
not product-specific labels or screens. Optional weak AX *role* cues only
(textfield vs button), never app vocabulary.
"""

from __future__ import annotations

import math
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from plugin.worldmodel.entities.entity import Entity
from plugin.worldmodel.scene.types import (
    ContextGraph,
    EdgeKind,
    RegionKind,
    RegionMembership,
    SceneEdge,
    SceneNodeRef,
    SceneUnderstandingReport,
    SemanticRegion,
    WorldGraph,
)

Bounds = Tuple[float, float, float, float]

# Tunables — fractions of the observed entity extent (not pixels of a named app).
_SIDEBAR_X_FRAC = 0.32
_HEADER_Y_FRAC = 0.14
_COMPOSER_Y_FRAC = 0.28  # bottom band
_CLUSTER_RADIUS = 160.0
_CLUSTER_MIN_SIZE = 2
_SMALL_CONTROL_MAX_AREA_FRAC = 0.04  # vs window area


def _valid_bounds(b: Bounds) -> bool:
    return len(b) >= 4 and float(b[2]) > 4 and float(b[3]) > 4


def _center(b: Bounds) -> Tuple[float, float]:
    return float(b[0]) + float(b[2]) / 2.0, float(b[1]) + float(b[3]) / 2.0


def _area(b: Bounds) -> float:
    return max(0.0, float(b[2])) * max(0.0, float(b[3]))


def _union(bounds_list: Sequence[Bounds]) -> Bounds:
    if not bounds_list:
        return (0.0, 0.0, 0.0, 0.0)
    xs = [b[0] for b in bounds_list]
    ys = [b[1] for b in bounds_list]
    rights = [b[0] + b[2] for b in bounds_list]
    bottoms = [b[1] + b[3] for b in bounds_list]
    x0, y0 = min(xs), min(ys)
    return (x0, y0, max(rights) - x0, max(bottoms) - y0)


def _inflate(b: Bounds, pad_x: float, pad_y: float) -> Bounds:
    return (b[0] - pad_x, b[1] - pad_y, b[2] + 2 * pad_x, b[3] + 2 * pad_y)


def _intersection_area(a: Bounds, b: Bounds) -> float:
    ax0, ay0, aw, ah = a
    bx0, by0, bw, bh = b
    ax1, ay1 = ax0 + aw, ay0 + ah
    bx1, by1 = bx0 + bw, by0 + bh
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    return (ix1 - ix0) * (iy1 - iy0)


def _point_in_bounds(x: float, y: float, b: Bounds) -> bool:
    return b[0] <= x <= b[0] + b[2] and b[1] <= y <= b[1] + b[3]


def _membership_confidence(entity: Entity, region_bounds: Bounds, region_kind: RegionKind) -> float:
    """Geometric confidence that an entity participates in a region.

    This intentionally produces overlapping memberships instead of a single
    winner. The dominant region is still chosen later, but downstream layers now
    get the full candidate set.
    """
    eb = tuple(entity.bounds)  # type: ignore[arg-type]
    ea = max(1.0, _area(eb))
    overlap = _intersection_area(eb, region_bounds)
    if overlap <= 0.0:
        # Allow near-misses for the parts of the UI that often sit just outside
        # a padded region boundary (e.g. header controls).
        ex, ey = _center(eb)
        rx, ry, rw, rh = region_bounds
        pad_x = max(16.0, 0.08 * rw)
        pad_y = max(16.0, 0.08 * rh)
        padded = (rx - pad_x, ry - pad_y, rw + 2 * pad_x, rh + 2 * pad_y)
        if not _point_in_bounds(ex, ey, padded):
            return 0.0
        # Near-miss inside padded region.
        base = 0.18
    else:
        overlap_ratio = min(1.0, overlap / ea)
        base = 0.25 + 0.6 * overlap_ratio
        if overlap_ratio > 0.85:
            base += 0.1

    # Region-specific boost for likely containment bands.
    if region_kind in {RegionKind.COMPOSER, RegionKind.HEADER, RegionKind.SIDEBAR, RegionKind.NAVIGATION}:
        base += 0.05
    if region_kind in {RegionKind.FLOATING_MENU, RegionKind.MODAL}:
        base += 0.08
    if _is_interactive(entity):
        base += 0.03
    return max(0.0, min(0.95, base))


def _visible_entities(entities: Sequence[Entity]) -> List[Entity]:
    out: List[Entity] = []
    for e in entities:
        if not e.visible:
            continue
        if e.entity_type in {"group", "scroll", "window"}:
            continue
        if not _valid_bounds(tuple(e.bounds)):  # type: ignore[arg-type]
            continue
        out.append(e)
    return out


def _is_text_input(e: Entity) -> bool:
    if e.entity_type == "textfield":
        return True
    role = (e.role or "").lower()
    return "textfield" in role or "textarea" in role or "searchfield" in role


def _is_interactive(e: Entity) -> bool:
    if e.entity_type in {"button", "textfield"}:
        return True
    if e.actions:
        return True
    role = (e.role or "").lower()
    return any(k in role for k in ("button", "link", "menuitem", "checkbox", "popup"))


def _cluster_interactive(
    ents: Sequence[Entity],
    *,
    radius: float,
    min_size: int,
    max_member_area: float,
) -> List[List[Entity]]:
    """Greedy spatial clusters of small interactive controls (menus / popovers)."""
    candidates = [
        e
        for e in ents
        if _is_interactive(e)
        and e.entity_type != "textfield"
        and _area(tuple(e.bounds)) <= max_member_area  # type: ignore[arg-type]
    ]
    unused = set(range(len(candidates)))
    clusters: List[List[Entity]] = []
    while unused:
        seed = min(unused)
        unused.remove(seed)
        cluster_idx = [seed]
        changed = True
        while changed:
            changed = False
            centers = [_center(tuple(candidates[i].bounds)) for i in cluster_idx]  # type: ignore[misc]
            mx = sum(c[0] for c in centers) / len(centers)
            my = sum(c[1] for c in centers) / len(centers)
            for j in list(unused):
                cx, cy = _center(tuple(candidates[j].bounds))  # type: ignore[arg-type]
                if math.hypot(cx - mx, cy - my) <= radius:
                    unused.remove(j)
                    cluster_idx.append(j)
                    changed = True
        if len(cluster_idx) >= min_size:
            clusters.append([candidates[i] for i in cluster_idx])
    # Prefer compact clusters (menu-like) over sprawling toolbars
    def _compactness(cl: List[Entity]) -> float:
        bb = _union([tuple(e.bounds) for e in cl])  # type: ignore[misc]
        return _area(bb) / max(1.0, len(cl))

    clusters.sort(key=_compactness)
    return clusters


def reconstruct_world_graph(
    entities: Sequence[Entity],
    *,
    app: str = "",
    source_patch_id: Optional[str] = None,
) -> WorldGraph:
    """
    Geometry-first Stage 3+4 reconstruction (app-agnostic).

    Regions are spatial hypotheses. Affordance / attention are Stage 5–7.
    """
    ents = _visible_entities(entities)
    if not ents:
        return WorldGraph(
            report=SceneUnderstandingReport(
                layout_confidence=0.0,
                region_coverage=0.0,
                affordance_entropy=1.0,
                unassigned_entity_fraction=1.0,
                notes=["no_visible_entities"],
            ),
            source_patch_id=source_patch_id,
            app=app,
        )

    extent = _union([tuple(e.bounds) for e in ents])  # type: ignore[misc]
    x0, y0, W, H = extent
    if W < 8 or H < 8:
        return WorldGraph(
            report=SceneUnderstandingReport(
                layout_confidence=0.1,
                region_coverage=0.0,
                affordance_entropy=1.0,
                unassigned_entity_fraction=1.0,
                notes=["degenerate_extent"],
            ),
            source_patch_id=source_patch_id,
            app=app,
        )

    window_area = max(1.0, W * H)
    seeds: Dict[str, SemanticRegion] = {}
    claimed: Set[int] = set()
    membership_meta: Dict[Tuple[int, str], Tuple[float, str, Dict[str, str]]] = {}

    def _record_membership(
        entity_id: int,
        region_id: str,
        confidence: float,
        relation: str,
        evidence: Dict[str, str],
    ) -> None:
        key = (entity_id, region_id)
        current = membership_meta.get(key)
        if current is None:
            membership_meta[key] = (float(confidence), relation, dict(evidence))
            return
        cur_conf, cur_relation, cur_evidence = current
        if float(confidence) > cur_conf or (
            float(confidence) == cur_conf and relation == "contained_by" and cur_relation != "contained_by"
        ):
            merged_evidence = dict(cur_evidence)
            merged_evidence.update(evidence)
            membership_meta[key] = (float(confidence), relation, merged_evidence)

    def _claim(region: SemanticRegion, members: Iterable[Entity], conf: float) -> None:
        ids: List[int] = []
        bbs: List[Bounds] = []
        for e in members:
            if e.id in claimed:
                continue
            claimed.add(e.id)
            ids.append(e.id)
            bbs.append(tuple(e.bounds))  # type: ignore[arg-type]
        if not ids:
            return
        region.entity_ids = ids
        region.bounds = _inflate(_union(bbs), 8.0, 8.0)
        region.confidence = conf
        seeds[region.id] = region
        for eid in ids:
            _record_membership(
                eid,
                region.id,
                conf,
                "contained_by",
                {"region_kind": region.kind.value, "reason": "geometry_claim"},
            )

    # --- Composer: text input(s) in the bottom band + same-row siblings ---
    bottom_cut = y0 + (1.0 - _COMPOSER_Y_FRAC) * H
    main_x_cut = x0 + _SIDEBAR_X_FRAC * W
    bottom_fields = [
        e
        for e in ents
        if _is_text_input(e) and _center(tuple(e.bounds))[1] >= bottom_cut  # type: ignore[arg-type]
    ]
    if bottom_fields:
        anchor = max(bottom_fields, key=lambda e: _area(tuple(e.bounds)))  # type: ignore[arg-type]
        ax, ay = _center(tuple(anchor.bounds))  # type: ignore[arg-type]
        members = [
            e
            for e in ents
            if _center(tuple(e.bounds))[1] >= bottom_cut  # type: ignore[arg-type]
            and _center(tuple(e.bounds))[0] >= main_x_cut  # type: ignore[arg-type]
        ]
        for e in ents:
            cx, cy = _center(tuple(e.bounds))  # type: ignore[arg-type]
            if abs(cy - ay) <= max(48.0, 0.06 * H) and abs(cx - ax) <= max(280.0, 0.45 * W):
                if e not in members:
                    members.append(e)
        _claim(
            SemanticRegion(id="composer", kind=RegionKind.COMPOSER, label="composer"),
            members,
            0.85,
        )
    else:
        # Fallback: densest interactive row in bottom band (no textfield detected)
        bottom_interactives = [
            e
            for e in ents
            if _is_interactive(e)
            and _center(tuple(e.bounds))[1] >= bottom_cut  # type: ignore[arg-type]
            and _center(tuple(e.bounds))[0] >= main_x_cut  # type: ignore[arg-type]
        ]
        if len(bottom_interactives) >= 2:
            _claim(
                SemanticRegion(id="composer", kind=RegionKind.COMPOSER, label="composer"),
                bottom_interactives,
                0.55,
            )

    # --- Floating menus: compact clusters of small controls outside composer ---
    unclaimed = [e for e in ents if e.id not in claimed]
    clusters = _cluster_interactive(
        unclaimed,
        radius=_CLUSTER_RADIUS,
        min_size=_CLUSTER_MIN_SIZE,
        max_member_area=_SMALL_CONTROL_MAX_AREA_FRAC * window_area,
    )
    for i, cluster in enumerate(clusters):
        # Skip clusters that look like a full-width toolbar (too wide)
        bb = _union([tuple(e.bounds) for e in cluster])  # type: ignore[misc]
        if bb[2] > 0.55 * W and bb[3] < 0.08 * H:
            continue  # likely bottom/top toolbar already handled or header
        # Skip if majority already would fall in bottom composer band and we have composer
        if "composer" in seeds:
            in_bottom = sum(
                1 for e in cluster if _center(tuple(e.bounds))[1] >= bottom_cut  # type: ignore[arg-type]
            )
            if in_bottom >= len(cluster) * 0.6:
                continue
        rid = "floating_menu" if i == 0 else f"floating_menu_{i}"
        _claim(
            SemanticRegion(id=rid, kind=RegionKind.FLOATING_MENU, label="floating_menu"),
            cluster,
            0.88 if len(cluster) >= 3 else 0.75,
        )

    # --- Navigation strip: top-left / left-rail short plural tabs ---
    from plugin.worldmodel.pragmatic_role import (
        UiPragmaticRole,
        get_pragmatic_role,
        refine_pragmatic_roles_with_regions,
    )

    header_cut = y0 + _HEADER_Y_FRAC * H
    nav_cut_y = y0 + min(0.12 * H, 96.0)
    nav_members = [
        e
        for e in ents
        if e.id not in claimed
        and _is_interactive(e)
        and (
            get_pragmatic_role(e) == UiPragmaticRole.NAV_CHROME
            or (
                _center(tuple(e.bounds))[0] < main_x_cut  # type: ignore[arg-type]
                and _center(tuple(e.bounds))[1] <= nav_cut_y  # type: ignore[arg-type]
                and len((e.label or e.semantic_role or "")) < 24
            )
        )
    ]
    # Prefer entities already tagged nav_chrome
    nav_tagged = [e for e in ents if e.id not in claimed and get_pragmatic_role(e) == UiPragmaticRole.NAV_CHROME]
    if len(nav_tagged) >= 2:
        _claim(
            SemanticRegion(id="navigation", kind=RegionKind.NAVIGATION, label="navigation"),
            nav_tagged,
            0.82,
        )
    elif len(nav_members) >= 3 and all(
        _center(tuple(e.bounds))[0] < main_x_cut for e in nav_members  # type: ignore[arg-type]
    ):
        _claim(
            SemanticRegion(id="navigation", kind=RegionKind.NAVIGATION, label="navigation"),
            nav_members[:12],
            0.65,
        )

    # --- Status bar: thin top band static banners ---
    status_cut = y0 + min(0.08 * H, 64.0)
    status_members = [
        e
        for e in ents
        if e.id not in claimed
        and get_pragmatic_role(e) == UiPragmaticRole.STATUS
        and _center(tuple(e.bounds))[1] <= status_cut  # type: ignore[arg-type]
    ]
    if len(status_members) >= 1:
        _claim(
            SemanticRegion(id="status_bar", kind=RegionKind.STATUS_BAR, label="status_bar"),
            status_members,
            0.7,
        )

    # --- Toolbar: wide thin interactive strip (top of main) ---
    toolbar_candidates = [
        e
        for e in ents
        if e.id not in claimed
        and _is_interactive(e)
        and e.entity_type != "textfield"
        and _area(tuple(e.bounds)) <= _SMALL_CONTROL_MAX_AREA_FRAC * window_area  # type: ignore[arg-type]
    ]
    if len(toolbar_candidates) >= 3:
        top_bar = [
            e
            for e in toolbar_candidates
            if _center(tuple(e.bounds))[1] <= header_cut  # type: ignore[arg-type]
            and _center(tuple(e.bounds))[0] >= main_x_cut  # type: ignore[arg-type]
        ]
        if len(top_bar) >= 3:
            bb = _union([tuple(e.bounds) for e in top_bar])  # type: ignore[misc]
            if bb[2] > 0.4 * W and bb[3] < 0.12 * H:
                _claim(
                    SemanticRegion(id="toolbar", kind=RegionKind.TOOLBAR, label="toolbar"),
                    top_bar,
                    0.7,
                )

    # --- Sidebar: left column density ---
    sidebar_members = [
        e
        for e in ents
        if e.id not in claimed and _center(tuple(e.bounds))[0] < main_x_cut  # type: ignore[arg-type]
    ]
    if len(sidebar_members) >= 3:
        _claim(
            SemanticRegion(id="sidebar", kind=RegionKind.SIDEBAR, label="sidebar"),
            sidebar_members,
            0.75,
        )

    # --- Header: top band of main column ---
    header_members = [
        e
        for e in ents
        if e.id not in claimed
        and _center(tuple(e.bounds))[1] <= header_cut  # type: ignore[arg-type]
        and _center(tuple(e.bounds))[0] >= main_x_cut  # type: ignore[arg-type]
    ]
    if header_members:
        _claim(
            SemanticRegion(id="header", kind=RegionKind.HEADER, label="header"),
            header_members,
            0.8,
        )

    # --- Content body: remaining main-column ---
    body_members = [
        e
        for e in ents
        if e.id not in claimed and _center(tuple(e.bounds))[0] >= main_x_cut  # type: ignore[arg-type]
    ]
    if body_members:
        _claim(
            SemanticRegion(id="content", kind=RegionKind.TIMELINE, label="content"),
            body_members,
            0.55,
        )

    leftover = [e for e in ents if e.id not in claimed]
    if leftover:
        _claim(
            SemanticRegion(id="unknown", kind=RegionKind.UNKNOWN, label="unassigned"),
            leftover,
            0.3,
        )

    regions = list(seeds.values())

    # Emit overlapping memberships from the final region hypotheses.
    region_by_id = {r.id: r for r in regions}
    for e in ents:
        candidates: List[Tuple[str, float, str]] = []
        for r in regions:
            if r.kind == RegionKind.UNKNOWN:
                continue
            conf = _membership_confidence(e, r.bounds, r.kind)
            if conf <= 0.0:
                continue
            relation = "contained_by" if conf >= 0.45 else "overlaps"
            candidates.append((r.id, conf, relation))

        # Keep the most plausible few memberships so the graph stays legible.
        candidates.sort(key=lambda item: (-item[1], item[0]))
        for region_id, conf, relation in candidates[:4]:
            _record_membership(
                e.id,
                region_id,
                round(conf, 4),
                relation,
                {"region_kind": region_by_id[region_id].kind.value, "reason": "geometry_overlap"},
            )

    # Parent pane wraps header / content / composer when present
    child_kinds = {RegionKind.HEADER, RegionKind.TIMELINE, RegionKind.COMPOSER}
    if any(r.kind in child_kinds for r in regions):
        child_ids = [r.id for r in regions if r.kind in child_kinds]
        conv = SemanticRegion(
            id="main_pane",
            kind=RegionKind.CONVERSATION,
            bounds=_union([r.bounds for r in regions if r.id in child_ids]),
            confidence=0.7,
            entity_ids=[],
            label="main_pane",
        )
        for r in regions:
            if r.id in child_ids:
                r.parent_region_id = "main_pane"
        regions.insert(0, conv)

    nodes: List[SceneNodeRef] = []
    edges: List[SceneEdge] = []
    seen_nodes: Set[Tuple[str, str]] = set()

    def _add_node(kind: str, nid: str) -> None:
        key = (kind, nid)
        if key in seen_nodes:
            return
        seen_nodes.add(key)
        nodes.append(SceneNodeRef(kind=kind, id=nid))

    for e in ents:
        _add_node("entity", str(e.id))
        if e.parent_id is not None:
            _add_node("entity", str(e.parent_id))
            edges.append(
                SceneEdge(
                    kind=EdgeKind.PARENT_OF,
                    source=SceneNodeRef(kind="entity", id=str(e.parent_id)),
                    target=SceneNodeRef(kind="entity", id=str(e.id)),
                    confidence=0.9,
                )
            )

    for r in regions:
        _add_node("region", r.id)
        if r.parent_region_id:
            _add_node("region", r.parent_region_id)
            edges.append(
                SceneEdge(
                    kind=EdgeKind.CONTAINS,
                    source=SceneNodeRef(kind="region", id=r.parent_region_id),
                    target=SceneNodeRef(kind="region", id=r.id),
                    confidence=0.8,
                )
            )
        for eid in r.entity_ids:
            _add_node("entity", str(eid))
            edges.append(
                SceneEdge(
                    kind=EdgeKind.CONTAINS,
                    source=SceneNodeRef(kind="region", id=r.id),
                    target=SceneNodeRef(kind="entity", id=str(eid)),
                    confidence=float(r.confidence),
                )
            )

    memberships: List[RegionMembership] = []
    for (entity_id, region_id), (confidence, relation, evidence) in sorted(membership_meta.items()):
        memberships.append(
            RegionMembership(
                entity_id=entity_id,
                region_id=region_id,
                relation=relation,
                confidence=round(confidence, 4),
                evidence=dict(evidence),
            )
        )
        edges.append(
            SceneEdge(
                kind=EdgeKind.MEMBER_OF,
                source=SceneNodeRef(kind="entity", id=str(entity_id)),
                target=SceneNodeRef(kind="region", id=region_id),
                confidence=round(confidence, 4),
            )
        )

    assigned_ids: Set[int] = set()
    for r in regions:
        if r.kind != RegionKind.UNKNOWN:
            assigned_ids.update(r.entity_ids)
    coverage = len(assigned_ids) / max(1, len(ents))
    layout_conf = min(
        0.95,
        0.35
        + 0.2 * (1.0 if "composer" in seeds else 0.0)
        + 0.2 * (1.0 if any(k.startswith("floating_menu") for k in seeds) else 0.0)
        + 0.15 * (1.0 if "header" in seeds else 0.0)
        + 0.2 * coverage,
    )

    graph = WorldGraph(
        regions=regions,
        context_graph=ContextGraph(nodes=nodes, edges=edges),
        memberships=memberships,
        report=SceneUnderstandingReport(
            layout_confidence=round(layout_conf, 4),
            region_coverage=round(coverage, 4),
            affordance_entropy=1.0,
            unassigned_entity_fraction=round(1.0 - coverage, 4),
            notes=["geometry_ax_generic_v1"],
        ),
        source_patch_id=source_patch_id,
        app=app,
    )

    # Refine pragmatic roles from region membership (mutates entity beliefs)
    kind_map: Dict[int, str] = {}
    for r in regions:
        for eid in r.entity_ids:
            if eid not in kind_map or r.kind != RegionKind.UNKNOWN:
                kind_map[eid] = r.kind.value
    # Also refine entities passed in that may lack geometry filters
    all_ents = list(entities)
    refine_pragmatic_roles_with_regions(all_ents, entity_region_kind=kind_map)
    return graph


def region_kind_for_entity(graph: WorldGraph, entity_id: int) -> Optional[RegionKind]:
    """Most specific non-main_pane region containing entity_id."""
    regions = region_ids_and_kinds_for_entity(graph, entity_id)
    if not regions:
        return None
    return regions[0][1]


def region_ids_and_kinds_for_entity(
    graph: WorldGraph,
    entity_id: int,
) -> List[Tuple[str, RegionKind]]:
    """All plausible region memberships for an entity, best first."""
    region_by_id = {r.id: r for r in graph.regions}
    hits: List[Tuple[str, RegionKind, float, str]] = []
    for m in graph.memberships:
        if m.entity_id != entity_id:
            continue
        region = region_by_id.get(m.region_id)
        if region is None or region.kind == RegionKind.CONVERSATION:
            continue
        hits.append((region.id, region.kind, float(m.confidence), region.id))
    if not hits:
        for r in graph.regions:
            if entity_id in r.entity_ids and r.kind != RegionKind.CONVERSATION:
                hits.append((r.id, r.kind, float(r.confidence), r.id))
    if not hits:
        for r in graph.regions:
            if entity_id in r.entity_ids:
                hits.append((r.id, r.kind, float(r.confidence), r.id))
    if not hits:
        return []
    priority = {
        RegionKind.FLOATING_MENU: 0,
        RegionKind.MODAL: 1,
        RegionKind.COMPOSER: 2,
        RegionKind.NAVIGATION: 3,
        RegionKind.STATUS_BAR: 4,
        RegionKind.HEADER: 5,
        RegionKind.TOOLBAR: 6,
        RegionKind.SIDEBAR: 7,
        RegionKind.TIMELINE: 8,
        RegionKind.UNKNOWN: 9,
    }
    hits.sort(key=lambda item: (priority.get(item[1], 8), -item[2], item[3]))
    return [(region_id, kind) for region_id, kind, _conf, _key in hits]


def region_kinds_for_entity(graph: WorldGraph, entity_id: int) -> List[RegionKind]:
    return [kind for _region_id, kind in region_ids_and_kinds_for_entity(graph, entity_id)]


def region_ids_for_entity(graph: WorldGraph, entity_id: int) -> List[str]:
    return [region_id for region_id, _kind in region_ids_and_kinds_for_entity(graph, entity_id)]


def region_id_for_entity(graph: WorldGraph, entity_id: int) -> Optional[str]:
    regions = region_ids_and_kinds_for_entity(graph, entity_id)
    if not regions:
        return None
    return regions[0][0]
