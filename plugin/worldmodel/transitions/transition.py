"""Layer 8 — transitions as Screen + Action → Patch."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from plugin.worldmodel.entities.entity import Entity


@dataclass
class EntityPatch:
    entity_id: int
    changes: Dict[str, Any]  # e.g. {"visible": False}


@dataclass
class Transition:
    from_screen: int
    to_screen: int
    action: str
    target_entity_id: Optional[int] = None
    diff: List[EntityPatch] = field(default_factory=list)
    count: int = 1

    def key(self) -> str:
        return f"{self.from_screen}|{self.action}|{self.target_entity_id}|{self.to_screen}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from_screen": self.from_screen,
            "to_screen": self.to_screen,
            "action": self.action,
            "target_entity_id": self.target_entity_id,
            "diff": [asdict(d) for d in self.diff],
            "count": self.count,
        }


def compute_entity_diff(before: Sequence[Entity], after: Sequence[Entity]) -> List[EntityPatch]:
    """Attribute patches only — not full snapshot compare."""
    before_map = {e.id: e for e in before}
    after_map = {e.id: e for e in after}
    patches: List[EntityPatch] = []
    for eid, a in after_map.items():
        b = before_map.get(eid)
        if b is None:
            patches.append(EntityPatch(entity_id=eid, changes={"appeared": True, "visible": a.visible}))
            continue
        changes: Dict[str, Any] = {}
        if b.visible != a.visible:
            changes["visible"] = a.visible
        if b.label != a.label:
            changes["label"] = a.label
        if b.bounds != a.bounds:
            changes["bounds"] = a.bounds
        if b.enabled != a.enabled:
            changes["enabled"] = a.enabled
        if changes:
            patches.append(EntityPatch(entity_id=eid, changes=changes))
    for eid, b in before_map.items():
        if eid not in after_map:
            patches.append(EntityPatch(entity_id=eid, changes={"visible": False, "disappeared": True}))
    return patches


class TransitionStore:
    def __init__(self) -> None:
        self._by_key: Dict[str, Transition] = {}

    @property
    def transitions(self) -> List[Transition]:
        return list(self._by_key.values())

    def record(
        self,
        *,
        from_screen: int,
        to_screen: int,
        action: str,
        target_entity_id: Optional[int],
        diff: List[EntityPatch],
    ) -> Transition:
        t = Transition(
            from_screen=from_screen,
            to_screen=to_screen,
            action=action,
            target_entity_id=target_entity_id,
            diff=diff,
        )
        key = t.key()
        if key in self._by_key:
            existing = self._by_key[key]
            existing.count += 1
            existing.diff = diff  # latest patch
            return existing
        self._by_key[key] = t
        return t

    def predict(self, from_screen: int, action: str, target_entity_id: Optional[int] = None) -> Optional[Transition]:
        """Return most-seen transition matching from+action(+target)."""
        candidates = [
            t
            for t in self._by_key.values()
            if t.from_screen == from_screen
            and t.action == action
            and (target_entity_id is None or t.target_entity_id == target_entity_id)
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda t: t.count)
