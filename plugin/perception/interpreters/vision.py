"""Vision interpreter stub — Screen2AX / OCR → visibility & text hypotheses."""

from __future__ import annotations

from typing import List

from plugin.perception.hypothesis import EntityHypothesis
from plugin.perception.sources.base import ObservationBundle
from plugin.worldmodel.entities.normalize import _clean_label


class VisionInterpreter:
    """Maps vision/screen2ax observations into hypotheses (safe no-op if empty)."""

    interpreter_id = "vision"

    def __init__(self, *, source_prior: float = 0.76) -> None:
        self.source_prior = source_prior

    def interpret(self, bundle: ObservationBundle) -> List[EntityHypothesis]:
        obs = bundle.observation
        source = bundle.source_id or obs.source or "vision"
        if not obs.nodes:
            return []
        out: List[EntityHypothesis] = []
        prior = self.source_prior * (0.6 if bundle.degraded else 1.0)
        for n in obs.nodes:
            label = _clean_label(n.name or n.description or "")
            if not label:
                continue
            bounds = tuple(n.bbox) if n.bbox else (0.0, 0.0, 0.0, 0.0)
            attrs = dict(n.attributes or {})
            ocr_conf = attrs.get("ocr_confidence")
            confidence = prior
            if ocr_conf is not None:
                try:
                    confidence = max(0.05, min(0.99, float(ocr_conf)))
                except (TypeError, ValueError):
                    confidence = prior
            out.append(
                EntityHypothesis.make(
                    role=n.role or "vision",
                    label=label,
                    bounds=bounds,  # type: ignore[arg-type]
                    actions=[],
                    properties={
                        "exists": True,
                        "visible": True,
                        "label": label,
                        "text": label,
                        "ocr": bool(attrs.get("ocr", False)),
                    },
                    confidence=confidence,
                    source=source,
                    raw_refs={"vision": True, "ocr_confidence": ocr_conf},
                )
            )
        return out
