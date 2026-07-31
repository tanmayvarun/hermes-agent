from agent.capabilities import describe_capability, ensure_builtins, list_capability_specs


def test_describe_capability_includes_required_tool_metadata():
    ensure_builtins()
    spec = describe_capability("locate_file")
    assert spec is not None
    assert spec["name"] == "locate_file"
    assert isinstance(spec["required_tools"], list)
    names = {tool["name"] for tool in spec["required_tools"]}
    assert {"search_files", "read_file"}.issubset(names)


def test_list_capability_specs_contains_locate_file():
    ensure_builtins()
    specs = list_capability_specs()
    names = {spec["name"] for spec in specs}
    assert "locate_file" in names
    assert "prompt_benchmark" in names
