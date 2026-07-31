"""Tests for Task Controller plugin + research/filesystem domain skills."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
RESEARCH_SKILL = REPO_ROOT / "skills" / "research" / "web-research" / "SKILL.md"
FS_SKILL = (
    REPO_ROOT / "skills" / "productivity" / "filesystem-workspace" / "SKILL.md"
)
PLUGIN_DIR = REPO_ROOT / "plugins" / "task-controller"
PLUGIN_INIT = PLUGIN_DIR / "__init__.py"


def _mock_llm_label(monkeypatch, label: str):
    class _Msg:
        content = label

    class _Choice:
        message = _Msg()

    class _Resp:
        choices = [_Choice()]

    monkeypatch.setenv("TASK_CONTROLLER_LLM_CLASSIFY", "1")
    monkeypatch.setattr("agent.auxiliary_client.call_llm", lambda **kwargs: _Resp())


def _load_task_controller():
    name = "task_controller_plugin_under_test"
    spec = importlib.util.spec_from_file_location(name, PLUGIN_INIT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_web_research_skill_is_research_controller():
    text = RESEARCH_SKILL.read_text(encoding="utf-8")
    assert "name: web-research" in text
    assert "Research Controller" in text
    assert "Task Controller" in text
    assert "requires_tools: [web_search]" in text
    assert "Research Plan" in text
    assert "todo" in text.lower()
    assert "verify the date on the item itself" in text


def test_filesystem_workspace_skill_exists():
    text = FS_SKILL.read_text(encoding="utf-8")
    assert text.startswith("---")
    assert "name: filesystem-workspace" in text
    assert "Filesystem Controller" in text
    assert "requires_tools: [locate_file, search_files, read_file]" in text
    assert "Filesystem Plan" in text
    assert "todo" in text.lower()
    assert "locate_file" in text
    assert "LocateFileCapability" in text or "capabilities" in text.lower()
    assert "search_files" in text
    assert "~/" in text or "computer-wide" in text.lower() or "Escalate" in text
    assert "Stop" in text or "stop" in text


def test_filesystem_hint_prefers_locate_capability(tc, monkeypatch):
    _mock_llm_label(monkeypatch, "filesystem")
    result = tc.on_pre_llm_call(
        session_id="sess-test",
        user_message="Find the Plugin 3.3kW Technical Specifications V3 file",
    )
    ctx = result["context"]
    assert "type: filesystem" in ctx
    assert "LocateFileCapability" in ctx
    assert "locate_file:" in ctx and "2/2" in ctx
    assert "Capability" in ctx or "layering" in ctx


def test_task_controller_plugin_manifest():
    yaml_text = (PLUGIN_DIR / "plugin.yaml").read_text(encoding="utf-8")
    assert "name: task-controller" in yaml_text
    assert "pre_llm_call" in yaml_text
    assert "pre_tool_call" in yaml_text
    assert "post_tool_call" in yaml_text


@pytest.fixture
def tc(monkeypatch):
    mod = _load_task_controller()
    for var in (
        "TASK_CONTROLLER_DISABLE",
        "TASK_CONTROLLER_MAX_WEB_SEARCH",
        "TASK_CONTROLLER_MAX_WEB_EXTRACT",
        "TASK_CONTROLLER_MAX_TOOL_CALLS",
    ):
        monkeypatch.delenv(var, raising=False)
    # Default tests opt out of FS auto-dispatch (avoid real disk scans).
    monkeypatch.setenv("TASK_CONTROLLER_AUTO_LOCATE", "0")
    monkeypatch.setenv("TASK_CONTROLLER_LLM_CLASSIFY", "0")
    mod.reset_decision_metrics()
    mod.reset_session("sess-test")
    yield mod
    mod.reset_session("sess-test")
    mod.reset_decision_metrics()


def test_pre_llm_call_injects_generic_task_budget(tc, monkeypatch):
    _mock_llm_label(monkeypatch, "research")
    result = tc.on_pre_llm_call(
        session_id="sess-test",
        user_message="Research three providers and compare pricing",
    )
    assert isinstance(result, dict)
    ctx = result["context"]
    assert "[Task Controller]" in ctx
    assert "type: research" in ctx
    assert "web_search: 5/5" in ctx or "web_search: 5/5" in ctx.replace(" ", "")
    assert "web_search:" in ctx and "5/5" in ctx
    assert "web_extract:" in ctx and "4/4" in ctx
    assert "read_file:" in ctx
    assert "tool_calls:" in ctx
    assert "Research Controller" in ctx


def test_filesystem_message_detects_domain(tc, monkeypatch):
    _mock_llm_label(monkeypatch, "filesystem")
    result = tc.on_pre_llm_call(
        session_id="sess-test",
        user_message="Find the latest Plugin brochure PDF in Downloads",
    )
    ctx = result["context"]
    assert "type: filesystem" in ctx
    assert "Filesystem Controller" in ctx
    assert "describe_capability" in ctx


def test_ev_charger_spec_prompt_detects_filesystem_domain(tc, monkeypatch):
    _mock_llm_label(monkeypatch, "filesystem")
    result = tc.on_pre_llm_call(
        session_id="sess-test",
        user_message="find the plugin 3.3kw ev charger tech specifications file in downloads folder",
    )
    ctx = result["context"]
    assert "type: filesystem" in ctx
    assert "Filesystem Controller" in ctx


def test_jaya_kishori_latest_podcast_prompt_detects_research_domain(tc, monkeypatch):
    _mock_llm_label(monkeypatch, "research")
    result = tc.on_pre_llm_call(
        session_id="sess-test",
        user_message="share the youtube link to latest podcast of jaya kishori",
    )
    ctx = result["context"]
    assert "type: research" in ctx
    assert "Research Controller" in ctx
    assert "Recency guardrail:" in ctx
    assert "publication date" in ctx


def test_latest_tweet_prompt_detects_research_domain(tc, monkeypatch):
    _mock_llm_label(monkeypatch, "research")
    result = tc.on_pre_llm_call(
        session_id="sess-test",
        user_message="find the latest tweet by elon musk",
    )
    ctx = result["context"]
    assert "type: research" in ctx
    assert "Research Controller" in ctx


def test_auto_dispatch_latest_media_capability(tc, monkeypatch):
    _mock_llm_label(monkeypatch, "research")

    responses = {
        "jaya kishori latest podcast youtube": {
            "success": True,
            "data": {
                "web": [
                    {
                        "title": "Jaya Kishori Ji Podcast",
                        "url": "https://www.youtube.com/playlist?list=old",
                        "description": "Last updated on Feb 1, 2026. 8 years ago.",
                        "position": 1,
                    }
                ]
            },
        },
        "jaya kishori podcast 2026": {
            "success": True,
            "data": {
                "web": [
                    {
                        "title": "Jaya Kishori - God's Love, Marriage, Relationships, Parenting & Life | TRS",
                        "url": "https://podcasts.apple.com/in/podcast/jaya-kishori-gods-love-marriage-relationships-parenting/id1542452346?i=1000775815286",
                        "description": "7 July 2026 at 14:57 UTC",
                        "position": 1,
                    }
                ]
            },
        },
        "jaya kishori the ranveer show podcast 2026": {
            "success": True,
            "data": {"web": []},
        },
        "site:youtube.com/watch jaya kishori podcast": {
            "success": True,
            "data": {"web": []},
        },
    }

    def search_fn(query: str, limit: int = 5) -> str:
        import json

        return json.dumps(responses.get(query, {"success": True, "data": {"web": []}}))

    tc.reset_session("sess-test")
    block = tc._dispatch_latest_media_capability(
        "sess-test",
        "share the youtube link to latest podcast of jaya kishori",
        search_fn=search_fn,
    )
    assert "[latest_media]" in block
    assert "podcasts.apple.com" in block


def test_auto_dispatch_latest_tweet_capability(tc, monkeypatch):
    _mock_llm_label(monkeypatch, "research")

    responses = {
        "elon musk latest tweet x": {
            "success": True,
            "data": {
                "web": [
                    {
                        "title": "Elon Musk on X: Launch update",
                        "url": "https://x.com/elonmusk/status/1949651234567890123",
                        "description": "Posted on Jul 27, 2026 by @elonmusk. Starship update soon.",
                        "position": 1,
                    }
                ]
            },
        },
        "site:x.com elon musk status": {"success": True, "data": {"web": []}},
        "site:twitter.com elon musk status": {"success": True, "data": {"web": []}},
        "elon musk latest post twitter 2026": {"success": True, "data": {"web": []}},
    }

    def search_fn(query: str, limit: int = 5) -> str:
        import json

        return json.dumps(responses.get(query, {"success": True, "data": {"web": []}}))

    tc.reset_session("sess-test")
    block = tc._dispatch_latest_media_capability(
        "sess-test",
        "find the latest tweet by elon musk",
        search_fn=search_fn,
    )
    assert "[latest_media]" in block
    assert "x.com/elonmusk/status" in block
    assert "author: @elonmusk" in block


def test_auto_dispatch_locate_capability(tc, monkeypatch):
    from tools.locate_file import reset_locate_state

    reset_locate_state()
    monkeypatch.setenv("TASK_CONTROLLER_AUTO_LOCATE", "1")
    hit = "/Users/me/Downloads/Plugin_3.3kW_Technical_Specifications_V3.pdf"

    def search_fn(pattern, path, target="files", file_glob=None, limit=40):
        return [hit]

    # Patch dispatcher to inject search_fn (avoid real FS).
    original = tc._dispatch_locate_capability

    def wrapped(key, user_message, *, search_fn=None):
        return original(key, user_message, search_fn=search_fn or search_fn)

    # Call dispatch directly with mock
    tc.reset_session("sess-test")
    tc._ensure_turn("sess-test", user_message="Find Plugin specs V3 file")
    block = tc._dispatch_locate_capability(
        "sess-test",
        "Find the Plugin 3.3kW Technical Specifications V3 file",
        search_fn=search_fn,
    )
    assert "[locate_file]" in block or "LocateFile" in block or "status:" in block
    assert hit in block or "selected" in block.lower() or "artifacts" in block.lower()
    counts = tc.get_counts(session_id="sess-test")
    assert counts.get("locate_file", 0) == 1


def test_auto_dispatch_locate_capability_for_ev_charger_prompt(tc, monkeypatch):
    from tools.locate_file import reset_locate_state

    reset_locate_state()
    monkeypatch.setenv("TASK_CONTROLLER_AUTO_LOCATE", "1")
    hit = "/Users/me/Downloads/Plugin_3.3kW_Technical_Specifications_V3.pdf"

    def search_fn(pattern, path, target="files", file_glob=None, limit=40):
        return [hit]

    tc.reset_session("sess-test")
    tc._ensure_turn(
        "sess-test",
        user_message="find the plugin 3.3kw ev charger tech specifications file in downloads folder",
    )
    block = tc._dispatch_locate_capability(
        "sess-test",
        "find the plugin 3.3kw ev charger tech specifications file in downloads folder",
        search_fn=search_fn,
    )
    assert "[locate_file]" in block or "LocateFile" in block or "status:" in block
    assert hit in block or "selected" in block.lower() or "artifacts" in block.lower()
    counts = tc.get_counts(session_id="sess-test")
    assert counts.get("locate_file", 0) == 1


def test_blocks_sixth_web_search(tc, monkeypatch):
    _mock_llm_label(monkeypatch, "research")
    tc.on_pre_llm_call(session_id="sess-test", user_message="research X")
    for _ in range(5):
        assert (
            tc.on_pre_tool_call(
                tool_name="web_search",
                args={"query": "x"},
                session_id="sess-test",
            )
            is None
        )
        tc.on_post_tool_call(
            tool_name="web_search",
            args={"query": "x"},
            result="{}",
            session_id="sess-test",
        )

    sixth = tc.on_pre_tool_call(
        tool_name="web_search",
        args={"query": "x"},
        session_id="sess-test",
    )
    assert sixth is not None
    assert sixth["action"] == "block"
    assert "budget exhausted" in sixth["message"].lower()


def test_blocks_read_file_over_cap(tc, monkeypatch):
    monkeypatch.setenv("TASK_CONTROLLER_MAX_TOOL_CALLS", "100")
    tiny = dict(tc._DEFAULT_BUDGETS)
    tiny["read_file"] = 2
    tiny["tool_calls"] = 100
    monkeypatch.setattr(tc, "_config_caps", lambda: tiny)
    tc.reset_session("sess-test")
    tc.on_pre_llm_call(session_id="sess-test", user_message="find brochure")

    for _ in range(2):
        assert (
            tc.on_pre_tool_call(
                tool_name="read_file",
                args={"path": "/tmp/a"},
                session_id="sess-test",
            )
            is None
        )
        tc.on_post_tool_call(
            tool_name="read_file",
            args={"path": "/tmp/a"},
            result="{}",
            session_id="sess-test",
        )

    blocked = tc.on_pre_tool_call(
        tool_name="read_file",
        args={"path": "/tmp/a"},
        session_id="sess-test",
    )
    assert blocked is not None
    assert blocked["action"] == "block"


def test_global_tool_calls_cap_blocks_any_tool(tc, monkeypatch):
    monkeypatch.setenv("TASK_CONTROLLER_MAX_TOOL_CALLS", "3")
    tc.reset_session("sess-test")
    tc.on_pre_llm_call(session_id="sess-test", user_message="hi")

    for name in ("todo", "clarify", "memory"):
        assert (
            tc.on_pre_tool_call(
                tool_name=name, args={}, session_id="sess-test"
            )
            is None
        )
        tc.on_post_tool_call(
            tool_name=name, args={}, result="{}", session_id="sess-test"
        )

    blocked = tc.on_pre_tool_call(
        tool_name="todo", args={}, session_id="sess-test"
    )
    assert blocked is not None
    assert blocked["action"] == "block"
    assert "tool_calls" in blocked["message"].lower() or "Global" in blocked["message"]


def test_terminal_allowed_under_budget(tc):
    tc.on_pre_llm_call(session_id="sess-test", user_message="list files")
    assert (
        tc.on_pre_tool_call(
            tool_name="terminal",
            args={"command": "echo hi"},
            session_id="sess-test",
        )
        is None
    )


def test_env_web_caps(tc, monkeypatch):
    monkeypatch.setenv("TASK_CONTROLLER_MAX_WEB_SEARCH", "2")
    monkeypatch.setenv("TASK_CONTROLLER_MAX_WEB_EXTRACT", "1")
    _mock_llm_label(monkeypatch, "research")
    tc.reset_session("sess-test")
    result = tc.on_pre_llm_call(session_id="sess-test", user_message="research")
    ctx = result["context"]
    assert "web_search:" in ctx and "2/2" in ctx
    assert "web_extract:" in ctx and "1/1" in ctx


def test_detect_task_type_uses_llm_fallback_for_ambiguous_prompt(tc, monkeypatch):
    calls = []

    def fake_call_llm(**kwargs):
        calls.append(kwargs)
        class _Msg:
            content = "research"

        class _Choice:
            message = _Msg()

        class _Resp:
            choices = [_Choice()]

        return _Resp()

    monkeypatch.setenv("TASK_CONTROLLER_LLM_CLASSIFY", "1")
    monkeypatch.setattr("agent.auxiliary_client.call_llm", fake_call_llm)
    label = tc.detect_task_type("share latest link for jaya kishori")
    assert label == "research"
    assert calls


def test_detect_task_type_prefers_llm_classifier(tc, monkeypatch):
    _mock_llm_label(monkeypatch, "research")
    label = tc.detect_task_type("share the youtube link to latest podcast of jaya kishori")
    assert label == "research"


def test_decision_metrics_track_llm_classifier_success(tc, monkeypatch):
    _mock_llm_label(monkeypatch, "research")
    tc.detect_task_type("share the youtube link to latest podcast of jaya kishori")
    metrics = tc.get_decision_metrics()
    llm = metrics["task_controller.llm_classifier"]
    assert llm["attempts"] == 1
    assert llm["successes"] == 1
    assert llm["failures"] == 0
    assert llm["accuracy"] == 1.0


def test_detect_task_type_returns_general_when_llm_is_unavailable(tc, monkeypatch):
    monkeypatch.setenv("TASK_CONTROLLER_LLM_CLASSIFY", "1")

    monkeypatch.setattr(
        "agent.auxiliary_client.call_llm",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("llm unavailable")),
    )
    label = tc.detect_task_type("Find the latest Plugin brochure PDF in Downloads")
    assert label == "general"


def test_llm_classifier_metrics_remain_empty_when_fallback_is_used(tc, monkeypatch):
    monkeypatch.setenv("TASK_CONTROLLER_LLM_CLASSIFY", "1")

    monkeypatch.setattr(
        "agent.auxiliary_client.call_llm",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("llm unavailable")),
    )
    tc.detect_task_type("Find the latest Plugin brochure PDF in Downloads")
    metrics = tc.get_decision_metrics()
    llm = metrics.get("task_controller.llm_classifier")
    assert llm is None or llm["attempts"] == 0


def test_decision_metrics_track_llm_classifier_for_research_prompt(tc, monkeypatch):
    _mock_llm_label(monkeypatch, "research")
    label = tc.detect_task_type("share latest link for jaya kishori")
    assert label == "research"
    metrics = tc.get_decision_metrics()
    llm = metrics["task_controller.llm_classifier"]
    assert llm["attempts"] == 1
    assert llm["successes"] == 1
    assert llm["accuracy"] == 1.0


def test_register_wires_hooks(tc):
    hooks = []

    class FakeCtx:
        def register_hook(self, name, callback):
            hooks.append((name, callback))

    tc.register(FakeCtx())
    assert [n for n, _ in hooks] == [
        "pre_llm_call",
        "pre_tool_call",
        "post_tool_call",
    ]
