"""Recover richer observations from screenshots via OCR engines."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from plugin.perception.capture_frame import CaptureFrame, frame_from_meta
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


def _spans_to_nodes(
    spans: Sequence[OCRSpan],
    *,
    engine_id: str = "",
    frame: Optional[CaptureFrame] = None,
) -> List[AxNode]:
    """Turn OCR spans into nodes, in the coordinate space the pointer speaks.

    OCR measures the screenshot, so its boxes are in captured pixels relative to
    that image's corner. The world model's bounds are clicked directly, and the
    pointer speaks screen points. Converting here — at the one place OCR
    geometry becomes world geometry — keeps every downstream consumer honest;
    the alternative, an entity whose bounds mean something different depending
    on which source produced it, is how a click ends up on empty screen while
    the log reports it landed on a chat row.
    """
    transform = frame or CaptureFrame()
    nodes: List[AxNode] = []
    for i, span in enumerate(spans):
        label = _clean_label(span.text)
        if not label:
            continue
        span_engine = span.engine or engine_id
        bbox = transform.bbox_to_screen(span.bbox) if not transform.is_identity else span.bbox
        nodes.append(
            AxNode(
                role="AXStaticText",
                name=label,
                description=label,
                value=None,
                enabled=True,
                bbox=bbox,
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


# A bound against a pathological read, not a relevance filter: a dense chat list
# runs well past sixty lines, and the ones past the cut are the recent messages
# at the bottom of the timeline.
MAX_OCR_LINES = 200


def _spans_to_lines(
    spans: Sequence[OCRSpan],
    *,
    frame: Optional[CaptureFrame] = None,
    limit: int = MAX_OCR_LINES,
) -> List[Dict[str, Any]]:
    """The OCR read as text, for the perceptor to reason over directly.

    OCR is an *input to* perception, not a competing account of it. Turning
    spans into pseudo-accessibility nodes (``_spans_to_nodes``) hands the runtime
    a second inventory of the screen that it must then reconcile against the real
    AX tree, which is the adjudication this design removes. The model is the only
    party that can sensibly decide whether a line of read text and an AX element
    are the same thing, so it should see the text.

    Bounds are converted to screen points here for the same reason as in
    ``_spans_to_nodes``: a rectangle that means captured pixels in one consumer
    and screen points in another is how a click lands on empty screen while the
    log claims it hit a chat row.
    """
    transform = frame or CaptureFrame()
    lines: List[Dict[str, Any]] = []
    for span in spans:
        label = _clean_label(span.text)
        if not label:
            continue
        bbox = transform.bbox_to_screen(span.bbox) if not transform.is_identity else span.bbox
        lines.append(
            {
                "text": label[:120],
                "bounds": [round(float(v), 1) for v in tuple(bbox)[:4]],
                "confidence": round(float(span.confidence), 3),
            }
        )
        if len(lines) >= limit:
            break
    return lines


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

    deduped = _dedupe_spans(chosen.spans)
    capture = frame_from_meta(obs.meta)
    ocr_nodes = _spans_to_nodes(
        deduped,
        engine_id=chosen.engine_id,
        frame=capture,
    )
    ocr_lines = _spans_to_lines(deduped, frame=capture)
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
                # The read itself, for the perceptor. Travels with the
                # observation so the packet does not have to re-derive it and
                # race the window moving in between.
                "lines": ocr_lines,
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
