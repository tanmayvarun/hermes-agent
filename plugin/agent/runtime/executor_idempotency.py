"""Idempotency guard for side-effecting method executors.

Same ``task_request_id`` + effect key → reuse prior success (or in-flight skip),
so retries / nested resumes do not double-send WhatsApp or re-fire CU acts.
"""

from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from plugin.agent.runtime.method_executors import MethodExecutionResult


@dataclass(frozen=True)
class IdempotencyKey:
    task_request_id: str
    effect: str
    fingerprint: str

    def as_str(self) -> str:
        return f"{self.task_request_id}|{self.effect}|{self.fingerprint}"


def make_effect_key(
    *,
    task_request_id: str,
    effect: str,
    parts: Tuple[Any, ...] = (),
) -> IdempotencyKey:
    tid = str(task_request_id or "").strip() or "_"
    eff = str(effect or "").strip() or "effect"
    raw = "|".join(str(p) for p in parts)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return IdempotencyKey(task_request_id=tid, effect=eff, fingerprint=digest)


class ExecutorIdempotencyGuard:
    """Process-local success memo for mutating executors."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._done: Dict[str, MethodExecutionResult] = {}

    def lookup(self, key: IdempotencyKey) -> Optional[MethodExecutionResult]:
        with self._lock:
            prior = self._done.get(key.as_str())
            if prior is None:
                return None
            # Return a shallow copy so callers cannot mutate the memo.
            return MethodExecutionResult(
                ok=prior.ok,
                status=prior.status,
                detail=prior.detail,
                payload=dict(prior.payload) if isinstance(prior.payload, dict) else prior.payload,
                executor_id=prior.executor_id,
            )

    def remember_success(self, key: IdempotencyKey, result: MethodExecutionResult) -> None:
        if not result.ok:
            return
        with self._lock:
            payload = dict(result.payload) if isinstance(result.payload, dict) else result.payload
            if isinstance(payload, dict):
                payload = {**payload, "idempotent_replay": False, "idempotency_key": key.as_str()}
            self._done[key.as_str()] = MethodExecutionResult(
                ok=True,
                status=result.status,
                detail=result.detail,
                payload=payload,
                executor_id=result.executor_id,
            )

    def mark_replay(self, result: MethodExecutionResult) -> MethodExecutionResult:
        payload = dict(result.payload) if isinstance(result.payload, dict) else {}
        if not isinstance(payload, dict):
            payload = {"prior": payload}
        payload["idempotent_replay"] = True
        return MethodExecutionResult(
            ok=result.ok,
            status=result.status or "idempotent_replay",
            detail=result.detail or "Reused prior successful effect for this task_request_id.",
            payload=payload,
            executor_id=result.executor_id,
        )

    def clear(self) -> None:
        with self._lock:
            self._done.clear()


_GLOBAL = ExecutorIdempotencyGuard()


def get_executor_idempotency_guard() -> ExecutorIdempotencyGuard:
    return _GLOBAL


def reset_executor_idempotency_for_tests() -> None:
    global _GLOBAL
    _GLOBAL = ExecutorIdempotencyGuard()
