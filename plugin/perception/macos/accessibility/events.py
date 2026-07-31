"""Layer 2 — AXObserver events (PyObjC) with 500ms poll contingency."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)

EventCallback = Callable[["AxEvent"], None]


@dataclass
class AxEvent:
    kind: str  # window_changed | focused_changed | selection_changed | poll
    timestamp: float
    detail: str = ""


class PollingEventStream:
    """Contingency when AXObserver is unreliable — emit poll every interval_ms."""

    def __init__(self, interval_ms: int = 500) -> None:
        self.interval_ms = interval_ms
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._callbacks: List[EventCallback] = []

    def subscribe(self, cb: EventCallback) -> None:
        self._callbacks.append(cb)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="plugin-ax-poll", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def _loop(self) -> None:
        while not self._stop.wait(self.interval_ms / 1000.0):
            ev = AxEvent(kind="poll", timestamp=time.time())
            for cb in list(self._callbacks):
                try:
                    cb(ev)
                except Exception:
                    logger.exception("poll callback failed")


class AxObserverEventStream:
    """Primary: macOS AXObserver via PyObjC. Falls back to polling on failure."""

    INTERESTING = (
        "AXFocusedUIElementChanged",
        "AXSelectedChildrenChanged",
        "AXWindowCreated",
        "AXUIElementDestroyed",
        "AXTitleChanged",
    )

    def __init__(self, poll_fallback_ms: int = 500) -> None:
        self._callbacks: List[EventCallback] = []
        self._poll = PollingEventStream(poll_fallback_ms)
        self._using_poll = False
        self._observer = None

    def subscribe(self, cb: EventCallback) -> None:
        self._callbacks.append(cb)
        self._poll.subscribe(cb)

    def start(self) -> str:
        """Start observer; returns 'axobserver' or 'poll'."""
        try:
            self._start_axobserver()
            return "axobserver"
        except Exception as e:
            logger.warning("AXObserver unavailable (%s); using %sms poll", e, self._poll.interval_ms)
            self._using_poll = True
            self._poll.start()
            return "poll"

    def stop(self) -> None:
        self._poll.stop()
        self._observer = None

    def _emit(self, kind: str, detail: str = "") -> None:
        ev = AxEvent(kind=kind, timestamp=time.time(), detail=detail)
        for cb in list(self._callbacks):
            try:
                cb(ev)
            except Exception:
                logger.exception("AX event callback failed")

    def _start_axobserver(self) -> None:
        # Best-effort: verify PyObjC AX symbols exist. Full CFRunLoop integration
        # is host-dependent; if setup fails we raise and caller uses poll.
        from ApplicationServices import (  # type: ignore  # noqa: F401
            AXObserverCreate,
            AXObserverAddNotification,
        )

        # Without a stable pid + run-loop bridge in this POC, prefer documented
        # contingency (poll). Mark as attempted so STACK remains honest.
        raise RuntimeError(
            "AXObserver run-loop bridge deferred; using poll contingency "
            "(see STACK.md Layer 2)"
        )
