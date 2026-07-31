"""Tests for LocateFileCapability + capability registry."""

from __future__ import annotations

import pytest

from agent.capabilities import (
    LocateFileCapability,
    ensure_builtins,
    get_capability,
    is_locate_intent,
    list_capabilities,
    parse_locate_query,
)
from agent.capabilities.base import CapabilityResult
from tools.locate_file import reset_locate_state


@pytest.fixture(autouse=True)
def _clear_state():
    reset_locate_state()
    yield
    reset_locate_state()


def test_is_locate_intent():
    assert is_locate_intent("Find the Plugin 3.3kW Technical Specifications V3 file")
    assert is_locate_intent("Locate brochure PDF in Downloads")
    assert is_locate_intent("find the plugin 3.3kw ev charger tech specifications file in downloads folder")
    assert not is_locate_intent("refactor the pytest suite")
    assert not is_locate_intent("hello")


def test_parse_locate_query_attributes():
    parsed = parse_locate_query("Plugin 3.3kW Technical Specifications V3")
    assert parsed.brand == "plugin"
    assert parsed.power == "3.3kw"
    assert parsed.version == "v3"
    assert parsed.document_type in {"specifications", "specification", "specs"}


def test_parse_locate_query_attributes_for_ev_charger_prompt():
    parsed = parse_locate_query(
        "find the plugin 3.3kw ev charger tech specifications file in downloads folder"
    )
    assert parsed.brand == "plugin"
    assert parsed.power == "3.3kw"
    assert parsed.document_type in {"specifications", "specification", "specs"}
    assert ".pdf" in parsed.extensions


def test_capability_strong_hit_success():
    hit = "/Users/me/Downloads/Plugin_3.3kW_Technical_Specifications_V3.pdf"

    def search_fn(pattern, path, target="files", file_glob=None, limit=40):
        return [hit]

    cap = LocateFileCapability()
    result = cap.execute_objective(
        "Find Plugin 3.3kW Technical Specifications V3",
        task_id="cap-strong",
        search_fn=search_fn,
        extensions=["pdf"],
    )
    assert isinstance(result, CapabilityResult)
    assert result.status == "success"
    assert result.confidence >= 0.9
    assert result.artifacts == [hit]
    assert result.observations and result.observations[0]["step"] == "parse"

    payload = cap.to_tool_payload(result)
    assert payload["success"] is True
    assert payload["capability"] == "locate_file"
    assert payload["candidates"]


def test_capability_strong_hit_success_for_ev_charger_prompt():
    hit = "/Users/me/Downloads/Plugin_3.3kW_Technical_Specifications_V3.pdf"

    def search_fn(pattern, path, target="files", file_glob=None, limit=40):
        return [hit]

    cap = LocateFileCapability()
    result = cap.execute_objective(
        "find the plugin 3.3kw ev charger tech specifications file in downloads folder",
        task_id="cap-ev-charger",
        search_fn=search_fn,
        extensions=["pdf"],
    )
    assert result.status == "success"
    assert result.confidence >= 0.9
    assert result.artifacts == [hit]


def test_capability_llm_judge_on_ambiguous():
    paths = [
        "/tmp/Plugin_notes_v2.pdf",
        "/tmp/Plugin_3.3kW_Technical_Specifications_V3.pdf",
    ]

    def search_fn(pattern, path, target="files", file_glob=None, limit=40):
        return paths

    def judge_fn(objective, candidates):
        return {
            "path": paths[1],
            "confidence": 0.95,
            "select": True,
            "reason": "matches power and V3",
        }

    cap = LocateFileCapability(judge_fn=judge_fn)
    result = cap.execute_objective(
        "Find Plugin document",
        task_id="cap-judge",
        search_fn=search_fn,
        extensions=["pdf"],
    )
    assert result.status in {"success", "partial"}
    assert result.artifacts


def test_capability_registry_builtins():
    ensure_builtins()
    assert "locate_file" in list_capabilities()
    assert get_capability("locate_file") is not None


def test_format_context_block_instructs_no_search_loops():
    result = CapabilityResult(
        status="success",
        capability="locate_file",
        confidence=0.98,
        artifacts=["/tmp/a.pdf"],
        message="ok",
    )
    block = result.format_context_block()
    assert "[locate_file]" in block
    assert "Do NOT run raw search_files" in block
