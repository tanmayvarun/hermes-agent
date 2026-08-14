"""Stable HermesErrorCode catalog + user-message resolution (ChargePe-shaped).

Flow (mirrors ChargePe ErrorCode → ChargepeException → GenericError):

    raise / return with HermesErrorCode
      → resolve_user_message(code, override=...)
      → client payload {error_code, message, retryable?, context?}

``override`` wins when non-blank (ASK / setup body / executor detail);
otherwise the catalog default message is used.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Tuple

from plugin.agent.runtime.task_facts import (
    ERROR_AUTH_REQUIRED,
    ERROR_EXECUTION_FAILED,
    ERROR_INTERRUPTED,
    ERROR_PROVIDER_UNAVAILABLE,
    ERROR_SETUP_BLOCKED,
    ERROR_TIMEOUT,
    ERROR_UNKNOWN,
    HERMES_ERROR_CODES,
    STATUS_FAILED,
    STATUS_INTERRUPTED,
    STATUS_WAITING_FOR_USER,
)


@dataclass(frozen=True)
class HermesErrorCode:
    """Closed client-boundary error: stable code + default user-facing copy."""

    code: str
    default_message: str
    retryable: bool = False

    def to_payload(
        self,
        *,
        override: str = "",
        context: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "error_code": self.code,
            "message": resolve_user_message(self.code, override=override),
            "retryable": bool(self.retryable),
        }
        if context:
            out["context"] = dict(context)
        return out


SETUP_BLOCKED = HermesErrorCode(
    ERROR_SETUP_BLOCKED,
    "Finish app setup on this device, then reply when you're ready.",
    retryable=False,
)
AUTH_REQUIRED = HermesErrorCode(
    ERROR_AUTH_REQUIRED,
    "Link or sign in so I can continue with the preferred method.",
    retryable=False,
)
PROVIDER_UNAVAILABLE = HermesErrorCode(
    ERROR_PROVIDER_UNAVAILABLE,
    "That service isn't available right now. Trying another approach if possible.",
    retryable=True,
)
TIMEOUT = HermesErrorCode(
    ERROR_TIMEOUT,
    "This step took too long and was stopped.",
    retryable=True,
)
INTERRUPTED = HermesErrorCode(
    ERROR_INTERRUPTED,
    "Stopped before finishing.",
    retryable=False,
)
EXECUTION_FAILED = HermesErrorCode(
    ERROR_EXECUTION_FAILED,
    "Something went wrong while carrying out that step.",
    retryable=True,
)
UNKNOWN = HermesErrorCode(
    ERROR_UNKNOWN,
    "Something went wrong.",
    retryable=False,
)

_CATALOG: Tuple[HermesErrorCode, ...] = (
    SETUP_BLOCKED,
    AUTH_REQUIRED,
    PROVIDER_UNAVAILABLE,
    TIMEOUT,
    INTERRUPTED,
    EXECUTION_FAILED,
    UNKNOWN,
)

_BY_CODE: Dict[str, HermesErrorCode] = {e.code: e for e in _CATALOG}


def lookup_error_code(code: str) -> HermesErrorCode:
    key = str(code or "").strip().lower()
    return _BY_CODE.get(key, UNKNOWN)


def resolve_user_message(code: str | None, *, override: str = "") -> str:
    """ChargePe mapper rule: non-blank override wins; else catalog default."""
    custom = str(override or "").strip()
    if custom:
        return custom
    return lookup_error_code(str(code or "")).default_message


def error_code_defaults() -> Dict[str, str]:
    return {e.code: e.default_message for e in _CATALOG}


def infer_error_code(
    *,
    final_status: str = "",
    explicit_code: str = "",
    ui_hints: Optional[Mapping[str, Any]] = None,
    payload: Optional[Mapping[str, Any]] = None,
) -> str:
    """Pick a stable code for settle / message.complete (empty when success)."""
    explicit = str(explicit_code or "").strip().lower()
    if explicit in _BY_CODE:
        return explicit

    hints = dict(ui_hints or {})
    bag = dict(payload or {})
    for src in (hints, bag):
        c = str(src.get("error_code") or "").strip().lower()
        if c in _BY_CODE:
            return c
        kind = str(src.get("kind") or "").strip().lower()
        if kind == "user_setup_blocker" or src.get("blocker") or src.get("setup_blocker"):
            return ERROR_SETUP_BLOCKED
        ask_pre = str(
            src.get("ask_precondition") or src.get("missing_precondition") or ""
        ).strip()
        if ask_pre == "whatsapp_linked":
            return ERROR_AUTH_REQUIRED
        if ask_pre == "desktop_app_ready":
            return ERROR_SETUP_BLOCKED
        fallback = str(src.get("fallback") or "").strip()
        if fallback == "ask_prerequisite" and ask_pre:
            return ERROR_AUTH_REQUIRED if "link" in ask_pre or "auth" in ask_pre else ERROR_SETUP_BLOCKED

    status = str(final_status or "").strip().lower()
    if status == STATUS_WAITING_FOR_USER:
        # Waiting is not always an error — only stamp a code when we know why.
        if hints.get("kind") == "user_setup_blocker" or hints.get("blocker"):
            return ERROR_SETUP_BLOCKED
        ask_pre = str(
            hints.get("ask_precondition")
            or bag.get("missing_precondition")
            or bag.get("ask_precondition")
            or ""
        ).strip()
        if ask_pre == "whatsapp_linked":
            return ERROR_AUTH_REQUIRED
        if ask_pre == "desktop_app_ready":
            return ERROR_SETUP_BLOCKED
        if ask_pre:
            return ERROR_AUTH_REQUIRED
        return ""
    if status == STATUS_INTERRUPTED:
        return ERROR_INTERRUPTED
    if status == STATUS_FAILED:
        return ERROR_EXECUTION_FAILED
    return ""


def client_error_payload(
    code: str | None,
    *,
    override: str = "",
    context: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """GenericError-shaped bag for gateway / UI."""
    if not str(code or "").strip():
        return {}
    return lookup_error_code(str(code)).to_payload(override=override, context=context)


def vocab_error_schema() -> Dict[str, Any]:
    return {
        "error_codes": list(HERMES_ERROR_CODES),
        "error_code_messages": error_code_defaults(),
    }
