"""Benchmark perception prompt shapes against structured screen fixtures.

This is the prompt-engineering counterpart to the generic model benchmark:
we keep the same perception state and compare how different prompt shapes
affect JSON validity, target selection, and latency.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from agent.auxiliary_client import call_llm, get_runtime_main_snapshot, set_runtime_main
from plugin.agent.features import StateFeatures
from plugin.agent.goal import Goal
from plugin.agent.perception_synthesis import (
    _extract_json_block,
    _extract_text,
    build_perception_prompt_payload,
)
from plugin.experiments.model_benchmark import ModelCandidateSpec, discover_ollama_candidates
from plugin.worldmodel.entities.entity import Entity
from plugin.worldmodel.model import WorldModel


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    if hasattr(value, "to_dict") and callable(value.to_dict):
        try:
            return _json_safe(value.to_dict())
        except Exception:
            pass
    if hasattr(value, "__dict__"):
        try:
            return _json_safe(vars(value))
        except Exception:
            pass
    return str(value)


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().split()).lower()


def _contains_expected(haystack: Any, needle: str) -> bool:
    needle_norm = _norm(needle)
    if not needle_norm:
        return True
    return needle_norm in _norm(haystack)


def _extract_response_text(response: Any) -> str:
    if isinstance(response, str):
        return response.strip()
    if isinstance(response, dict):
        choices = response.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                message = first.get("message")
                if isinstance(message, dict):
                    content = message.get("content")
                    if isinstance(content, str) and content.strip():
                        return content.strip()
            content = getattr(getattr(first, "message", None), "content", None)
            if isinstance(content, str) and content.strip():
                return content.strip()
        for key in ("output_text", "text", "content"):
            val = response.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return _extract_text(response)


@dataclass
class PerceptionPromptCase:
    case_id: str
    description: str
    goal: Goal
    world: WorldModel
    view: Dict[str, Any]
    features: StateFeatures
    expected_screen_type: str = ""
    expected_active_surface: str = ""
    expected_family: str = ""
    expected_target: str = ""
    expected_text: str = ""

    def prompt_payload(self, prompt_shape: str) -> Dict[str, Any]:
        return build_perception_prompt_payload(
            self.goal,
            self.world,
            self.view,
            self.features,
            prompt_shape=prompt_shape,
        )


@dataclass
class PerceptionPromptResult:
    case_id: str
    model_name: str
    provider: str
    prompt_shape: str
    raw: Dict[str, Any]
    parsed: Dict[str, Any]
    finish_reason: str
    latency_s: float
    score: float
    parseable: bool
    complete_json: bool
    screen_type_match: bool
    active_surface_match: bool
    family_match: bool
    target_match: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "model_name": self.model_name,
            "provider": self.provider,
            "prompt_shape": self.prompt_shape,
            "raw": _json_safe(self.raw),
            "parsed": _json_safe(self.parsed),
            "finish_reason": self.finish_reason,
            "latency_s": round(float(self.latency_s or 0.0), 4),
            "score": round(float(self.score or 0.0), 4),
            "parseable": bool(self.parseable),
            "complete_json": bool(self.complete_json),
            "screen_type_match": bool(self.screen_type_match),
            "active_surface_match": bool(self.active_surface_match),
            "family_match": bool(self.family_match),
            "target_match": bool(self.target_match),
        }


@dataclass
class PromptShapeSummary:
    prompt_shape: str
    case_count: int
    accuracy: float
    avg_score: float
    median_latency_s: float
    parseable_rate: float
    complete_json_rate: float
    by_model: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "prompt_shape": self.prompt_shape,
            "case_count": self.case_count,
            "accuracy": round(float(self.accuracy or 0.0), 4),
            "avg_score": round(float(self.avg_score or 0.0), 4),
            "median_latency_s": round(float(self.median_latency_s or 0.0), 4),
            "parseable_rate": round(float(self.parseable_rate or 0.0), 4),
            "complete_json_rate": round(float(self.complete_json_rate or 0.0), 4),
            "by_model": list(self.by_model),
        }


@dataclass
class CandidatePromptSummary:
    model_name: str
    provider: str
    prompt_shape: str
    case_count: int
    accuracy: float
    avg_score: float
    median_latency_s: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_name": self.model_name,
            "provider": self.provider,
            "prompt_shape": self.prompt_shape,
            "case_count": self.case_count,
            "accuracy": round(float(self.accuracy or 0.0), 4),
            "avg_score": round(float(self.avg_score or 0.0), 4),
            "median_latency_s": round(float(self.median_latency_s or 0.0), 4),
        }


@dataclass
class PerceptionPromptBenchmarkReport:
    case_count: int
    shapes: List[str]
    candidates: List[ModelCandidateSpec]
    case_results: List[PerceptionPromptResult]
    shape_summaries: List[PromptShapeSummary]
    candidate_summaries: List[CandidatePromptSummary]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_count": self.case_count,
            "shapes": list(self.shapes),
            "candidates": [c.to_dict() for c in self.candidates],
            "case_results": [r.to_dict() for r in self.case_results],
            "shape_summaries": [s.to_dict() for s in self.shape_summaries],
            "candidate_summaries": [c.to_dict() for c in self.candidate_summaries],
        }


def _response_finish_reason(response: Any) -> str:
    choices = getattr(response, "choices", None)
    if isinstance(choices, list) and choices:
        finish_reason = getattr(choices[0], "finish_reason", "")
        return str(finish_reason or "").strip().lower()
    if isinstance(response, dict):
        if "finish_reason" in response:
            return str(response.get("finish_reason") or "").strip().lower()
    return ""


def _score_response(
    parsed: Dict[str, Any],
    case: PerceptionPromptCase,
    finish_reason: str,
) -> Tuple[float, bool, bool, bool, bool, bool, bool]:
    parseable = bool(parsed)
    complete_json = parseable and finish_reason != "length"
    screen_type_match = True if not case.expected_screen_type else _contains_expected(
        parsed.get("screen_type") or parsed.get("screen"), case.expected_screen_type
    )
    active_surface_match = True if not case.expected_active_surface else _contains_expected(
        parsed.get("active_surface") or parsed.get("surface"), case.expected_active_surface
    )
    family_match = True if not case.expected_family else _norm(parsed.get("likely_next_family") or parsed.get("next_family")) == _norm(
        case.expected_family
    )
    target_blob = " ".join(
        str(parsed.get(key) or "") for key in ("likely_next_target", "likely_next_text", "brief_reason", "reason")
    )
    target_match = True if not case.expected_target else _contains_expected(target_blob, case.expected_target)

    parts = [
        1.0 if parseable else 0.0,
        1.0 if complete_json else 0.0,
        1.0 if screen_type_match else 0.0,
        1.0 if active_surface_match else 0.0,
        1.0 if family_match else 0.0,
        1.0 if target_match else 0.0,
    ]
    score = sum(parts) / len(parts)
    return score, parseable, complete_json, screen_type_match, active_surface_match, family_match, target_match


def _make_goal_world_view() -> Tuple[Goal, WorldModel, Dict[str, Any], StateFeatures]:
    goal = Goal(
        kind="whatsapp_forward_message",
        contact="Kulvinder",
        target_contact="Pallavi",
        link_query="zarooratwala",
    )
    world = WorldModel()
    world.active_app = "WhatsApp"
    world.entities = {
        1: Entity(
            id=1,
            entity_type="button",
            semantic_role="Chats",
            label="Chats",
            role="AXButton",
            actions=["click"],
            visible=True,
            bounds=(20, 20, 100, 32),
        ),
        2: Entity(
            id=2,
            entity_type="textfield",
            semantic_role="Search",
            label="Search",
            role="AXTextField",
            actions=["click", "type"],
            visible=True,
            bounds=(20, 80, 220, 32),
        ),
        3: Entity(
            id=3,
            entity_type="static",
            semantic_role="Kulvinder Ji",
            label="Kulvinder Ji",
            role="AXStaticText",
            actions=[],
            visible=True,
            bounds=(20, 150, 240, 40),
        ),
        4: Entity(
            id=4,
            entity_type="static",
            semantic_role="Pallavi",
            label="Pallavi",
            role="AXStaticText",
            actions=[],
            visible=True,
            bounds=(20, 190, 240, 40),
        ),
    }
    world.tracker._entities = dict(world.entities)
    world.tracker._next_id = 5
    world.last_scene_graph = {
        "report": {"layout_confidence": 0.61, "region_coverage": 0.87, "affordance_entropy": 0.67},
        "attention": {"region_ids": ["sidebar"], "entity_ids": [1, 2, 3, 4]},
        "regions": [{"kind": "sidebar"}],
    }
    view = {
        "app": "WhatsApp",
        "screen": "LIST",
        "search_query": "",
        "search_visible": True,
        "search_focused": False,
        "open_conversation": "",
        "visible_contacts": ["Kulvinder Ji", "Pallavi"],
        "blocking_overlay": False,
        "system_warnings": [],
        "window_name": "‎WhatsApp",
    }
    features = StateFeatures(
        app="WhatsApp",
        screen_bucket="list",
        screen_kind="list",
        conversation_open=False,
        search_focused=False,
        worldview_score=0.82,
        mean_belief=0.91,
        extras={"resolution_policy": "observe", "observation_node_count": 12},
    )
    return goal, world, view, features


def build_default_cases() -> List[PerceptionPromptCase]:
    goal, world, view, features = _make_goal_world_view()
    startup = PerceptionPromptCase(
        case_id="startup_search_entry",
        description="Startup list screen should suggest the search query, not a random contact row.",
        goal=goal,
        world=world,
        view=view,
        features=features,
        expected_screen_type="list",
        expected_active_surface="contact list",
        expected_family="type_query",
        expected_target="Search",
    )

    followup_view = dict(view)
    followup_view.update(
        {
            "search_query": "Kulvinder",
            "search_focused": True,
            "open_conversation": "Kulvinder Ji",
            "visible_contacts": ["Kulvinder Ji"],
        }
    )
    followup_features = StateFeatures(
        app="WhatsApp",
        screen_bucket="search",
        screen_kind="search",
        conversation_open=False,
        search_focused=True,
        worldview_score=0.86,
        mean_belief=0.92,
        extras={"resolution_policy": "observe", "observation_node_count": 12},
    )
    followup = PerceptionPromptCase(
        case_id="search_result_open_source_row",
        description="After typing the contact name, the next step should be opening the source conversation row.",
        goal=goal,
        world=world,
        view=followup_view,
        features=followup_features,
        expected_screen_type="search",
        expected_active_surface="search",
        expected_family="click",
        expected_target="Kulvinder Ji",
    )
    return [startup, followup]


def run_perception_prompt_benchmark(
    candidates: Sequence[ModelCandidateSpec],
    *,
    cases: Optional[Sequence[PerceptionPromptCase]] = None,
    shapes: Optional[Sequence[str]] = None,
    invoker: Optional[Callable[[ModelCandidateSpec, PerceptionPromptCase, str], Any]] = None,
) -> PerceptionPromptBenchmarkReport:
    cases = list(cases or build_default_cases())
    shapes = [str(shape).strip().lower() for shape in (shapes or ["compact", "balanced", "rich"]) if str(shape).strip()]
    candidates = list(candidates)
    invoker = invoker or _invoke_live

    results: List[PerceptionPromptResult] = []
    for candidate in candidates:
        for shape in shapes:
            for case in cases:
                started = time.time()
                response = invoker(candidate, case, shape)
                latency = time.time() - started
                raw_text = _extract_response_text(response)
                parsed = _extract_json_block(raw_text) or {}
                finish_reason = _response_finish_reason(response)
                score, parseable, complete_json, screen_type_match, active_surface_match, family_match, target_match = _score_response(
                    parsed,
                    case,
                    finish_reason,
                )
                results.append(
                    PerceptionPromptResult(
                        case_id=case.case_id,
                        model_name=candidate.name,
                        provider=candidate.provider,
                        prompt_shape=shape,
                        raw=_json_safe(getattr(response, "__dict__", response)),
                        parsed=parsed,
                        finish_reason=finish_reason,
                        latency_s=latency,
                        score=score,
                        parseable=parseable,
                        complete_json=complete_json,
                        screen_type_match=screen_type_match,
                        active_surface_match=active_surface_match,
                        family_match=family_match,
                        target_match=target_match,
                    )
                )

    shape_summaries: List[PromptShapeSummary] = []
    for shape in shapes:
        bucket = [r for r in results if r.prompt_shape == shape]
        shape_summaries.append(
            PromptShapeSummary(
                prompt_shape=shape,
                case_count=len(bucket),
                accuracy=(sum(1.0 for r in bucket if r.score >= 0.75) / len(bucket)) if bucket else 0.0,
                avg_score=(sum(r.score for r in bucket) / len(bucket)) if bucket else 0.0,
                median_latency_s=statistics.median([r.latency_s for r in bucket]) if bucket else 0.0,
                parseable_rate=(sum(1.0 for r in bucket if r.parseable) / len(bucket)) if bucket else 0.0,
                complete_json_rate=(sum(1.0 for r in bucket if r.complete_json) / len(bucket)) if bucket else 0.0,
                by_model=[],
            )
        )

    candidate_summaries: List[CandidatePromptSummary] = []
    for candidate in candidates:
        for shape in shapes:
            bucket = [r for r in results if r.model_name == candidate.name and r.prompt_shape == shape]
            if not bucket:
                continue
            candidate_summaries.append(
                CandidatePromptSummary(
                    model_name=candidate.name,
                    provider=candidate.provider,
                    prompt_shape=shape,
                    case_count=len(bucket),
                    accuracy=sum(1.0 for r in bucket if r.score >= 0.75) / len(bucket),
                    avg_score=sum(r.score for r in bucket) / len(bucket),
                    median_latency_s=statistics.median([r.latency_s for r in bucket]),
                )
            )

    return PerceptionPromptBenchmarkReport(
        case_count=len(cases),
        shapes=shapes,
        candidates=list(candidates),
        case_results=results,
        shape_summaries=shape_summaries,
        candidate_summaries=candidate_summaries,
    )


def _invoke_live(candidate: ModelCandidateSpec, case: PerceptionPromptCase, shape: str) -> Any:
    token = set_runtime_main(
        candidate.provider,
        candidate.model,
        base_url=candidate.base_url,
        api_key=candidate.api_key,
        api_mode=candidate.api_mode,
    )
    try:
        prompt_payload = case.prompt_payload(shape)
        messages = [
            {
                "role": "system",
                "content": "Return strict JSON only. Infer screen meaning from AX evidence.",
            },
            {"role": "user", "content": json.dumps(prompt_payload, ensure_ascii=False, separators=(",", ":"))},
        ]
        return call_llm(
            task="perception",
            provider=candidate.provider,
            model=candidate.model,
            base_url=candidate.base_url,
            api_key=candidate.api_key,
            api_mode=candidate.api_mode,
            messages=messages,
            temperature=candidate.temperature,
            max_tokens=candidate.max_output_tokens,
            timeout=candidate.timeout_s,
            main_runtime=get_runtime_main_snapshot(),
            extra_body={"format": "json"} if "ollama" in (candidate.base_url or "").lower() else {},
        )
    finally:
        from agent.auxiliary_client import reset_runtime_main

        reset_runtime_main(token)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark perception prompt shapes")
    parser.add_argument("--ollama-base-url", default="", help="Remote Ollama base URL")
    parser.add_argument("--provider", action="append", default=[], help="Provider to discover candidates from")
    parser.add_argument("--candidate", action="append", default=[], help="Inline JSON candidate spec")
    parser.add_argument("--candidate-file", default="", help="JSON file with candidate specs")
    parser.add_argument("--shape", action="append", default=[], help="Prompt shape to include")
    parser.add_argument("--json", action="store_true", help="Print JSON only")
    parser.add_argument("--report", default="", help="Optional output JSON path")
    args = parser.parse_args(list(argv) if argv is not None else None)

    candidates: List[ModelCandidateSpec] = []
    if args.ollama_base_url:
        candidates.extend(
            discover_ollama_candidates(
                args.ollama_base_url,
                min_params_b=14,
                max_params_b=32,
                include_unknown_size=False,
                max_models=10,
            )
        )
    if args.candidate_file:
        data = json.loads(Path(args.candidate_file).read_text(encoding="utf-8"))
        raw = data if isinstance(data, list) else data.get("candidates", [])
        candidates.extend(ModelCandidateSpec.from_mapping(item) for item in raw if isinstance(item, dict))
    for raw in args.candidate or []:
        candidates.append(ModelCandidateSpec.from_mapping(json.loads(raw)))
    if not candidates:
        raise SystemExit("No candidates supplied. Use --ollama-base-url, --candidate, or --candidate-file.")

    report = run_perception_prompt_benchmark(candidates, shapes=args.shape or None)
    payload = report.to_dict()
    if args.report:
        Path(args.report).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False) if not args.json else json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
