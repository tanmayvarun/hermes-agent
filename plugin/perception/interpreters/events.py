"""Event interpreter stub — AXObserver / focus / window change → hypotheses."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from plugin.perception.hypothesis import EntityHypothesis


class EventInterpreter:
    """Maps AXObserver-style events into lightweight hypotheses (future wire-up)."""

    interpreter_id = "events"

    def __init__(self, *, source_prior: float = 0.85) -> None:
        self.source_prior = source_prior

    def interpret_event(
        self,
        *,
        kind: str,
        label: str = "",
        role: str = "",
        focused: Optional[bool] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> List[EntityHypothesis]:
        kind_l = (kind or "").lower()
        props: Dict[str, Any] = {"exists": True}
        if focused is not None:
            props["focused"] = focused
        if label:
            props["label"] = label
        if "focus" in kind_l and label:
            return [
                EntityHypothesis.make(
                    role=role or "AXTextField",
                    label=label,
                    properties=props,
                    confidence=self.source_prior,
                    source="ax_observer",
                    raw_refs={"kind": kind, "meta": meta or {}, "ts": time.time()},
                )
            ]
        if "window" in kind_l:
            return [
                EntityHypothesis.make(
                    role="AXWindow",
                    label=label or "Window",
                    properties={"exists": True, "visible": True},
                    confidence=self.source_prior * 0.8,
                    source="ax_observer",
                    raw_refs={"kind": kind},
                )
            ]
        return []

    def interpret(self, bundle) -> List[EntityHypothesis]:
        meta = dict(getattr(bundle, "raw_meta", None) or {})
        ev = meta.get("event")
        if isinstance(ev, dict):
            return self.interpret_event(**ev)
        return []
