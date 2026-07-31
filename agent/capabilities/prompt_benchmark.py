"""Capability for comparing prompt variants against shared eval cases."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence

from agent.auxiliary_client import call_llm, get_runtime_main_snapshot, set_runtime_main
from agent.capabilities.base import Capability, CapabilityContext, CapabilityResult
from agent.prompt_comparison import (
    PromptComparisonCase,
    PromptComparisonReport,
    PromptScorer,
    PromptVariantSpec,
    compare_prompt_variants,
    default_prompt_scorer,
)

logger = logging.getLogger(__name__)


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


def _coerce_cases(raw_cases: Any) -> List[PromptComparisonCase]:
    cases: List[PromptComparisonCase] = []
    for item in list(raw_cases or []):
        if isinstance(item, PromptComparisonCase):
            cases.append(item)
        elif isinstance(item, dict):
            cases.append(PromptComparisonCase.from_mapping(item))
    return cases


def _coerce_variants(raw_variants: Any) -> List[PromptVariantSpec]:
    variants: List[PromptVariantSpec] = []
    for item in list(raw_variants or []):
        if isinstance(item, PromptVariantSpec):
            variants.append(item)
        elif isinstance(item, dict):
            variants.append(PromptVariantSpec.from_mapping(item))
    return variants


def _default_invoker(runtime: Dict[str, Any]):
    provider = str(runtime.get("provider") or "").strip()
    model = str(runtime.get("model") or "").strip()
    base_url = str(runtime.get("base_url") or "").strip()
    api_key = str(runtime.get("api_key") or "").strip()
    api_mode = str(runtime.get("api_mode") or "").strip()
    temperature = float(runtime.get("temperature") if runtime.get("temperature") is not None else 0.0)
    timeout = float(runtime.get("timeout_s") if runtime.get("timeout_s") is not None else 120.0)
    max_tokens = int(runtime.get("max_output_tokens") if runtime.get("max_output_tokens") is not None else 256)

    def _invoke(variant: PromptVariantSpec, case: PromptComparisonCase) -> Any:
        messages = variant.render_messages(case)
        token = set_runtime_main(provider, model, base_url=base_url, api_key=api_key, api_mode=api_mode)
        try:
            extra_body = dict(runtime.get("extra_body") or {})
            if runtime.get("force_json", True):
                extra_body.setdefault("format", "json")
            return call_llm(
                task="prompt_benchmark",
                provider=provider,
                model=model,
                base_url=base_url,
                api_key=api_key,
                api_mode=api_mode,
                messages=messages,
                temperature=float(variant.metadata.get("temperature") if variant.metadata.get("temperature") is not None else temperature),
                max_tokens=int(variant.metadata.get("max_output_tokens") if variant.metadata.get("max_output_tokens") is not None else max_tokens),
                timeout=float(variant.metadata.get("timeout_s") if variant.metadata.get("timeout_s") is not None else timeout),
                main_runtime=get_runtime_main_snapshot(),
                extra_body=extra_body,
            )
        finally:
            from agent.auxiliary_client import reset_runtime_main

            reset_runtime_main(token)

    return _invoke


class PromptBenchmarkCapability(Capability):
    name = "prompt_benchmark"
    description = (
        "Compare two or more prompt variants on a shared eval suite, using the "
        "same case set, scoring rule, and runtime model/provider."
    )
    required_tools: List[str] = []

    def execute(self, ctx: CapabilityContext) -> CapabilityResult:
        extras = dict(ctx.extras or {})
        cases = _coerce_cases(extras.get("cases"))
        variants = _coerce_variants(extras.get("variants"))
        if len(variants) < 2:
            return CapabilityResult(
                status="needs_input",
                capability=self.name,
                message="prompt_benchmark needs at least two prompt variants",
                unresolved_questions=["Provide at least two variants to compare."],
                confidence=0.0,
            )
        if not cases:
            return CapabilityResult(
                status="needs_input",
                capability=self.name,
                message="prompt_benchmark needs at least one case",
                unresolved_questions=["Provide at least one evaluation case."],
                confidence=0.0,
            )

        scorer: Optional[PromptScorer] = extras.get("score_fn")
        if not callable(scorer):
            scorer = default_prompt_scorer

        invoker = extras.get("invoke_fn")
        if not callable(invoker):
            runtime = extras.get("runtime") if isinstance(extras.get("runtime"), dict) else {}
            if not runtime:
                runtime = {
                    "provider": extras.get("provider") or "",
                    "model": extras.get("model") or "",
                    "base_url": extras.get("base_url") or "",
                    "api_key": extras.get("api_key") or "",
                    "api_mode": extras.get("api_mode") or "",
                    "temperature": extras.get("temperature"),
                    "timeout_s": extras.get("timeout_s"),
                    "max_output_tokens": extras.get("max_output_tokens"),
                    "force_json": extras.get("force_json", True),
                    "extra_body": extras.get("extra_body") or {},
                }
            invoker = _default_invoker(runtime)

        report: PromptComparisonReport = compare_prompt_variants(
            variants,
            cases,
            invoker,
            scorer,
            success_threshold=float(extras.get("success_threshold") or 0.75),
        )
        comparison = report.comparison()
        best_variant_id = report.best_variant_id()
        best_summary = next((summary for summary in report.summaries if summary.variant_id == best_variant_id), None)
        result_message = "Prompt comparison complete."
        if best_summary is not None:
            result_message = (
                f"Best variant {best_summary.variant_id} with accuracy {best_summary.accuracy:.3f} "
                f"and avg score {best_summary.avg_score:.3f}."
            )
        return CapabilityResult(
            status="success",
            capability=self.name,
            output={
                "report": report.to_dict(),
                "best_variant_id": best_variant_id,
                "comparison": comparison.to_dict() if comparison is not None else None,
            },
            confidence=best_summary.accuracy if best_summary is not None else 0.0,
            message=result_message,
            artifacts=[best_variant_id] if best_variant_id else [],
        )
