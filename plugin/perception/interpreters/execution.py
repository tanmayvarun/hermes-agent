"""Execution feedback → hypotheses (typed text, click landed)."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from plugin.perception.hypothesis import EntityHypothesis


class ExecutionInterpreter:
    """Turns executor evidence into world hypotheses (not AX trees)."""

    interpreter_id = "execution"

    def __init__(self, *, source_prior: float = 0.88) -> None:
        self.source_prior = source_prior

    def interpret_feedback(
        self,
        *,
        action: str = "",
        target: str = "",
        text: str = "",
        ok: bool = True,
        message: str = "",
    ) -> List[EntityHypothesis]:
        if not ok:
            return []
        out: List[EntityHypothesis] = []
        act = (action or "").lower()
        if act == "type" and text:
            out.append(
                EntityHypothesis.make(
                    role="AXTextField",
                    label="Search",
                    properties={
                        "exists": True,
                        "focused": True,
                        "value": text,
                        "label": "Search",
                    },
                    confidence=self.source_prior,
                    source="execution",
                    raw_refs={"message": message[:200], "ts": time.time()},
                )
            )
        if act == "click" and target:
            out.append(
                EntityHypothesis.make(
                    role="AXButton",
                    label=target,
                    properties={"exists": True, "visible": True, "label": target},
                    confidence=self.source_prior * 0.9,
                    source="execution",
                    raw_refs={"message": message[:200]},
                )
            )
        return out

    def interpret(self, bundle) -> List[EntityHypothesis]:
        # Execution is not an ObservationBundle sensor — no-op for bus observe
        meta = dict(getattr(bundle, "raw_meta", None) or {})
        if meta.get("execution"):
            return self.interpret_feedback(**(meta.get("execution") or {}))
        return []
