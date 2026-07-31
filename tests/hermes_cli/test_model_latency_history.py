from __future__ import annotations

import pytest

from hermes_cli.model_latency import (
    get_model_latency_entry,
    record_model_outcome,
    record_model_latency,
    sort_candidates_by_latency,
)


def test_model_latency_history_updates_moving_average(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_MODEL_LATENCY_PATH", str(tmp_path / "latency.json"))

    record_model_latency("ollama-remote", "qwen2.5:32b", 4.0, task="session_search")
    record_model_latency("ollama-remote", "qwen2.5:32b", 2.0, task="session_search")

    entry = get_model_latency_entry("ollama-remote", "qwen2.5:32b", task="session_search")
    assert entry is not None
    assert entry["samples"] == 2
    assert entry["ewma_latency_s"] == 3.6


def test_model_latency_history_sorts_known_fast_models_first(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_MODEL_LATENCY_PATH", str(tmp_path / "latency.json"))

    record_model_latency("ollama-remote", "gpt-oss:120b", 6.0, task="session_search")
    record_model_latency("ollama-remote", "nemotron-3-super-120b-a12b", 3.0, task="session_search")

    candidates = [
        {"provider": "ollama-remote", "model": "mistral-large-3:675b"},
        {"provider": "ollama-remote", "model": "gpt-oss:120b"},
        {"provider": "ollama-remote", "model": "nemotron-3-super-120b-a12b"},
    ]

    ranked = sort_candidates_by_latency(candidates, task="session_search")
    assert [row["model"] for row in ranked] == [
        "nemotron-3-super-120b-a12b",
        "gpt-oss:120b",
        "mistral-large-3:675b",
    ]


def test_model_latency_history_counts_failures_and_timeouts(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_MODEL_LATENCY_PATH", str(tmp_path / "latency.json"))

    record_model_outcome(
        "ollama-remote",
        "qwen2.5:32b",
        3.0,
        success=True,
        task="session_search",
    )
    record_model_outcome(
        "ollama-remote",
        "qwen2.5:32b",
        5.0,
        success=False,
        timed_out=True,
        task="session_search",
    )

    entry = get_model_latency_entry("ollama-remote", "qwen2.5:32b", task="session_search")
    assert entry is not None
    assert entry["samples"] == 2
    assert entry["success_count"] == 1
    assert entry["failure_count"] == 1
    assert entry["timeout_count"] == 1
    assert entry["last_success"] is False
    assert entry["last_timed_out"] is True
    assert entry["ewma_latency_s"] == pytest.approx(3.4)


def test_model_latency_history_prefers_reliable_models_over_faster_failures(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_MODEL_LATENCY_PATH", str(tmp_path / "latency.json"))

    record_model_outcome(
        "ollama-remote",
        "fast-but-flaky",
        1.0,
        success=False,
        timed_out=True,
        task="session_search",
    )
    record_model_outcome(
        "ollama-remote",
        "slower-but-reliable",
        4.0,
        success=True,
        task="session_search",
    )

    candidates = [
        {"provider": "ollama-remote", "model": "fast-but-flaky"},
        {"provider": "ollama-remote", "model": "slower-but-reliable"},
    ]

    ranked = sort_candidates_by_latency(candidates, task="session_search")
    assert [row["model"] for row in ranked] == [
        "slower-but-reliable",
        "fast-but-flaky",
    ]
