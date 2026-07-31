"""Recover richer observations from screenshots via OCR engines."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from plugin.perception.observation import AxNode, Observation
from plugin.worldmodel.entities.normalize import _clean_label

from .base import OCRRun, OCRSpan
from .engines import available_ocr_engines
from .selector import get_ocr_selector

OCR_COVERAGE_THRESHOLD = 0.80


def _estimated_coverage(obs: Observation) -> float:
    if obs.coverage is not None:
        return float(obs.coverage)
    return 1.0 if obs.nodes else 0.0


def _dedupe_spans(spans: Sequence[OCRSpan]) -> List[OCRSpan]:
    seen = set()
    out: List[OCRSpan] = []
    for span in spans:
        label = _clean_label(span.text)
        if not label:
            continue
        key = (label.lower(), tuple(round(v, 1) for v in span.bbox))
        if key in seen:
            continue
        seen.add(key)
        out.append(span)
    return out


def _spans_to_nodes(spans: Sequence[OCRSpan], *, engine_id: str = "") -> List[AxNode]:
    nodes: List[AxNode] = []
    for i, span in enumerate(spans):
        label = _clean_label(span.text)
        if not label:
            continue
        span_engine = span.engine or engine_id
        nodes.append(
            AxNode(
                role="AXStaticText",
                name=label,
                description=label,
                value=None,
                enabled=True,
                bbox=span.bbox,
                raw_id=f"ocr:{span_engine}:{i}",
                attributes={
                    "ocr": True,
                    "ocr_engine": span_engine,
                    "ocr_confidence": float(span.confidence),
                    "ocr_use_case": span.meta.get("use_case", ""),
                },
            )
        )
    return nodes


def _existing_text_key(node: AxNode) -> str:
    return _clean_label(node.name or node.description or "").lower()


def _merge_nodes(existing: Sequence[AxNode], ocr_nodes: Sequence[AxNode]) -> List[AxNode]:
    merged: List[AxNode] = list(existing)
    seen = {
        (_existing_text_key(n), tuple(round(float(v), 1) for v in (n.bbox or (0.0, 0.0, 0.0, 0.0))))
        for n in existing
    }
    for node in ocr_nodes:
        key = (_existing_text_key(node), tuple(round(float(v), 1) for v in (node.bbox or (0.0, 0.0, 0.0, 0.0))))
        if key in seen:
            continue
        seen.add(key)
        merged.append(node)
    return merged


def recover_observation_with_ocr(
    obs: Observation,
    *,
    use_case: str = "",
    force: bool = False,
    selector=None,
) -> Observation:
    """Return an OCR-augmented observation when a screenshot is available."""
    if not obs.screenshot_path:
        return obs

    should_try = force or _estimated_coverage(obs) < OCR_COVERAGE_THRESHOLD
    if not should_try:
        return obs

    sel = selector or get_ocr_selector()
    engines = available_ocr_engines()
    if not engines:
        obs.degraded = True
        obs.meta = {**obs.meta, "ocr": {"status": "missing_engines", "use_case": use_case}}
        return obs

    case = (use_case or obs.meta.get("ocr_use_case") or obs.app_name or "").strip()
    ranked = sel.rank(engines, use_case=case)
    runs: List[OCRRun] = []
    chosen: Optional[OCRRun] = None
    fallback: Optional[OCRRun] = None
    for engine in ranked[:2]:
        try:
            run = engine.recognize(str(obs.screenshot_path), use_case=case)
        except Exception as e:
            run = OCRRun(
                engine_id=getattr(engine, "engine_id", "ocr"),
                use_case=case,
                spans=[],
                meta={"error": str(e)},
                degraded=True,
            )
        sel.record(case, run)
        runs.append(run)
        if fallback is None or run.score() > fallback.score():
            fallback = run
        if run.success() and run.score() >= sel.min_accept_score:
            chosen = run
            break
    if chosen is None:
        chosen = fallback

    if chosen is None or not chosen.spans:
        obs.degraded = True
        obs.meta = {
            **obs.meta,
            "ocr": {
                "status": "empty",
                "use_case": case,
                "candidates": [r.to_dict() for r in runs],
            },
        }
        return obs

    ocr_nodes = _spans_to_nodes(_dedupe_spans(chosen.spans), engine_id=chosen.engine_id)
    merged_nodes = _merge_nodes(obs.nodes or [], ocr_nodes)
    score = chosen.score()
    return Observation(
        timestamp=obs.timestamp,
        app_name=obs.app_name,
        window_name=obs.window_name,
        bundle_id=obs.bundle_id,
        ax_tree=obs.ax_tree,
        nodes=merged_nodes,
        screenshot_path=obs.screenshot_path,
        source=f"screen2ax:{chosen.engine_id}",
        coverage=min(1.0, max(float(obs.coverage or 0.0), score)),
        degraded=bool(obs.degraded and score < sel.min_accept_score),
        meta={
            **obs.meta,
            "ocr": {
                "status": "applied",
                "use_case": case,
                "selected_engine": chosen.engine_id,
                "score": round(score, 4),
                "mean_confidence": round(chosen.mean_confidence(), 4),
                "candidate_runs": [r.to_dict() for r in runs],
            },
        },
    )


def prewarm_ocr_engines(*, use_case: str = "", selector=None) -> Dict[str, Any]:
    """Load OCR engines once so the first live observation does not pay cold-start cost."""
    sel = selector or get_ocr_selector()
    engines = available_ocr_engines()
    case = (use_case or "").strip()
    ranked = sel.rank(engines, use_case=case)
    chosen = ranked[:2]
    warmed: List[str] = []
    errors: List[Dict[str, str]] = []
    if not chosen:
        return {"status": "missing_engines", "use_case": case, "warmed": warmed, "errors": errors}

    from PIL import Image

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        Image.new("RGB", (8, 8), color="white").save(tmp_path)
        for engine in chosen:
            engine_id = getattr(engine, "engine_id", "ocr")
            try:
                warm_fn = getattr(engine, "_reader", None) or getattr(engine, "_model", None)
                if callable(warm_fn):
                    warm_fn()
                else:
                    engine.recognize(str(tmp_path), use_case=case)
                warmed.append(engine_id)
            except Exception as exc:
                errors.append({"engine_id": engine_id, "error": str(exc)})
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
    return {
        "status": "ok" if warmed else "failed",
        "use_case": case,
        "warmed": warmed,
        "errors": errors or None,
    }
