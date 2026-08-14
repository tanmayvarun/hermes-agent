"""Tests for HermesErrorCode catalog + user-message resolution."""

from __future__ import annotations

from plugin.agent.runtime.error_codes import (
    AUTH_REQUIRED,
    SETUP_BLOCKED,
    client_error_payload,
    infer_error_code,
    resolve_user_message,
)
from plugin.agent.runtime.task_tracker import (
    STATUS_FAILED,
    TaskTracker,
    reset_task_tracker_for_tests,
)


def test_resolve_user_message_override_wins():
    assert resolve_user_message("setup_blocked") == SETUP_BLOCKED.default_message
    assert (
        resolve_user_message("setup_blocked", override="Scan the QR on WhatsApp.")
        == "Scan the QR on WhatsApp."
    )
    assert resolve_user_message("nope") == resolve_user_message("unknown")


def test_client_error_payload_generic_error_shape():
    bag = client_error_payload(
        AUTH_REQUIRED.code,
        override="",
        context={"ask_precondition": "whatsapp_linked"},
    )
    assert bag["error_code"] == "auth_required"
    assert bag["message"] == AUTH_REQUIRED.default_message
    assert bag["retryable"] is False
    assert bag["context"]["ask_precondition"] == "whatsapp_linked"


def test_infer_error_code_from_setup_hints_and_status():
    assert (
        infer_error_code(
            final_status="waiting_for_user",
            ui_hints={"kind": "user_setup_blocker", "blocker": "welcome"},
        )
        == "setup_blocked"
    )
    assert (
        infer_error_code(
            final_status="waiting_for_user",
            payload={"missing_precondition": "whatsapp_linked"},
        )
        == "auth_required"
    )
    assert infer_error_code(final_status="waiting_for_user") == ""
    assert infer_error_code(final_status=STATUS_FAILED) == "execution_failed"


def test_tracker_complete_payload_includes_resolved_message():
    reset_task_tracker_for_tests()
    t = TaskTracker(throttle_s=0)
    t.start(task_request_id="e1", session_id="s", prompt="hi")
    t.settle(
        "e1",
        status="waiting_for_user",
        summary="Custom link copy",
        error_code="auth_required",
    )
    payload = t.complete_payload("e1")
    assert payload["error_code"] == "auth_required"
    assert payload["message"] == "Custom link copy"
