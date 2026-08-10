"""Layer 1 primary: macapptree. Backup: PyObjC AXUIElement (stub). Fixture for CI."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Protocol

from plugin.perception.capture_frame import IDENTITY_KEY as CAPTURE_FRAME_KEY, CaptureFrame
from plugin.perception.macos.accessibility.tree_parse import observation_from_tree
from plugin.perception.observation import Observation

logger = logging.getLogger(__name__)


def _normalize_owner(name: Any) -> str:
    """Owner/app name with invisible format characters dropped, lowercased.

    macOS reports some window owners with leading Unicode bidi/format marks
    (e.g. WhatsApp as ``"\u200eWhatsApp"``); comparing raw strings misses them.
    """
    import unicodedata

    text = str(name or "")
    cleaned = "".join(ch for ch in text if unicodedata.category(ch) != "Cf")
    return cleaned.strip().lower()


def _window_frame_for_app(app_name: str) -> Optional[tuple[int, tuple[float, float, float, float]]]:
    """The window id *and* its bounds in screen points, for the same window.

    The bounds must come from the same lookup as the id: resolving them
    separately invites a capture scoped to one window and coordinates measured
    against another if the app raises a second window in between.
    """
    target = _normalize_owner(app_name)
    if not target:
        return None
    try:
        from Quartz import (
            CGWindowListCopyWindowInfo,
            kCGNullWindowID,
            kCGWindowListOptionOnScreenOnly,
        )
    except Exception:
        return None
    try:
        infos = CGWindowListCopyWindowInfo(kCGWindowListOptionOnScreenOnly, kCGNullWindowID) or []
    except Exception:
        return None
    best: Optional[tuple[int, tuple[float, float, float, float]]] = None
    best_area = 0.0
    for info in infos:
        owner = _normalize_owner(info.get("kCGWindowOwnerName"))
        if owner != target and target not in owner and owner not in target:
            continue
        layer = info.get("kCGWindowLayer")
        if layer not in (0, None):
            continue
        bounds = info.get("kCGWindowBounds") or {}
        try:
            x = float(bounds.get("X", 0.0))
            y = float(bounds.get("Y", 0.0))
            w = float(bounds.get("Width", 0.0))
            h = float(bounds.get("Height", 0.0))
        except (TypeError, ValueError):
            continue
        area = w * h
        if area > best_area:
            num = info.get("kCGWindowNumber")
            if num is None:
                continue
            best_area = area
            best = (int(num), (x, y, w, h))
    return best


def _window_id_for_app(app_name: str) -> Optional[int]:
    """The window id of the target app's largest on-screen normal window.

    Perception must look at the app it is controlling, not at whatever window
    happens to be topmost. A full-screen grab leaks an occluding app's pixels
    into the vision path — e.g. an editor in front of WhatsApp reads as the
    editor's content, and the perceptor then reasons about the wrong world.
    Resolving the window id lets the capture be scoped to that window's pixels
    (composited by the window server) regardless of z-order, which is how a
    human "looks at the WhatsApp window" even when another window overlaps it.

    Returns None when Quartz is unavailable or the app has no normal window, so
    the caller can fall back to a full-screen grab.
    """
    target = _normalize_owner(app_name)
    if not target:
        return None
    try:
        from Quartz import (
            CGWindowListCopyWindowInfo,
            kCGNullWindowID,
            kCGWindowListOptionOnScreenOnly,
        )
    except Exception:
        return None
    try:
        infos = CGWindowListCopyWindowInfo(kCGWindowListOptionOnScreenOnly, kCGNullWindowID) or []
    except Exception:
        return None
    best_id: Optional[int] = None
    best_area = 0.0
    for info in infos:
        owner = _normalize_owner(info.get("kCGWindowOwnerName"))
        # WhatsApp for Mac reports its owner as "\u200eWhatsApp" (a leading bidi
        # mark), so a raw equality check misses it. Normalising both sides drops
        # invisible format characters; containment tolerates similar decorations.
        if owner != target and target not in owner and owner not in target:
            continue
        # Layer 0 is a normal application window; menubar items, overlays, and
        # shadows live on other layers and must not win the size comparison.
        layer = info.get("kCGWindowLayer")
        if layer not in (0, None):
            continue
        bounds = info.get("kCGWindowBounds") or {}
        try:
            area = float(bounds.get("Width", 0.0)) * float(bounds.get("Height", 0.0))
        except (TypeError, ValueError):
            continue
        if area > best_area:
            best_area = area
            num = info.get("kCGWindowNumber")
            best_id = int(num) if num is not None else None
    return best_id


def _raise_app(app_name: str) -> None:
    """Bring the app forward / un-minimize it so it has a composited window.

    For an AX-blind app, background window-scoped capture needs an on-screen
    window; when there is none (the app is minimized or on another Space), there
    is nothing to scope to. Raising the app is the agent's job — it owns keeping
    its own surface perceivable — so we activate it rather than grabbing whatever
    else is on screen and perceiving the wrong app.
    """
    import time as _time

    try:
        subprocess.run(["open", "-a", app_name], capture_output=True, timeout=10)
    except Exception:
        pass
    _time.sleep(0.6)


def _measure_capture_frame(
    shot: Path, window_bounds: Optional[tuple[float, float, float, float]]
) -> CaptureFrame:
    """The transform from this capture's pixels to screen points.

    Measured from the file rather than assumed, so a Retina window (2x) and a
    window on a non-Retina second display (1x) each get the right scale.
    """
    try:
        from PIL import Image

        with Image.open(shot) as im:
            width_px = float(im.size[0])
    except Exception:
        return CaptureFrame()
    return CaptureFrame.measure(width_px, window_bounds)


def resolve_screenshot_capture_mode(*, include_overlays: bool) -> str:
    """Which capture strategy to use for the next observation screenshot.

    ``window`` — ``screencapture -l <layer-0 id>``. Correct for ordinary looks
    (ignores occluding apps) but **drops macOS context menus**, which live on
    non-zero window layers (live 150708: menu open on display, absent in agent
    pixels → VLM truthfully reported "no context menu").

    ``overlay_display`` — display-region composite over the task window bounds
    (all on-screen layers in that rect). Use when a reveal handoff / overlay
    surface is expected so Forward/Reply appear in the image the perceptor sees.
    """
    return "overlay_display" if include_overlays else "window"


def _save_pil_rgb(image: Any, dest: Path) -> bool:
    try:
        rgb = image.convert("RGB") if hasattr(image, "convert") else image
        rgb.save(str(dest))
        return dest.exists() and dest.stat().st_size > 0
    except Exception:
        return False


def _capture_overlay_display_region(
    shot: Path, window_bounds: tuple[float, float, float, float]
) -> tuple[bool, str]:
    """Composite all on-screen layers inside the task window's screen rect."""
    try:
        from plugin.perception.continuity.witness import capture_rect
    except Exception as exc:
        return False, f"overlay_import: {exc}"
    img = capture_rect(window_bounds)
    if img is None:
        return False, "overlay_rect: empty"
    if not _save_pil_rgb(img, shot):
        return False, "overlay_rect: save failed"
    return True, ""


def _capture_screen_screenshot(
    *, app_name: str = "WhatsApp", include_overlays: bool = False
) -> tuple[Optional[str], Optional[str], CaptureFrame]:
    """Capture the target app's window to a temp PNG, or return an explicit error.

    Default prefers a window-scoped grab (``screencapture -l <id>``) so an
    occluding window cannot leak into perception. When ``include_overlays`` is
    set (reveal handoff / expected context_menu), use a display-region composite
    over the task window bounds so floating menus are in the pixels.

    If the app has no on-screen window at all (minimized / another Space), the
    agent raises it and re-resolves rather than perceiving the wrong app; a
    full-screen grab is the last resort only.

    Also returns the transform from the resulting image's pixels back to screen
    points. A window-scoped Retina grab is offset by the window's origin and
    doubled in scale, so anything measured on these pixels is unclickable until
    it is converted -- see plugin/perception/capture_frame.
    """
    fd, path = tempfile.mkstemp(suffix=".png", prefix=f"{app_name.lower().replace(' ', '_')}_obs_")
    os.close(fd)
    shot = Path(path)
    mode = resolve_screenshot_capture_mode(include_overlays=include_overlays)

    def _run(cmd: list[str]) -> tuple[bool, str]:
        try:
            proc = subprocess.run(
                cmd,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=12,
            )
        except Exception as exc:  # noqa: BLE001 - capture must be best-effort
            return False, str(exc)
        if shot.exists() and shot.stat().st_size > 0:
            return True, ""
        return False, (proc.stderr or "").strip() or "screencapture produced an empty file"

    errors: list[str] = []
    found = _window_frame_for_app(app_name)
    if found is None:
        # No on-screen window for the task app: it is minimized or on another
        # Space, so there is nothing to scope a background grab to. Raise it and
        # re-resolve — capturing the whole screen here would perceive whatever
        # foreign app happens to be frontmost (the exact drift we must avoid).
        _raise_app(app_name)
        found = _window_frame_for_app(app_name)

    if mode == "overlay_display" and found is not None:
        _win_id, window_bounds = found
        ok, err = _capture_overlay_display_region(shot, window_bounds)
        if ok:
            return str(shot), None, _measure_capture_frame(shot, window_bounds)
        if err:
            errors.append(err)
        # Fall through to full-screen (still composites menus) before window -l.
        ok, err = _run(["screencapture", "-x", str(shot)])
        if ok:
            return str(shot), None, _measure_capture_frame(shot, _main_screen_bounds())
        if err:
            errors.append(f"full-screen: {err}")

    if found is not None and mode == "window":
        win_id, window_bounds = found
        # -l scopes to the window; -o drops the drop-shadow border. The window
        # server composites just this window, so z-order / occlusion is moot —
        # and so are context menus on other layers (hence overlay_display).
        ok, err = _run(["screencapture", "-x", "-o", "-l", str(win_id), str(shot)])
        if ok:
            return str(shot), None, _measure_capture_frame(shot, window_bounds)
        if err:
            errors.append(f"window-scoped: {err}")

    ok, err = _run(["screencapture", "-x", str(shot)])
    if ok:
        # Full-screen: the origin is the display's, but the scale still is not
        # the identity on a Retina panel, so measure it against the main screen.
        return str(shot), None, _measure_capture_frame(shot, _main_screen_bounds())
    if err:
        errors.append(f"full-screen: {err}")
    try:
        shot.unlink(missing_ok=True)
    except Exception:
        pass
    return None, "; ".join(errors) or "screencapture failed", CaptureFrame()


def _main_screen_bounds() -> Optional[tuple[float, float, float, float]]:
    """The main display's frame in points, for scaling a full-screen grab."""
    try:
        from AppKit import NSScreen

        frame = NSScreen.mainScreen().frame()
        return (0.0, 0.0, float(frame.size.width), float(frame.size.height))
    except Exception:
        return None


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
                    screenshot_path, screenshot_error, _frame = _capture_screen_screenshot(
                        app_name=app_name
                    )
            except Exception as exc:  # noqa: BLE001 - prefer a recoverable fallback
                screenshot_error = str(exc)
                screenshot_path, capture_error, _frame = _capture_screen_screenshot(
                    app_name=app_name
                )
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
    include_overlays: bool = False,
) -> tuple[Observation, Optional[str]]:
    """Best-effort attach a screenshot to an observation that lacks one.

    The deep-AX source (``pyobjc_ax``) produces a tree without pixels; the
    multimodal perceptor (screen understanding / unified cognition) needs the
    screenshot to reason over the actual surface. This captures the screen and
    attaches its path so AX + pixels travel together in one observation — the
    redundant, complete input the perceptor was designed around. Returns the
    (possibly mutated) observation and any capture error.

    ``include_overlays`` selects display-region capture so context menus are in
    the pixels (see :func:`resolve_screenshot_capture_mode`).
    """
    if obs.screenshot_path:
        return obs, None
    mode = resolve_screenshot_capture_mode(include_overlays=include_overlays)
    screenshot_path, screenshot_error, frame = _capture_screen_screenshot(
        app_name=app_name, include_overlays=include_overlays
    )
    if screenshot_path:
        obs.screenshot_path = screenshot_path
        obs.meta = dict(obs.meta or {})
        obs.meta["screenshot_source"] = (
            "overlay_display" if mode == "overlay_display" else "screencapture"
        )
        obs.meta["screenshot_capture_mode"] = mode
        # Travel the transform with the pixels. Anything that measures a
        # rectangle on this image (OCR, the vision model) owes a conversion back
        # to screen points before the result can be clicked, and re-deriving it
        # later would race the window being moved or resized in between.
        obs.meta[CAPTURE_FRAME_KEY] = frame.as_dict()
        # Stamp authoritative FrameGraph at capture time (Capture ≠ Window).
        try:
            from plugin.perception.coordinate_frame import (
                FRAME_GRAPH_KEY,
                frame_graph_from_capture_artifact,
                new_capture_id,
            )

            cid = new_capture_id()
            # Full-window screencapture: image origin in window is (0,0);
            # window origin in screen is CaptureFrame.origin_*.
            img_w = float(getattr(frame, "image_width", 0) or 0)
            img_h = float(getattr(frame, "image_height", 0) or 0)
            if img_w <= 0 or img_h <= 0:
                try:
                    from PIL import Image

                    with Image.open(screenshot_path) as im:
                        img_w, img_h = float(im.size[0]), float(im.size[1])
                except Exception:
                    pass
            graph = frame_graph_from_capture_artifact(
                capture_id=cid,
                image_size=(img_w, img_h),
                window_origin_in_screen=(frame.origin_x, frame.origin_y),
                image_origin_in_window=(0.0, 0.0),
                capture_scale=float(frame.scale or 1.0),
                point_scale=(1.0 / float(frame.scale)) if float(frame.scale or 0) > 0 else 1.0,
                backing_scale=float(frame.scale or 1.0),
            )
            obs.meta[FRAME_GRAPH_KEY] = graph.to_dict()
            obs.meta["capture_id"] = cid
        except Exception as exc:
            obs.meta["frame_graph_error"] = str(exc)[:160]
        if screenshot_error:
            obs.meta["screenshot_error"] = screenshot_error
        return obs, screenshot_error
    if screenshot_error:
        obs.meta = dict(obs.meta or {})
        obs.meta["screenshot_error"] = screenshot_error
        obs.meta["screenshot_capture_mode"] = mode
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
        screenshot_path, screenshot_error, _frame = _capture_screen_screenshot(
            app_name=app_name
        )
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
