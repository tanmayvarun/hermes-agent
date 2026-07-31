import json

import tools.capability_tools  # noqa: F401
from tools.registry import registry


def test_capability_tools_registered():
    assert registry.get_entry("list_capabilities") is not None
    assert registry.get_entry("describe_capability") is not None
    assert registry.get_toolset_for_tool("list_capabilities") == "capability"


def test_list_capabilities_tool_returns_locate_file():
    raw = registry.dispatch("list_capabilities", {})
    payload = json.loads(raw)
    assert payload["success"] is True
    names = {spec["name"] for spec in payload["capabilities"]}
    assert "locate_file" in names


def test_describe_capability_tool_returns_required_tools():
    raw = registry.dispatch("describe_capability", {"name": "locate_file"})
    payload = json.loads(raw)
    assert payload["success"] is True
    cap = payload["capability"]
    assert cap["name"] == "locate_file"
    required = {tool["name"] for tool in cap["required_tools"]}
    assert {"search_files", "read_file"}.issubset(required)
