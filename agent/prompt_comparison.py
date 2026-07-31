"""Reusable prompt comparison primitives.

This module is intentionally generic: callers supply the prompt variants,
cases, invocation strategy, and scoring function. The same engine can be used
to compare two prompt shapes, benchmark model-specific prompt tuning, or run
regression checks on prompt rewrites.
"""

from __future__ import annotations

import json
import statistics
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence


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


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _extract_text(response: Any) -> str:
    if isinstance(response, str):
        return response.strip()
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()
    choices = getattr(response, "choices", None)
    if isinstance(choices, list) and choices:
        message = getattr(choices[0], "message", None)
        if message is not None:
            content = getattr(message, "content", None)
            if isinstance(content, str) and content.strip():
                return content.strip()
    if isinstance(response, dict):
        for key in ("output_text", "text", "content"):
            val = response.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
        choices = response.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                message = first.get("message")
                if isinstance(message, dict):
                    content = message.get("content")
                    if isinstance(content, str) and content.strip():
                        return content.strip()
    return str(response).strip()


def extract_json_block(text: str) -> Optional[Dict[str, Any]]:
    raw = (text or "").strip()
    if not raw:
        return None
    if raw.startswith("```"):
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            raw = raw[start : end + 1]
    if not raw.startswith("{"):
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            raw = raw[start : end + 1]
    try:
        parsed = json.loads(raw)
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def _response_finish_reason(response: Any) -> str:
    choices = getattr(response, "choices", None)
    if isinstance(choices, list) and choices:
        finish_reason = getattr(choices[0], "finish_reason", "")
        return str(finish_reason or "").strip().lower()
    if isinstance(response, dict) and "finish_reason" in response:
        return str(response.get("finish_reason") or "").strip().lower()
    return ""


@dataclass(frozen=True)
class PromptComparisonCase:
    """A single evaluation case for prompt comparison."""

    case_id: str
    description: str = ""
    input_payload: Any = None
    expected: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "PromptComparisonCase":
        return cls(
            case_id=_clean_text(data.get("case_id") or data.get("id") or ""),
            description=_clean_text(data.get("description") or ""),
            input_payload=data.get("input_payload", data.get("input")),
            expected=dict(data.get("expected") or {}),
            metadata=dict(data.get("metadata") or {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "description": self.description,
            "input_payload": _json_safe(self.input_payload),
            "expected": _json_safe(self.expected),
            "metadata": _json_safe(self.metadata),
        }


@dataclass(frozen=True)
class PromptVariantSpec:
    """A prompt variant to compare against another variant."""

    variant_id: str
    name: str = ""
    system_prompt: str = ""
    user_prompt: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "PromptVariantSpec":
        variant_id = _clean_text(data.get("variant_id") or data.get("name") or data.get("id") or "")
        name = _clean_text(data.get("name") or variant_id)
        return cls(
            variant_id=variant_id or name,
            name=name,
            system_prompt=str(data.get("system_prompt") or ""),
            user_prompt=str(data.get("user_prompt") or data.get("prompt") or ""),
            metadata=dict(data.get("metadata") or {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "variant_id": self.variant_id,
            "name": self.name,
            "system_prompt": self.system_prompt,
            "user_prompt": self.user_prompt,
            "metadata": _json_safe(self.metadata),
        }

    def render_messages(self, case: PromptComparisonCase) -> List[Dict[str, str]]:
        """Render a prompt stack for the case.

        The default contract is conservative: prompt text stays intact and the
        case payload is appended as a final user turn unless the variant opts
        out via ``metadata.append_case_input = False``.
        """

        messages: List[Dict[str, str]] = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        if self.user_prompt:
            messages.append({"role": "user", "content": self.user_prompt})
        append_case = bool(self.metadata.get("append_case_input", True))
        if append_case and case.input_payload is not None:
            if isinstance(case.input_payload, str):
                content = case.input_payload
            else:
                content = json.dumps(_json_safe(case.input_payload), ensure_ascii=False, separators=(",", ":"))
            messages.append({"role": "user", "content": content})
        return messages


@dataclass
class PromptComparisonScore:
    score: float
    parseable: bool = False
    complete_json: bool = False
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PromptComparisonResult:
    case_id: str
    variant_id: str
    raw: Dict[str, Any]
    parsed: Dict[str, Any]
    finish_reason: str
    latency_s: float
    score: float
    parseable: bool
    complete_json: bool
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "variant_id": self.variant_id,
            "raw": _json_safe(self.raw),
            "parsed": _json_safe(self.parsed),
            "finish_reason": self.finish_reason,
            "latency_s": round(float(self.latency_s or 0.0), 4),
            "score": round(float(self.score or 0.0), 4),
            "parseable": bool(self.parseable),
            "complete_json": bool(self.complete_json),
            "details": _json_safe(self.details),
        }


@dataclass
class PromptComparisonSummary:
    variant_id: str
    case_count: int
    accuracy: float
    avg_score: float
    median_latency_s: float
    parseable_rate: float
    complete_json_rate: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "variant_id": self.variant_id,
            "case_count": self.case_count,
            "accuracy": round(float(self.accuracy or 0.0), 4),
            "avg_score": round(float(self.avg_score or 0.0), 4),
            "median_latency_s": round(float(self.median_latency_s or 0.0), 4),
            "parseable_rate": round(float(self.parseable_rate or 0.0), 4),
            "complete_json_rate": round(float(self.complete_json_rate or 0.0), 4),
        }


@dataclass
class PromptComparisonDelta:
    winner_variant_id: str
    loser_variant_id: str
    accuracy_delta: float
    avg_score_delta: float
    median_latency_delta_s: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "winner_variant_id": self.winner_variant_id,
            "loser_variant_id": self.loser_variant_id,
            "accuracy_delta": round(float(self.accuracy_delta or 0.0), 4),
            "avg_score_delta": round(float(self.avg_score_delta or 0.0), 4),
            "median_latency_delta_s": round(float(self.median_latency_delta_s or 0.0), 4),
        }


@dataclass
class PromptComparisonReport:
    case_count: int
    variants: List[PromptVariantSpec]
    case_results: List[PromptComparisonResult]
    summaries: List[PromptComparisonSummary]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_count": self.case_count,
            "variants": [variant.to_dict() for variant in self.variants],
            "case_results": [result.to_dict() for result in self.case_results],
            "summaries": [summary.to_dict() for summary in self.summaries],
            "best_variant_id": self.best_variant_id(),
            "comparison": self.comparison().to_dict() if self.comparison() is not None else None,
        }

    def best_variant_id(self) -> str:
        if not self.summaries:
            return ""
        ranked = sorted(self.summaries, key=lambda s: (-s.accuracy, -s.avg_score, s.median_latency_s, s.variant_id))
        return ranked[0].variant_id

    def comparison(self) -> Optional[PromptComparisonDelta]:
        if len(self.summaries) < 2:
            return None
        ranked = sorted(self.summaries, key=lambda s: (-s.accuracy, -s.avg_score, s.median_latency_s, s.variant_id))
        winner, loser = ranked[0], ranked[1]
        return PromptComparisonDelta(
            winner_variant_id=winner.variant_id,
            loser_variant_id=loser.variant_id,
            accuracy_delta=winner.accuracy - loser.accuracy,
            avg_score_delta=winner.avg_score - loser.avg_score,
            median_latency_delta_s=winner.median_latency_s - loser.median_latency_s,
        )


PromptInvoker = Callable[[PromptVariantSpec, PromptComparisonCase], Any]
PromptScorer = Callable[[Dict[str, Any], PromptComparisonCase, PromptVariantSpec, str], PromptComparisonScore]


def default_prompt_scorer(
    parsed: Dict[str, Any],
    case: PromptComparisonCase,
    variant: PromptVariantSpec,
    finish_reason: str,
) -> PromptComparisonScore:
    parseable = bool(parsed)
    complete_json = parseable and finish_reason != "length"
    if not case.expected:
        score = 1.0 if parseable else 0.0
        return PromptComparisonScore(
            score=score,
            parseable=parseable,
            complete_json=complete_json,
            details={"reason": "no_expected_fields"},
        )

    matched = 0
    total = 0
    mismatched_fields: List[str] = []
    for key, expected in case.expected.items():
        total += 1
        actual = parsed.get(key)
        if _clean_text(actual).lower() == _clean_text(expected).lower() or _clean_text(expected).lower() in _clean_text(actual).lower():
            matched += 1
        else:
            mismatched_fields.append(str(key))
    score = matched / total if total else 0.0
    return PromptComparisonScore(
        score=score,
        parseable=parseable,
        complete_json=complete_json,
        details={
            "matched_fields": matched,
            "total_fields": total,
            "mismatched_fields": mismatched_fields,
        },
    )


def compare_prompt_variants(
    variants: Sequence[PromptVariantSpec],
    cases: Sequence[PromptComparisonCase],
    invoker: PromptInvoker,
    scorer: Optional[PromptScorer] = None,
    *,
    success_threshold: float = 0.75,
) -> PromptComparisonReport:
    scorer = scorer or default_prompt_scorer
    cases = list(cases)
    variants = list(variants)
    results: List[PromptComparisonResult] = []

    for variant in variants:
        for case in cases:
            started = time.time()
            response = invoker(variant, case)
            latency = time.time() - started
            raw_text = _extract_text(response)
            parsed = extract_json_block(raw_text) or {}
            finish_reason = _response_finish_reason(response)
            score_record = scorer(parsed, case, variant, finish_reason)
            details = dict(score_record.details or {})
            details.setdefault("variant_name", variant.name)
            details.setdefault("case_description", case.description)
            results.append(
                PromptComparisonResult(
                    case_id=case.case_id,
                    variant_id=variant.variant_id,
                    raw=_json_safe(getattr(response, "__dict__", response)),
                    parsed=parsed,
                    finish_reason=finish_reason,
                    latency_s=latency,
                    score=float(score_record.score),
                    parseable=bool(score_record.parseable),
                    complete_json=bool(score_record.complete_json),
                    details=details,
                )
            )

    summaries: List[PromptComparisonSummary] = []
    for variant in variants:
        bucket = [result for result in results if result.variant_id == variant.variant_id]
        summaries.append(
            PromptComparisonSummary(
                variant_id=variant.variant_id,
                case_count=len(bucket),
                accuracy=(sum(1.0 for result in bucket if result.score >= success_threshold) / len(bucket)) if bucket else 0.0,
                avg_score=(sum(result.score for result in bucket) / len(bucket)) if bucket else 0.0,
                median_latency_s=statistics.median([result.latency_s for result in bucket]) if bucket else 0.0,
                parseable_rate=(sum(1.0 for result in bucket if result.parseable) / len(bucket)) if bucket else 0.0,
                complete_json_rate=(sum(1.0 for result in bucket if result.complete_json) / len(bucket)) if bucket else 0.0,
            )
        )

    return PromptComparisonReport(
        case_count=len(cases),
        variants=variants,
        case_results=results,
        summaries=summaries,
    )
