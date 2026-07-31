"""Parse macapptree JSON trees into AxNode / Observation."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

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
) -> Observation:
    root = parse_macapptree_node(tree)
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
