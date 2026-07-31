"""Pure PyObjC accessibility tree dump — backup when macapptree fails."""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Dict, List, Optional

from plugin.perception.macos.accessibility.tree_parse import observation_from_tree
from plugin.perception.observation import Observation

logger = logging.getLogger(__name__)


def _pid_for_app(app_name: str) -> Optional[int]:
    from AppKit import NSWorkspace  # type: ignore

    needle = (app_name or "").lower()
    for app in NSWorkspace.sharedWorkspace().runningApplications():
        name = str(app.localizedName() or "")
        bundle = str(app.bundleIdentifier() or "")
        if name.lower() == needle or needle in name.lower():
            return int(app.processIdentifier())
        if "whatsapp" in needle and "whatsapp" in bundle.lower():
            return int(app.processIdentifier())
    return None


def _copy_attr(el: Any, attr: str) -> Any:
    from ApplicationServices import AXUIElementCopyAttributeValue  # type: ignore

    try:
        result = AXUIElementCopyAttributeValue(el, attr, None)
        # PyObjC variants: value | (err, value)
        if isinstance(result, tuple):
            if len(result) >= 2:
                return result[1]
            return None
        return result
    except Exception:
        return None


def _str_attr(el: Any, attr: str) -> str:
    v = _copy_attr(el, attr)
    if v is None:
        return ""
    return str(v)


def _frame(el: Any) -> List[float]:
    import re

    pos = _copy_attr(el, "AXPosition")
    size = _copy_attr(el, "AXSize")
    x = y = w = h = 0.0
    try:
        x = float(getattr(pos, "x", 0) if pos is not None else 0)
        y = float(getattr(pos, "y", 0) if pos is not None else 0)
        w = float(getattr(size, "width", 0) if size is not None else 0)
        h = float(getattr(size, "height", 0) if size is not None else 0)
        if hasattr(pos, "__getitem__") and pos is not None:
            try:
                x, y = float(pos[0]), float(pos[1])
            except Exception:
                pass
        if hasattr(size, "__getitem__") and size is not None:
            try:
                w, h = float(size[0]), float(size[1])
            except Exception:
                pass
    except Exception:
        pass
    # AXValueRef repr embeds coordinates when getattr fails
    if pos is not None and (x == 0 and y == 0 or True):
        m = re.search(r"x:([-\d.]+)\s+y:([-\d.]+)", str(pos))
        if m:
            x, y = float(m.group(1)), float(m.group(2))
    if size is not None and w <= 0:
        m = re.search(r"w:([-\d.]+)\s+h:([-\d.]+)", str(size))
        if m:
            w, h = float(m.group(1)), float(m.group(2))
    return [x, y, w, h]


def _node_id(role: str, name: str, bbox: List[float]) -> str:
    raw = f"{role}|{name}|{bbox}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:16]


def _serialize(el: Any, depth: int = 0, max_depth: int = 40) -> Optional[Dict[str, Any]]:
    if el is None or depth > max_depth:
        return None
    role = _str_attr(el, "AXRole") or "AXUnknown"
    # Keep title and description separate — Electron often puts contact name in
    # AXDescription and message preview in AXTitle (or query in title + "Search" desc).
    title = _str_attr(el, "AXTitle") or ""
    desc = _str_attr(el, "AXDescription") or ""
    value = _copy_attr(el, "AXValue")
    name = title or desc or ("" if value is None else str(value)) or ""
    enabled = _copy_attr(el, "AXEnabled")
    bbox = _frame(el)
    children_raw = _copy_attr(el, "AXChildren") or []
    children: List[Dict[str, Any]] = []
    try:
        for child in list(children_raw):
            serialized = _serialize(child, depth + 1, max_depth)
            if serialized is not None:
                children.append(serialized)
    except Exception:
        pass
    return {
        "id": _node_id(role, name, bbox),
        "name": name or None,
        "role": role,
        "description": desc or None,
        "role_description": _str_attr(el, "AXRoleDescription") or None,
        "value": None if value is None else str(value),
        "enabled": bool(enabled) if enabled is not None else True,
        "bbox": bbox,
        "children": children,
    }


def observe_app_ax(app_name: str = "WhatsApp") -> Observation:
    """Build Observation from live AX tree via PyObjC (no macapptree subprocess)."""
    from ApplicationServices import AXUIElementCreateApplication  # type: ignore

    pid = _pid_for_app(app_name)
    if pid is None:
        raise RuntimeError(f"application not running: {app_name}")
    root = AXUIElementCreateApplication(pid)
    tree = _serialize(root)
    if tree is None:
        tree = {"role": "AXApplication", "name": app_name, "children": [], "id": "empty"}
    # Pick a window title if present
    window_name = ""
    for c in tree.get("children") or []:
        if c.get("role") == "AXWindow":
            window_name = str(c.get("name") or "")
            break
    return observation_from_tree(
        tree,
        app_name=app_name,
        window_name=window_name,
        bundle_id="",
        source="pyobjc_ax",
        coverage=1.0 if (tree.get("children") or []) else 0.0,
        degraded=not bool(tree.get("children")),
    )
