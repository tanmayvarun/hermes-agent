"""Layer 1 primary: macapptree. Backup: PyObjC AXUIElement (stub). Fixture for CI."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Protocol

from plugin.perception.macos.accessibility.tree_parse import observation_from_tree
from plugin.perception.observation import Observation

logger = logging.getLogger(__name__)


def _capture_screen_screenshot(*, app_name: str = "WhatsApp") -> tuple[Optional[str], Optional[str]]:
    """Capture the current screen to a temp PNG, or return an explicit error."""
    fd, path = tempfile.mkstemp(suffix=".png", prefix=f"{app_name.lower().replace(' ', '_')}_obs_")
    os.close(fd)
    shot = Path(path)
    try:
        proc = subprocess.run(
            ["screencapture", "-x", str(shot)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=12,
        )
        if shot.exists() and shot.stat().st_size > 0:
            return str(shot), None
        err = (proc.stderr or "").strip() or "screencapture produced an empty file"
        raise RuntimeError(err)
    except Exception as exc:  # noqa: BLE001 - capture must be best-effort
        try:
            shot.unlink(missing_ok=True)
        except Exception:
            pass
        return None, str(exc)


class Observer(Protocol):
    def observe(self, app: Optional[str] = None) -> Observation: ...


def macapptree_available() -> bool:
    try:
        import macapptree  # noqa: F401

        return True
    except ImportError:
        return False


class MacAppTreeObserver:
    """Primary accessibility + screenshot capture via macapptree."""

    def __init__(self, *, with_screenshot: bool = True) -> None:
        if not macapptree_available():
            raise ImportError(
                "macapptree is not installed. "
                "pip install macapptree  (or hermes-agent[plugin-world])"
            )
        self.with_screenshot = with_screenshot

    def observe(self, app: Optional[str] = None) -> Observation:
        import os
        import sys

        from macapptree import get_app_bundle, get_tree, get_tree_screenshot

        # macapptree spawns subprocesses as ``python -m macapptree…``.
        # Ensure the active interpreter's bin dir is first on PATH so ``python`` resolves.
        bin_dir = str(Path(sys.executable).resolve().parent)
        env_path = os.environ.get("PATH", "")
        if bin_dir not in env_path.split(os.pathsep):
            os.environ["PATH"] = bin_dir + os.pathsep + env_path
        python_shim = Path(bin_dir) / "python"
        if not python_shim.exists():
            try:
                python_shim.symlink_to(Path(sys.executable).name)
            except OSError:
                pass

        app_name = app or self._front_app_name()
        bundle = get_app_bundle(app_name)
        screenshot_path: Optional[str] = None
        screenshot_error: Optional[str] = None
        tree = None
        if self.with_screenshot:
            try:
                tree, im, _im_seg = get_tree_screenshot(bundle)
                if im is not None:
                    fd, path = tempfile.mkstemp(suffix=".png", prefix="plugin_obs_")
                    os.close(fd)
                    im.save(path)
                    screenshot_path = path
                else:
                    screenshot_path, screenshot_error = _capture_screen_screenshot(app_name=app_name)
            except Exception as exc:  # noqa: BLE001 - prefer a recoverable fallback
                screenshot_error = str(exc)
                screenshot_path, capture_error = _capture_screen_screenshot(app_name=app_name)
                if not screenshot_path and capture_error:
                    screenshot_error = f"{screenshot_error}; screenshot_fallback={capture_error}"
                # Screenshot failed, but we can still recover the AX tree so the
                # observation is not empty — perception degrades to AX, not to nothing.
                try:
                    tree = get_tree(bundle)
                except Exception:
                    tree = None
        else:
            tree = get_tree(bundle)

        if not isinstance(tree, dict):
            tree = {"role": "AXApplication", "name": app_name, "children": []}

        window_name = ""
        if tree.get("role") == "AXWindow":
            window_name = str(tree.get("name") or "")
        else:
            for c in tree.get("children") or []:
                if isinstance(c, dict) and c.get("role") == "AXWindow":
                    window_name = str(c.get("name") or "")
                    break

        obs = observation_from_tree(
            tree,
            app_name=app_name,
            window_name=window_name,
            bundle_id=str(bundle or ""),
            screenshot_path=screenshot_path,
            source="macapptree",
            coverage=1.0,
            degraded=False,
            meta={"screenshot_error": screenshot_error} if screenshot_error else None,
        )
        if screenshot_error and not obs.screenshot_path:
            obs.degraded = True
            obs.meta = dict(obs.meta or {})
            obs.meta["screenshot_error"] = screenshot_error
        return obs

    @staticmethod
    def _front_app_name() -> str:
        try:
            from AppKit import NSWorkspace  # type: ignore

            app = NSWorkspace.sharedWorkspace().frontmostApplication()
            return str(app.localizedName() or "Unknown")
        except Exception:
            return "Unknown"


def attach_screenshot_to_observation(
    obs: Observation,
    *,
    app_name: str,
    require_screenshot: bool = False,
) -> tuple[Observation, Optional[str]]:
    """Best-effort attach a screenshot to an observation that lacks one.

    The deep-AX source (``pyobjc_ax``) produces a tree without pixels; the
    multimodal perceptor (screen understanding / unified cognition) needs the
    screenshot to reason over the actual surface. This captures the screen and
    attaches its path so AX + pixels travel together in one observation — the
    redundant, complete input the perceptor was designed around. Returns the
    (possibly mutated) observation and any capture error.
    """
    if obs.screenshot_path:
        return obs, None
    screenshot_path, screenshot_error = _capture_screen_screenshot(app_name=app_name)
    if screenshot_path:
        obs.screenshot_path = screenshot_path
        obs.meta = dict(obs.meta or {})
        obs.meta["screenshot_source"] = "screencapture"
        if screenshot_error:
            obs.meta["screenshot_error"] = screenshot_error
        return obs, screenshot_error
    if screenshot_error:
        obs.meta = dict(obs.meta or {})
        obs.meta["screenshot_error"] = screenshot_error
        # In strict mode a missing screenshot is a degraded observation: the
        # caller asked for pixels and we could not provide them.
        if require_screenshot:
            obs.degraded = True
    return obs, screenshot_error


class FixtureObserver:
    """Offline / CI observer that loads a macapptree-shaped JSON fixture."""

    def __init__(self, path: Path, *, app_name: str = "WhatsApp") -> None:
        self.path = Path(path)
        self.app_name = app_name

    def observe(self, app: Optional[str] = None) -> Observation:
        data = json.loads(self.path.read_text(encoding="utf-8"))
        tree = data.get("tree") if isinstance(data, dict) and "tree" in data else data
        meta = data.get("meta", {}) if isinstance(data, dict) else {}
        return observation_from_tree(
            tree,
            app_name=app or meta.get("app_name") or self.app_name,
            window_name=meta.get("window_name", ""),
            bundle_id=meta.get("bundle_id", ""),
            source="fixture",
            coverage=float(meta.get("coverage", 1.0)),
            degraded=bool(meta.get("degraded", False)),
            meta=meta,
        )


class PyObjCFallbackObserver:
    """Backup when macapptree is limiting — minimal AX walk via ApplicationServices."""

    def observe(self, app: Optional[str] = None) -> Observation:
        try:
            from ApplicationServices import (  # type: ignore
                AXUIElementCopyAttributeValue,
                AXUIElementCreateSystemWide,
                kAXFocusedApplicationAttribute,
                kAXRoleAttribute,
                kAXTitleAttribute,
                kAXChildrenAttribute,
            )
            from Cocoa import NSWorkspace  # type: ignore
        except ImportError as e:
            raise ImportError("PyObjC ApplicationServices required for AX fallback") from e

        # Minimal stub: front app name + empty children if deep walk fails.
        app_name = app or "Unknown"
        try:
            front = NSWorkspace.sharedWorkspace().frontmostApplication()
            app_name = str(front.localizedName() or app_name)
        except Exception:
            pass

        tree: Dict[str, Any] = {
            "role": "AXApplication",
            "name": app_name,
            "children": [],
            "id": "pyobjc-fallback",
        }
        screenshot_path, screenshot_error = _capture_screen_screenshot(app_name=app_name)
        return observation_from_tree(
            tree,
            app_name=app_name,
            source="pyobjc",
            screenshot_path=screenshot_path,
            coverage=0.0,
            degraded=True,
            meta={
                "note": "shallow PyObjC fallback — install macapptree for full trees",
                **({"screenshot_error": screenshot_error} if screenshot_error else {}),
            },
        )


def get_observer(
    *,
    fixture: Optional[Path] = None,
    prefer: str = "auto",
    with_screenshot: bool = True,
) -> Observer:
    """Resolve observer: fixture → macapptree → pyobjc."""
    if fixture is not None:
        return FixtureObserver(fixture)
    if prefer in ("auto", "macapptree") and macapptree_available():
        return MacAppTreeObserver(with_screenshot=with_screenshot)
    if prefer == "macapptree":
        raise ImportError("macapptree requested but not installed")
    return PyObjCFallbackObserver()
