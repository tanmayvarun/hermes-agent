"""OCR engines and recovery helpers for screenshot-backed perception."""

from .base import OCRRun, OCRSpan, OCREngine, OCREngineStats
from .engines import EasyOCREngine, PaddleOCREngine, available_ocr_engines
from .recovery import prewarm_ocr_engines, recover_observation_with_ocr
from .selector import OCRSelector, get_ocr_selector

__all__ = [
    "EasyOCREngine",
    "OCRRun",
    "OCRSelector",
    "OCREngine",
    "OCREngineStats",
    "OCRSpan",
    "PaddleOCREngine",
    "prewarm_ocr_engines",
    "available_ocr_engines",
    "get_ocr_selector",
    "recover_observation_with_ocr",
]
