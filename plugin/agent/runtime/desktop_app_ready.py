"""Prerequisite resolver for Computer Use setup walls (desktop_app_ready)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from plugin.agent.executive.setup_blockers import (
    DESKTOP_APP_READY_PRECONDITION,
    probe_desktop_app_ready,
)
from plugin.agent.runtime.prerequisite_resolver import PrerequisiteResolveResult


class DesktopAppReadyPrerequisiteResolver:
    """Resume after user says done: re-probe; keep ASK if still blocked."""

    owned = frozenset({DESKTOP_APP_READY_PRECONDITION})

    def ask_prompt(self, precondition: str) -> Optional[str]:
        if str(precondition or "").strip() not in self.owned:
            return None
        return (
            "The target app isn’t ready for Computer Use yet. Finish setup in the "
            "app until the normal UI is available, then reply **done** so I can continue."
        )

    def resolve(
        self,
        precondition: str,
        *,
        permission_granted: bool,
        context: Optional[Dict[str, Any]] = None,
    ) -> PrerequisiteResolveResult:
        key = str(precondition or "").strip()
        if key not in self.owned:
            return PrerequisiteResolveResult(
                status="unsupported", precondition=key, detail="not_owned"
            )
        if not permission_granted:
            return PrerequisiteResolveResult(
                status="failed",
                precondition=key,
                detail="permission_not_granted",
                failure_policy="fallback_next_method",
            )

        ctx = dict(context or {})
        app = str(ctx.get("app") or ctx.get("goal_app") or "WhatsApp").strip() or "WhatsApp"
        hints = ctx.get("ui_hints") if isinstance(ctx.get("ui_hints"), dict) else {}
        if hints.get("app"):
            app = str(hints.get("app")).strip() or app

        ready, blocker = probe_desktop_app_ready(app)
        if ready:
            return PrerequisiteResolveResult(
                status="achieved",
                precondition=key,
                detail="desktop_app_ready",
                evidence={"app": app, "ready": True},
            )

        if blocker is None:
            # Probe inconclusive — trust the user and let CU re-detect.
            return PrerequisiteResolveResult(
                status="achieved",
                precondition=key,
                detail="user_confirmed_ready",
                evidence={"app": app, "ready": True, "probe": "inconclusive"},
            )

        return PrerequisiteResolveResult(
            status="pending",
            precondition=key,
            detail=blocker.id,
            user_message=blocker.question,
            failure_policy="keep_ask",
            evidence=blocker.ui_hints,
        )


def ensure_desktop_app_ready_resolver_registered() -> dict:
    from plugin.agent.runtime.prerequisite_resolver import register_prerequisite_resolver

    register_prerequisite_resolver(DesktopAppReadyPrerequisiteResolver())
    return {
        "event": "desktop_app_ready_resolver",
        "ok": True,
        "resolver_registered": True,
    }
