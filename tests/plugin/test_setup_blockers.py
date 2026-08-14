"""Setup-blocker detection + WAITING_FOR_USER ui_hints for CU walls."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Optional

from plugin.agent.executive.setup_blockers import (
    DESKTOP_APP_READY_PRECONDITION,
    USER_SETUP_BLOCKER_KIND,
    detect_setup_blocker,
)
from plugin.agent.ingress import SessionRef, TaskRequest
from plugin.agent.runtime.agent_runtime import AgentRuntime
from plugin.agent.runtime.method_executors import (
    MethodExecutionResult,
    register_method_executor,
)
from plugin.agent.runtime.prerequisite_resolver import (
    clear_prerequisite_resolvers,
    register_prerequisite_resolver,
)
from plugin.agent.runtime.session_store import reset_session_store
from plugin.agent.runtime.state import RuntimeState
from plugin.agent.runtime.turn_result import TurnStatus
from plugin.agent.executive.intention_frame import MethodSpec
from plugin.agent.executive.method_availability import MethodReadiness
from plugin.agent.executive.method_providers import (
    clear_method_providers,
    register_method_provider,
)
from plugin.agent.runtime.method_executors import clear_method_executors
from plugin.agent.composition import reset_composition_for_tests


def test_detect_whatsapp_welcome() -> None:
    blocker = detect_setup_blocker(
        app="WhatsApp",
        observation_texts=[
            "Welcome to WhatsApp",
            "Message privately with friends and family using WhatsApp.",
            "Continue",
        ],
    )
    assert blocker is not None
    assert blocker.id == "whatsapp_welcome"
    assert "Welcome" in blocker.title or "isn’t set up" in blocker.title
    assert blocker.ui_hints["kind"] == USER_SETUP_BLOCKER_KIND
    assert "done" in blocker.question.lower()


def test_detect_whatsapp_link_device_desktop() -> None:
    blocker = detect_setup_blocker(
        app="WhatsApp",
        observation_texts=[
            "Link a device",
            "Use WhatsApp on your computer",
            "Scan the QR code",
        ],
    )
    assert blocker is not None
    assert blocker.id == "whatsapp_link_device_desktop"
    assert "link" in blocker.body.lower()


def test_chat_list_not_blocked() -> None:
    blocker = detect_setup_blocker(
        app="WhatsApp",
        observation_texts=["Chats", "Search", "Archived", "Pallavi", "Tanmay"],
    )
    assert blocker is None


class _CatalogProvider:
    provider_id = "test_catalog"

    def __init__(self, specs):
        self.specs = list(specs)

    def discover(self, interpretation, *, constraints: Optional[Any] = None):
        return list(self.specs)


def test_executor_ask_prerequisite_preserves_ui_hints() -> None:
    clear_method_providers()
    clear_method_executors()
    clear_prerequisite_resolvers()
    reset_session_store()
    reset_composition_for_tests()

    class _BlockedCU:
        executor_id = "computer_use_closed_loop"
        substrates = ("computer_use",)

        def execute(self, spec, *, context):
            return MethodExecutionResult(
                ok=False,
                status="failed",
                detail="setup wall",
                payload={
                    "fallback": "ask_prerequisite",
                    "ask_precondition": DESKTOP_APP_READY_PRECONDITION,
                    "ask_question": (
                        "WhatsApp on this Mac isn’t ready — it’s showing Link a device. "
                        "Reply **done** when ready."
                    ),
                    "ui_hints": {
                        "kind": USER_SETUP_BLOCKER_KIND,
                        "blocker": "whatsapp_link_device_desktop",
                        "app": "WhatsApp",
                        "title": "WhatsApp needs to be linked on this Mac",
                        "body": "Finish linking in the WhatsApp desktop app",
                        "cta": "Reply **done** when ready",
                    },
                },
                executor_id=self.executor_id,
            )

    register_method_provider(
        _CatalogProvider(
            [
                MethodSpec(
                    id="native_computer_use_forward",
                    capability="forward_message",
                    substrate="computer_use",
                    provider="test",
                    preconditions=[],
                    readiness=MethodReadiness.READY.value,
                    reliability=0.9,
                )
            ]
        )
    )
    register_method_executor(_BlockedCU())
    # Minimal resolver so resume path exists; not exercised here.
    from plugin.agent.runtime.desktop_app_ready import DesktopAppReadyPrerequisiteResolver

    register_prerequisite_resolver(DesktopAppReadyPrerequisiteResolver())

    result = AgentRuntime(runtime_state=RuntimeState()).handle_turn(
        TaskRequest(
            user_turn="send hi to pallavi on whatsapp",
            session=SessionRef("setup-blocker-ask"),
        )
    )
    assert result.status == TurnStatus.WAITING_FOR_USER
    assert "WhatsApp" in (result.question or result.message or "")
    assert (result.ui_hints or {}).get("kind") == USER_SETUP_BLOCKER_KIND
    assert (result.ui_hints or {}).get("blocker") == "whatsapp_link_device_desktop"
    assert result.acceptance_trace.get("executor_recover_ask") is True
