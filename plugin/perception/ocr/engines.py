"""Local OCR engine adapters."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .base import OCRRun, OCRSpan


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


class EasyOCREngine:
    engine_id = "easyocr"
    _reader_cache: Dict[Tuple[str, bool], Any] = {}

    def __init__(self, *, languages: Optional[Sequence[str]] = None, gpu: bool = False) -> None:
        self.languages = tuple(languages or ("en",))
        self.gpu = bool(gpu)

    def _reader(self):
        key = (",".join(self.languages), self.gpu)
        cached = self._reader_cache.get(key)
        if cached is not None:
            return cached
        import easyocr  # type: ignore

        reader = easyocr.Reader(list(self.languages), gpu=self.gpu)
        self._reader_cache[key] = reader
        return reader

    def recognize(self, screenshot_path: str, *, use_case: str = "") -> OCRRun:
        reader = self._reader()
        raw = reader.readtext(str(screenshot_path), detail=1, paragraph=False)
        spans: List[OCRSpan] = []
        for i, item in enumerate(raw or []):
            if not isinstance(item, (list, tuple)) or len(item) < 3:
                continue
            bbox, text, conf = item[:3]
            label = str(text or "").strip()
            if not label:
                continue
            spans.append(
                OCRSpan(
                    text=label,
                    bbox=_bbox_from_points(bbox),
                    confidence=float(conf or 0.0),
                    engine=self.engine_id,
                    line_index=i,
                    meta={"engine": self.engine_id, "use_case": use_case},
                )
            )
        return OCRRun(
            engine_id=self.engine_id,
            use_case=use_case,
            spans=spans,
            meta={"languages": list(self.languages), "gpu": self.gpu},
        )


class PaddleOCREngine:
    engine_id = "paddleocr"
    _model_cache: Dict[Tuple[str, str], Any] = {}

    def __init__(self, *, engine: str = "paddle", use_textline_orientation: bool = False) -> None:
        self.engine = engine
        self.use_textline_orientation = bool(use_textline_orientation)

    def _model(self):
        key = (self.engine, str(self.use_textline_orientation))
        cached = self._model_cache.get(key)
        if cached is not None:
            return cached
        from paddleocr import PaddleOCR  # type: ignore

        model = PaddleOCR(
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=self.use_textline_orientation,
            engine=self.engine,
        )
        self._model_cache[key] = model
        return model

    def _extract_spans(self, raw: Any, *, use_case: str = "") -> List[OCRSpan]:
        spans: List[OCRSpan] = []

        def _add(text: Any, bbox: Any, conf: Any, index: int) -> None:
            label = str(text or "").strip()
            if not label:
                return
            try:
                confidence = float(conf or 0.0)
            except (TypeError, ValueError):
                confidence = 0.0
            spans.append(
                OCRSpan(
                    text=label,
                    bbox=_bbox_from_points(bbox),
                    confidence=confidence,
                    engine=self.engine_id,
                    line_index=index,
                    meta={"engine": self.engine_id, "use_case": use_case},
                )
            )

        def _walk(obj: Any) -> None:
            if obj is None:
                return
            if isinstance(obj, (list, tuple)):
                for item in obj:
                    _walk(item)
                return
            mapping = _coerce_mapping(obj)
            if not mapping:
                return
            res = mapping.get("res") if isinstance(mapping.get("res"), dict) else mapping
            if not isinstance(res, dict):
                return
            if "rec_text" in res:
                _add(res.get("rec_text"), res.get("rec_boxes") or res.get("bbox"), res.get("rec_score"), len(spans))
                return
            texts = res.get("rec_texts")
            scores = res.get("rec_scores") or []
            boxes = res.get("rec_boxes") or res.get("dt_polys") or res.get("rec_polys") or []
            if isinstance(texts, list):
                for idx, text in enumerate(texts):
                    conf = scores[idx] if idx < len(scores) else res.get("rec_score", 0.0)
                    box = boxes[idx] if isinstance(boxes, list) and idx < len(boxes) else boxes
                    _add(text, box, conf, len(spans))
                return
            if "text" in res:
                _add(res.get("text"), res.get("bbox") or res.get("box"), res.get("score"), len(spans))

        _walk(raw)
        return spans

    def recognize(self, screenshot_path: str, *, use_case: str = "") -> OCRRun:
        model = self._model()
        raw = model.predict(str(screenshot_path))
        spans = self._extract_spans(raw, use_case=use_case)
        return OCRRun(
            engine_id=self.engine_id,
            use_case=use_case,
            spans=spans,
            meta={"engine": self.engine, "use_textline_orientation": self.use_textline_orientation},
        )


def available_ocr_engines() -> List[Any]:
    engines: List[Any] = []
    try:
        engines.append(EasyOCREngine())
    except Exception:
        pass
    try:
        engines.append(PaddleOCREngine())
    except Exception:
        pass
    return engines
