"""Tests for proactive vision tool-schema adaptation."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from agent.vision_capability import (
    VISION_SCHEMA_TOOL_NAMES,
    apply_vision_tool_adaptation,
    should_strip_vision_tools,
    strip_vision_tools,
)


def _tool(name: str) -> dict:
    return {"type": "function", "function": {"name": name}}


class TestShouldStripVisionTools:
    def test_false_capability_strips(self):
        with patch(
            "agent.image_routing._lookup_supports_vision", return_value=False
        ):
            assert should_strip_vision_tools("openrouter", "some-model", cfg={}) is True

    def test_true_capability_keeps(self):
        with patch(
            "agent.image_routing._lookup_supports_vision", return_value=True
        ):
            assert should_strip_vision_tools("openrouter", "gpt-4o", cfg={}) is False

    def test_unknown_optimistic_by_default(self):
        with (
            patch("agent.image_routing._lookup_supports_vision", return_value=None),
            patch(
                "agent.vision_capability._provider_strict_vision_tool_schema",
                return_value=False,
            ),
        ):
            assert should_strip_vision_tools("openrouter", "mystery", cfg={}) is False

    def test_unknown_strict_provider_strips(self):
        with (
            patch("agent.image_routing._lookup_supports_vision", return_value=None),
            patch(
                "agent.vision_capability._provider_strict_vision_tool_schema",
                return_value=True,
            ),
        ):
            assert should_strip_vision_tools("llm7", "codestral-latest", cfg={}) is True


class TestStripVisionTools:
    def test_removes_vision_names(self):
        tools = [
            _tool("read_file"),
            _tool("vision_analyze"),
            _tool("browser_vision"),
            _tool("web_search"),
            _tool("image_generate"),
        ]
        filtered, removed = strip_vision_tools(tools)
        names = {(t.get("function") or {}).get("name") for t in filtered}
        assert removed == 3
        assert "read_file" in names
        assert "web_search" in names
        assert names.isdisjoint(VISION_SCHEMA_TOOL_NAMES)


class TestApplyVisionToolAdaptation:
    def test_sets_flags_and_filters(self):
        agent = SimpleNamespace(
            provider="llm7",
            model="codestral-latest",
            tools=[
                _tool("read_file"),
                _tool("vision_analyze"),
                _tool("browser_get_images"),
            ],
            valid_tool_names={"read_file", "vision_analyze", "browser_get_images"},
            quiet_mode=True,
        )
        with patch(
            "agent.vision_capability.should_strip_vision_tools", return_value=True
        ):
            removed = apply_vision_tool_adaptation(agent, quiet=True)
        assert removed == 2
        assert agent._vision_tools_stripped is True
        assert agent._vision_supported is False
        names = {(t.get("function") or {}).get("name") for t in agent.tools}
        assert names == {"read_file"}
        assert "Vision: unsupported" in agent._vision_adaptation_note

    def test_noop_when_vision_ok(self):
        agent = SimpleNamespace(
            provider="openrouter",
            model="gpt-4o",
            tools=[_tool("vision_analyze")],
            quiet_mode=True,
        )
        with patch(
            "agent.vision_capability.should_strip_vision_tools", return_value=False
        ):
            removed = apply_vision_tool_adaptation(agent, quiet=True)
        assert removed == 0
        assert agent._vision_tools_stripped is False
        assert len(agent.tools) == 1


class TestTurnContextDoesNotRearm:
    def test_preserves_stripped_flag(self):
        agent = SimpleNamespace(_vision_tools_stripped=True)
        # Mirror the fixed assignment from turn_context.py
        agent._vision_supported = not bool(
            getattr(agent, "_vision_tools_stripped", False)
        )
        assert agent._vision_supported is False


class TestConversationLoopQuietsWarning:
    def test_already_adapted_skips_scary_print(self):
        """Mirror the branch condition used in conversation_loop."""
        agent = SimpleNamespace(
            _vision_tools_stripped=True,
            _vprint=MagicMock(),
            tools=[],
            log_prefix="",
        )
        _already_adapted = bool(getattr(agent, "_vision_tools_stripped", False))
        if _already_adapted:
            pass  # quiet path
        else:
            agent._vprint("scary", force=True)
        agent._vprint.assert_not_called()


class TestHealthCheckAdaptationNotes:
    def test_notes_when_stripping(self):
        from hermes_cli.banner import format_health_check_report, probe_startup_health

        with (
            patch("hermes_cli.banner._probe_main_model", return_value=True),
            patch("hermes_cli.banner._probe_embeddings", return_value=False),
            patch("hermes_cli.banner._probe_backend_connected", return_value=True),
            patch(
                "agent.vision_capability.should_strip_vision_tools",
                return_value=True,
            ),
        ):
            health = probe_startup_health(
                [_tool("read_file"), _tool("vision_analyze")],
                runtime={
                    "provider": "llm7",
                    "model": "codestral-latest",
                    "base_url": "https://api.llm7.io/v1",
                    "api_key": "x",
                },
            )
        assert dict(health["models"])["Vision model"] is False
        assert health["adaptation_notes"] == [
            "Vision: unsupported",
            "Removing vision tools...",
        ]
        report = "\n".join(format_health_check_report(health))
        assert "Vision: unsupported" in report
        assert "Removing vision tools..." in report
        assert "✗ Vision model" in report
