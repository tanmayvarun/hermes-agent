"""Navigation graph over screens — networkx when available."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from plugin.worldmodel.transitions.transition import Transition


class NavigationGraph:
    def __init__(self) -> None:
        self._edges: List[Tuple[int, int, str, int]] = []  # from, to, action, count

    def add_transition(self, t: Transition) -> None:
        self._edges.append((t.from_screen, t.to_screen, t.action, t.count))

    def sync_from_store(self, transitions: List[Transition]) -> None:
        self._edges = [(t.from_screen, t.to_screen, t.action, t.count) for t in transitions]

    def path(self, start: int, goal: int) -> Optional[List[Tuple[int, str, int]]]:
        """BFS path as list of (from, action, to)."""
        adj: Dict[int, List[Tuple[str, int]]] = {}
        for frm, to, action, _c in self._edges:
            adj.setdefault(frm, []).append((action, to))
        if start == goal:
            return []
        queue = [(start, [])]
        seen = {start}
        while queue:
            node, path = queue.pop(0)
            for action, nxt in adj.get(node, []):
                if nxt in seen:
                    continue
                new_path = path + [(node, action, nxt)]
                if nxt == goal:
                    return new_path
                seen.add(nxt)
                queue.append((nxt, new_path))
        return None

    def to_networkx(self) -> Any:
        try:
            import networkx as nx
        except ImportError:
            return None
        g = nx.DiGraph()
        for frm, to, action, count in self._edges:
            g.add_edge(frm, to, action=action, count=count)
        return g

    def to_mermaid(self) -> str:
        lines = ["flowchart LR"]
        for frm, to, action, count in self._edges:
            lines.append(f'  S{frm} -->|"{action} x{count}"| S{to}')
        return "\n".join(lines)
