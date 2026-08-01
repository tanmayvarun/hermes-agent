"""Pure PyObjC accessibility tree dump — backup when macapptree fails."""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Dict, List, Optional, Set

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


def _node_id(role: str, name: str, desc: str, value: str, bbox: List[float]) -> str:
    raw = f"{role}|{name}|{desc}|{value}|{bbox}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:16]


def _as_children(raw: Any) -> List[Any]:
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        return [child for child in raw if child is not None]
    return [raw]


def _child_attributes_for_role(role: str) -> List[str]:
    role_l = str(role or "").strip().lower()
    if role_l == "axapplication":
        # On macOS the content subtree is often split across focused/main
        # windows and the general children collection. Pull all of them so the
        # active app content survives traversal even when one attribute is
        # sparse.
        return ["AXFocusedWindow", "AXMainWindow", "AXWindows", "AXChildren"]
    if role_l in {
        "axwindow",
        "axsheet",
        "axdrawer",
        "axdialog",
        "axpopover",
        "axgroup",
        "axscrollarea",
        "axsplitgroup",
        "axwebarea",
        "axlist",
        "axtable",
        "axoutline",
    }:
        return ["AXChildren", "AXVisibleChildren"]
    return ["AXChildren", "AXVisibleChildren"]


def _serialize(
    el: Any,
    *,
    depth: int = 0,
    max_depth: int = 20,
    max_nodes: int = 1000,
    total_nodes: Optional[List[int]] = None,
    seen: Optional[Set[str]] = None,
    signature_counts: Optional[Dict[str, int]] = None,
    is_root: bool = False,
) -> Optional[Dict[str, Any]]:
    if el is None or depth > max_depth:
        return None
    if total_nodes is None:
        total_nodes = [0]
    if seen is None:
        seen = set()
    if signature_counts is None:
        signature_counts = {}
    if total_nodes[0] >= max_nodes:
        return None
    role = _str_attr(el, "AXRole") or "AXUnknown"
    role_l = role.strip().lower()
    # Keep title and description separate — Electron often puts contact name in
    # AXDescription and message preview in AXTitle (or query in title + "Search" desc).
    title = _str_attr(el, "AXTitle") or ""
    desc = _str_attr(el, "AXDescription") or ""
    value = _copy_attr(el, "AXValue")
    name = title or desc or ("" if value is None else str(value)) or ""
    enabled = _copy_attr(el, "AXEnabled")
    bbox = _frame(el)
    sig = _node_id(role, name, desc, "" if value is None else str(value), bbox)
    if sig in seen and not is_root:
        return None
    # Menu-bar chrome is global shell noise for our app-embedded workflows.
    # Keep the content subtree; drop the closed application menu subtree.
    if role_l in {"axmenubar", "axmenubaritem"} and not is_root:
        return None
    count = signature_counts.get(sig, 0) + 1
    signature_counts[sig] = count
    if count > 3 and not is_root:
        return None
    if role == "AXApplication" and not is_root:
        return None
    seen.add(sig)
    total_nodes[0] += 1
    children_raw: List[Any] = []
    seen_child_ids: Set[int] = set()
    for attr in _child_attributes_for_role(role):
        try:
            raw_children = _as_children(_copy_attr(el, attr))
        except Exception:
            raw_children = []
        for child in raw_children:
            try:
                child_key = id(child)
            except Exception:
                child_key = 0
            if child_key in seen_child_ids:
                continue
            seen_child_ids.add(child_key)
            children_raw.append(child)
    children: List[Dict[str, Any]] = []
    try:
        for child in list(children_raw):
            if total_nodes[0] >= max_nodes:
                break
            serialized = _serialize(
                child,
                depth=depth + 1,
                max_depth=max_depth,
                max_nodes=max_nodes,
                total_nodes=total_nodes,
                seen=seen,
                signature_counts=signature_counts,
            )
            if serialized is not None:
                children.append(serialized)
    except Exception:
        pass
    return {
        "id": sig,
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
    tree = _serialize(root, depth=0, max_depth=20, max_nodes=1000, is_root=True)
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
