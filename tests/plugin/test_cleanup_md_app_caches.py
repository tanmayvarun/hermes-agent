"""cleanup.md preferences + app_caches stage (Chrome cache-style only)."""

from __future__ import annotations

from pathlib import Path


def test_load_cleanup_preferences_parses_allow_deny(tmp_path, monkeypatch):
    md = tmp_path / "cleanup.md"
    md.write_text(
        """
## enabled
- tracked
- app_caches

## app_caches
allow:
- chrome
- slack
deny:
- downloads
- docker
""",
        encoding="utf-8",
    )
    from plugin.agent.runtime.recovery import _load_disk_cleanup_library

    lib = _load_disk_cleanup_library()
    monkeypatch.setattr(lib, "get_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(lib, "get_cleanup_md_path", lambda: md)
    monkeypatch.setattr(lib, "ensure_cleanup_md", lambda: md)
    prefs = lib.load_cleanup_preferences()
    assert set(prefs["enabled"]) == {"app_caches", "tracked"}
    assert "chrome" in prefs["app_caches_allow"]
    assert "slack" in prefs["app_caches_allow"]
    assert "downloads" in prefs["app_caches_deny"]
    assert "docker" in prefs["app_caches_deny"]
    # hard deny always present
    assert "indexeddb" in prefs["app_caches_deny"]


def test_iter_app_cache_targets_chrome_cache_style_only(tmp_path):
    from plugin.agent.runtime.recovery import _load_disk_cleanup_library

    lib = _load_disk_cleanup_library()
    chrome = tmp_path / "Library" / "Application Support" / "Google" / "Chrome"
    profile = chrome / "Profile 1"
    (profile / "Service Worker" / "CacheStorage").mkdir(parents=True)
    (profile / "GPUCache").mkdir(parents=True)
    (profile / "IndexedDB").mkdir(parents=True)
    (profile / "Cookies").write_text("secret", encoding="utf-8")
    (chrome / "GPUPersistentCache").mkdir(parents=True)
    downloads = tmp_path / "Downloads" / "movie.mp4"
    downloads.parent.mkdir(parents=True)
    downloads.write_bytes(b"x" * 10)

    targets = lib.iter_app_cache_targets(allow=["chrome"], home=tmp_path)
    joined = "\n".join(str(p) for p in targets)
    assert "Service Worker" in joined
    assert "GPUCache" in joined
    assert "GPUPersistentCache" in joined
    assert "IndexedDB" not in joined
    assert "Cookies" not in joined
    assert "Downloads" not in joined


def test_cleanup_app_caches_deletes_service_worker_not_indexeddb(tmp_path, monkeypatch):
    from plugin.agent.runtime.recovery import _load_disk_cleanup_library

    lib = _load_disk_cleanup_library()
    chrome = tmp_path / "Library" / "Application Support" / "Google" / "Chrome"
    profile = chrome / "Profile 1"
    sw = profile / "Service Worker" / "CacheStorage"
    sw.mkdir(parents=True)
    (sw / "blob").write_bytes(b"y" * 1000)
    idb = profile / "IndexedDB"
    idb.mkdir(parents=True)
    (idb / "keep").write_text("keep", encoding="utf-8")

    md = tmp_path / "cleanup.md"
    md.write_text(
        "## enabled\n- app_caches\n\n## app_caches\nallow:\n- chrome\ndeny:\n- downloads\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(lib, "get_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(lib, "get_cleanup_md_path", lambda: md)
    monkeypatch.setattr(
        lib,
        "iter_app_cache_targets",
        lambda allow=None, home=None: [profile / "Service Worker"],
    )

    out = lib._cleanup_app_caches()
    assert out["freed"] >= 1000
    assert not (profile / "Service Worker").exists()
    assert idb.exists()


def test_relieve_includes_app_caches_stage_when_earlier_stages_insufficient(monkeypatch):
    from plugin.agent.runtime.recovery import _load_disk_cleanup_library

    lib = _load_disk_cleanup_library()
    calls = []
    free_seq = {"n": 0, "vals": [10, 10, 10, 10, 5_000_000_000]}

    def fake_free(path="/"):
        i = min(free_seq["n"], len(free_seq["vals"]) - 1)
        free_seq["n"] += 1
        return free_seq["vals"][i]

    monkeypatch.setattr(lib, "free_bytes", fake_free)
    monkeypatch.setattr(
        lib,
        "load_cleanup_preferences",
        lambda: {
            "enabled": ["tracked", "host_temp", "host_cache", "app_caches"],
            "app_caches_allow": ["chrome"],
            "app_caches_deny": [],
        },
    )
    monkeypatch.setattr(
        lib,
        "quick",
        lambda: calls.append("tracked_disposables")
        or {"deleted": 0, "empty_dirs": 0, "freed": 1, "errors": []},
    )
    monkeypatch.setattr(
        lib,
        "_cleanup_host_temp_roots",
        lambda: calls.append("host_temp")
        or {"deleted": 0, "empty_dirs": 0, "freed": 1, "errors": []},
    )
    monkeypatch.setattr(
        lib,
        "_cleanup_host_cache_roots",
        lambda: calls.append("host_cache")
        or {"deleted": 0, "empty_dirs": 0, "freed": 1, "errors": []},
    )
    monkeypatch.setattr(
        lib,
        "_cleanup_app_caches",
        lambda: calls.append("app_caches")
        or {"deleted": 1, "empty_dirs": 0, "freed": 9_000_000_000, "errors": []},
    )
    out = lib.relieve_until_headroom(target_free_bytes=1_000_000_000, reason="test")
    assert calls == [
        "tracked_disposables",
        "host_temp",
        "host_cache",
        "app_caches",
    ]
    assert out["headroom_met"] is True
    assert out["stages"][-1]["stage"] == "app_caches"
