"""Shim so tools.registry auto-discovers Plugin World Model tools."""

from plugin.adapters.hermes.tools import register_hermes_tools

register_hermes_tools()
