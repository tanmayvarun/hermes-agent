"""Model-family adapters for screen-perception backends."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .base import ScreenElement, ScreenModelRun


def _bbox_from_points(points: Any) -> Tuple[float, float, float, float]:
    if isinstance(points, (list, tuple)) and points:
        xs: List[float] = []
        ys: List[float] = []
        for p in points:
            if isinstance(p, (list, tuple)) and len(p) >= 2:
                try:
                    xs.append(float(p[0]))
                    ys.append(float(p[1]))
                except (TypeError, ValueError):
                    continue
        if xs and ys:
            return (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
    if isinstance(points, (list, tuple)) and len(points) >= 4:
        try:
            x1, y1, x2, y2 = (float(points[0]), float(points[1]), float(points[2]), float(points[3]))
            return (x1, y1, max(0.0, x2 - x1), max(0.0, y2 - y1))
        except (TypeError, ValueError):
            pass
    return (0.0, 0.0, 0.0, 0.0)


def _coerce_mapping(obj: Any) -> Dict[str, Any]:
    if isinstance(obj, dict):
        return obj
    for method in ("to_dict", "dict", "json"):
        fn = getattr(obj, method, None)
        if callable(fn):
            try:
                out = fn()
                if isinstance(out, dict):
                    return out
                if isinstance(out, str):
                    import json

                    parsed = json.loads(out)
                    if isinstance(parsed, dict):
                        return parsed
            except Exception:
                continue
    if hasattr(obj, "__dict__"):
        try:
            return dict(obj.__dict__)
        except Exception:
            return {}
    return {}


def elements_from_payload(payload: Any, *, source: str = "") -> List[ScreenElement]:
    """Normalize a loose parser payload into ScreenElement objects."""
    out: List[ScreenElement] = []

    def _add(element: Any, index: int) -> None:
        mapping = _coerce_mapping(element)
        if not mapping:
            return
        bbox = mapping.get("bbox") or mapping.get("box") or mapping.get("bounds") or mapping.get("rect")
        label = str(
            mapping.get("label")
            or mapping.get("text")
            or mapping.get("name")
            or mapping.get("title")
            or ""
        ).strip()
        icon = str(mapping.get("icon_description") or mapping.get("icon") or "").strip()
        text = str(mapping.get("text") or mapping.get("label") or mapping.get("name") or "").strip()
        interactive = bool(mapping.get("interactive", False))
        confidence = mapping.get("confidence", mapping.get("score", 0.0))
        try:
            conf_f = float(confidence or 0.0)
        except (TypeError, ValueError):
            conf_f = 0.0
        element_id = str(mapping.get("id") or mapping.get("element_id") or index)
        meta = dict(mapping.get("meta") or {})
        for key in ("kind", "role", "region", "source", "engine"):
            if key in mapping and key not in meta:
                meta[key] = mapping.get(key)
        out.append(
            ScreenElement(
                element_id=element_id,
                label=label or text or icon,
                bbox=_bbox_from_points(bbox),
                text=text or label,
                icon_description=icon,
                interactive=interactive,
                confidence=conf_f,
                source=str(mapping.get("source") or source or ""),
                meta=meta,
            )
        )

    if isinstance(payload, dict):
        candidates = payload.get("elements") or payload.get("items") or payload.get("nodes") or []
        if isinstance(candidates, list):
            for idx, element in enumerate(candidates):
                _add(element, idx)
            return out
        _add(payload, 0)
        return out
    if isinstance(payload, (list, tuple)):
        for idx, element in enumerate(payload):
            _add(element, idx)
    return out


class ScreenParserAdapter:
    """Generic callable-backed parser wrapper."""

    model_id = "screen-parser"

    def __init__(self, *, model_id: str = "screen-parser", infer_fn: Optional[Callable[..., Any]] = None) -> None:
        self.model_id = model_id
        self.infer_fn = infer_fn

    def parse(self, screenshot_path: str, *, use_case: str = "") -> ScreenModelRun:
        if self.infer_fn is None:
            return ScreenModelRun(
                model_id=self.model_id,
                use_case=use_case,
                elements=[],
                degraded=True,
                meta={"error": "screen parser unavailable"},
            )
        raw = self.infer_fn(screenshot_path, use_case=use_case)
        return ScreenModelRun(
            model_id=self.model_id,
            use_case=use_case,
            elements=elements_from_payload(raw, source=self.model_id),
            meta={"raw_type": type(raw).__name__},
            degraded=False,
        )


class CallableScreenParser(ScreenParserAdapter):
    """Alias for backward readability."""


class OmniParserV2Parser(ScreenParserAdapter):
    model_id = "omniparser_v2"
