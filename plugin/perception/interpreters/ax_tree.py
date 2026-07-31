"""AX tree → entity hypotheses (pyobjc_ax / macapptree)."""

from __future__ import annotations

from typing import Any, Dict, List

from plugin.perception.hypothesis import EntityHypothesis
from plugin.perception.observation import AxNode
from plugin.perception.sources.base import ObservationBundle
from plugin.worldmodel.entities.normalize import _ACTION_MAP, _ROLE_MAP, _clean_label


class AxTreeInterpreter:
    interpreter_id = "ax_tree"

    def __init__(self, *, source_prior: float = 0.92) -> None:
        self.source_prior = source_prior

    def interpret(self, bundle: ObservationBundle) -> List[EntityHypothesis]:
        obs = bundle.observation
        source = bundle.source_id or obs.source or "ax"
        # Source-specific prior: pyobjc deeper → slightly higher
        prior = self.source_prior
        if source == "pyobjc_ax":
            prior = max(prior, 0.94)
        elif source == "macapptree":
            prior = min(prior, 0.82)
        if bundle.degraded:
            prior *= 0.6

        out: List[EntityHypothesis] = []
        for n in obs.nodes or []:
            h = self._node_to_hypothesis(n, source=source, prior=prior)
            if h is not None:
                out.append(h)
        return out

    def _node_to_hypothesis(self, node: AxNode, *, source: str, prior: float) -> EntityHypothesis | None:
        role = node.role or ""
        etype = _ROLE_MAP.get(role, "unknown")
        raw_name = (node.name or "").strip()
        raw_desc = (node.description or "").strip()
        label = _clean_label(raw_name or raw_desc or (str(node.value) if node.value else "") or "")
        if not label and etype == "unknown":
            return None
        bounds = tuple(node.bbox) if node.bbox else (0.0, 0.0, 0.0, 0.0)
        actions = list(_ACTION_MAP.get(etype, []))
        focused = bool((node.attributes or {}).get("focused") or (node.attributes or {}).get("AXFocused"))
        props: Dict[str, Any] = {
            "exists": True,
            "visible": True,
            "enabled": bool(node.enabled),
            "focused": focused,
            "label": label,
            "entity_type": etype,
        }
        if node.value is not None:
            props["value"] = node.value
        if raw_desc:
            props["description"] = _clean_label(raw_desc)
        conf = prior
        if not label:
            conf *= 0.7
        return EntityHypothesis.make(
            role=role,
            label=label or etype,
            bounds=bounds,  # type: ignore[arg-type]
            actions=actions,
            properties=props,
            confidence=conf,
            source=source,
            raw_refs={"raw_id": node.raw_id, "role": role},
        )
