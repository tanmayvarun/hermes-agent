"""Unit tests for the locate_file staged search engine."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.locate_file import (
    CONFIDENCE_STOP,
    build_filename_globs,
    infer_extensions,
    locate_file,
    normalize_query,
    reset_locate_state,
    score_candidate,
    tokenize_query,
)


@pytest.fixture(autouse=True)
def _clear_locate_state():
    reset_locate_state()
    yield
    reset_locate_state()


def _glob_matches_name(pattern: str, name: str) -> bool:
    parts = [p for p in pattern.replace("**/", "").strip("*").split("*") if p]
    if not parts:
        return True
    lower = name.lower()
    return all(part.lower() in lower for part in parts)


def test_token_normalization_kw_and_version():
    assert "3.3kw" in tokenize_query("Plugin 3.3 kW Technical Specifications V3")
    assert "3.3kw" in tokenize_query("Plugin 3.3kW Specs v3")
    assert normalize_query("3.3 kW") == normalize_query("3.3kW")
    tokens = tokenize_query("specs V3")
    assert "v3" in tokens


def test_infer_extensions_from_query():
    assert ".pdf" in infer_extensions("find the brochure PDF")
    assert ".pdf" in infer_extensions("technical specifications")
    assert infer_extensions("x", explicit=["docx"]) == [".docx"]


def test_exact_basename_hit_stops_at_filename(tmp_path: Path):
    hit_file = tmp_path / "Plugin_3.3kW_Technical_Specifications_V3.pdf"
    hit_file.write_text("spec", encoding="utf-8")

    def search_fn(pattern, path, target="files", file_glob=None, limit=40):
        if target != "files":
            return []
        if _glob_matches_name(pattern, hit_file.name):
            return [str(hit_file)]
        return []

    result = locate_file(
        query="Plugin 3.3kW Technical Specifications V3",
        roots=[str(tmp_path)],
        extensions=["pdf"],
        task_id="t-exact",
        search_fn=search_fn,
    )

    assert result["success"] is True
    assert result["stages_run"] == ["filename"]
    assert result["stopped_reason"] == "confidence_threshold"
    assert result["candidates"]
    top = result["candidates"][0]
    assert top["confidence"] >= CONFIDENCE_STOP
    assert "Plugin_3.3kW_Technical_Specifications_V3.pdf" in top["path"]
    assert "content" not in result["stages_run"]
    assert "scoped_dirs" not in result["stages_run"]


def test_weak_miss_escalates_stages():
    def search_fn(pattern, path, target="files", file_glob=None, limit=40):
        if target == "files":
            return ["/tmp/random_readme.md"]
        return ["/Users/me/Downloads/Plugin_3.3kW_Technical_Specifications_V3.pdf"]

    result = locate_file(
        query="Plugin 3.3kW Technical Specifications V3",
        roots=["."],
        extensions=["pdf"],
        task_id="t-weak",
        search_fn=search_fn,
    )

    assert "filename" in result["stages_run"]
    assert "scoped_dirs" in result["stages_run"] or "content" in result["stages_run"]
    assert len(result["stages_run"]) >= 2


def test_same_query_twice_uses_stage_cache():
    calls = {"n": 0}
    hit = "/Users/me/Downloads/Plugin_3.3kW_Technical_Specifications_V3.pdf"

    def search_fn(pattern, path, target="files", file_glob=None, limit=40):
        calls["n"] += 1
        return [hit]

    q = "Plugin 3.3kW Technical Specifications V3"
    first = locate_file(
        query=q,
        roots=["~/Downloads"],
        extensions=["pdf"],
        task_id="t-cache",
        search_fn=search_fn,
    )
    n_after_first = calls["n"]
    assert first["already_completed"] is False
    assert first["candidates"][0]["confidence"] >= CONFIDENCE_STOP

    second = locate_file(
        query=q,
        roots=["~/Downloads"],
        extensions=["pdf"],
        task_id="t-cache",
        search_fn=search_fn,
    )
    assert second["already_completed"] is True
    assert calls["n"] == n_after_first
    assert second["stages_run"] == first["stages_run"]


def test_locate_expands_tilde_roots_before_search(monkeypatch, tmp_path: Path):
    fake_home = tmp_path / "home"
    downloads = fake_home / "Downloads"
    downloads.mkdir(parents=True)
    hit_file = downloads / "Plugin_Mini_3.3kW_Technical_Specifications.pdf"
    hit_file.write_text("spec", encoding="utf-8")
    monkeypatch.setenv("HOME", str(fake_home))

    seen_paths = []

    def search_fn(pattern, path, target="files", file_glob=None, limit=40):
        seen_paths.append(path)
        if path == str(downloads):
            return [str(hit_file)]
        return []

    result = locate_file(
        query="find the plugin 3.3kw tech specifications file in downloads folder",
        roots=["~/Downloads"],
        extensions=["pdf"],
        task_id="t-tilde",
        search_fn=search_fn,
    )

    assert result["success"] is True
    assert result["candidates"]
    assert seen_paths
    assert all("~" not in path for path in seen_paths)


def test_search_files_pathlib_matches_case_insensitively(tmp_path: Path):
    hit_file = tmp_path / "Plugin_Mini_3.3kW_Technical_Specifications.pdf"
    hit_file.write_text("spec", encoding="utf-8")

    from tools.locate_file import _search_files_pathlib

    results = _search_files_pathlib("*3.3kw*pdf", str(tmp_path), limit=20)
    assert str(hit_file) in results


def test_score_candidate_version_and_tokens():
    path = "/Users/x/Downloads/Plugin_3.3kW_Technical_Specifications_V3.pdf"
    tokens = tokenize_query("Plugin 3.3kW Technical Specifications V3")
    conf, reason = score_candidate(path, tokens, [".pdf"], stage="filename")
    assert conf >= CONFIDENCE_STOP
    assert "version" in reason.lower() or "all tokens" in reason.lower()


def test_build_filename_globs_include_kw():
    tokens = tokenize_query("Plugin 3.3kW Specs V3")
    globs = build_filename_globs(tokens, [".pdf"])
    assert globs
    joined = " ".join(globs).lower()
    assert "plugin" in joined
    assert "pdf" in joined
    assert globs[0].startswith("*plugin*")


def test_default_roots_prioritize_downloads_for_downloads_query(monkeypatch, tmp_path: Path):
    fake_home = tmp_path / "home"
    downloads = fake_home / "Downloads"
    downloads.mkdir(parents=True)
    hit_file = downloads / "Plugin_Mini_3.3kW_Technical_Specifications.pdf"
    hit_file.write_text("spec", encoding="utf-8")
    monkeypatch.setenv("HOME", str(fake_home))

    seen_paths = []

    def search_fn(pattern, path, target="files", file_glob=None, limit=40):
        seen_paths.append(path)
        if path == str(downloads):
            return [str(hit_file)]
        return []

    result = locate_file(
        query="find the plugin 3.3kw tech specifications file in downloads folder",
        task_id="t-default-downloads",
        search_fn=search_fn,
    )

    assert result["success"] is True
    assert result["candidates"]
    assert seen_paths
    assert seen_paths[0] == str(downloads)


def test_schema_registered_in_file_toolset():
    import tools.file_tools  # noqa: F401 — registers tools
    from tools.registry import registry
    from toolsets import TOOLSETS

    entry = registry.get_entry("locate_file")
    assert entry is not None
    assert entry.schema["name"] == "locate_file"
    assert "query" in entry.schema["parameters"]["properties"]
    assert registry.get_toolset_for_tool("locate_file") == "file"
    assert "locate_file" in TOOLSETS["file"]["tools"]
    assert "locate_file" in registry.get_all_tool_names()
