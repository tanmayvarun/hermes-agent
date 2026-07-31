"""Layer 6 — stable identity. Plugin + scipy Hungarian; greedy backup."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from plugin.worldmodel.entities.entity import Entity

# Match weights
W_ROLE = 0.30
W_LABEL = 0.30
W_GEOM = 0.25
W_PARENT = 0.10
W_CHILDREN = 0.05

MATCH_THRESHOLD = 0.55
ALIAS_THRESHOLD = 0.40


def _iou(a: Tuple[float, float, float, float], b: Tuple[float, float, float, float]) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ax2, ay2 = ax + max(aw, 0), ay + max(ah, 0)
    bx2, by2 = bx + max(bw, 0), by + max(bh, 0)
    ix1, iy1 = max(ax, bx), max(ay, by)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    union = max(aw, 0) * max(ah, 0) + max(bw, 0) * max(bh, 0) - inter
    if union <= 0:
        return 0.0
    return inter / union


def _label_sim(a: str, b: str) -> float:
    a, b = (a or "").strip().lower(), (b or "").strip().lower()
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if a in b or b in a:
        return 0.7
    # token Jaccard
    ta, tb = set(a.split()), set(b.split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def similarity(prev: Entity, cur: Entity) -> float:
    role = 1.0 if prev.role == cur.role else 0.0
    label = _label_sim(prev.label, cur.label)
    geom = _iou(prev.bounds, cur.bounds)
    parent = 1.0 if prev.parent_id == cur.parent_id else 0.0
    # children count proximity
    pc, cc = len(prev.child_ids), len(cur.child_ids)
    children = 1.0 if pc == cc else (0.5 if abs(pc - cc) <= 2 else 0.0)
    return (
        W_ROLE * role
        + W_LABEL * label
        + W_GEOM * geom
        + W_PARENT * parent
        + W_CHILDREN * children
    )


@dataclass
class MatchResult:
    tracked: List[Entity]
    new_ids: List[int]
    matched_prev_ids: List[int]
    retention: float  # fraction of prev entities retained


def _hungarian(cost: List[List[float]]) -> List[Tuple[int, int]]:
    """Minimize cost; return list of (row, col)."""
    try:
        import numpy as np
        from scipy.optimize import linear_sum_assignment

        arr = np.array(cost, dtype=float)
        r, c = linear_sum_assignment(arr)
        return list(zip(r.tolist(), c.tolist()))
    except ImportError:
        return _greedy_assignment(cost)


def _greedy_assignment(cost: List[List[float]]) -> List[Tuple[int, int]]:
    pairs: List[Tuple[float, int, int]] = []
    for i, row in enumerate(cost):
        for j, v in enumerate(row):
            pairs.append((v, i, j))
    pairs.sort()
    used_r, used_c = set(), set()
    out: List[Tuple[int, int]] = []
    for v, i, j in pairs:
        if i in used_r or j in used_c:
            continue
        used_r.add(i)
        used_c.add(j)
        out.append((i, j))
    return out


class IdentityTracker:
    """Maintain stable entity IDs across snapshots."""

    def __init__(self) -> None:
        self._next_id = 1
        self._entities: Dict[int, Entity] = {}

    @property
    def entities(self) -> Dict[int, Entity]:
        return self._entities

    def seed(self, entities: Sequence[Entity]) -> List[Entity]:
        tracked: List[Entity] = []
        for e in entities:
            ne = Entity(**{**e.to_dict(), "id": self._next_id})
            self._next_id += 1
            self._entities[ne.id] = ne
            tracked.append(ne)
        return tracked

    def update(self, current: Sequence[Entity]) -> MatchResult:
        prev_list = list(self._entities.values())
        if not prev_list:
            tracked = self.seed(current)
            return MatchResult(tracked=tracked, new_ids=[e.id for e in tracked], matched_prev_ids=[], retention=1.0)

        if not current:
            for e in prev_list:
                e.visible = False
            return MatchResult(tracked=prev_list, new_ids=[], matched_prev_ids=[], retention=0.0)

        # cost = 1 - similarity
        cost = [[1.0 - similarity(p, c) for c in current] for p in prev_list]
        assignment = _hungarian(cost)

        matched_prev: Dict[int, int] = {}  # prev_idx -> cur_idx
        matched_cur: Dict[int, int] = {}
        for pi, ci in assignment:
            score = 1.0 - cost[pi][ci]
            if score >= MATCH_THRESHOLD:
                matched_prev[pi] = ci
                matched_cur[ci] = pi
            elif score >= ALIAS_THRESHOLD:
                # uncertain: keep prev, mark alias candidate on new
                matched_prev[pi] = ci
                matched_cur[ci] = pi

        tracked: List[Entity] = []
        matched_prev_ids: List[int] = []
        new_ids: List[int] = []

        # Update matched
        for pi, ci in matched_prev.items():
            prev = prev_list[pi]
            cur = current[ci]
            score = similarity(prev, cur)
            updated = Entity(
                id=prev.id,
                entity_type=cur.entity_type,
                semantic_role=cur.semantic_role or prev.semantic_role,
                actions=cur.actions or prev.actions,
                role=cur.role,
                label=cur.label,
                bounds=cur.bounds,
                parent_id=cur.parent_id,
                child_ids=cur.child_ids,
                visible=True,
                enabled=cur.enabled,
                aliases=list(prev.aliases),
                snapshot_count=prev.snapshot_count + 1,
                raw_ax_id=cur.raw_ax_id or prev.raw_ax_id,
                attributes=cur.attributes,
                confidence=float(getattr(cur, "confidence", None) or getattr(prev, "confidence", 1.0) or 1.0),
                beliefs=dict(getattr(cur, "beliefs", None) or getattr(prev, "beliefs", None) or {}),
                evidence=list(getattr(cur, "evidence", None) or getattr(prev, "evidence", None) or []),
                miss_frames=0,
                entity_key=str(getattr(cur, "entity_key", None) or getattr(prev, "entity_key", None) or ""),
            )
            if score < MATCH_THRESHOLD:
                # soft match — record alias of ephemeral id space (use negative)
                updated.aliases = list(set(prev.aliases + [-ci]))
            self._entities[prev.id] = updated
            tracked.append(updated)
            matched_prev_ids.append(prev.id)

        # Unmatched previous → invisible
        for pi, prev in enumerate(prev_list):
            if pi not in matched_prev:
                prev.visible = False
                tracked.append(prev)

        # Unmatched current → new entities
        for ci, cur in enumerate(current):
            if ci in matched_cur:
                continue
            ne = Entity(**{**cur.to_dict(), "id": self._next_id, "snapshot_count": 1})
            self._next_id += 1
            self._entities[ne.id] = ne
            tracked.append(ne)
            new_ids.append(ne.id)

        retention = len(matched_prev_ids) / max(1, len(prev_list))
        return MatchResult(
            tracked=tracked,
            new_ids=new_ids,
            matched_prev_ids=matched_prev_ids,
            retention=retention,
        )
