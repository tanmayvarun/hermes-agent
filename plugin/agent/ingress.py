"""Common TaskIngress seam — normalize TaskRequest into AgentRuntime.

Canonical direction:

    raw user request → TaskRequest → TaskIngress.normalize → AgentRuntime

``from_legacy_goal`` is an explicit compatibility adapter for callers that
already hold a parsed ``Goal`` (e.g. live harness → ``run_goal_closed_loop``).
It is **not** the target ingress source of truth.

TaskIngress has no cognition and never retrieves / writes memory.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence


@dataclass(frozen=True)
class SessionRef:
    """Runtime-owned session handle. TaskRequest holds a ref; it does not own lifecycle."""

    session_id: str


@dataclass(frozen=True)
class ExecutionConstraints:
    """Constraints that may affect executive / method choice — not presentation config.

    ``allowed_substrates`` / ``forced_substrate`` are the architectural way to
    force ComputerUse (or other) for benchmarks — not a harness-specific branch.
    Empty ``allowed_substrates`` means no substrate filter.
    """

    foreground_allowed: bool = True
    network_allowed: bool = True
    destructive_actions_allowed: bool = False
    approval_policy: str = "default"
    allowed_substrates: tuple[str, ...] = ()
    forced_substrate: str = ""


@dataclass
class TaskRequest:
    """Client-neutral task ingress shape.

    Goal is intentionally not required. Legacy adapters may attach an already-parsed
    Goal via ``legacy_goal`` without making Goal the canonical TaskRequest field.
    """

    user_turn: str = ""
    attachments: list[Any] = field(default_factory=list)
    session: Optional[SessionRef] = None
    client_context: dict[str, Any] = field(default_factory=dict)
    constraints: ExecutionConstraints = field(default_factory=ExecutionConstraints)
    interaction_capabilities: dict[str, Any] = field(default_factory=dict)
    # Explicit legacy payload — not part of the long-term TaskRequest contract.
    legacy_goal: Any = None


class TaskIngress:
    """Normalize TaskRequest; attach session/memory handles only — no cognition."""

    @staticmethod
    def normalize(request: TaskRequest) -> TaskRequest:
        """Canonical ingress operation.

        Pass-through normalize: trim user_turn, shallow-copy presentation maps so
        callers cannot mutate the normalized request in place via shared dicts.
        Does not consult MemorySystem.
        """
        if request is None:
            raise TypeError("TaskRequest is required")
        client_context = dict(request.client_context or {})
        interaction_capabilities = dict(request.interaction_capabilities or {})
        attachments = list(request.attachments or [])
        user_turn = str(request.user_turn or "").strip()
        constraints = request.constraints or ExecutionConstraints()
        return TaskRequest(
            user_turn=user_turn,
            attachments=attachments,
            session=request.session,
            client_context=client_context,
            constraints=constraints,
            interaction_capabilities=interaction_capabilities,
            legacy_goal=request.legacy_goal,
        )

    @staticmethod
    def from_legacy_goal(
        goal: Any,
        *,
        session: Optional[SessionRef] = None,
        client_context: Optional[Mapping[str, Any]] = None,
        constraints: Optional[ExecutionConstraints] = None,
        interaction_capabilities: Optional[Mapping[str, Any]] = None,
        attachments: Optional[Sequence[Any]] = None,
    ) -> TaskRequest:
        """Compatibility constructor for callers that already hold a parsed Goal.

        Temporary migration adapter — not the target ingress direction.
        """
        prompt = ""
        try:
            prompt = str(getattr(goal, "prompt", "") or "").strip()
        except Exception:
            prompt = ""
        if not prompt:
            try:
                kind = str(getattr(goal, "kind", "") or "").strip()
                contact = str(getattr(goal, "contact", "") or "").strip()
                prompt = " ".join(p for p in (kind, contact) if p).strip()
            except Exception:
                prompt = ""
        return TaskRequest(
            user_turn=prompt,
            attachments=list(attachments or []),
            session=session,
            client_context=dict(client_context or {}),
            constraints=constraints or ExecutionConstraints(),
            interaction_capabilities=dict(interaction_capabilities or {}),
            legacy_goal=goal,
        )


def semantic_task_fingerprint(request: TaskRequest) -> dict[str, Any]:
    """Client-neutral semantic core of a TaskRequest (excludes presentation labels)."""
    ctx = dict(request.client_context or {})
    # Presentation-only keys that must not affect task semantics.
    for key in ("client", "supports_rich_ui", "supports_streaming", "ui_theme"):
        ctx.pop(key, None)
    constraints = request.constraints or ExecutionConstraints()
    return {
        "user_turn": str(request.user_turn or ""),
        "attachments": list(request.attachments or []),
        "session_id": request.session.session_id if request.session else None,
        "constraints": {
            "foreground_allowed": bool(constraints.foreground_allowed),
            "network_allowed": bool(constraints.network_allowed),
            "destructive_actions_allowed": bool(constraints.destructive_actions_allowed),
            "approval_policy": str(constraints.approval_policy or "default"),
            "allowed_substrates": list(constraints.allowed_substrates or ()),
            "forced_substrate": str(constraints.forced_substrate or ""),
        },
        "interaction_capabilities": dict(request.interaction_capabilities or {}),
        "client_context_semantic": ctx,
        "has_legacy_goal": request.legacy_goal is not None,
    }
