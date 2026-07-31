"""Tests for Plugin connected startup greeting + Health Check."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from hermes_cli.banner import (
    format_health_check_report,
    format_startup_greeting,
    probe_connected_capabilities,
    probe_startup_health,
)


def _tool(name: str) -> dict:
    return {"type": "function", "function": {"name": name}}


class TestProbeConnectedCapabilities:
    def test_marks_present_tools(self):
        tools = [
            _tool("read_file"),
            _tool("memory"),
            _tool("browser_navigate"),
            _tool("web_search"),
        ]
        with patch("hermes_cli.banner._calendar_connected", return_value=False):
            caps = dict(probe_connected_capabilities(tools))
        assert caps["Files"] is True
        assert caps["Memory"] is True
        assert caps["Browser"] is True
        assert caps["Web Search"] is True
        assert caps["Calendar"] is False

    def test_marks_missing_tools(self):
        with patch("hermes_cli.banner._calendar_connected", return_value=True):
            caps = dict(probe_connected_capabilities([]))
        assert caps["Files"] is False
        assert caps["Memory"] is False
        assert caps["Browser"] is False
        assert caps["Web Search"] is False
        assert caps["Calendar"] is True


class TestProbeStartupHealth:
    def test_structured_sections(self):
        tools = [
            _tool("read_file"),
            _tool("memory"),
            _tool("browser_navigate"),
            _tool("web_search"),
        ]
        runtime = {
            "provider": "ollama-cloud",
            "model": "gpt-oss:120b",
            "base_url": "https://ollama.com/v1",
            "api_key": "test-key",
        }
        with (
            patch("hermes_cli.banner._probe_main_model", return_value=True),
            patch("hermes_cli.banner._probe_vision_model", return_value=True),
            patch("hermes_cli.banner._probe_embeddings", return_value=False),
            patch("hermes_cli.banner._probe_backend_connected", return_value=True),
        ):
            health = probe_startup_health(tools, runtime=runtime)

        assert dict(health["models"]) == {
            "Main model": True,
            "Vision model": True,
            "Embeddings": False,
        }
        assert dict(health["tools"]) == {
            "Files": True,
            "Browser": True,
            "Search": True,
            "Memory": True,
        }
        assert dict(health["backend"]) == {"Connected": True}

    def test_format_health_check_report(self):
        health = {
            "models": [("Main model", True), ("Vision model", False), ("Embeddings", False)],
            "tools": [
                ("Files", True),
                ("Browser", True),
                ("Search", False),
                ("Memory", True),
            ],
            "backend": [("Connected", True)],
        }
        text = "\n".join(format_health_check_report(health))
        assert "Checking models..." in text
        assert "✓ Main model" in text
        assert "✗ Vision model" in text
        assert "Checking tools..." in text
        assert "✗ Search" in text
        assert "Checking backend..." in text
        assert "✓ Connected" in text


class TestFormatStartupGreeting:
    def test_classic_welcome_when_mode_unset(self):
        skin = SimpleNamespace(
            get_branding=lambda key, fallback="": {
                "welcome_mode": "",
                "agent_name": "Hermes Agent",
                "welcome": "Welcome to Hermes Agent! Type your message or /help for commands.",
            }.get(key, fallback)
        )
        text = format_startup_greeting([], skin=skin)
        assert text == "Welcome to Hermes Agent! Type your message or /help for commands."

    def test_connected_layout_is_health_check(self):
        branding = {
            "welcome_mode": "connected",
            "agent_name": "Plugin",
            "tagline": "I'm your personal AI agent.",
            "cta": "Type anything to begin.",
            "welcome": "ignored when connected",
        }
        skin = SimpleNamespace(
            get_branding=lambda key, fallback="": branding.get(key, fallback)
        )
        tools = [
            _tool("read_file"),
            _tool("memory"),
            _tool("browser_navigate"),
            _tool("web_search"),
        ]
        fake_health = {
            "models": [
                ("Main model", True),
                ("Vision model", True),
                ("Embeddings", False),
            ],
            "tools": [
                ("Files", True),
                ("Browser", True),
                ("Search", True),
                ("Memory", True),
            ],
            "backend": [("Connected", True)],
        }
        with patch(
            "hermes_cli.banner.probe_startup_health", return_value=fake_health
        ):
            text = format_startup_greeting(tools, skin=skin)

        assert text.startswith("Welcome to Plugin\n")
        assert "I'm your personal AI agent." in text
        assert "Checking models..." in text
        assert "✓ Main model" in text
        assert "✗ Embeddings" in text
        assert "Checking tools..." in text
        assert "✓ Search" in text
        assert "✓ Memory" in text
        assert "Checking backend..." in text
        assert "✓ Connected" in text
        assert "Connected:" not in text  # old flat list replaced
        assert text.endswith("Type anything to begin.")
