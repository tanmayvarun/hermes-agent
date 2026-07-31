"""Benchmark cloud LLMs against a growing suite of routed evals.

The goal is not just to rank models globally, but to learn which model is
best for which subusecase: perception interpretation, message relevance,
backtracking, and irreversible-action gating.

This module keeps the benchmark surface generic:
* suites are explicit data
* model candidates are explicit data
* invocation is pluggable for tests / offline runs
* output is JSON-first so routing code can consume it later
"""

from __future__ import annotations

import argparse
import inspect
import json
import re
import statistics
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import URLError
from urllib.request import Request, urlopen

from agent.auxiliary_client import auxiliary_max_tokens_param, resolve_provider_client
from hermes_cli.fallback_config import estimate_model_params_b
from hermes_cli.models import provider_model_ids
from utils import fast_safe_load


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
    return str(value)


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


_BENCHMARK_NOISE_RE = re.compile(
    r"(embed|rerank|transcribe|speech|audio|image|vision|ocr|clip|embedding)",
    re.IGNORECASE,
)


def _choice_label(index: int) -> str:
    return chr(ord("A") + index)


def _f1(precision: float, recall: float) -> float:
    if precision <= 0.0 or recall <= 0.0:
        return 0.0
    return 2.0 * precision * recall / (precision + recall)


def _extract_json_payload(text: str) -> Dict[str, Any]:
    raw = _clean_text(text)
    if not raw:
        return {}
    # Fast path: already JSON.
    try:
        loaded = json.loads(raw)
        if isinstance(loaded, dict):
            return loaded
    except Exception:
        pass
    # Fallback: look for the outermost JSON object.
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            loaded = json.loads(raw[start : end + 1])
            if isinstance(loaded, dict):
                return loaded
        except Exception:
            return {}
    return {}


def _normalize_choice_answer(answer: Any, choices: Sequence[str]) -> str:
    raw = _clean_text(answer).upper()
    if not raw:
        return ""
    if raw in {_choice_label(i) for i in range(len(choices))}:
        return raw
    for idx, choice in enumerate(choices):
        if raw == _clean_text(choice).upper():
            return _choice_label(idx)
    # Handle answers like "A: type into the search field".
    first = raw[:1]
    if first in {_choice_label(i) for i in range(len(choices))}:
        return first
    return raw


def _clamp_unit_interval(value: Any, default: float = 0.0) -> float:
    try:
        numeric = float(value)
    except Exception:
        return default
    if numeric != numeric:  # NaN guard
        return default
    return max(0.0, min(1.0, numeric))


@dataclass
class ModelCandidateSpec:
    """A single model/provider pair to benchmark."""

    name: str
    provider: str = "auto"
    model: str = ""
    base_url: str = ""
    api_key: str = ""
    api_mode: str = ""
    temperature: float = 0.0
    timeout_s: float = 120.0
    max_output_tokens: int = 256
    params_b: float | None = None
    notes: str = ""

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "ModelCandidateSpec":
        name = _clean_text(data.get("name") or data.get("id") or data.get("label") or "")
        provider = _clean_text(data.get("provider") or "auto") or "auto"
        model = _clean_text(data.get("model") or "")
        if not name:
            if provider != "auto" and model:
                name = f"{provider}:{model}"
            elif model:
                name = model
            else:
                name = provider
        return cls(
            name=name,
            provider=provider,
            model=model,
            base_url=_clean_text(data.get("base_url") or ""),
            api_key=_clean_text(data.get("api_key") or ""),
            api_mode=_clean_text(data.get("api_mode") or ""),
            temperature=float(data.get("temperature") if data.get("temperature") is not None else 0.0),
            timeout_s=float(data.get("timeout_s") if data.get("timeout_s") is not None else 120.0),
            max_output_tokens=int(data.get("max_output_tokens") if data.get("max_output_tokens") is not None else 256),
            params_b=(
                float(data.get("params_b"))
                if data.get("params_b") not in (None, "", False)
                else estimate_model_params_b(model)
            ),
            notes=_clean_text(data.get("notes") or ""),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BenchmarkCase:
    """A single routed eval case."""

    case_id: str
    subusecase: str
    prompt: str
    choices: List[str]
    gold_choice: str
    risk_tier: str = "medium"
    description: str = ""
    notes: str = ""
    ideal_model_family: str = ""

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "BenchmarkCase":
        choices = [str(x) for x in (data.get("choices") or []) if _clean_text(x)]
        if len(choices) < 2:
            raise ValueError("benchmark case needs at least two choices")
        gold_choice = _clean_text(data.get("gold_choice") or "").upper()
        if gold_choice not in {_choice_label(i) for i in range(len(choices))}:
            raise ValueError(f"benchmark case {data.get('case_id')!r} has invalid gold_choice")
        return cls(
            case_id=_clean_text(data.get("case_id") or ""),
            subusecase=_clean_text(data.get("subusecase") or "general"),
            prompt=_clean_text(data.get("prompt") or ""),
            choices=choices,
            gold_choice=gold_choice,
            risk_tier=_clean_text(data.get("risk_tier") or "medium"),
            description=_clean_text(data.get("description") or ""),
            notes=_clean_text(data.get("notes") or ""),
            ideal_model_family=_clean_text(data.get("ideal_model_family") or ""),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def labeled_choices(self) -> List[Tuple[str, str]]:
        return [(_choice_label(i), choice) for i, choice in enumerate(self.choices)]

    def prompt_text(self) -> str:
        lines = [
            "You are benchmarking an LLM for Hermes routing.",
            "Return ONLY JSON with keys: answer, confidence, brief_reason.",
            "Choose one answer label from the options below.",
        ]
        if self.description:
            lines.append(f"Case: {self.description}")
        lines.append(f"Subusecase: {self.subusecase}")
        lines.append(f"Risk tier: {self.risk_tier}")
        if self.ideal_model_family:
            lines.append(f"Ideal model family: {self.ideal_model_family}")
        lines.append("")
        lines.append(self.prompt)
        lines.append("")
        lines.append("Choices:")
        for label, choice in self.labeled_choices():
            lines.append(f"{label}. {choice}")
        return "\n".join(lines)


@dataclass
class ContextPackSpec:
    """How we package supporting context around a case."""

    name: str
    include_case_id: bool = False
    include_description: bool = True
    include_subusecase: bool = True
    include_risk_tier: bool = True
    include_ideal_model_family: bool = True
    include_notes: bool = False
    label: str = "Context"

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "ContextPackSpec":
        return cls(
            name=_clean_text(data.get("name") or data.get("id") or data.get("label") or "default"),
            include_case_id=bool(data.get("include_case_id", False)),
            include_description=bool(data.get("include_description", True)),
            include_subusecase=bool(data.get("include_subusecase", True)),
            include_risk_tier=bool(data.get("include_risk_tier", True)),
            include_ideal_model_family=bool(data.get("include_ideal_model_family", True)),
            include_notes=bool(data.get("include_notes", False)),
            label=_clean_text(data.get("label") or "Context"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def render_lines(self, case: BenchmarkCase) -> List[str]:
        lines: List[str] = []
        if self.include_case_id and case.case_id:
            lines.append(f"Case ID: {case.case_id}")
        if self.include_subusecase and case.subusecase:
            lines.append(f"Subusecase: {case.subusecase}")
        if self.include_risk_tier and case.risk_tier:
            lines.append(f"Risk tier: {case.risk_tier}")
        if self.include_ideal_model_family and case.ideal_model_family:
            lines.append(f"Ideal model family: {case.ideal_model_family}")
        if self.include_description and case.description:
            lines.append(f"Description: {case.description}")
        if self.include_notes and case.notes:
            lines.append(f"Notes: {case.notes}")
        return lines


@dataclass
class PromptShapeSpec:
    """How the benchmark asks the model to reason and answer."""

    name: str
    system_message: str = (
        "You are a benchmark judge for Hermes. Return ONLY JSON with keys "
        "answer, confidence, brief_reason. Choose one label from the provided choices."
    )
    user_preamble: str = (
        "Inspect the provided task, context, and choices carefully before answering."
    )
    response_contract: str = (
        "Return ONLY JSON with keys: answer, confidence, brief_reason. "
        "Confidence must be a number from 0 to 1 and must reflect belief, not any score_hint or ranking artifact."
    )
    context_before_prompt: bool = True
    choices_after_prompt: bool = True
    include_reasoning_hint: bool = False

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "PromptShapeSpec":
        return cls(
            name=_clean_text(data.get("name") or data.get("id") or data.get("label") or "default"),
            system_message=_clean_text(data.get("system_message") or cls.system_message),
            user_preamble=_clean_text(data.get("user_preamble") or cls.user_preamble),
            response_contract=_clean_text(data.get("response_contract") or cls.response_contract),
            context_before_prompt=bool(data.get("context_before_prompt", True)),
            choices_after_prompt=bool(data.get("choices_after_prompt", True)),
            include_reasoning_hint=bool(data.get("include_reasoning_hint", False)),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def render_prompt(self, case: BenchmarkCase, context_pack: ContextPackSpec) -> str:
        lines = [self.user_preamble, ""]
        context_lines = context_pack.render_lines(case)
        if self.context_before_prompt and context_lines:
            lines.append(f"{context_pack.label}:")
            lines.extend(f"- {line}" for line in context_lines)
            lines.append("")
        lines.append(case.prompt)
        lines.append("")
        if (not self.context_before_prompt) and context_lines:
            lines.append(f"{context_pack.label}:")
            lines.extend(f"- {line}" for line in context_lines)
            lines.append("")
        if self.choices_after_prompt:
            lines.append("Choices:")
            for label, choice in case.labeled_choices():
                lines.append(f"{label}. {choice}")
        if self.include_reasoning_hint:
            lines.append("")
            lines.append("Reason briefly, but keep the response JSON-only.")
        return "\n".join(lines)


@dataclass
class BenchmarkRunSpec:
    """A single benchmark configuration = model + prompt shape + context pack."""

    candidate: ModelCandidateSpec
    prompt_shape: PromptShapeSpec
    context_pack: ContextPackSpec

    @property
    def name(self) -> str:
        return f"{self.candidate.name} | {self.prompt_shape.name} | {self.context_pack.name}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "candidate": self.candidate.to_dict(),
            "prompt_shape": self.prompt_shape.to_dict(),
            "context_pack": self.context_pack.to_dict(),
        }


@dataclass
class BenchmarkSuite:
    suite_id: str
    description: str = ""
    cases: List[BenchmarkCase] = field(default_factory=list)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "BenchmarkSuite":
        raw_cases = data.get("cases")
        cases = [BenchmarkCase.from_mapping(item) for item in raw_cases or [] if isinstance(item, Mapping)]
        return cls(
            suite_id=_clean_text(data.get("suite_id") or data.get("name") or "default"),
            description=_clean_text(data.get("description") or ""),
            cases=cases,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "suite_id": self.suite_id,
            "description": self.description,
            "cases": [case.to_dict() for case in self.cases],
        }


@dataclass
class BenchmarkCaseResult:
    case_id: str
    subusecase: str
    model_name: str
    provider: str
    predicted_choice: str
    gold_choice: str
    correct: bool
    confidence: float
    latency_s: float
    prompt_shape: str = ""
    context_pack: str = ""
    error: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "subusecase": self.subusecase,
            "model_name": self.model_name,
            "provider": self.provider,
            "prompt_shape": self.prompt_shape,
            "context_pack": self.context_pack,
            "predicted_choice": self.predicted_choice,
            "gold_choice": self.gold_choice,
            "correct": bool(self.correct),
            "confidence": round(float(self.confidence or 0.0), 4),
            "latency_s": round(float(self.latency_s or 0.0), 4),
            "error": self.error,
            "raw": _json_safe(self.raw),
        }


@dataclass
class ModelSubusecaseSummary:
    subusecase: str
    case_count: int
    accuracy: float
    avg_confidence: float
    correct_avg_confidence: float
    wrong_avg_confidence: float
    median_latency_s: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "subusecase": self.subusecase,
            "case_count": self.case_count,
            "accuracy": round(float(self.accuracy or 0.0), 4),
            "avg_confidence": round(float(self.avg_confidence or 0.0), 4),
            "correct_avg_confidence": round(float(self.correct_avg_confidence or 0.0), 4),
            "wrong_avg_confidence": round(float(self.wrong_avg_confidence or 0.0), 4),
            "median_latency_s": round(float(self.median_latency_s or 0.0), 4),
        }


@dataclass
class ModelSummary:
    model_name: str
    provider: str
    case_count: int
    correct_count: int
    accuracy: float
    avg_confidence: float
    correct_avg_confidence: float
    wrong_avg_confidence: float
    median_latency_s: float
    by_subusecase: List[ModelSubusecaseSummary] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_name": self.model_name,
            "provider": self.provider,
            "case_count": self.case_count,
            "correct_count": self.correct_count,
            "accuracy": round(float(self.accuracy or 0.0), 4),
            "avg_confidence": round(float(self.avg_confidence or 0.0), 4),
            "correct_avg_confidence": round(float(self.correct_avg_confidence or 0.0), 4),
            "wrong_avg_confidence": round(float(self.wrong_avg_confidence or 0.0), 4),
            "median_latency_s": round(float(self.median_latency_s or 0.0), 4),
            "by_subusecase": [item.to_dict() for item in self.by_subusecase],
        }


@dataclass
class DimensionSummary:
    dimension: str
    label: str
    case_count: int
    correct_count: int
    accuracy: float
    avg_confidence: float
    correct_avg_confidence: float
    wrong_avg_confidence: float
    median_latency_s: float
    by_subusecase: List[ModelSubusecaseSummary] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dimension": self.dimension,
            "label": self.label,
            "case_count": self.case_count,
            "correct_count": self.correct_count,
            "accuracy": round(float(self.accuracy or 0.0), 4),
            "avg_confidence": round(float(self.avg_confidence or 0.0), 4),
            "correct_avg_confidence": round(float(self.correct_avg_confidence or 0.0), 4),
            "wrong_avg_confidence": round(float(self.wrong_avg_confidence or 0.0), 4),
            "median_latency_s": round(float(self.median_latency_s or 0.0), 4),
            "by_subusecase": [item.to_dict() for item in self.by_subusecase],
        }


@dataclass
class RoutingRecommendation:
    subusecase: str
    best_model: str
    runner_up_model: str = ""
    sample_count: int = 0
    best_accuracy: float = 0.0
    runner_up_accuracy: float = 0.0
    accuracy_gap: float = 0.0
    best_median_latency_s: float = 0.0
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "subusecase": self.subusecase,
            "best_model": self.best_model,
            "runner_up_model": self.runner_up_model,
            "sample_count": self.sample_count,
            "best_accuracy": round(float(self.best_accuracy or 0.0), 4),
            "runner_up_accuracy": round(float(self.runner_up_accuracy or 0.0), 4),
            "accuracy_gap": round(float(self.accuracy_gap or 0.0), 4),
            "best_median_latency_s": round(float(self.best_median_latency_s or 0.0), 4),
            "note": self.note,
        }


@dataclass
class BenchmarkReport:
    suite_id: str
    case_count: int
    model_count: int
    prompt_shape_count: int
    context_pack_count: int
    cases: List[BenchmarkCase]
    candidates: List[ModelCandidateSpec]
    prompt_shapes: List[PromptShapeSpec]
    context_packs: List[ContextPackSpec]
    case_results: List[BenchmarkCaseResult]
    model_summaries: List[ModelSummary]
    prompt_shape_summaries: List[DimensionSummary]
    context_pack_summaries: List[DimensionSummary]
    config_summaries: List[DimensionSummary]
    recommendations: List[RoutingRecommendation]
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "suite_id": self.suite_id,
            "case_count": self.case_count,
            "model_count": self.model_count,
            "prompt_shape_count": self.prompt_shape_count,
            "context_pack_count": self.context_pack_count,
            "notes": list(self.notes),
            "cases": [case.to_dict() for case in self.cases],
            "candidates": [cand.to_dict() for cand in self.candidates],
            "prompt_shapes": [shape.to_dict() for shape in self.prompt_shapes],
            "context_packs": [pack.to_dict() for pack in self.context_packs],
            "case_results": [result.to_dict() for result in self.case_results],
            "model_summaries": [summary.to_dict() for summary in self.model_summaries],
            "prompt_shape_summaries": [summary.to_dict() for summary in self.prompt_shape_summaries],
            "context_pack_summaries": [summary.to_dict() for summary in self.context_pack_summaries],
            "config_summaries": [summary.to_dict() for summary in self.config_summaries],
            "recommendations": [rec.to_dict() for rec in self.recommendations],
        }

    def best_model_for_subusecase(self, subusecase: str) -> Optional[RoutingRecommendation]:
        for rec in self.recommendations:
            if rec.subusecase == subusecase:
                return rec
        return None


def build_default_prompt_shapes() -> List[PromptShapeSpec]:
    return [
        PromptShapeSpec(
            name="compact-json",
            system_message=(
                "You are a benchmark judge for Hermes. Return ONLY JSON with keys "
                "answer, confidence, brief_reason. Choose one label from the provided choices. "
                "Confidence must be between 0 and 1 and must not mirror any score_hint."
            ),
            user_preamble="Inspect the task, context, and choices carefully before answering.",
            context_before_prompt=True,
            choices_after_prompt=True,
            include_reasoning_hint=False,
        ),
        PromptShapeSpec(
            name="calibrated-json",
            system_message=(
                "You are a benchmark judge for Hermes. Return ONLY JSON with keys "
                "answer, confidence, brief_reason. Choose one label from the provided choices. "
                "Do not copy any score_hint, ranking hint, or candidate score into confidence. "
                "Confidence must be a calibrated belief from 0 to 1."
            ),
            user_preamble="Inspect the task, context, and choices carefully before answering.",
            response_contract=(
                "Return ONLY JSON with keys: answer, confidence, brief_reason. "
                "Confidence must be a number from 0 to 1."
            ),
            context_before_prompt=True,
            choices_after_prompt=True,
            include_reasoning_hint=False,
        ),
        PromptShapeSpec(
            name="evidence-first",
            system_message=(
                "You are a benchmark judge for Hermes. Inspect context before you judge the answer. "
                "Return ONLY JSON with keys answer, confidence, brief_reason."
            ),
            user_preamble="Start from the evidence, then choose the best label.",
            context_before_prompt=True,
            choices_after_prompt=True,
            include_reasoning_hint=True,
        ),
        PromptShapeSpec(
            name="safety-first",
            system_message=(
                "You are a benchmark judge for Hermes. Prefer the option that best preserves the goal "
                "and avoids unnecessary irreversible action. Return ONLY JSON with keys answer, confidence, brief_reason."
            ),
            user_preamble="Use the safest plausible interpretation of the task.",
            context_before_prompt=True,
            choices_after_prompt=True,
            include_reasoning_hint=False,
        ),
    ]


def build_default_context_packs() -> List[ContextPackSpec]:
    return [
        ContextPackSpec(
            name="metadata_rich",
            include_case_id=True,
            include_description=True,
            include_subusecase=True,
            include_risk_tier=True,
            include_ideal_model_family=True,
            include_notes=True,
            label="Task context",
        ),
        ContextPackSpec(
            name="metadata_lean",
            include_case_id=False,
            include_description=False,
            include_subusecase=True,
            include_risk_tier=True,
            include_ideal_model_family=False,
            include_notes=False,
            label="Task context",
        ),
    ]


def build_default_suite() -> BenchmarkSuite:
    return BenchmarkSuite(
        suite_id="hermes-core-routing",
        description="Core LLM routing and decision-quality evals for Hermes.",
        cases=[
            BenchmarkCase(
                case_id="message_relevance_link_row",
                subusecase="message_relevance",
                risk_tier="low",
                ideal_model_family="general reasoning",
                description="Pick the row that most directly contains the target link.",
                prompt=(
                    "The agent is trying to find the target message in a chat.\n"
                    "Which option best identifies the row that should be opened first?"
                ),
                choices=[
                    "The row containing the exact URL and link preview title.",
                    "A reply-only message that says thanks.",
                    "The sender's profile card in the side panel.",
                    "A group member list entry.",
                ],
                gold_choice="A",
            ),
            BenchmarkCase(
                case_id="source_message_reconstruction",
                subusecase="source_message_reconstruction",
                risk_tier="low",
                ideal_model_family="general reasoning",
                description="Prefer the source conversation evidence over sidebar chatter.",
                prompt=(
                    "Which option most strongly suggests the source conversation contains "
                    "the target content instead of unrelated sidebar noise?"
                ),
                choices=[
                    "A message row with the exact target name, URL, and preview text.",
                    "A profile card that shows the contact avatar only.",
                    "A group info panel with member names.",
                    "A timestamp badge with no message text.",
                ],
                gold_choice="A",
            ),
            BenchmarkCase(
                case_id="editable_affordance_gate",
                subusecase="editable_affordance_gate",
                risk_tier="medium",
                ideal_model_family="perception heavy reasoning",
                description="Decide whether the visible Search surface is a safe typing target.",
                prompt=(
                    "The screen shows a visible search surface and a contact card. "
                    "What should the agent do next?"
                ),
                choices=[
                    "Type into the active editable search field.",
                    "Click the avatar/info card first.",
                    "Treat the visible Search label as a non-editable label and type there anyway.",
                    "Trigger a call immediately.",
                ],
                gold_choice="A",
            ),
            BenchmarkCase(
                case_id="whatsapp_hover_reveal_message_actions",
                subusecase="latent_affordance_probe",
                risk_tier="medium",
                ideal_model_family="production routing / latent affordance reasoning",
                description="Use hover or message actions to reveal hidden forward-related controls before changing strategy.",
                prompt=(
                    "The agent is already on the source conversation and the target message row is visible in the timeline.\n"
                    "Without hovering, the row only shows the message text and timestamp.\n"
                    "When the pointer moves over the message card or the top-right message actions control, extra actions "
                    "such as reply, react, star, pin, and forward become visible.\n"
                    "What should the agent do next to keep moving toward the forwarding goal?"
                ),
                choices=[
                    "Hover the message card or open its message actions to reveal the forward option and related controls.",
                    "Click the contact info card or avatar panel first.",
                    "Restart the name search in the left sidebar.",
                    "Start a voice or video call because the contact is visible.",
                ],
                gold_choice="A",
                notes="Captured from live zarooratwala trace plugin/experiments/fixtures/whatsapp_hover_reveal.json",
            ),
            BenchmarkCase(
                case_id="whatsapp_production_bundle_message_relevance",
                subusecase="message_relevance",
                risk_tier="medium",
                ideal_model_family="production routing / message understanding",
                description="Use the real production AX/world bundle to choose the next step from a WhatsApp forward task.",
                prompt=(
                    "The agent is running a real production prompt for a WhatsApp forward task.\n"
                    "The bundle includes AX tree data, visible entities, conversation context, and a goal:\n"
                    "goal_prompt: find the zarooratwala link sent to kulvinder on whatsapp and forward to pallavi.\n"
                    "The screen is already on Kulvinder Ji's conversation, the Search field is visible, and the timeline "
                    "contains messages including the zarooratwala link.\n"
                    "What should the selector choose as the next action?"
                ),
                choices=[
                    "Inspect or select the source conversation timeline entry containing the zarooratwala link and related message evidence.",
                    "Click the contact info card or avatar panel first.",
                    "Start a voice or video call.",
                    "Ignore the timeline and keep searching only by the contact name.",
                ],
                gold_choice="A",
            ),
            BenchmarkCase(
                case_id="godrej_nurture_electronic_city_phase_1_maps_share_location_production_bundle",
                subusecase="procedure_stage_selection",
                risk_tier="high",
                ideal_model_family="production routing / forward-message reasoning",
                description="Canonical Google Maps share-location regression for a different location prompt.",
                prompt=(
                    "The agent is executing a WhatsApp forward task for a Google Maps location share.\n"
                    "Goal prompt: find the google share location of godrej nurutre electronic city phase 1 and share with pallavi on whatsapp.\n"
                    "The screen already exposes a visible search surface, a contact list, and source-chat context.\n"
                    "Which next step best preserves the procedure contract?"
                ),
                choices=[
                    "Open or inspect the source conversation timeline entry that contains the Google Maps share location.",
                    "Click the contact info card or avatar panel first.",
                    "Start a voice or video call because the contact is nearby.",
                    "Ignore the timeline and keep searching only by the contact name.",
                ],
                gold_choice="A",
            ),
            BenchmarkCase(
                case_id="zarooratwala_forward_message_production_bundle",
                subusecase="procedure_stage_selection",
                risk_tier="high",
                ideal_model_family="production routing / forward-message reasoning",
                description="Canonical WhatsApp forward regression that should stay source-first.",
                prompt=(
                    "The agent is executing the canonical WhatsApp forward regression.\n"
                    "Goal prompt: find the zarooratwala link sent to kulvinder on whatsapp and forward to pallavi.\n"
                    "The screen already exposes a visible search surface, a contact list, and source-chat context.\n"
                    "Which next step best preserves the procedure contract?"
                ),
                choices=[
                    "Open or inspect the source conversation timeline entry that contains the zarooratwala link.",
                    "Click the contact info card or avatar panel first.",
                    "Start a voice or video call because the contact is nearby.",
                    "Ignore the timeline and keep searching only by the contact name.",
                ],
                gold_choice="A",
            ),
            BenchmarkCase(
                case_id="irreversible_action_gate",
                subusecase="irreversible_action_gate",
                risk_tier="high",
                ideal_model_family="high-risk reasoning",
                description="Footprint-bearing actions should wait for enough confidence.",
                prompt=(
                    "Confidence is 0.58 and the next action would leave an external footprint. "
                    "What should the agent do?"
                ),
                choices=[
                    "Proceed immediately because a plausible match exists.",
                    "Inspect more evidence or ask for confirmation before acting.",
                    "Make the irreversible action now and fix it later.",
                    "Ignore the confidence and re-run the same branch.",
                ],
                gold_choice="B",
            ),
            BenchmarkCase(
                case_id="backtrack_dead_end",
                subusecase="backtrack_strategy",
                risk_tier="medium",
                ideal_model_family="planner/reasoner",
                description="The branch is dead and should be backed out of rather than repeated.",
                prompt=(
                    "The current branch has stalled and no new evidence is appearing. "
                    "What is the best next move?"
                ),
                choices=[
                    "Backtrack to the previous branch and try the other plausible option.",
                    "Keep clicking the same control until it works.",
                    "Close the app and abandon the task.",
                    "Perform a risky irreversible action to force progress.",
                ],
                gold_choice="A",
            ),
            BenchmarkCase(
                case_id="procedure_stage_selection",
                subusecase="procedure_stage_selection",
                risk_tier="medium",
                ideal_model_family="procedure-aware reasoning",
                description="Prefer the stage that narrows the search before actuation.",
                prompt=(
                    "The goal is to forward a useful WhatsApp link. Which stage should come first?"
                ),
                choices=[
                    "Identify and verify the source message before forwarding.",
                    "Open the forward composer immediately.",
                    "Jump to the call UI because the contact appears nearby.",
                    "Delete the existing chat history.",
                ],
                gold_choice="A",
            ),
        ],
    )


def discover_candidates_from_providers(
    providers: Sequence[str],
    *,
    min_params_b: float | None = None,
    max_params_b: float | None = None,
    include_unknown_size: bool = False,
    max_per_provider: int | None = None,
) -> List[ModelCandidateSpec]:
    """Build candidate specs from provider catalogs.

    The discovery path is intentionally generic: provider_model_ids() gives us
    the current catalog, while the size band keeps the benchmark focused on
    the model class we actually want to route toward.
    """
    out: List[ModelCandidateSpec] = []
    seen: set[tuple[str, str]] = set()
    for provider in providers:
        ids = provider_model_ids(provider) or []
        kept: List[ModelCandidateSpec] = []
        for model_id in ids:
            model_id = _clean_text(model_id)
            if not model_id:
                continue
            key = (provider.lower(), model_id.lower())
            if key in seen:
                continue
            if _BENCHMARK_NOISE_RE.search(model_id):
                continue
            size_b = estimate_model_params_b(model_id)
            if size_b is None and not include_unknown_size:
                continue
            if min_params_b is not None and size_b is not None and size_b < float(min_params_b):
                continue
            if max_params_b is not None and size_b is not None and size_b > float(max_params_b):
                continue
            candidate = ModelCandidateSpec(
                name=f"{provider}:{model_id}",
                provider=provider,
                model=model_id,
                params_b=size_b,
            )
            kept.append(candidate)
            seen.add(key)
        if max_per_provider is not None and max_per_provider > 0:
            kept = kept[:max_per_provider]
        out.extend(kept)
    return out


def _normalize_ollama_base_url(base_url: str) -> str:
    cleaned = _clean_text(base_url).rstrip("/")
    if cleaned.endswith("/v1"):
        cleaned = cleaned[: -len("/v1")].rstrip("/")
    return cleaned


def discover_ollama_candidates(
    base_url: str,
    *,
    min_params_b: float | None = None,
    max_params_b: float | None = None,
    include_unknown_size: bool = False,
    max_models: int | None = None,
    provider_name: str = "ollama-remote",
) -> List[ModelCandidateSpec]:
    """Discover candidates from a remote Ollama server.

    The discovery call is intentionally narrow: only the Ollama tags endpoint
    is queried, and the caller decides whether to keep the models by size band.
    This lets the benchmark stay focused on the new Ollama box while other
    providers are effectively commented out for the current run.
    """
    root = _normalize_ollama_base_url(base_url)
    if not root:
        return []
    tags_url = f"{root}/api/tags"
    req = Request(tags_url, headers={"Accept": "application/json"})
    try:
        with urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError(f"failed to discover Ollama models from {tags_url}: {exc}") from exc

    models = payload.get("models") if isinstance(payload, Mapping) else []
    if not isinstance(models, list):
        models = []

    out: List[ModelCandidateSpec] = []
    seen: set[str] = set()
    for item in models:
        if not isinstance(item, Mapping):
            continue
        model_id = _clean_text(item.get("name") or item.get("model") or item.get("id") or "")
        if not model_id:
            continue
        if model_id.lower() in seen:
            continue
        if _BENCHMARK_NOISE_RE.search(model_id):
            continue
        details = item.get("details") if isinstance(item.get("details"), Mapping) else {}
        params_raw = (
            item.get("parameter_size")
            or item.get("parameters")
            or (details.get("parameter_size") if isinstance(details, Mapping) else None)
        )
        size_b = estimate_model_params_b(model_id)
        if size_b is None and isinstance(params_raw, str):
            match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*B", params_raw, re.IGNORECASE)
            if match:
                try:
                    size_b = float(match.group(1))
                except Exception:
                    size_b = None
        if size_b is None and not include_unknown_size:
            continue
        if min_params_b is not None and size_b is not None and size_b < float(min_params_b):
            continue
        if max_params_b is not None and size_b is not None and size_b > float(max_params_b):
            continue
        out.append(
            ModelCandidateSpec(
                name=f"{provider_name}:{model_id}",
                provider=provider_name,
                model=model_id,
                base_url=root,
                api_mode="ollama_native",
                params_b=size_b,
                notes="discovered from Ollama /api/tags",
            )
        )
        seen.add(model_id.lower())
        if max_models is not None and max_models > 0 and len(out) >= max_models:
            break
    return out


def load_suite(source: str | Path | None) -> BenchmarkSuite:
    if not source:
        return build_default_suite()
    path = Path(source).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"suite file not found: {path}")
    data = fast_safe_load(path.read_text(encoding="utf-8")) or {}
    if isinstance(data, list):
        return BenchmarkSuite(
            suite_id=path.stem,
            description="",
            cases=[BenchmarkCase.from_mapping(item) for item in data if isinstance(item, Mapping)],
        )
    if isinstance(data, Mapping):
        return BenchmarkSuite.from_mapping(data)
    raise ValueError(f"unsupported suite file structure: {path}")


def load_candidates(source: str | Path | None) -> List[ModelCandidateSpec]:
    if not source:
        return []
    path = Path(source).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"candidate file not found: {path}")
    data = fast_safe_load(path.read_text(encoding="utf-8")) or {}
    if isinstance(data, list):
        raw = data
    elif isinstance(data, Mapping):
        raw = data.get("candidates") if isinstance(data.get("candidates"), list) else data.get("models")
        if raw is None and all(k in data for k in ("provider", "model")):
            raw = [data]
        elif raw is None:
            raw = []
    else:
        raw = []
    return [ModelCandidateSpec.from_mapping(item) for item in raw if isinstance(item, Mapping)]


def _default_context_pack() -> ContextPackSpec:
    return build_default_context_packs()[0]


def _default_prompt_shape() -> PromptShapeSpec:
    return build_default_prompt_shapes()[0]


def _render_prompt_text(
    case: BenchmarkCase,
    prompt_shape: PromptShapeSpec | None = None,
    context_pack: ContextPackSpec | None = None,
) -> str:
    prompt_shape = prompt_shape or _default_prompt_shape()
    context_pack = context_pack or _default_context_pack()
    return prompt_shape.render_prompt(case, context_pack)


def _default_prompt(case: BenchmarkCase) -> List[Dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You are a benchmark judge for Hermes. Return ONLY JSON with "
                "keys answer, confidence, brief_reason. Choose one label from "
                "the provided choices."
            ),
        },
        {"role": "user", "content": case.prompt_text()},
    ]


def _parse_case_response(content: Any, choices: Sequence[str]) -> Tuple[str, float, Dict[str, Any]]:
    text = _clean_text(content)
    payload = _extract_json_payload(text)
    answer = payload.get("answer")
    confidence = payload.get("confidence")
    if answer is None:
        # Tolerate a plain label or a leading label in free text.
        answer = text
    choice = _normalize_choice_answer(answer, choices)
    try:
        conf = float(confidence) if confidence is not None else 0.0
    except Exception:
        conf = 0.0
    conf = _clamp_unit_interval(conf)
    return choice, conf, payload


def build_default_invoker() -> Callable[..., Dict[str, Any]]:
    def _invoke_ollama_native(
        candidate: ModelCandidateSpec,
        case: BenchmarkCase,
        prompt_shape: PromptShapeSpec | None = None,
        context_pack: ContextPackSpec | None = None,
    ) -> Dict[str, Any]:
        base_url = _normalize_ollama_base_url(candidate.base_url)
        if not base_url:
            raise RuntimeError(f"candidate {candidate.name!r} is missing an Ollama base_url")
        url = f"{base_url}/api/chat"
        payload = {
            "model": candidate.model,
            "messages": [
                {
                    "role": "system",
                    "content": (prompt_shape.system_message if prompt_shape else _default_prompt_shape().system_message),
                },
                {"role": "user", "content": _render_prompt_text(case, prompt_shape, context_pack)},
            ],
            "stream": False,
            "options": {
                "temperature": candidate.temperature,
                "num_predict": candidate.max_output_tokens,
            },
        }
        data = json.dumps(payload).encode("utf-8")
        req = Request(
            url,
            data=data,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        with urlopen(req, timeout=candidate.timeout_s) as resp:
            body = resp.read().decode("utf-8")
        parsed = json.loads(body) if body else {}
        content = ""
        if isinstance(parsed, Mapping):
            message = parsed.get("message")
            if isinstance(message, Mapping):
                content = _clean_text(message.get("content") or "")
            if not content:
                content = _clean_text(parsed.get("response") or parsed.get("content") or "")
        return {
            "content": content,
            "usage": _json_safe(parsed.get("usage") if isinstance(parsed, Mapping) else {}),
            "resolved_model": candidate.model,
            "response": parsed,
        }

    def _invoke(
        candidate: ModelCandidateSpec,
        case: BenchmarkCase,
        prompt_shape: PromptShapeSpec | None = None,
        context_pack: ContextPackSpec | None = None,
    ) -> Dict[str, Any]:
        prompt_shape = prompt_shape or _default_prompt_shape()
        context_pack = context_pack or _default_context_pack()
        if candidate.api_mode == "ollama_native" or candidate.provider.startswith("ollama"):
            return _invoke_ollama_native(candidate, case, prompt_shape, context_pack)
        client, resolved_model = resolve_provider_client(
            candidate.provider,
            model=candidate.model or None,
            explicit_base_url=candidate.base_url or None,
            explicit_api_key=candidate.api_key or None,
            api_mode=candidate.api_mode or None,
            task="benchmark",
        )
        if client is None or not resolved_model:
            raise RuntimeError(
                f"no usable client for candidate {candidate.name!r} "
                f"(provider={candidate.provider!r}, model={candidate.model!r})"
            )
        messages = [
            {"role": "system", "content": prompt_shape.system_message},
            {"role": "user", "content": _render_prompt_text(case, prompt_shape, context_pack)},
        ]
        kwargs = {
            "model": resolved_model,
            "messages": messages,
            "temperature": candidate.temperature,
            "timeout": candidate.timeout_s,
            **auxiliary_max_tokens_param(candidate.max_output_tokens),
        }
        response = client.chat.completions.create(**kwargs)
        content = ""
        try:
            content = response.choices[0].message.content or ""
        except Exception:
            content = ""
        usage = {}
        try:
            usage = getattr(response, "usage", None) or {}
        except Exception:
            usage = {}
        return {
            "content": content,
            "usage": _json_safe(usage),
            "resolved_model": resolved_model,
            "response": response,
        }

    return _invoke


def _aggregate_model_summary(
    candidate: ModelCandidateSpec,
    results: List[BenchmarkCaseResult],
) -> ModelSummary:
    total = len(results)
    correct = sum(1 for r in results if r.correct)
    confidences = [r.confidence for r in results]
    correct_conf = [r.confidence for r in results if r.correct]
    wrong_conf = [r.confidence for r in results if not r.correct]
    latencies = [r.latency_s for r in results]

    by_subusecase: List[ModelSubusecaseSummary] = []
    for subusecase in sorted({r.subusecase for r in results}):
        subset = [r for r in results if r.subusecase == subusecase]
        sub_total = len(subset)
        sub_correct = sum(1 for r in subset if r.correct)
        sub_conf = [r.confidence for r in subset]
        sub_correct_conf = [r.confidence for r in subset if r.correct]
        sub_wrong_conf = [r.confidence for r in subset if not r.correct]
        sub_latencies = [r.latency_s for r in subset]
        by_subusecase.append(
            ModelSubusecaseSummary(
                subusecase=subusecase,
                case_count=sub_total,
                accuracy=sub_correct / max(1, sub_total),
                avg_confidence=sum(sub_conf) / max(1, len(sub_conf)),
                correct_avg_confidence=(
                    sum(sub_correct_conf) / max(1, len(sub_correct_conf))
                    if sub_correct_conf
                    else 0.0
                ),
                wrong_avg_confidence=(
                    sum(sub_wrong_conf) / max(1, len(sub_wrong_conf))
                    if sub_wrong_conf
                    else 0.0
                ),
                median_latency_s=statistics.median(sub_latencies) if sub_latencies else 0.0,
            )
        )

    return ModelSummary(
        model_name=candidate.name,
        provider=candidate.provider,
        case_count=total,
        correct_count=correct,
        accuracy=correct / max(1, total),
        avg_confidence=sum(confidences) / max(1, len(confidences)),
        correct_avg_confidence=(sum(correct_conf) / max(1, len(correct_conf)) if correct_conf else 0.0),
        wrong_avg_confidence=(sum(wrong_conf) / max(1, len(wrong_conf)) if wrong_conf else 0.0),
        median_latency_s=statistics.median(latencies) if latencies else 0.0,
        by_subusecase=by_subusecase,
    )


def _aggregate_dimension_summary(
    dimension: str,
    label: str,
    results: List[BenchmarkCaseResult],
) -> DimensionSummary:
    total = len(results)
    correct = sum(1 for r in results if r.correct)
    confidences = [r.confidence for r in results]
    correct_conf = [r.confidence for r in results if r.correct]
    wrong_conf = [r.confidence for r in results if not r.correct]
    latencies = [r.latency_s for r in results]

    by_subusecase: List[ModelSubusecaseSummary] = []
    for subusecase in sorted({r.subusecase for r in results}):
        subset = [r for r in results if r.subusecase == subusecase]
        sub_total = len(subset)
        sub_correct = sum(1 for r in subset if r.correct)
        sub_conf = [r.confidence for r in subset]
        sub_correct_conf = [r.confidence for r in subset if r.correct]
        sub_wrong_conf = [r.confidence for r in subset if not r.correct]
        sub_latencies = [r.latency_s for r in subset]
        by_subusecase.append(
            ModelSubusecaseSummary(
                subusecase=subusecase,
                case_count=sub_total,
                accuracy=sub_correct / max(1, sub_total),
                avg_confidence=sum(sub_conf) / max(1, len(sub_conf)),
                correct_avg_confidence=(
                    sum(sub_correct_conf) / max(1, len(sub_correct_conf))
                    if sub_correct_conf
                    else 0.0
                ),
                wrong_avg_confidence=(
                    sum(sub_wrong_conf) / max(1, len(sub_wrong_conf))
                    if sub_wrong_conf
                    else 0.0
                ),
                median_latency_s=statistics.median(sub_latencies) if sub_latencies else 0.0,
            )
        )

    return DimensionSummary(
        dimension=dimension,
        label=label,
        case_count=total,
        correct_count=correct,
        accuracy=correct / max(1, total),
        avg_confidence=sum(confidences) / max(1, len(confidences)),
        correct_avg_confidence=(sum(correct_conf) / max(1, len(correct_conf)) if correct_conf else 0.0),
        wrong_avg_confidence=(sum(wrong_conf) / max(1, len(wrong_conf)) if wrong_conf else 0.0),
        median_latency_s=statistics.median(latencies) if latencies else 0.0,
        by_subusecase=by_subusecase,
    )


def _supports_variants(invoker: Callable[..., Dict[str, Any]]) -> bool:
    try:
        sig = inspect.signature(invoker)
    except (TypeError, ValueError):
        return False
    positional = [
        p for p in sig.parameters.values()
        if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    if any(p.kind == inspect.Parameter.VAR_POSITIONAL for p in sig.parameters.values()):
        return True
    return len(positional) >= 4


def _recommend_routing(model_summaries: Sequence[ModelSummary]) -> List[RoutingRecommendation]:
    per_subusecase: Dict[str, List[ModelSummary]] = {}
    for summary in model_summaries:
        for item in summary.by_subusecase:
            per_subusecase.setdefault(item.subusecase, []).append(summary)

    recommendations: List[RoutingRecommendation] = []
    for subusecase, summaries in sorted(per_subusecase.items()):
        ranked = sorted(
            summaries,
            key=lambda summary: (
                -next((item.accuracy for item in summary.by_subusecase if item.subusecase == subusecase), 0.0),
                next((item.median_latency_s for item in summary.by_subusecase if item.subusecase == subusecase), 0.0),
                -next((item.correct_avg_confidence for item in summary.by_subusecase if item.subusecase == subusecase), 0.0),
                summary.model_name.lower(),
            ),
        )
        if not ranked:
            continue
        best = ranked[0]
        best_item = next(item for item in best.by_subusecase if item.subusecase == subusecase)
        runner_up = ranked[1] if len(ranked) > 1 else None
        runner_item = None
        if runner_up is not None:
            runner_item = next(item for item in runner_up.by_subusecase if item.subusecase == subusecase)
        sample_count = best_item.case_count
        gap = best_item.accuracy - (runner_item.accuracy if runner_item else 0.0)
        note = ""
        if sample_count < 3:
            note = "small sample; treat as provisional"
        elif gap < 0.10:
            note = "close race; keep a fallback"
        recommendations.append(
            RoutingRecommendation(
                subusecase=subusecase,
                best_model=best.model_name,
                runner_up_model=runner_up.model_name if runner_up else "",
                sample_count=sample_count,
                best_accuracy=best_item.accuracy,
                runner_up_accuracy=runner_item.accuracy if runner_item else 0.0,
                accuracy_gap=gap,
                best_median_latency_s=best_item.median_latency_s,
                note=note,
            )
        )
    return recommendations


def run_model_benchmark(
    candidates: Sequence[ModelCandidateSpec],
    suite: Optional[BenchmarkSuite] = None,
    *,
    invoker: Optional[Callable[..., Dict[str, Any]]] = None,
    prompt_shapes: Optional[Sequence[PromptShapeSpec]] = None,
    context_packs: Optional[Sequence[ContextPackSpec]] = None,
) -> BenchmarkReport:
    suite = suite or build_default_suite()
    if not candidates:
        raise ValueError("at least one candidate is required")
    invoke = invoker or build_default_invoker()
    prompt_shapes = list(prompt_shapes or [_default_prompt_shape()])
    context_packs = list(context_packs or [_default_context_pack()])
    supports_variants = _supports_variants(invoke)

    case_results: List[BenchmarkCaseResult] = []
    model_summaries: List[ModelSummary] = []
    prompt_shape_summaries: List[DimensionSummary] = []
    context_pack_summaries: List[DimensionSummary] = []
    config_summaries: List[DimensionSummary] = []
    notes: List[str] = []

    for candidate in candidates:
        per_candidate_results: List[BenchmarkCaseResult] = []
        for prompt_shape in prompt_shapes:
            for context_pack in context_packs:
                per_config_results: List[BenchmarkCaseResult] = []
                for case in suite.cases:
                    started = time.perf_counter()
                    error = ""
                    content = {}
                    predicted = ""
                    conf = 0.0
                    try:
                        if supports_variants:
                            payload = invoke(candidate, case, prompt_shape, context_pack)
                        else:
                            payload = invoke(candidate, case)
                        content = payload or {}
                        predicted, conf, parsed = _parse_case_response(content.get("content", ""), case.choices)
                        content = {**content, "parsed": _json_safe(parsed)}
                    except Exception as exc:
                        error = str(exc)
                    latency = time.perf_counter() - started
                    correct = bool(predicted and predicted == case.gold_choice)
                    result = BenchmarkCaseResult(
                        case_id=case.case_id,
                        subusecase=case.subusecase,
                        model_name=candidate.name,
                        provider=candidate.provider,
                        predicted_choice=predicted,
                        gold_choice=case.gold_choice,
                        correct=correct,
                        confidence=conf,
                        latency_s=latency,
                        prompt_shape=prompt_shape.name,
                        context_pack=context_pack.name,
                        error=error,
                        raw=content,
                    )
                    per_candidate_results.append(result)
                    per_config_results.append(result)
                    case_results.append(result)

                config_summaries.append(
                    _aggregate_dimension_summary(
                        "config",
                        f"{candidate.name} | {prompt_shape.name} | {context_pack.name}",
                        per_config_results,
                    )
                )

        model_summaries.append(_aggregate_model_summary(candidate, per_candidate_results))

    recommendations = _recommend_routing(model_summaries)
    for shape in prompt_shapes:
        shape_results = [r for r in case_results if r.prompt_shape == shape.name]
        prompt_shape_summaries.append(
            _aggregate_dimension_summary("prompt_shape", shape.name, shape_results)
        )
    for pack in context_packs:
        pack_results = [r for r in case_results if r.context_pack == pack.name]
        context_pack_summaries.append(
            _aggregate_dimension_summary("context_pack", pack.name, pack_results)
        )
    for rec in recommendations:
        if rec.note:
            notes.append(f"{rec.subusecase}: {rec.note}")

    return BenchmarkReport(
        suite_id=suite.suite_id,
        case_count=len(suite.cases),
        model_count=len(candidates),
        prompt_shape_count=len(prompt_shapes),
        context_pack_count=len(context_packs),
        cases=list(suite.cases),
        candidates=list(candidates),
        prompt_shapes=list(prompt_shapes),
        context_packs=list(context_packs),
        case_results=case_results,
        model_summaries=model_summaries,
        prompt_shape_summaries=prompt_shape_summaries,
        context_pack_summaries=context_pack_summaries,
        config_summaries=config_summaries,
        recommendations=recommendations,
        notes=notes,
    )


def _load_candidate_specs_from_args(args: argparse.Namespace) -> List[ModelCandidateSpec]:
    specs: List[ModelCandidateSpec] = []
    ollama_base_url = _clean_text(getattr(args, "ollama_base_url", "") or "")
    if ollama_base_url:
        min_params_b = getattr(args, "min_params_b", None)
        max_params_b = getattr(args, "max_params_b", None)
        include_unknown = bool(getattr(args, "include_unknown_size", False))
        max_models = getattr(args, "max_candidates_per_provider", None)
        return discover_ollama_candidates(
            ollama_base_url,
            min_params_b=min_params_b,
            max_params_b=max_params_b,
            include_unknown_size=include_unknown,
            max_models=max_models,
            provider_name="ollama-remote",
        )
    if getattr(args, "candidate_file", ""):
        specs.extend(load_candidates(args.candidate_file))
    for item in getattr(args, "candidate", []) or []:
        payload = fast_safe_load(item) if isinstance(item, str) else item
        if isinstance(payload, Mapping):
            specs.append(ModelCandidateSpec.from_mapping(payload))
        else:
            raise ValueError(f"invalid --candidate payload: {item!r}")
    if specs:
        return specs

    providers = [str(x).strip() for x in (getattr(args, "provider", []) or []) if str(x).strip()]
    if providers:
        min_params_b = getattr(args, "min_params_b", None)
        max_params_b = getattr(args, "max_params_b", None)
        include_unknown = bool(getattr(args, "include_unknown_size", False))
        max_per_provider = getattr(args, "max_candidates_per_provider", None)
        return discover_candidates_from_providers(
            providers,
            min_params_b=min_params_b,
            max_params_b=max_params_b,
            include_unknown_size=include_unknown,
            max_per_provider=max_per_provider,
        )
    return specs


def _resolve_named_or_mapping_spec(
    raw_item: Any,
    defaults: Sequence[Any],
    spec_cls: Any,
) -> Any:
    payload = fast_safe_load(raw_item) if isinstance(raw_item, str) else raw_item
    if isinstance(payload, Mapping):
        return spec_cls.from_mapping(payload)
    if isinstance(payload, str):
        name = _clean_text(payload)
        if not name:
            return None
        for item in defaults:
            if getattr(item, "name", "") == name:
                return item
        return spec_cls(name=name)
    return None


def _load_prompt_shapes_from_args(args: argparse.Namespace) -> List[PromptShapeSpec]:
    raw = getattr(args, "prompt_shape", []) or []
    if not raw:
        return [_default_prompt_shape()]
    defaults = build_default_prompt_shapes()
    out: List[PromptShapeSpec] = []
    for item in raw:
        spec = _resolve_named_or_mapping_spec(item, defaults, PromptShapeSpec)
        if spec is None:
            raise ValueError(f"invalid --prompt-shape payload: {item!r}")
        out.append(spec)
    return out


def _load_context_packs_from_args(args: argparse.Namespace) -> List[ContextPackSpec]:
    raw = getattr(args, "context_pack", []) or []
    if not raw:
        return [_default_context_pack()]
    defaults = build_default_context_packs()
    out: List[ContextPackSpec] = []
    for item in raw:
        spec = _resolve_named_or_mapping_spec(item, defaults, ContextPackSpec)
        if spec is None:
            raise ValueError(f"invalid --context-pack payload: {item!r}")
        out.append(spec)
    return out


def _load_suite_from_args(args: argparse.Namespace) -> BenchmarkSuite:
    suite_path = getattr(args, "suite", "")
    if suite_path:
        return load_suite(suite_path)
    return build_default_suite()


def _print_human_summary(report: BenchmarkReport) -> None:
    print(
        f"Suite: {report.suite_id}  cases={report.case_count}  models={report.model_count}  "
        f"prompt_shapes={report.prompt_shape_count}  context_packs={report.context_pack_count}"
    )
    print()
    print("Leaderboard")
    print(f"{'model':<28} {'provider':<14} {'size':>7} {'acc':>8} {'median_lat':>11} {'cases':>5}")
    print("-" * 72)
    for summary in sorted(
        report.model_summaries,
        key=lambda s: (-s.accuracy, s.median_latency_s, s.model_name.lower()),
    ):
        size = next((c.params_b for c in report.candidates if c.name == summary.model_name), None)
        size_txt = f"{size:.0f}B" if size is not None else "unknown"
        print(
            f"{summary.model_name:<28} {summary.provider:<14} "
            f"{size_txt:>7} {summary.accuracy:>8.2%} {summary.median_latency_s:>11.2f}s {summary.case_count:>5}"
        )
    print()
    print("Prompt shapes")
    print(f"{'shape':<22} {'acc':>8} {'median_lat':>11} {'cases':>5}")
    print("-" * 52)
    for summary in sorted(report.prompt_shape_summaries, key=lambda s: (-s.accuracy, s.median_latency_s, s.label.lower())):
        print(f"{summary.label:<22} {summary.accuracy:>8.2%} {summary.median_latency_s:>11.2f}s {summary.case_count:>5}")
    print()
    print("Context packs")
    print(f"{'pack':<22} {'acc':>8} {'median_lat':>11} {'cases':>5}")
    print("-" * 52)
    for summary in sorted(report.context_pack_summaries, key=lambda s: (-s.accuracy, s.median_latency_s, s.label.lower())):
        print(f"{summary.label:<22} {summary.accuracy:>8.2%} {summary.median_latency_s:>11.2f}s {summary.case_count:>5}")
    print()
    print("Top configs")
    print(f"{'config':<52} {'acc':>8} {'median_lat':>11} {'cases':>5}")
    print("-" * 82)
    for summary in sorted(report.config_summaries, key=lambda s: (-s.accuracy, s.median_latency_s, s.label.lower()))[:10]:
        print(f"{summary.label:<52} {summary.accuracy:>8.2%} {summary.median_latency_s:>11.2f}s {summary.case_count:>5}")
    print()
    print("Routing recommendations")
    for rec in report.recommendations:
        gap = f"{rec.accuracy_gap:.2%}"
        runner = f" runner-up={rec.runner_up_model}" if rec.runner_up_model else ""
        note = f" ({rec.note})" if rec.note else ""
        print(
            f"- {rec.subusecase}: {rec.best_model} "
            f"[acc={rec.best_accuracy:.2%}, gap={gap}, n={rec.sample_count}]"
            f"{runner}{note}"
        )


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark cloud LLMs across Hermes eval suites")
    parser.add_argument(
        "--suite",
        default="",
        help="Path to a YAML/JSON suite file. Defaults to a built-in Hermes routing suite.",
    )
    parser.add_argument(
        "--candidate-file",
        default="",
        help="Path to a YAML/JSON file containing candidate model specs.",
    )
    parser.add_argument(
        "--candidate",
        action="append",
        default=[],
        help="Inline JSON/YAML candidate spec (repeatable).",
    )
    parser.add_argument(
        "--prompt-shape",
        action="append",
        default=[],
        help="Prompt-shape preset name or JSON/YAML spec (repeatable).",
    )
    parser.add_argument(
        "--context-pack",
        action="append",
        default=[],
        help="Context-pack preset name or JSON/YAML spec (repeatable).",
    )
    parser.add_argument(
        "--provider",
        action="append",
        default=[],
        help="Provider name to auto-discover candidates from (repeatable).",
    )
    parser.add_argument(
        "--ollama-base-url",
        default="",
        help="Remote Ollama base URL to discover candidates from (e.g. http://host:11434).",
    )
    parser.add_argument(
        "--min-params-b",
        type=float,
        default=None,
        help="Optional minimum parameter size filter for auto-discovered candidates.",
    )
    parser.add_argument(
        "--max-params-b",
        type=float,
        default=None,
        help="Optional maximum parameter size filter for auto-discovered candidates.",
    )
    parser.add_argument(
        "--include-unknown-size",
        action="store_true",
        help="Keep candidates whose parameter size cannot be inferred.",
    )
    parser.add_argument(
        "--max-candidates-per-provider",
        type=int,
        default=5,
        help="Cap auto-discovered candidates per provider (default 5).",
    )
    parser.add_argument(
        "--report",
        default="",
        help="Optional path to write the benchmark report as JSON.",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON only")
    args = parser.parse_args(argv)

    candidates = _load_candidate_specs_from_args(args)
    if not candidates:
        raise SystemExit("no candidates provided; use --candidate-file/--candidate or --provider")
    suite = _load_suite_from_args(args)
    prompt_shapes = _load_prompt_shapes_from_args(args)
    context_packs = _load_context_packs_from_args(args)
    report = run_model_benchmark(
        candidates,
        suite=suite,
        prompt_shapes=prompt_shapes,
        context_packs=context_packs,
    )
    payload = report.to_dict()
    if args.report:
        path = Path(args.report).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if args.json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        _print_human_summary(report)
        print()
        print(json.dumps(payload, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
