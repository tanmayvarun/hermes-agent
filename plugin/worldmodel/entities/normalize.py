"""Layer 5 — AX node → Plugin entity. Deterministic; no LLM."""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from plugin.perception.observation import AxNode, Observation
from plugin.worldmodel.entities.entity import Entity

_ROLE_MAP = {
    "AXButton": "button",
    "AXPopUpButton": "button",
    "AXCheckBox": "button",
    "AXRadioButton": "button",
    "AXTextField": "textfield",
    "AXTextArea": "textfield",
    "AXSearchField": "textfield",
    "AXComboBox": "textfield",
    "AXStaticText": "static",
    "AXLink": "link",
    "AXList": "list",
    "AXTable": "list",
    "AXOutline": "list",
    "AXScrollArea": "scroll",
    "AXImage": "image",
    "AXGroup": "group",
    "AXWindow": "window",
    "AXToolbar": "toolbar",
    "AXMenuItem": "menu",
}

_ACTION_MAP = {
    "button": ["click"],
    "textfield": ["click", "type"],
    "link": ["click"],
    "list": ["click", "scroll"],
    "scroll": ["scroll"],
    "menu": ["click"],
}


def _clean_label(label: str) -> str:
    """Strip bidi / zero-width marks WhatsApp injects into AX titles (U+200E etc.)."""
    if not label:
        return ""
    cleaned = re.sub(r"[\u200e\u200f\u202a-\u202e\u2066-\u2069\ufeff]", "", label)
    return re.sub(r"\s+", " ", cleaned).strip()


def _semantic_from_label(label: str, role: str) -> str:
    lab = _clean_label(label)
    if not lab:
        return role.replace("AX", "").lower() or "unknown"
    return lab[:120]


def normalize_node(
    node: AxNode,
    entity_id: int,
    *,
    parent_id: Optional[int] = None,
) -> Entity:
    etype = _ROLE_MAP.get(node.role, "unknown")
    # Prefer AXTitle/name for label; keep description even when used as name fallback.
    raw_name = (node.name or "").strip()
    raw_desc = (node.description or "").strip()
    raw_value = (node.value or "") if node.value is not None else ""
    name = _clean_label(raw_name or raw_desc or str(raw_value) or "")
    attrs = dict(node.attributes)
    if node.value is not None and "value" not in attrs:
        attrs["value"] = node.value
    # Always preserve description on attributes (Electron contact rows / search mirrors).
    if raw_desc:
        attrs["description"] = _clean_label(raw_desc)
    elif "description" not in attrs and "AXDescription" in attrs:
        attrs["description"] = _clean_label(str(attrs["AXDescription"]))
    if node.role in {"AXTextField", "AXSearchField"} and raw_desc:
        attrs.setdefault("placeholder", _clean_label(raw_desc))
    return Entity(
        id=entity_id,
        entity_type=etype,
        semantic_role=_semantic_from_label(name, node.role),
        actions=list(_ACTION_MAP.get(etype, [])),
        role=node.role,
        label=name,
        bounds=node.bbox,
        parent_id=parent_id,
        visible=True,
        enabled=node.enabled,
        raw_ax_id=node.raw_id,
        attributes=attrs,
    )


def entities_from_observation(obs: Observation) -> List[Entity]:
    """Flatten AX tree to entities with parent links (by flatten order ids)."""
    if not obs.ax_tree:
        ents = [normalize_node(n, i + 1) for i, n in enumerate(obs.nodes)]
        _apply_stage2_roles(ents)
        return ents

    entities: List[Entity] = []
    next_id = 1

    def walk(node: AxNode, parent_id: Optional[int]) -> int:
        nonlocal next_id
        eid = next_id
        next_id += 1
        ent = normalize_node(node, eid, parent_id=parent_id)
        entities.append(ent)
        child_ids: List[int] = []
        for child in node.children:
            cid = walk(child, eid)
            child_ids.append(cid)
        ent.child_ids = child_ids
        return eid

    walk(obs.ax_tree, None)
    _apply_stage2_roles(entities)
    return entities


def _apply_stage2_roles(entities: List[Entity]) -> None:
    from plugin.worldmodel.pragmatic_role import infer_pragmatic_role_stage2

    for e in entities:
        infer_pragmatic_role_stage2(e)


# Optional one-shot semantic cache (contingency — never classify every frame).
_SEMANTIC_CACHE: Dict[str, str] = {}


def cache_semantic(key: str, semantic: str) -> None:
    _SEMANTIC_CACHE[key] = semantic


def cached_semantic(key: str) -> Optional[str]:
    return _SEMANTIC_CACHE.get(key)


def apply_cached_semantics(entities: List[Entity]) -> None:
    for e in entities:
        if e.semantic_role and e.semantic_role != "unknown":
            continue
        key = f"{e.role}|{e.label}|{int(e.bounds[0])},{int(e.bounds[1])}"
        cached = cached_semantic(key)
        if cached:
            e.semantic_role = cached
