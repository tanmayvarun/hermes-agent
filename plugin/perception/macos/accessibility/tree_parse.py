"""Parse macapptree JSON trees into AxNode / Observation."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Set, Tuple

from plugin.perception.observation import AxNode, Bounds, Observation


def _parse_bbox(raw: Any) -> Bounds:
    if isinstance(raw, (list, tuple)) and len(raw) >= 4:
        return float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3])
    if isinstance(raw, str) and ";" in raw:
        # absolute_position "x;y" + size "w;h" handled elsewhere
        parts = raw.replace(",", ";").split(";")
        if len(parts) >= 4:
            return tuple(float(p) for p in parts[:4])  # type: ignore[return-value]
    return (0.0, 0.0, 0.0, 0.0)


def _parse_size_pos(node: Dict[str, Any]) -> Bounds:
    if "bbox" in node:
        return _parse_bbox(node["bbox"])
    size = str(node.get("size") or "0;0")
    pos = str(node.get("position") or node.get("absolute_position") or "0;0")
    try:
        sw, sh = [float(x) for x in size.replace(",", ";").split(";")[:2]]
        px, py = [float(x) for x in pos.replace(",", ";").split(";")[:2]]
        return (px, py, sw, sh)
    except (ValueError, TypeError):
        return (0.0, 0.0, 0.0, 0.0)


def _node_signature(node: Dict[str, Any]) -> str:
    role = str(node.get("role") or "").strip().lower()
    name = " ".join(str(node.get("name") or node.get("title") or "").split()).strip().lower()
    desc = " ".join(str(node.get("description") or "").split()).strip().lower()
    value = " ".join(str(node.get("value") or "").split()).strip().lower()
    bbox = node.get("bbox") or []
    try:
        bbox_sig = tuple(round(float(v), 1) for v in list(bbox)[:4])
    except Exception:
        bbox_sig = (0.0, 0.0, 0.0, 0.0)
    return f"{role}|{name}|{desc}|{value}|{bbox_sig}"


def _prune_tree(
    node: Dict[str, Any],
    *,
    depth: int = 0,
    max_depth: int = 20,
    max_nodes: int = 1000,
    visited: Optional[Set[str]] = None,
    signature_counts: Optional[Dict[str, int]] = None,
    total_nodes: Optional[List[int]] = None,
    is_root: bool = False,
) -> Optional[Dict[str, Any]]:
    if visited is None:
        visited = set()
    if signature_counts is None:
        signature_counts = {}
    if total_nodes is None:
        total_nodes = [0]
    if not isinstance(node, dict):
        return None
    if depth > max_depth or total_nodes[0] >= max_nodes:
        return None

    role = str(node.get("role") or "").strip()
    sig = _node_signature(node)
    if sig in visited and not is_root:
        return None
    if role in {"AXMenuBar", "AXMenuBarItem"} and not is_root:
        return None
    count = signature_counts.get(sig, 0) + 1
    signature_counts[sig] = count
    if count > 3 and not is_root:
        return None
    if role == "AXApplication" and not is_root:
        return None

    children_raw = node.get("children") or []
    children: List[Dict[str, Any]] = []
    total_nodes[0] += 1
    visited.add(sig)
    for child in children_raw:
        if total_nodes[0] >= max_nodes:
            break
        if not isinstance(child, dict):
            continue
        pruned = _prune_tree(
            child,
            depth=depth + 1,
            max_depth=max_depth,
            max_nodes=max_nodes,
            visited=visited,
            signature_counts=signature_counts,
            total_nodes=total_nodes,
        )
        if pruned is not None:
            children.append(pruned)

    pruned_node = dict(node)
    pruned_node["children"] = children
    return pruned_node


def parse_macapptree_node(raw: Dict[str, Any]) -> AxNode:
    children_raw = raw.get("children") or []
    children = [
        parse_macapptree_node(c)
        for c in children_raw
        if isinstance(c, dict)
    ]
    name = raw.get("name") or raw.get("title") or ""
    desc = raw.get("description") or ""
    return AxNode(
        role=str(raw.get("role") or ""),
        name=str(name) if name is not None else "",
        description=str(desc) if desc is not None else "",
        value=None if raw.get("value") is None else str(raw.get("value")),
        enabled=bool(raw.get("enabled", True)),
        bbox=_parse_size_pos(raw),
        children=children,
        raw_id=str(raw.get("id") or ""),
        role_description=str(raw.get("role_description") or ""),
        attributes={
            k: v
            for k, v in raw.items()
            if k
            not in {
                "children",
                "role",
                "name",
                "description",
                "value",
                "enabled",
                "bbox",
                "id",
                "role_description",
                "position",
                "size",
                "absolute_position",
                "visible_bbox",
            }
        },
    )


def observation_from_tree(
    tree: Dict[str, Any],
    *,
    app_name: str,
    window_name: str = "",
    bundle_id: str = "",
    screenshot_path: Optional[str] = None,
    source: str = "macapptree",
    coverage: Optional[float] = None,
    degraded: bool = False,
    meta: Optional[Dict[str, Any]] = None,
    max_depth: int = 20,
    max_nodes: int = 1000,
) -> Observation:
    pruned = _prune_tree(
        tree,
        depth=0,
        max_depth=max_depth,
        max_nodes=max_nodes,
        is_root=True,
    )
    root = parse_macapptree_node(pruned or tree)
    nodes = root.flatten()
    # Drop the synthetic root duplicate if it is only a container — keep all.
    win = window_name or root.name or ""
    return Observation(
        timestamp=time.time(),
        app_name=app_name,
        window_name=win,
        bundle_id=bundle_id,
        ax_tree=root,
        nodes=nodes,
        screenshot_path=screenshot_path,
        source=source,
        coverage=coverage,
        degraded=degraded,
        meta=meta or {},
    )


def count_nodes(tree: Dict[str, Any]) -> int:
    n = 1
    for c in tree.get("children") or []:
        if isinstance(c, dict):
            n += count_nodes(c)
    return n
