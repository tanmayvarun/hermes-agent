#!/usr/bin/env python3
"""Keep Hermes desktop alive, foregrounded, and log-watched for live probes.

Does NOT kill a healthy instance. Restarts only after unexpected exit.
Writes heartbeats to /tmp/hermes_supervise.log.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ELECTRON = REPO / "node_modules/electron/dist/Electron.app/Contents/MacOS/Electron"
LOG = Path("/tmp/hermes_supervise.log")
ERR = Path("/tmp/hermes_cu.err")
OUT = Path("/tmp/hermes_cu.out")
DESKTOP_LOG = Path.home() / ".hermes/logs/desktop.log"
AGENT_LOG = Path.home() / ".hermes/logs/agent.log"


def log(msg: str) -> None:
    line = f"{datetime.now().strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def find_pid() -> int | None:
    # Prefer pgrep — NSWorkspace can stall without a macOS runloop in headless supervisors.
    try:
        out = subprocess.check_output(
            ["pgrep", "-f", "electron/dist/Electron.app/Contents/MacOS/Electron apps/desktop"],
            text=True,
        ).strip()
        if out:
            return int(out.splitlines()[0])
    except Exception:
        pass
    try:
        from AppKit import NSWorkspace
    except Exception:
        return None
    for a in NSWorkspace.sharedWorkspace().runningApplications():
        try:
            path = str(a.executableURL().path() if a.executableURL() else "").replace("\\", "/")
        except Exception:
            path = ""
        name = str(a.localizedName() or "")
        if name == "Hermes":
            return int(a.processIdentifier())
        if "hermes-agent" in path and path.endswith("/Electron"):
            return int(a.processIdentifier())
    return None


def cdp_up() -> bool:
    try:
        urllib.request.urlopen("http://127.0.0.1:9222/json/version", timeout=1.0).read(64)
        return True
    except Exception:
        return False


def activate(pid: int) -> None:
    try:
        from AppKit import NSApplicationActivateIgnoringOtherApps, NSRunningApplication

        app = NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
        if app is None:
            return
        app.unhide()
        app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
    except Exception as exc:
        log(f"activate_failed: {exc}")


def launch() -> subprocess.Popen:
    env = os.environ.copy()
    env.pop("ELECTRON_RUN_AS_NODE", None)
    env["HERMES_DESKTOP_HERMES_ROOT"] = str(REPO)
    env["PATH"] = f"{REPO / '.venv' / 'bin'}:{env.get('PATH', '')}"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out_f = OUT.open("a")
    err_f = ERR.open("a")
    log(f"launching electron cwd={REPO}")
    proc = subprocess.Popen(
        [str(ELECTRON), "apps/desktop", "--remote-debugging-port=9222"],
        cwd=str(REPO),
        env=env,
        stdout=out_f,
        stderr=err_f,
        start_new_session=True,  # survive supervisor SIGHUP; don't die with tty
    )
    log(f"launched pid={proc.pid}")
    return proc


def tail_new(path: Path, offset: int, needle: str | None = None) -> tuple[int, list[str]]:
    if not path.exists():
        return offset, []
    data = path.read_text(errors="replace")
    if offset > len(data):
        offset = 0
    chunk = data[offset:]
    offset = len(data)
    lines = [ln for ln in chunk.splitlines() if ln.strip()]
    if needle:
        lines = [ln for ln in lines if needle.lower() in ln.lower()]
    return offset, lines


def main() -> int:
    if not ELECTRON.exists():
        log(f"missing electron binary: {ELECTRON}")
        return 2

    stop = False

    def _stop(*_a):
        nonlocal stop
        stop = True
        log("supervisor stop signal")

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    child: subprocess.Popen | None = None
    desk_off = DESKTOP_LOG.stat().st_size if DESKTOP_LOG.exists() else 0
    agent_off = AGENT_LOG.stat().st_size if AGENT_LOG.exists() else 0
    last_fg = 0.0
    last_hb = 0.0
    adopted = False

    log("supervisor start")
    while not stop:
        pid = find_pid()
        if pid is None:
            adopted = False
            if child is not None and child.poll() is not None:
                log(f"child_exited code={child.returncode}")
                # dump last stderr lines
                if ERR.exists():
                    err_tail = ERR.read_text(errors="replace").splitlines()[-15:]
                    for ln in err_tail:
                        log(f"err| {ln}")
            child = launch()
            # wait for UI
            for i in range(40):
                if stop:
                    break
                time.sleep(0.5)
                pid = find_pid()
                if pid and cdp_up():
                    log(f"ui_ready pid={pid} cdp=1 t={i*0.5:.1f}s")
                    activate(pid)
                    break
            else:
                log("ui_ready_timeout")
        elif child is None and not adopted:
            log(f"adopting existing pid={pid}")
            adopted = True

        now = time.time()
        if pid and now - last_fg >= 8:
            activate(pid)
            last_fg = now

        if now - last_hb >= 5:
            log(
                f"heartbeat pid={pid} cdp={int(cdp_up())} "
                f"child_alive={child.poll() is None if child else 'n/a'}"
            )
            last_hb = now

        desk_off, dlines = tail_new(DESKTOP_LOG, desk_off)
        for ln in dlines:
            low = ln.lower()
            if any(
                k in low
                for k in (
                    "render-process-gone",
                    "sigterm",
                    "crash",
                    "killed",
                    "exited",
                    "zaroorat",
                    "compression",
                )
            ):
                log(f"desktop| {ln}")

        agent_off, alines = tail_new(AGENT_LOG, agent_off)
        for ln in alines:
            # Only forward newly written lines (offset-based); keep filters tight.
            if "2026-" not in ln and "Traceback" not in ln:
                continue
            low = ln.lower()
            if any(
                k in low
                for k in (
                    "zaroorat",
                    "agentruntime",
                    "taskingress",
                    "traceback",
                    "compose_domain",
                    "native_computer",
                    "acceptance_trace",
                    "turn_context",
                )
            ):
                log(f"agent| {ln}")

        time.sleep(1.0)

    log("supervisor exit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
