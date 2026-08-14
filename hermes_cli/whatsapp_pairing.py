"""WhatsApp link-device pairing (Baileys bridge --pair-json).

Shared by dashboard onboarding and AgentRuntime prerequisite resolution.
Produces qr_payload events the UI can render inline.
"""

from __future__ import annotations

import json
import secrets
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from hermes_cli._subprocess_compat import windows_hide_flags

TTL_SECONDS = 600
TERMINAL_STATUSES = frozenset({"connected", "error", "expired", "cancelled"})

_LOCK = threading.RLock()
_SESSIONS: Dict[str, "WhatsAppPairingSession"] = {}


@dataclass
class WhatsAppPairingSession:
    pairing_id: str
    session_path: str
    mode: str = "bot"
    status: str = "starting"
    expires_at: str = ""
    expires_at_ts: float = 0.0
    qr_payload: Optional[str] = None
    account_id: Optional[str] = None
    account_name: Optional[str] = None
    account_phone: Optional[str] = None
    error: Optional[str] = None
    proc: Optional[subprocess.Popen] = field(default=None, repr=False)


def _utc_iso_from_ts(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat().replace("+00:00", "Z")


def whatsapp_session_path() -> Path:
    from hermes_constants import get_hermes_dir

    return get_hermes_dir("platforms/whatsapp/session", "whatsapp/session")


def phone_from_identifier(value: Any) -> Optional[str]:
    import re

    raw = str(value or "").strip()
    if not raw:
        return None
    candidate = raw.split("@", 1)[0].split(":", 1)[0]
    digits = re.sub(r"\D+", "", candidate)
    return digits or None


def linked_account_from_session(session_path: Optional[Path] = None) -> tuple[Optional[str], Optional[str], Optional[str]]:
    path = session_path or whatsapp_session_path()
    creds_path = path / "creds.json"
    try:
        payload = json.loads(creds_path.read_text(encoding="utf-8"))
    except Exception:
        return None, None, None

    account_id: Optional[str] = None
    account_name: Optional[str] = None

    def collect(candidate: Any) -> None:
        nonlocal account_id, account_name
        if not isinstance(candidate, dict):
            return
        if account_id is None:
            for key in ("id", "jid", "lid"):
                value = str(candidate.get(key) or "").strip()
                if value:
                    account_id = value
                    break
        if account_name is None:
            for key in ("name", "verifiedName", "notify", "pushName"):
                value = str(candidate.get(key) or "").strip()
                if value:
                    account_name = value
                    break

    collect(payload.get("me"))
    collect(payload.get("account"))
    collect(payload)
    return account_id, account_name, phone_from_identifier(account_id)


def is_whatsapp_linked(session_path: Optional[Path] = None) -> bool:
    """True when Baileys creds look like a real linked account (not empty/corrupt).

    An empty or unparseable ``creds.json`` must NOT count as linked — that
    previously skipped Link-a-device QR and falsely continued the flow.
    """
    path = session_path or whatsapp_session_path()
    creds_path = path / "creds.json"
    try:
        if not creds_path.is_file() or creds_path.stat().st_size < 8:
            return False
    except OSError:
        return False
    account_id, _, _ = linked_account_from_session(path)
    return bool(account_id)


def clear_whatsapp_session(session_path: Optional[Path] = None) -> None:
    """Wipe Baileys auth files so a fresh Link-a-device QR can be issued."""
    import shutil

    path = session_path or whatsapp_session_path()
    if not path.exists():
        return
    for child in path.iterdir():
        try:
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)
        except Exception:
            pass


def bridge_port() -> int:
    import os

    raw = str(os.environ.get("WHATSAPP_BRIDGE_PORT") or "3000").strip() or "3000"
    try:
        return int(raw)
    except ValueError:
        return 3000


def probe_bridge_connection(*, timeout_s: float = 2.0) -> tuple[bool, str]:
    """Return (connected, detail) from the local Baileys bridge ``/health``.

    When creds exist but ``/health`` is down, callers should
    :func:`ensure_whatsapp_bridge_running` (pair-only exits leave no HTTP
    server). ASK for Link-a-device only when there is no linked account.
    """
    import urllib.error
    import urllib.request

    url = f"http://127.0.0.1:{bridge_port()}/health"
    try:
        with urllib.request.urlopen(url, timeout=max(0.5, float(timeout_s))) as resp:
            body = json.loads(resp.read().decode("utf-8", errors="replace") or "{}")
    except urllib.error.URLError as exc:
        return False, f"unreachable:{exc.reason if getattr(exc, 'reason', None) else exc}"
    except Exception as exc:
        return False, f"health_error:{exc}"

    status = str(body.get("status") or body.get("state") or "").strip().lower()
    if status == "connected" or body.get("connected") is True:
        return True, "connected"
    return False, status or "not_connected"


def is_whatsapp_live(*, timeout_s: float = 2.0) -> bool:
    """True only when the gateway bridge reports an authenticated WhatsApp session."""
    ok, _detail = probe_bridge_connection(timeout_s=timeout_s)
    return bool(ok)


_BRIDGE_DAEMON_LOCK = threading.RLock()
_BRIDGE_DAEMON_PROC: Optional[subprocess.Popen] = None


def ensure_whatsapp_bridge_running(*, timeout_s: float = 30.0) -> tuple[bool, str]:
    """Ensure the long-lived Baileys HTTP bridge is up when the device is linked.

    Link ASK uses ``--pair-only`` (QR + creds, then exit — no ``/health``).
    Gateway send needs the daemon. This starts it after a successful link
    instead of treating a down bridge as "need another QR".
    """
    live, detail = probe_bridge_connection(timeout_s=min(2.0, timeout_s))
    if live:
        return True, detail
    if not is_whatsapp_linked():
        return False, "not_linked"
    ok, reason = bridge_available()
    if not ok:
        return False, reason

    with _BRIDGE_DAEMON_LOCK:
        live, detail = probe_bridge_connection(timeout_s=min(2.0, timeout_s))
        if live:
            return True, detail
        return _start_long_lived_bridge(timeout_s=timeout_s)


def _start_long_lived_bridge(*, timeout_s: float = 30.0) -> tuple[bool, str]:
    """Spawn bridge.js (HTTP) for the linked session and wait for /health."""
    global _BRIDGE_DAEMON_PROC
    import os

    from hermes_cli._subprocess_compat import windows_detach_popen_kwargs
    from hermes_constants import find_node_executable, with_hermes_node_path
    from gateway.platforms.whatsapp_common import resolve_whatsapp_bridge_dir

    # Reuse adapter cleanup helpers so we don't fight gateway-owned bridges.
    try:
        from plugins.platforms.whatsapp.adapter import (
            _kill_port_process,
            _kill_stale_bridge_by_pidfile,
            _write_bridge_pidfile,
        )
    except Exception:
        _kill_port_process = None  # type: ignore[assignment]
        _kill_stale_bridge_by_pidfile = None  # type: ignore[assignment]
        _write_bridge_pidfile = None  # type: ignore[assignment]

    session_path = whatsapp_session_path()
    bridge_dir = resolve_whatsapp_bridge_dir()
    bridge_script = bridge_dir / "bridge.js"
    node = find_node_executable("node")
    if not node or not bridge_script.is_file():
        return False, "missing_bridge_or_node"

    _ensure_bridge_dependencies(bridge_dir)
    session_path.mkdir(parents=True, exist_ok=True)
    port = bridge_port()

    if _BRIDGE_DAEMON_PROC is not None and _BRIDGE_DAEMON_PROC.poll() is None:
        # Already spawning/running under us — just wait.
        return _wait_bridge_connected(timeout_s=timeout_s)

    try:
        if _kill_stale_bridge_by_pidfile is not None:
            _kill_stale_bridge_by_pidfile(session_path)
        if _kill_port_process is not None:
            _kill_port_process(port)
    except Exception:
        pass

    mode = str(os.environ.get("WHATSAPP_MODE") or "bot").strip() or "bot"
    log_path = session_path.parent / "bridge.log"
    log_fh = open(log_path, "a", encoding="utf-8")
    try:
        proc = subprocess.Popen(
            [
                node,
                str(bridge_script),
                "--port",
                str(port),
                "--session",
                str(session_path),
                "--mode",
                mode,
            ],
            cwd=str(bridge_dir),
            stdout=log_fh,
            stderr=log_fh,
            env=with_hermes_node_path(),
            **windows_detach_popen_kwargs(),
        )
    except Exception as exc:
        try:
            log_fh.close()
        except Exception:
            pass
        return False, f"spawn_failed:{exc}"

    _BRIDGE_DAEMON_PROC = proc
    try:
        if _write_bridge_pidfile is not None:
            _write_bridge_pidfile(session_path, proc.pid)
    except Exception:
        pass

    ok, detail = _wait_bridge_connected(timeout_s=timeout_s, proc=proc)
    if not ok and proc.poll() is not None:
        return False, f"bridge_exited:{proc.returncode}:{detail}"
    return ok, detail


def _wait_bridge_connected(
    *, timeout_s: float = 30.0, proc: Optional[subprocess.Popen] = None
) -> tuple[bool, str]:
    deadline = time.time() + max(3.0, float(timeout_s))
    last = "starting"
    http_seen = False
    while time.time() < deadline:
        if proc is not None and proc.poll() is not None:
            return False, f"exited:{proc.returncode}"
        ok, detail = probe_bridge_connection(timeout_s=1.5)
        last = detail
        if ok:
            return True, detail
        # HTTP up but WhatsApp still connecting (common after 515 restart).
        if detail and detail not in {"unreachable", "not_connected"} and not detail.startswith(
            "unreachable"
        ):
            http_seen = True
        time.sleep(0.75)
    if http_seen:
        # Daemon is up; WA may finish connecting shortly — treat as usable for
        # subsequent probes (executor will re-check /send). Prefer not CU solely
        # because auth took >timeout after a fresh link.
        return False, f"http_up_not_connected:{last}"
    return False, last


def bridge_available() -> tuple[bool, str]:
    try:
        from gateway.platforms.whatsapp_common import resolve_whatsapp_bridge_dir
        from hermes_constants import find_node_executable
    except Exception as exc:
        return False, f"import_error:{exc}"

    bridge_dir = resolve_whatsapp_bridge_dir()
    bridge_script = bridge_dir / "bridge.js"
    if not bridge_script.exists():
        return False, f"missing_bridge:{bridge_script}"
    if not find_node_executable("node"):
        return False, "missing_node"
    return True, "ok"


def _ensure_bridge_dependencies(bridge_dir: Path) -> None:
    if (bridge_dir / "node_modules").exists():
        return
    from hermes_constants import find_node_executable, with_hermes_node_path
    from utils import env_int

    npm = find_node_executable("npm")
    if not npm:
        raise RuntimeError("npm was not found. WhatsApp setup needs Node.js and npm.")
    timeout = env_int("WHATSAPP_NPM_INSTALL_TIMEOUT", 300)
    proc = subprocess.run(
        [npm, "install", "--no-fund", "--no-audit"],
        cwd=str(bridge_dir),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=with_hermes_node_path(),
        timeout=timeout,
        creationflags=windows_hide_flags(),
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"npm install failed for WhatsApp bridge: {detail or 'no output'}")


def _spawn_pairing_process(session_path: Path, mode: str) -> subprocess.Popen:
    from gateway.platforms.whatsapp_common import resolve_whatsapp_bridge_dir
    from hermes_constants import find_node_executable, with_hermes_node_path

    bridge_dir = resolve_whatsapp_bridge_dir()
    bridge_script = bridge_dir / "bridge.js"
    node = find_node_executable("node")
    if not node:
        raise RuntimeError("Node.js was not found. WhatsApp setup needs Node.js.")
    _ensure_bridge_dependencies(bridge_dir)
    session_path.mkdir(parents=True, exist_ok=True)
    env = with_hermes_node_path()
    env["WHATSAPP_MODE"] = mode
    env["WHATSAPP_DM_POLICY"] = "pairing"
    return subprocess.Popen(
        [
            node,
            str(bridge_script),
            "--pair-only",
            "--pair-json",
            "--session",
            str(session_path),
        ],
        cwd=str(bridge_dir),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        start_new_session=True,
        env=env,
        creationflags=windows_hide_flags(),
    )


def _terminate(proc: Optional[subprocess.Popen]) -> None:
    if proc is None or proc.poll() is not None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=3)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def _watch(pairing_id: str, proc: subprocess.Popen) -> None:
    try:
        stream = proc.stdout
        if stream is not None:
            for line in stream:
                raw = line.strip()
                if not raw:
                    continue
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                event = str(payload.get("event") or "").strip()
                with _LOCK:
                    record = _SESSIONS.get(pairing_id)
                    if not record or record.proc is not proc:
                        return
                    if event == "qr":
                        qr = str(payload.get("qr") or "").strip()
                        if qr:
                            record.qr_payload = qr
                            record.status = "waiting"
                            record.error = None
                    elif event == "connected":
                        user = payload.get("user")
                        if isinstance(user, dict):
                            account_id = str(user.get("id") or "").strip()
                            account_name = str(user.get("name") or "").strip()
                            record.account_id = account_id or None
                            record.account_name = account_name or None
                            record.account_phone = phone_from_identifier(account_id)
                        record.status = "connected"
                        record.error = None
                    elif event == "error":
                        err = str(payload.get("error") or "WhatsApp pairing failed.")
                        # Bridge may auto-reset a logged-out session and emit QR next;
                        # keep status non-terminal so waiters don't bail early.
                        if err == "logged_out":
                            record.error = err
                            if record.status not in {"waiting", "connected"}:
                                record.status = "starting"
                        else:
                            record.status = "error"
                            record.error = err
                    elif event == "session_reset":
                        record.error = None
                        if record.status not in {"waiting", "connected"}:
                            record.status = "starting"
                    elif event == "disconnected" and record.status == "starting":
                        record.status = "waiting"
        returncode = proc.wait()
    except Exception as exc:
        with _LOCK:
            record = _SESSIONS.get(pairing_id)
            if record and record.proc is proc and record.status not in TERMINAL_STATUSES:
                record.status = "error"
                record.error = str(exc)
        return

    with _LOCK:
        record = _SESSIONS.get(pairing_id)
        if not record or record.proc is not proc:
            return
        if record.status in {"connected", "cancelled", "expired"}:
            return
        record.status = "error"
        record.error = (
            "WhatsApp pairing process exited before pairing completed."
            if returncode == 0
            else f"WhatsApp pairing process exited with code {returncode}."
        )


def _run_pairing(pairing_id: str, session_path: Path, mode: str) -> None:
    with _LOCK:
        record = _SESSIONS.get(pairing_id)
        if not record or record.status in TERMINAL_STATUSES:
            return
        record.status = "installing"
    try:
        proc = _spawn_pairing_process(session_path, mode)
    except Exception as exc:
        with _LOCK:
            record = _SESSIONS.get(pairing_id)
            if record and record.status not in TERMINAL_STATUSES:
                record.status = "error"
                record.error = str(exc)
        return
    with _LOCK:
        record = _SESSIONS.get(pairing_id)
        if not record or record.status in TERMINAL_STATUSES:
            _terminate(proc)
            return
        record.proc = proc
        record.status = "starting"
    _watch(pairing_id, proc)


def _prune() -> None:
    now = time.time()
    remove_ids: list[str] = []
    for pairing_id, record in _SESSIONS.items():
        if (
            record.proc is not None
            and record.status not in TERMINAL_STATUSES
            and record.proc.poll() is not None
        ):
            record.status = "error"
            record.error = "WhatsApp pairing process exited before pairing completed."
        if record.expires_at_ts <= now and record.status not in TERMINAL_STATUSES:
            _terminate(record.proc)
            record.status = "expired"
            record.error = "WhatsApp QR setup expired. Start a new setup."
        if record.status in TERMINAL_STATUSES and record.expires_at_ts + 300 <= now:
            remove_ids.append(pairing_id)
    for pairing_id in remove_ids:
        _SESSIONS.pop(pairing_id, None)


def _supersede(session_path: Path) -> None:
    for existing in _SESSIONS.values():
        if existing.session_path == str(session_path) and existing.status not in TERMINAL_STATUSES:
            existing.status = "cancelled"
            existing.error = "Superseded by a newer WhatsApp setup session."
            _terminate(existing.proc)


def session_payload(record: WhatsAppPairingSession) -> Dict[str, Any]:
    return {
        "pairing_id": record.pairing_id,
        "status": record.status,
        "qr_payload": record.qr_payload,
        "expires_at": record.expires_at,
        "mode": record.mode,
        "account_id": record.account_id,
        "account_name": record.account_name,
        "account_phone": record.account_phone,
        "error": record.error,
        "kind": "whatsapp_link_device",
    }


def get_pairing(pairing_id: str) -> Optional[Dict[str, Any]]:
    with _LOCK:
        _prune()
        record = _SESSIONS.get(str(pairing_id or "").strip())
        if not record:
            return None
        return session_payload(record)


def start_pairing(
    *,
    mode: str = "bot",
    pairing_id: Optional[str] = None,
    force: bool = False,
    reset_session: bool = False,
) -> Dict[str, Any]:
    """Start (or short-circuit) link-device pairing. Returns status payload.

    ``force=True`` skips the live-bridge short-circuit so a pair process can
    run even when /health is down (e.g. after pair-only exited).

    ``reset_session=True`` wipes Baileys files first — only for logged-out /
    corrupt sessions. Do **not** reset after a successful phone scan or
    ``done``; that deletes the fresh link and forces another QR.
    """
    mode_n = str(mode or "bot").strip().lower()
    if mode_n not in {"bot", "self-chat"}:
        mode_n = "bot"
    session_path = whatsapp_session_path()
    expires_at_ts = time.time() + TTL_SECONDS
    expires_at = _utc_iso_from_ts(expires_at_ts)
    pid = str(pairing_id or secrets.token_urlsafe(16))

    # Already linked + bridge live → nothing to do.
    if (not force) and (not reset_session) and is_whatsapp_linked(session_path) and is_whatsapp_live():
        account_id, account_name, account_phone = linked_account_from_session(session_path)
        record = WhatsAppPairingSession(
            pairing_id=pid,
            session_path=str(session_path),
            mode=mode_n,
            status="connected",
            expires_at=expires_at,
            expires_at_ts=expires_at_ts,
            account_id=account_id,
            account_name=account_name,
            account_phone=account_phone,
        )
        with _LOCK:
            _prune()
            _supersede(session_path)
            _SESSIONS[pid] = record
        return session_payload(record)

    # Linked on disk (phone already finished Link-a-device) even if the long-lived
    # HTTP bridge is down — treat as connected so "done" / next turn continue.
    if (not reset_session) and is_whatsapp_linked(session_path):
        account_id, account_name, account_phone = linked_account_from_session(session_path)
        record = WhatsAppPairingSession(
            pairing_id=pid,
            session_path=str(session_path),
            mode=mode_n,
            status="connected",
            expires_at=expires_at,
            expires_at_ts=expires_at_ts,
            account_id=account_id,
            account_name=account_name,
            account_phone=account_phone,
        )
        with _LOCK:
            _prune()
            _supersede(session_path)
            _SESSIONS[pid] = record
        return session_payload(record)

    if reset_session:
        with _LOCK:
            _supersede(session_path)
        clear_whatsapp_session(session_path)

    record = WhatsAppPairingSession(
        pairing_id=pid,
        session_path=str(session_path),
        mode=mode_n,
        status="starting",
        expires_at=expires_at,
        expires_at_ts=expires_at_ts,
    )
    with _LOCK:
        _prune()
        _supersede(session_path)
        _SESSIONS[pid] = record

    threading.Thread(
        target=_run_pairing,
        args=(pid, session_path, mode_n),
        daemon=True,
    ).start()
    return session_payload(record)


def wait_for_qr_or_terminal(
    pairing_id: str,
    *,
    timeout_s: float = 12.0,
    poll_s: float = 0.25,
) -> Dict[str, Any]:
    """Block briefly until QR appears, connected, or error/timeout."""
    deadline = time.time() + max(0.5, float(timeout_s))
    last: Dict[str, Any] = {}
    while time.time() < deadline:
        last = get_pairing(pairing_id) or {}
        if not last:
            return {"status": "error", "error": "pairing_session_missing", "pairing_id": pairing_id}
        status = str(last.get("status") or "")
        if last.get("qr_payload") or status in TERMINAL_STATUSES:
            return last
        time.sleep(poll_s)
    return last or {"status": "starting", "pairing_id": pairing_id}


def reset_pairing_sessions_for_tests() -> None:
    with _LOCK:
        for record in list(_SESSIONS.values()):
            _terminate(record.proc)
        _SESSIONS.clear()
