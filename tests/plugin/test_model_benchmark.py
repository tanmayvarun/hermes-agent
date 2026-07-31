from __future__ import annotations

import json

from plugin.experiments.model_benchmark import (
    BenchmarkCase,
    BenchmarkSuite,
    ModelCandidateSpec,
    build_default_prompt_shapes,
    discover_candidates_from_providers,
    discover_ollama_candidates,
    load_candidates,
    load_suite,
    _parse_case_response,
    run_model_benchmark,
)


def test_model_benchmark_recommends_different_models_by_subusecase():
    suite = BenchmarkSuite(
        suite_id="routing-demo",
        cases=[
            BenchmarkCase(
                case_id="message_relevance_link_row",
                subusecase="message_relevance",
                prompt="pick the message row",
                choices=["row", "card"],
                gold_choice="A",
            ),
            BenchmarkCase(
                case_id="irreversible_action_gate",
                subusecase="irreversible_action_gate",
                prompt="should we act now",
                choices=["act", "wait"],
                gold_choice="B",
            ),
        ],
    )
    candidates = [
        ModelCandidateSpec(name="alpha", provider="openrouter", model="alpha-model"),
        ModelCandidateSpec(name="beta", provider="openrouter", model="beta-model"),
    ]

    def invoker(candidate, case):
        answer_map = {
            ("alpha", "message_relevance_link_row"): ("A", 0.96),
            ("alpha", "irreversible_action_gate"): ("A", 0.55),
            ("beta", "message_relevance_link_row"): ("B", 0.51),
            ("beta", "irreversible_action_gate"): ("B", 0.91),
        }
        answer, confidence = answer_map[(candidate.name, case.case_id)]
        return {
            "content": json.dumps(
                {"answer": answer, "confidence": confidence, "brief_reason": "demo"}
            ),
            "usage": {},
            "resolved_model": candidate.model,
        }

    report = run_model_benchmark(candidates, suite=suite, invoker=invoker)

    assert report.case_count == 2
    assert report.model_count == 2
    alpha = next(summary for summary in report.model_summaries if summary.model_name == "alpha")
    beta = next(summary for summary in report.model_summaries if summary.model_name == "beta")
    assert alpha.accuracy == 0.5
    assert beta.accuracy == 0.5
    alpha_message = next(item for item in alpha.by_subusecase if item.subusecase == "message_relevance")
    alpha_gate = next(item for item in alpha.by_subusecase if item.subusecase == "irreversible_action_gate")
    beta_message = next(item for item in beta.by_subusecase if item.subusecase == "message_relevance")
    beta_gate = next(item for item in beta.by_subusecase if item.subusecase == "irreversible_action_gate")
    assert alpha_message.accuracy == 1.0
    assert alpha_gate.accuracy == 0.0
    assert beta_message.accuracy == 0.0
    assert beta_gate.accuracy == 1.0

    relevance = report.best_model_for_subusecase("message_relevance")
    gate = report.best_model_for_subusecase("irreversible_action_gate")
    assert relevance is not None
    assert gate is not None
    assert relevance.best_model == "alpha"
    assert gate.best_model == "beta"
    assert relevance.sample_count == 1
    assert gate.sample_count == 1


def test_model_benchmark_loads_suite_and_candidates(tmp_path):
    candidate_file = tmp_path / "candidates.json"
    candidate_file.write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "name": "alpha",
                        "provider": "openrouter",
                        "model": "alpha-model",
                        "temperature": 0.0,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    suite_file = tmp_path / "suite.json"
    suite_file.write_text(
        json.dumps(
            {
                "suite_id": "custom-suite",
                "description": "custom routing evals",
                "cases": [
                    {
                        "case_id": "editability_gate",
                        "subusecase": "editable_affordance_gate",
                        "prompt": "what should the agent do",
                        "choices": ["type", "wait"],
                        "gold_choice": "A",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    candidates = load_candidates(candidate_file)
    suite = load_suite(suite_file)

    assert len(candidates) == 1
    assert candidates[0].name == "alpha"
    assert suite.suite_id == "custom-suite"
    assert len(suite.cases) == 1
    assert suite.cases[0].subusecase == "editable_affordance_gate"


def test_model_benchmark_default_suite_includes_whatsapp_production_bundle_case():
    suite = load_suite(None)
    case = next(
        item
        for item in suite.cases
        if item.case_id == "whatsapp_production_bundle_message_relevance"
    )
    assert case.subusecase == "message_relevance"
    assert case.gold_choice == "A"
    assert "AX tree data" in case.prompt
    assert "zarooratwala link sent to kulvinder" in case.prompt
    assert case.choices[0].startswith("Inspect or select the source conversation timeline")


def test_model_benchmark_default_suite_includes_hover_reveal_case():
    suite = load_suite(None)
    case = next(item for item in suite.cases if item.case_id == "whatsapp_hover_reveal_message_actions")

    assert case.subusecase == "latent_affordance_probe"
    assert case.gold_choice == "A"
    assert "hover" in case.prompt.lower()
    assert "forward" in case.prompt.lower()
    assert "Captured from live zarooratwala trace" in case.notes
    assert case.choices[0].startswith("Hover the message card")


def test_model_benchmark_default_suite_includes_canonical_zarooratwala_case():
    suite = load_suite(None)
    case = next(item for item in suite.cases if item.case_id == "zarooratwala_forward_message_production_bundle")

    assert case.subusecase == "procedure_stage_selection"
    assert case.gold_choice == "A"
    assert "zarooratwala link sent to kulvinder on whatsapp and forward to pallavi" in case.prompt
    assert case.choices[0].startswith("Open or inspect the source conversation timeline entry")


def test_model_benchmark_default_suite_includes_godrej_nurture_google_maps_case():
    suite = load_suite(None)
    case = next(
        item
        for item in suite.cases
        if item.case_id == "godrej_nurture_electronic_city_phase_1_maps_share_location_production_bundle"
    )

    assert case.subusecase == "procedure_stage_selection"
    assert case.gold_choice == "A"
    assert "godrej nurutre electronic city phase 1" in case.prompt
    assert case.choices[0].startswith("Open or inspect the source conversation timeline entry")


def test_model_benchmark_calibrated_prompt_shape_and_confidence_clamping():
    prompt_shapes = build_default_prompt_shapes()
    calibrated = next(shape for shape in prompt_shapes if shape.name == "calibrated-json")
    assert "0 to 1" in calibrated.system_message
    assert "score_hint" in calibrated.system_message

    choice, confidence, payload = _parse_case_response(
        json.dumps({"answer": "C", "confidence": 1.0596, "brief_reason": "demo"}),
        ["type", "wait", "inspect"],
    )
    assert choice == "C"
    assert confidence == 1.0
    assert payload["confidence"] == 1.0596

    choice, confidence, payload = _parse_case_response(
        json.dumps({"answer": "A", "confidence": -0.2, "brief_reason": "demo"}),
        ["type", "wait", "inspect"],
    )
    assert choice == "A"
    assert confidence == 0.0
    assert payload["confidence"] == -0.2


def test_model_benchmark_discovers_candidates_with_size_band(monkeypatch):
    def fake_provider_model_ids(provider):
        if provider == "ollama-cloud":
            return ["mistral-large-3:675b", "qwen3.5:397b", "gpt-oss:120b"]
        if provider == "cohere":
            return [
                "command-a-plus-05-2026",
                "c4ai-aya-expanse-32b",
                "command-r7b-12-2024",
                "embed-english-v3.0",
            ]
        return []

    monkeypatch.setattr("plugin.experiments.model_benchmark.provider_model_ids", fake_provider_model_ids)

    candidates = discover_candidates_from_providers(
        ["ollama-cloud", "cohere"],
        min_params_b=14,
        max_params_b=32,
        include_unknown_size=False,
        max_per_provider=10,
    )

    names = [c.name for c in candidates]
    assert "cohere:c4ai-aya-expanse-32b" in names
    assert "cohere:command-r7b-12-2024" not in names
    assert "ollama-cloud:mistral-large-3:675b" not in names
    assert all(c.params_b is not None and 14 <= c.params_b <= 32 for c in candidates)


def test_model_benchmark_discovers_ollama_candidates_from_tags(monkeypatch):
    class _FakeResponse:
        def __init__(self, payload: str):
            self._payload = payload.encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return self._payload

    def fake_urlopen(request, timeout=0):
        assert "http://157.20.215.33:11434/api/tags" in getattr(request, "full_url", str(request))
        return _FakeResponse(
            json.dumps(
                {
                    "models": [
                        {
                            "name": "deepseek-r1:14b",
                            "details": {"parameter_size": "14.8B"},
                        },
                        {
                            "name": "deepseek-r1:32b",
                            "details": {"parameter_size": "32.8B"},
                        },
                        {
                            "name": "qwen2.5:32b",
                            "details": {"parameter_size": "32.8B"},
                        },
                        {
                            "name": "llama3.1:latest",
                            "details": {"parameter_size": "8.0B"},
                        },
                        {
                            "name": "llama3.2-vision:latest",
                            "details": {"parameter_size": "10.7B"},
                        },
                    ]
                }
            )
        )

    monkeypatch.setattr("plugin.experiments.model_benchmark.urlopen", fake_urlopen)

    candidates = discover_ollama_candidates(
        "http://157.20.215.33:11434",
        min_params_b=14,
        max_params_b=32,
        include_unknown_size=False,
        max_models=10,
    )

    names = [c.name for c in candidates]
    assert names == [
        "ollama-remote:deepseek-r1:14b",
        "ollama-remote:deepseek-r1:32b",
        "ollama-remote:qwen2.5:32b",
    ]
    assert all(c.provider == "ollama-remote" for c in candidates)
    assert all(c.base_url == "http://157.20.215.33:11434" for c in candidates)
    assert all(c.api_mode == "ollama_native" for c in candidates)
    assert all(c.params_b is not None and 14 <= c.params_b <= 32 for c in candidates)
