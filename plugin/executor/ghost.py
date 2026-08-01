"""Layer 10 — Ghost OS primary executor; PyAutoGUI fallback."""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from typing import List, Optional

from plugin.worldmodel.entities.entity import Entity

logger = logging.getLogger(__name__)


@dataclass
class ExecResult:
    ok: bool
    backend: str  # ghost | pyautogui | dry_run
    message: str
    command: Optional[str] = None


def ghost_available() -> bool:
    return shutil.which("ghost") is not None


def pyautogui_available() -> bool:
    try:
        import pyautogui  # noqa: F401

        return True
    except ImportError:
        return False


class GhostExecutor:
    """Shell out to Ghost OS CLI for AX-native click/type/scroll/press."""

    def __init__(self, *, dry_run: bool = False, app: Optional[str] = None) -> None:
        self.dry_run = dry_run
        self.app = app

    def click(self, entity: Entity, *, app: Optional[str] = None) -> ExecResult:
        target = entity.label or entity.semantic_role
        app_name = app or self.app
        cmd: List[str] = ["ghost", "click", target]
        if app_name:
            cmd += ["--app", app_name]
        # Prefer AX click with observed bbox when Ghost is missing (WhatsApp
        # Search is often AXStaticText with a valid macapptree bbox).
        if not self.dry_run and not ghost_available():
            try:
                from plugin.executor.ax_action import ax_available, ax_click

                if ax_available():
                    return ax_click(app_name or "WhatsApp", target, bounds=entity.bounds)
            except Exception as e:
                logger.warning("direct ax_click failed: %s", e)
        return self._run(cmd, action="click")

    def type_text(self, text: str, *, into: Optional[str] = None, app: Optional[str] = None) -> ExecResult:
        cmd: List[str] = ["ghost", "type", text]
        if into:
            cmd += ["--into", into]
        app_name = app or self.app
        if app_name:
            cmd += ["--app", app_name]
        return self._run(cmd, action="type")

    def press(self, key: str) -> ExecResult:
        return self._run(["ghost", "press", key], action="press")

    def hover(self, entity: Entity, *, app: Optional[str] = None) -> ExecResult:
        target = entity.label or entity.semantic_role
        app_name = app or self.app
        try:
            from plugin.executor.ax_action import ax_available, ax_hover

            if ax_available():
                return ax_hover(app_name or "WhatsApp", target, bounds=entity.bounds)
        except Exception as e:
            logger.warning("AX hover failed: %s", e)
        return PyAutoGUIFallback().dispatch("hover", ["ghost", "hover", target], anchor=self._entity_anchor(entity))

    def context_click(self, entity: Entity, *, app: Optional[str] = None) -> ExecResult:
        target = entity.label or entity.semantic_role
        app_name = app or self.app
        try:
            from plugin.executor.ax_action import ax_available, ax_context_click

            if ax_available():
                return ax_context_click(app_name or "WhatsApp", target, bounds=entity.bounds)
        except Exception as e:
            logger.warning("AX context click failed: %s", e)
        return PyAutoGUIFallback().dispatch("context_click", ["ghost", "context_click", target], anchor=self._entity_anchor(entity))

    def scroll(
        self,
        direction: str = "down",
        amount: int = 3,
        *,
        anchor: Optional[tuple[int, int]] = None,
    ) -> ExecResult:
        if anchor is not None and pyautogui_available():
            try:
                import pyautogui

                pyautogui.moveTo(int(anchor[0]), int(anchor[1]), duration=0.08)
            except Exception:
                pass
        return self._run(
            ["ghost", "scroll", direction, "--amount", str(amount)],
            action="scroll",
        )

    def _entity_anchor(self, entity: Entity) -> Optional[tuple[int, int]]:
        if not entity.bounds or len(entity.bounds) < 4:
            return None
        x, y, w, h = entity.bounds
        if w <= 0 or h <= 0:
            return None
        return int(x + w / 2.0), int(y + h / 2.0)

    def _run(self, cmd: List[str], *, action: str) -> ExecResult:
        action = action.lower().strip()
        if self.dry_run:
            return ExecResult(ok=True, backend="dry_run", message=f"dry-run {' '.join(cmd)}", command=" ".join(cmd))

        # Prefer Ghost when installed
        if ghost_available():
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                ok = proc.returncode == 0
                msg = (proc.stdout or proc.stderr or "").strip() or f"exit {proc.returncode}"
                if ok:
                    return ExecResult(ok=True, backend="ghost", message=msg, command=" ".join(cmd))
                logger.warning("ghost failed: %s — trying AX", msg)
            except Exception as e:
                logger.warning("ghost error %s — trying AX", e)

        # AX UIElement Press / set value (Accessibility permission)
        try:
            from plugin.executor.ax_action import ax_available, ax_click, ax_context_click, ax_hover, ax_type

            if ax_available():
                app = self.app or "WhatsApp"
                if action == "click" and len(cmd) >= 3:
                    target = cmd[2]
                    # ghost click TARGET --app X
                    if "--app" in cmd:
                        i = cmd.index("--app")
                        if i + 1 < len(cmd):
                            app = cmd[i + 1]
                    return ax_click(app, target)
                if action == "hover" and len(cmd) >= 3:
                    target = cmd[2]
                    if "--app" in cmd:
                        i = cmd.index("--app")
                        if i + 1 < len(cmd):
                            app = cmd[i + 1]
                    return ax_hover(app, target)
                if action == "context_click" and len(cmd) >= 3:
                    target = cmd[2]
                    if "--app" in cmd:
                        i = cmd.index("--app")
                        if i + 1 < len(cmd):
                            app = cmd[i + 1]
                    return ax_context_click(app, target)
                if action == "type" and len(cmd) >= 3:
                    text = cmd[2]
                    into = None
                    if "--into" in cmd:
                        i = cmd.index("--into")
                        if i + 1 < len(cmd):
                            into = cmd[i + 1]
                    if "--app" in cmd:
                        i = cmd.index("--app")
                        if i + 1 < len(cmd):
                            app = cmd[i + 1]
                    return ax_type(app, text, into=into)
        except Exception as e:
            logger.warning("AX executor failed: %s", e)

        return PyAutoGUIFallback().dispatch(action, cmd)


class PyAutoGUIFallback:
    """Never primary — coordinate/keyboard only when Accessibility path fails."""

    def dispatch(self, action: str, ghost_cmd: List[str], *, anchor: Optional[tuple[int, int]] = None) -> ExecResult:
        action = action.lower().strip()
        if not pyautogui_available():
            return ExecResult(
                ok=False,
                backend="pyautogui",
                message="PyAutoGUI not installed and Ghost unavailable",
                command=" ".join(ghost_cmd),
            )
        import pyautogui

        try:
            if anchor is not None:
                pyautogui.moveTo(int(anchor[0]), int(anchor[1]), duration=0.08)
            if action == "type" and len(ghost_cmd) >= 3:
                pyautogui.typewrite(ghost_cmd[2], interval=0.02)
            elif action == "hover":
                if anchor is None:
                    return ExecResult(ok=False, backend="pyautogui", message="refuse blind hover without coordinates", command=" ".join(ghost_cmd))
                pyautogui.moveTo(int(anchor[0]), int(anchor[1]), duration=0.08)
                pyautogui.moveRel(1, 0, duration=0.06)
                pyautogui.moveRel(-1, 0, duration=0.06)
            elif action == "context_click":
                if anchor is None:
                    return ExecResult(ok=False, backend="pyautogui", message="refuse blind context click without coordinates", command=" ".join(ghost_cmd))
                pyautogui.rightClick(int(anchor[0]), int(anchor[1]))
            elif action == "press" and len(ghost_cmd) >= 3:
                pyautogui.press(ghost_cmd[2])
            elif action == "scroll":
                direction = "down"
                amount = 3
                if len(ghost_cmd) >= 3:
                    direction = ghost_cmd[2]
                if "--amount" in ghost_cmd:
                    i = ghost_cmd.index("--amount")
                    if i + 1 < len(ghost_cmd):
                        try:
                            amount = max(1, int(ghost_cmd[i + 1]))
                        except Exception:
                            amount = 3
                delta = 100 * amount
                pyautogui.scroll(-delta if direction == "down" else delta)
            elif action == "click":
                # Cannot resolve AX without Ghost — click center as last resort is refused
                # unless coordinates appear in command.
                return ExecResult(
                    ok=False,
                    backend="pyautogui",
                    message="refuse blind click without coordinates; install Ghost OS",
                    command=" ".join(ghost_cmd),
                )
            else:
                return ExecResult(ok=False, backend="pyautogui", message=f"unsupported {action}")
            return ExecResult(ok=True, backend="pyautogui", message=f"pyautogui {action}", command=" ".join(ghost_cmd))
        except Exception as e:
            return ExecResult(ok=False, backend="pyautogui", message=str(e), command=" ".join(ghost_cmd))


def get_executor(*, dry_run: bool = False, app: Optional[str] = None) -> GhostExecutor:
    return GhostExecutor(dry_run=dry_run, app=app)
