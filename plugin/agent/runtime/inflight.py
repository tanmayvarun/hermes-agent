"""Registry of the call the agent is currently blocked inside.

The control loop reports its cost per iteration, but that report is only
written once the iteration ends. A blocking call that stalls — an auxiliary
route that burns its whole timeout budget across every fallback candidate,
say — produces no output at all while it is happening, so a run can sit
silent for minutes and the log gives no clue which call is holding it.

This module keeps a thread-safe stack of the calls currently in flight so a
watchdog can name the one that is blocking and say how long it has been
waiting, while it is still waiting.
"""

from __future__ import annotations

import contextlib
import threading
import time
from typing import Iterator, List, Optional, Tuple

_lock = threading.Lock()
# (label, started_at_monotonic), innermost last.
_stack: List[Tuple[str, float]] = []


@contextlib.contextmanager
def mark(label: str) -> Iterator[None]:
    """Record ``label`` as in flight for the duration of the block."""
    entry = (str(label or "call"), time.monotonic())
    with _lock:
        _stack.append(entry)
    try:
        yield
    finally:
        with _lock:
            # Remove this exact entry rather than popping blindly: nesting is
            # expected, but so is a caller unwinding out of order on an error
            # path, and a mismatched pop would strand a stale label forever.
            for index in range(len(_stack) - 1, -1, -1):
                if _stack[index] is entry:
                    del _stack[index]
                    break


def current() -> Optional[Tuple[str, float]]:
    """Return ``(label, seconds_in_flight)`` for the innermost active call."""
    with _lock:
        if not _stack:
            return None
        label, started_at = _stack[-1]
    return label, max(0.0, time.monotonic() - started_at)


def reset() -> None:
    """Drop all entries. For tests and for recovery after an abandoned call."""
    with _lock:
        _stack.clear()
