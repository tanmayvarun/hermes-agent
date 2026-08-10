"""Did the multimodal model fuse AX + pixels (+ OCR) into the right reading?

Rival source reconciliation is gone: assembly hands every modality to one
model. These metrics ask whether that model did the job — naming the surface
the screen actually shows and finding goal-relevant objects when AX is chrome-
only. Action choice is the brain's job and is not scored here.

Gold comes from annotations (contract / outcome / shadow / manual), never from
the reply being scored. A model that confidently misreads the screen and is
scored against its own reply would look perfect.

Usage:
    python -m plugin.evals.run                     # offline corpus fusion block
    python -m plugin.evals.fusion --live \\
        --models ollama-cloud/gpt-oss:120b,ollama-cloud/qwen3.5:397b --limit 8
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from plugin.evals.corpus import (
    DEFAULT_CORPUS_DIR,
    DEFAULT_RECORD_DIR,
    Fixture,
    TRAIT_NO_AX_CONTENT,
    TRAIT_SHELL_ONLY,
    TRAIT_TARGET_VISIBLE,
    load_fixtures,
    model_surface,
)
from plugin.evals.metrics import MetricResult

LAYER_FUSION = "fusion"


def _rate(hits: float, total: float) -> Optional[float]:
    return None if total <= 0 else hits / total


def _norm(text: Any) -> str:
    return str(text or "").strip().lower()


def _tokens(text: Any) -> List[str]:
    return [t for t in re.findall(r"[a-z0-9]+", _norm(text)) if len(t) > 2]


def gold_surface(fixture: Fixture) -> str:
    """Annotated surface, when any non-empty label exists."""
    return _norm((fixture.annotation or {}).get("surface"))


def _proposal_from_response(response: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(response, dict):
        return {}
    return {
        "world_model": dict(response.get("world_model") or {}),
        "observed_state": dict(response.get("observed_state") or {}),
        "next_action": dict(response.get("next_action") or {}),
        "confidence": response.get("confidence"),
        "model": str(response.get("model") or ""),
        "latency_s": float(response.get("latency_s") or 0.0),
        "scene_summary": str(response.get("scene_summary") or ""),
    }


def _objects(reading: Dict[str, Any]) -> List[Dict[str, Any]]:
    document = reading.get("world_model") if isinstance(reading.get("world_model"), dict) else {}
    objects = [o for o in (document.get("objects") or []) if isinstance(o, dict)]
    if objects:
        return objects
    # Some replies only put objects on observed_state.
    state = reading.get("observed_state") if isinstance(reading.get("observed_state"), dict) else {}
    return [o for o in (state.get("objects") or []) if isinstance(o, dict)]


def _surface_of(reading: Dict[str, Any]) -> str:
    document = reading.get("world_model") if isinstance(reading.get("world_model"), dict) else {}
    state = reading.get("observed_state") if isinstance(reading.get("observed_state"), dict) else {}
    return _norm(document.get("surface") or state.get("surface"))


def _goal_tokens(fixture: Fixture) -> List[str]:
    goal = fixture.goal
    parts = [
        goal.get("source_conversation"),
        goal.get("source_query"),
        goal.get("destination"),
        goal.get("contact"),
        goal.get("link_query"),
    ]
    found: List[str] = []
    seen = set()
    for part in parts:
        for token in _tokens(part):
            if token not in seen:
                seen.add(token)
                found.append(token)
    return found


def _object_mentions_goal(obj: Dict[str, Any], goal_tokens: Sequence[str]) -> bool:
    if bool(obj.get("matches_goal")):
        return True
    blob = " ".join(
        str(obj.get(key) or "") for key in ("text", "label", "id", "kind", "description")
    )
    words = set(_tokens(blob))
    return bool(words & set(goal_tokens))


@dataclass
class FusionCheck:
    name: str
    passed: bool
    detail: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass
class FusionScore:
    fixture_id: str
    model: str = ""
    latency_s: float = 0.0
    checks: List[FusionCheck] = field(default_factory=list)
    surface_gold: str = ""
    surface_got: str = ""
    action_family: str = ""

    @property
    def score(self) -> float:
        if not self.checks:
            return 0.0
        return round(sum(1 for c in self.checks if c.passed) / len(self.checks), 4)

    def failures(self) -> List[str]:
        return [f"{c.name}: {c.detail}" for c in self.checks if not c.passed]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "model": self.model,
            "latency_s": round(self.latency_s, 3),
            "score": self.score,
            "surface_gold": self.surface_gold,
            "surface_got": self.surface_got,
            "action_family": self.action_family,
            "checks": [c.to_dict() for c in self.checks],
            "failures": self.failures(),
        }


def score_fusion_reading(
    fixture: Fixture,
    reading: Optional[Dict[str, Any]],
    *,
    model: str = "",
    latency_s: float = 0.0,
) -> FusionScore:
    """Grade one multimodal reading for fusion correctness against gold."""
    result = FusionScore(
        fixture_id=fixture.id,
        model=model or str((reading or {}).get("model") or ""),
        latency_s=latency_s or float((reading or {}).get("latency_s") or 0.0),
    )
    gold = gold_surface(fixture)
    result.surface_gold = gold

    if not reading:
        result.checks = [FusionCheck("model_returned_a_reading", False, "no parseable response")]
        return result

    got = _surface_of(reading)
    result.surface_got = got
    objects = _objects(reading)
    traits = set(fixture.traits or ())
    ax_blind = TRAIT_SHELL_ONLY in traits or TRAIT_NO_AX_CONTENT in traits

    if gold:
        result.checks.append(
            FusionCheck(
                "surface_matches_gold",
                got == gold,
                f"gold={gold!r} got={got!r}",
            )
        )
    else:
        result.checks.append(
            FusionCheck("surface_labelled", False, "fixture has no gold surface; skipped match")
        )
        # Still require *a* surface so blind empties fail.
        result.checks.append(
            FusionCheck("surface_reported", bool(got), got or "empty")
        )

    # The hard case for fusion: AX is chrome-only, so any content objects the
    # model reports came from the screenshot / OCR, not accessibility.
    if ax_blind:
        result.checks.append(
            FusionCheck(
                "sees_content_when_ax_blind",
                len(objects) >= 1,
                f"objects={len(objects)} ax_content={fixture.observation.get('ax_content_node_count')}",
            )
        )

    goal_tokens = _goal_tokens(fixture)
    if TRAIT_TARGET_VISIBLE in traits or goal_tokens:
        mentioned = [o for o in objects if _object_mentions_goal(o, goal_tokens)]
        result.checks.append(
            FusionCheck(
                "goal_object_identified",
                bool(mentioned),
                f"matches={len(mentioned)} tokens={goal_tokens[:4]}",
            )
        )

    # Search / list surfaces must not treat the typed query as an open chat —
    # that is the fusion failure that skipped the open step live.
    open_conv = _norm(
        (reading.get("world_model") or {}).get("open_conversation")
        or (reading.get("observed_state") or {}).get("open_conversation")
    )
    query = _norm(fixture.goal.get("source_query") or fixture.goal.get("link_query"))
    contact = _norm(fixture.goal.get("source_conversation") or fixture.goal.get("contact"))
    echo = bool(open_conv) and gold in {"search", "chat_list"} and (
        (query and query in open_conv)
        or (contact and open_conv == contact)
    )
    result.checks.append(
        FusionCheck(
            "open_conversation_not_search_echo",
            not echo,
            f"open={open_conv!r} gold_surface={gold!r}",
        )
    )

    return result


def fusion_surface_accuracy(fixtures: Sequence[Fixture]) -> MetricResult:
    hits = 0
    scored = 0
    skipped = 0
    wrong: List[str] = []
    for fixture in fixtures:
        gold = gold_surface(fixture)
        if not gold or not fixture.response:
            skipped += 1
            continue
        scored += 1
        got = model_surface(fixture) or _surface_of(_proposal_from_response(fixture.response))
        if got == gold:
            hits += 1
        elif len(wrong) < 12:
            wrong.append(f"{fixture.id}: gold={gold} got={got or 'none'}")
    return MetricResult(
        name="fusion_surface_accuracy",
        layer=LAYER_FUSION,
        value=_rate(hits, scored),
        scored=scored,
        skipped=skipped,
        question="Did the multimodal reading name the gold surface?",
        examples=wrong,
    )


def fusion_ax_blind_content_recall(fixtures: Sequence[Fixture]) -> MetricResult:
    hits = 0
    scored = 0
    skipped = 0
    misses: List[str] = []
    for fixture in fixtures:
        traits = set(fixture.traits or ())
        if TRAIT_SHELL_ONLY not in traits and TRAIT_NO_AX_CONTENT not in traits:
            skipped += 1
            continue
        if not fixture.response:
            skipped += 1
            continue
        scored += 1
        objects = _objects(_proposal_from_response(fixture.response))
        if objects:
            hits += 1
        elif len(misses) < 12:
            misses.append(f"{fixture.id}: 0 objects on AX-blind frame")
    return MetricResult(
        name="fusion_ax_blind_content_recall",
        layer=LAYER_FUSION,
        value=_rate(hits, scored),
        scored=scored,
        skipped=skipped,
        question="When AX is chrome-only, did the model still report content objects?",
        examples=misses,
    )


def fusion_goal_object_recall(fixtures: Sequence[Fixture]) -> MetricResult:
    hits = 0
    scored = 0
    skipped = 0
    misses: List[str] = []
    for fixture in fixtures:
        if TRAIT_TARGET_VISIBLE not in set(fixture.traits or ()):
            skipped += 1
            continue
        if not fixture.response:
            skipped += 1
            continue
        scored += 1
        tokens = _goal_tokens(fixture)
        objects = _objects(_proposal_from_response(fixture.response))
        if any(_object_mentions_goal(o, tokens) for o in objects):
            hits += 1
        elif len(misses) < 12:
            misses.append(f"{fixture.id}: no object matched {tokens[:3]}")
    return MetricResult(
        name="fusion_goal_object_recall",
        layer=LAYER_FUSION,
        value=_rate(hits, scored),
        scored=scored,
        skipped=skipped,
        question="Was a goal-relevant object present in the fused reading?",
        examples=misses,
    )


FUSION_METRICS = (
    fusion_surface_accuracy,
    fusion_ax_blind_content_recall,
    fusion_goal_object_recall,
)


def summarize_fusion(fixtures: Sequence[Fixture]) -> Dict[str, Any]:
    """Offline fusion block over the corpus's recorded multimodal replies."""
    metrics = []
    for metric in FUSION_METRICS:
        try:
            metrics.append(metric(fixtures).to_dict())
        except Exception as exc:
            metrics.append(
                {
                    "name": getattr(metric, "__name__", "metric"),
                    "layer": LAYER_FUSION,
                    "value": None,
                    "question": f"failed: {exc}"[:160],
                }
            )
    per_fixture = []
    for fixture in fixtures:
        if not fixture.response:
            continue
        score = score_fusion_reading(fixture, _proposal_from_response(fixture.response))
        per_fixture.append(score.to_dict())
    mean = (
        round(sum(f["score"] for f in per_fixture) / len(per_fixture), 4) if per_fixture else None
    )
    return {
        "fixtures_scored": len(per_fixture),
        "mean_fusion_score": mean,
        "metrics": metrics,
        "worst": sorted(per_fixture, key=lambda f: f["score"])[:8],
    }


def resolve_screenshot(fixture: Fixture, record_dir: Path) -> Optional[Path]:
    name = str((fixture.screenshot or {}).get("name") or "").strip()
    if not name:
        return None
    path = record_dir / name
    return path if path.is_file() else None


def _parse_model_spec(spec: str) -> Dict[str, str]:
    """``provider/model`` or bare ``model`` (provider defaults to ollama-cloud)."""
    text = str(spec or "").strip()
    if not text:
        raise ValueError("empty model spec")
    if "/" in text:
        provider, model = text.split("/", 1)
    else:
        provider, model = "ollama-cloud", text
    return {"provider": provider.strip(), "model": model.strip()}


def replay_on_model(
    fixture: Fixture,
    *,
    record_dir: Path,
    provider: str,
    model: str,
    timeout_s: float = 120.0,
) -> Tuple[Optional[Dict[str, Any]], float, str]:
    """Re-ask one model about a frozen multimodal packet + screenshot."""
    from plugin.agent.perception_synthesis import (
        _call_llm_hard_timeout,
        _main_runtime_snapshot,
        _perception_extra_body,
        _perception_max_tokens,
        _perception_reasoning_config,
    )
    from plugin.agent.reasoning_consultation import consult_reasoning
    from plugin.agent.unified_cognition import (
        ALLOWED_ACTIONS,
        UNIFIED_TASK,
        _build_messages,
        _parse_proposal,
    )

    packet = dict(fixture.packet or {})
    packet["allowed_actions"] = list(ALLOWED_ACTIONS)
    image = resolve_screenshot(fixture, record_dir)
    messages, _ = _build_messages(packet, str(image) if image else "")
    main_runtime = _main_runtime_snapshot()
    target = {"provider": provider, "model": model}
    started = time.time()
    try:
        consultation = consult_reasoning(
            UNIFIED_TASK,
            messages,
            caller=lambda **kwargs: _call_llm_hard_timeout(timeout_s, **kwargs),
            call_kwargs={
                "task": UNIFIED_TASK,
                "provider": provider or None,
                "model": model or None,
                "timeout": timeout_s,
                "main_runtime": main_runtime,
                "extra_body": _perception_extra_body(main_runtime),
                "reasoning_config": _perception_reasoning_config(target),
            },
            temperature=0.0,
            max_tokens=max(512, _perception_max_tokens()),
        )
    except Exception as exc:
        return None, time.time() - started, str(exc)[:200]
    if not consultation.parsed:
        return None, time.time() - started, "empty parse"
    proposal = _parse_proposal(consultation.parsed)
    latency = time.time() - started
    reading = {
        "world_model": dict(proposal.world_model or {}),
        "observed_state": dict(proposal.observed_state or {}),
        "next_action": dict(proposal.next_action or {}),
        "confidence": proposal.confidence,
        "model": model,
        "latency_s": latency,
        "scene_summary": proposal.scene_summary,
    }
    return reading, latency, ""


def bake_off(
    fixtures: Sequence[Fixture],
    model_specs: Sequence[str],
    *,
    record_dir: Path,
    limit: int = 0,
    timeout_s: float = 120.0,
) -> Dict[str, Any]:
    """Run the same fixtures through each model; return a comparable table."""
    selected = list(fixtures)
    if limit:
        selected = selected[: max(0, int(limit))]
    # Prefer AX-blind frames — they are the ones that require real fusion.
    selected.sort(
        key=lambda f: 0
        if (TRAIT_SHELL_ONLY in (f.traits or ()) or TRAIT_NO_AX_CONTENT in (f.traits or ()))
        else 1
    )
    if limit:
        selected = selected[: max(0, int(limit))]

    by_model: Dict[str, Dict[str, Any]] = {}
    for spec in model_specs:
        target = _parse_model_spec(spec)
        key = f"{target['provider']}/{target['model']}"
        scores: List[FusionScore] = []
        errors: List[str] = []
        for fixture in selected:
            reading, latency, err = replay_on_model(
                fixture,
                record_dir=record_dir,
                provider=target["provider"],
                model=target["model"],
                timeout_s=timeout_s,
            )
            if err and reading is None:
                errors.append(f"{fixture.id}: {err}")
            scores.append(
                score_fusion_reading(
                    fixture,
                    reading,
                    model=target["model"],
                    latency_s=latency,
                )
            )
        mean = (
            round(sum(s.score for s in scores) / len(scores), 4) if scores else None
        )
        by_model[key] = {
            "provider": target["provider"],
            "model": target["model"],
            "frames": len(scores),
            "mean_fusion_score": mean,
            "mean_latency_s": round(
                sum(s.latency_s for s in scores) / len(scores), 3
            )
            if scores
            else None,
            "check_rates": _check_rates(scores),
            "errors": errors[:12],
            "frames_detail": [s.to_dict() for s in scores],
        }
    ranking = sorted(
        (
            {
                "model": name,
                "mean_fusion_score": payload.get("mean_fusion_score"),
                "mean_latency_s": payload.get("mean_latency_s"),
            }
            for name, payload in by_model.items()
        ),
        key=lambda row: (-(row["mean_fusion_score"] or -1.0), row["mean_latency_s"] or 1e9),
    )
    return {
        "mode": "live_bake_off",
        "fixture_count": len(selected),
        "models": by_model,
        "ranking": ranking,
    }


def _check_rates(scores: Sequence[FusionScore]) -> Dict[str, float]:
    totals: Dict[str, List[int]] = {}
    for score in scores:
        for check in score.checks:
            bucket = totals.setdefault(check.name, [0, 0])
            bucket[1] += 1
            if check.passed:
                bucket[0] += 1
    return {
        name: round(hits / total, 4) if total else 0.0
        for name, (hits, total) in sorted(totals.items())
    }


def render_bake_off(report: Dict[str, Any]) -> str:
    lines = [
        f"Multimodal fusion bake-off — {report.get('fixture_count', 0)} fixtures",
        "",
        f"{'model':<42} {'fusion':>8} {'latency':>10}",
    ]
    for row in report.get("ranking") or []:
        score = row.get("mean_fusion_score")
        latency = row.get("mean_latency_s")
        lines.append(
            f"{str(row.get('model') or ''):<42} "
            f"{(f'{score:.2%}' if score is not None else 'n/a'):>8} "
            f"{(f'{latency:.1f}s' if latency is not None else 'n/a'):>10}"
        )
    models = report.get("models") or {}
    for name, payload in models.items():
        lines.append("")
        lines.append(f"[{name}]")
        for check, rate in (payload.get("check_rates") or {}).items():
            lines.append(f"  {check:<36} {rate:.2%}")
        if payload.get("errors"):
            lines.append(f"  errors: {payload['errors'][:3]}")
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", default=DEFAULT_CORPUS_DIR)
    parser.add_argument("--record-dir", default=DEFAULT_RECORD_DIR)
    parser.add_argument(
        "--live",
        action="store_true",
        help="re-ask the listed models about each fixture (requires network)",
    )
    parser.add_argument(
        "--models",
        default="",
        help="comma-separated provider/model specs for --live bake-off",
    )
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--json", default="", help="write the full report here")
    args = parser.parse_args(list(argv) if argv is not None else None)

    from plugin.evals.annotations import annotate, load_overrides

    fixtures = annotate(load_fixtures(args.corpus), overrides=load_overrides())
    if args.live:
        specs = [s.strip() for s in str(args.models or "").split(",") if s.strip()]
        if not specs:
            raise SystemExit("--live requires --models provider/model,...")
        # Match the live run's timeout defaults when unset.
        os.environ.setdefault("HERMES_PERCEPTION_LLM_TIMEOUT_SECONDS", str(int(args.timeout)))
        report = bake_off(
            fixtures,
            specs,
            record_dir=Path(args.record_dir),
            limit=args.limit,
            timeout_s=args.timeout,
        )
        print(render_bake_off(report))
    else:
        report = summarize_fusion(fixtures)
        print(
            f"Fusion (offline recorded replies) — "
            f"{report.get('fixtures_scored', 0)} fixtures  "
            f"mean={report.get('mean_fusion_score')}"
        )
        for metric in report.get("metrics") or []:
            value = metric.get("value")
            print(
                f"  {metric.get('name'):<36} "
                f"{(f'{value:.2%}' if isinstance(value, float) else 'n/a'):>8}  "
                f"scored={metric.get('scored', 0)}"
            )

    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(report, indent=2) + "\n")
        print(f"\nreport written to {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
