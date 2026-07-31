"""Recover richer observations from screenshots via screen-perception models."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from plugin.perception.observation import AxNode, Observation
from plugin.worldmodel.entities.normalize import _clean_label

from .base import ScreenElement, ScreenModelRun
from .engines import elements_from_payload
from .registry import list_screen_models
from .selector import get_screen_model_selector

SCREEN_MODEL_COVERAGE_THRESHOLD = 0.80


def _estimated_coverage(obs: Observation) -> float:
    if obs.coverage is not None:
        return float(obs.coverage)
    return 1.0 if obs.nodes else 0.0


def _dedupe_elements(elements: Sequence[ScreenElement]) -> List[ScreenElement]:
    seen = set()
    out: List[ScreenElement] = []
    for element in elements:
        label = _clean_label(element.label or element.text or element.icon_description)
        if not label:
            continue
        key = (label.lower(), tuple(round(v, 1) for v in element.bbox))
        if key in seen:
            continue
        seen.add(key)
        out.append(element)
    return out


def _elements_to_nodes(elements: Sequence[ScreenElement], *, model_id: str = "") -> List[AxNode]:
    nodes: List[AxNode] = []
    for i, element in enumerate(elements):
        label = _clean_label(element.label or element.text or element.icon_description)
        if not label:
            continue
        role = "AXButton" if element.interactive else "AXStaticText"
        nodes.append(
            AxNode(
                role=role,
                name=label,
                description=element.icon_description or label,
                value=None,
                enabled=bool(element.interactive),
                bbox=element.bbox,
                raw_id=f"screen_model:{element.source or model_id}:{i}",
                attributes={
                    "screen_model": True,
                    "screen_model_id": element.source or model_id,
                    "screen_model_confidence": float(element.confidence),
                    "screen_model_interactive": bool(element.interactive),
                    "screen_model_text": element.text,
                    "screen_model_icon_description": element.icon_description,
                    "screen_model_meta": dict(element.meta or {}),
                },
            )
        )
    return nodes


def _merge_nodes(existing: Sequence[AxNode], extra: Sequence[AxNode]) -> List[AxNode]:
    merged: List[AxNode] = list(existing)
    seen = {
        (_clean_label(n.name or n.description or "").lower(), tuple(round(float(v), 1) for v in (n.bbox or (0.0, 0.0, 0.0, 0.0))))
        for n in existing
    }
    for node in extra:
        key = (_clean_label(node.name or node.description or "").lower(), tuple(round(float(v), 1) for v in (node.bbox or (0.0, 0.0, 0.0, 0.0))))
        if key in seen:
            continue
        seen.add(key)
        merged.append(node)
    return merged


def recover_observation_with_screen_models(
    obs: Observation,
    *,
    use_case: str = "",
    force: bool = False,
    selector=None,
) -> Observation:
    """Return a screen-model-augmented observation when a screenshot is available."""
    if not obs.screenshot_path:
        return obs

    should_try = force or _estimated_coverage(obs) < SCREEN_MODEL_COVERAGE_THRESHOLD
    if not should_try:
        return obs

    sel = selector or get_screen_model_selector()
    models = list(getattr(obs, "screen_models", None) or [])
    if not models:
        models = list_screen_models()
    if not models:
        return obs

    case = (use_case or obs.meta.get("screen_model_use_case") or obs.app_name or "").strip()
    ranked = sel.rank(models, use_case=case)
    runs: List[ScreenModelRun] = []
    chosen: Optional[ScreenModelRun] = None
    fallback: Optional[ScreenModelRun] = None
    for model in ranked[:2]:
        try:
            run = model.parse(str(obs.screenshot_path), use_case=case)
        except Exception as e:
            run = ScreenModelRun(
                model_id=getattr(model, "model_id", "screen_model"),
                use_case=case,
                elements=[],
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

    if chosen is None or not chosen.elements:
        obs.degraded = True
        obs.meta = {
            **obs.meta,
            "screen_models": {
                "status": "empty",
                "use_case": case,
                "candidate_runs": [r.to_dict() for r in runs],
            },
        }
        return obs

    model_elements = _dedupe_elements(chosen.elements)
    nodes = _elements_to_nodes(model_elements, model_id=chosen.model_id)
    merged_nodes = _merge_nodes(obs.nodes or [], nodes)
    score = chosen.score()
    return Observation(
        timestamp=obs.timestamp,
        app_name=obs.app_name,
        window_name=obs.window_name,
        bundle_id=obs.bundle_id,
        ax_tree=obs.ax_tree,
        nodes=merged_nodes,
        screenshot_path=obs.screenshot_path,
        source=f"screen_model:{chosen.model_id}",
        coverage=min(1.0, max(float(obs.coverage or 0.0), score)),
        degraded=bool(obs.degraded and score < sel.min_accept_score),
        meta={
            **obs.meta,
            "screen_models": {
                "status": "applied",
                "use_case": case,
                "selected_model": chosen.model_id,
                "score": round(score, 4),
                "mean_confidence": round(chosen.mean_confidence(), 4),
                "candidate_runs": [r.to_dict() for r in runs],
            },
        },
    )


def maybe_recover_with_screen_models(obs: Observation, *, use_case: str = "", force: bool = False) -> Observation:
    """Backward-compatible alias for screenshot screen-model recovery."""
    return recover_observation_with_screen_models(obs, use_case=use_case, force=force)
