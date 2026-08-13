"""Thin AgentRuntime — domain-generic turn orchestration.

Owns RuntimeState + MemorySystem one-way. Orchestrates:

    TaskRequest → interpretation → capability/method discovery
    → MethodFrontier (quality ⊥ availability) → executive decision

No WhatsApp / forward_message branches. Domain catalogs register via
``method_providers``. ASK is resumable ``WAITING_FOR_USER``, not a sync UI call.

Construction has no MemorySystem side effects.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

from plugin.agent.executive.method_availability import (
    MethodAvailability,
    evaluate_method_availability,
    method_quality_score,
    should_ask_for_precondition,
)
from plugin.agent.executive.method_providers import (
    discover_methods,
    interpret_task_request,
)
from plugin.agent.ingress import SessionRef, TaskRequest, TaskIngress
from plugin.agent.memory.system import MemorySystem, NoopMemorySystem
from plugin.agent.runtime.session_store import (
    SuspendedAsk,
    get_or_create_session,
)
from plugin.agent.runtime.state import RuntimeState
from plugin.agent.runtime.turn_result import RuntimeTurnResult, TurnStatus


ConversationRunner = Callable[..., Any]


@dataclass
class AgentRuntime:
    """HermesRuntime façade for the common ingress seam."""

    runtime_state: RuntimeState
    memory: MemorySystem = field(default_factory=NoopMemorySystem)
    task_request: Optional[TaskRequest] = None
    session: Optional[SessionRef] = None
    precondition_facts: Dict[str, bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.runtime_state is None:
            raise TypeError("AgentRuntime requires runtime_state")
        if self.memory is None:
            self.memory = NoopMemorySystem()
        if self.session is None and self.task_request is not None:
            self.session = self.task_request.session
        # Construction must not touch MemorySystem (no retrieve/submit/invalidate).

    def handle_turn(
        self,
        request: TaskRequest,
        *,
        conversation_runner: Optional[ConversationRunner] = None,
        run_message: Any = None,
        conversation_kwargs: Optional[Dict[str, Any]] = None,
    ) -> RuntimeTurnResult:
        """Process one TaskRequest. Domain-generic; may legacy-delegate conversation."""
        req = TaskIngress.normalize(request)
        self.task_request = req
        if req.session is not None:
            self.session = req.session
        sid = self.session.session_id if self.session else "anonymous"
        session_state = get_or_create_session(sid)
        task_request_id = uuid.uuid4().hex[:12]
        intention_id = session_state.active_intention_id or uuid.uuid4().hex[:12]
        session_state.active_intention_id = intention_id

        # Resume suspended ASK before re-interpreting as a new goal.
        if session_state.suspended_ask is not None:
            return self._resume_ask(
                req,
                session_state=session_state,
                task_request_id=task_request_id,
                conversation_runner=conversation_runner,
                run_message=run_message,
                conversation_kwargs=conversation_kwargs,
            )

        interpretation = interpret_task_request(req)
        specs = discover_methods(interpretation, constraints=req.constraints)
        evaluated: list[dict[str, Any]] = []
        for spec in specs:
            avail, reason = evaluate_method_availability(
                spec,
                constraints=req.constraints,
                precondition_facts=self.precondition_facts,
                declined_method_ids=session_state.declined_method_ids,
                declined_preconditions=session_state.declined_preconditions,
            )
            evaluated.append(
                {
                    "id": spec.id,
                    "substrate": getattr(spec, "substrate", ""),
                    "provider": getattr(spec, "provider", ""),
                    "readiness": getattr(spec, "readiness", ""),
                    "quality": method_quality_score(spec),
                    "availability": avail,
                    "reason": reason,
                    "spec": spec,
                }
            )
        evaluated.sort(key=lambda e: float(e["quality"]), reverse=True)

        available = [
            e for e in evaluated if e["availability"] == MethodAvailability.AVAILABLE.value
        ]
        best_available_q = (
            float(available[0]["quality"]) if available else None
        )
        preferred = evaluated[0] if evaluated else None

        trace: Dict[str, Any] = {
            "client": (req.client_context or {}).get("client"),
            "task_request_id": task_request_id,
            "session_id": sid,
            "runtime_id": session_state.runtime_id,
            "intention_id": intention_id,
            "goal_interpretation": {
                "goal_kind": interpretation.goal_kind,
                "desired_effects": list(interpretation.desired_effects),
            },
            "candidate_methods": [
                {
                    "id": e["id"],
                    "substrate": e["substrate"],
                    "quality": e["quality"],
                    "availability": e["availability"],
                    "readiness": e["readiness"],
                    "reason": e["reason"],
                }
                for e in evaluated
            ],
            "constraints": {
                "allowed_substrates": list(req.constraints.allowed_substrates or ()),
                "forced_substrate": req.constraints.forced_substrate,
            },
        }

        if preferred is not None and should_ask_for_precondition(
            preferred_spec=preferred["spec"],
            preferred_availability=str(preferred["availability"]),
            best_available_quality=best_available_q,
        ):
            missing = str(preferred["reason"] or "")
            pre = missing.split("missing:", 1)[-1].split(",")[0] if "missing:" in missing else ""
            question = (
                f"A better method ({preferred['id']}) needs prerequisite "
                f"'{pre or 'access'}'. Allow me to establish it so I can proceed "
                f"without a more disruptive approach?"
            )
            session_state.suspended_ask = SuspendedAsk(
                intention_id=intention_id,
                method_id=str(preferred["id"]),
                precondition=pre,
                question=question,
                parent_effect=",".join(interpretation.desired_effects),
            )
            trace["method_availability"] = preferred["availability"]
            trace["missing_precondition"] = pre
            trace["ASK"] = question
            trace["original_user_turn"] = req.user_turn
            session_state.last_trace = trace
            return RuntimeTurnResult(
                status=TurnStatus.WAITING_FOR_USER,
                question=question,
                message=question,
                intention_id=intention_id,
                task_request_id=task_request_id,
                session_id=sid,
                runtime_id=session_state.runtime_id,
                acceptance_trace=trace,
                interpretation=interpretation,
            )

        selected = available[0] if available else None
        if selected is not None:
            trace["selected_method"] = selected["id"]
            trace["selected_substrate"] = selected["substrate"]
            session_state.last_trace = trace
            # Domain-generic: substrate execution engines plug in later.
            # Stage A: legacy conversation remains the default product path;
            # selected method is recorded for acceptance traces / frontier tests.
            if conversation_runner is not None:
                legacy = self._delegate_conversation(
                    interpretation=interpretation,
                    conversation_runner=conversation_runner,
                    run_message=run_message if run_message is not None else req.user_turn,
                    conversation_kwargs=conversation_kwargs,
                )
                return RuntimeTurnResult(
                    status=TurnStatus.LEGACY_DELEGATED,
                    message=_legacy_message(legacy),
                    intention_id=intention_id,
                    selected_method=str(selected["id"]),
                    selected_substrate=str(selected["substrate"]),
                    task_request_id=task_request_id,
                    session_id=sid,
                    runtime_id=session_state.runtime_id,
                    acceptance_trace=trace,
                    legacy_result=legacy,
                    interpretation=interpretation,
                )
            return RuntimeTurnResult(
                status=TurnStatus.COMPLETED,
                intention_id=intention_id,
                selected_method=str(selected["id"]),
                selected_substrate=str(selected["substrate"]),
                task_request_id=task_request_id,
                session_id=sid,
                runtime_id=session_state.runtime_id,
                acceptance_trace=trace,
                interpretation=interpretation,
            )

        # No executable method catalog — migration: legacy conversational engine.
        session_state.last_trace = trace
        if conversation_runner is not None:
            legacy = self._delegate_conversation(
                interpretation=interpretation,
                conversation_runner=conversation_runner,
                run_message=run_message if run_message is not None else req.user_turn,
                conversation_kwargs=conversation_kwargs,
            )
            return RuntimeTurnResult(
                status=TurnStatus.LEGACY_DELEGATED,
                message=_legacy_message(legacy),
                intention_id=intention_id,
                task_request_id=task_request_id,
                session_id=sid,
                runtime_id=session_state.runtime_id,
                acceptance_trace=trace,
                legacy_result=legacy,
                interpretation=interpretation,
            )
        return RuntimeTurnResult(
            status=TurnStatus.COMPLETED,
            message="",
            intention_id=intention_id,
            task_request_id=task_request_id,
            session_id=sid,
            runtime_id=session_state.runtime_id,
            acceptance_trace=trace,
            interpretation=interpretation,
        )

    def _resume_ask(
        self,
        req: TaskRequest,
        *,
        session_state: Any,
        task_request_id: str,
        conversation_runner: Optional[ConversationRunner],
        run_message: Any,
        conversation_kwargs: Optional[Dict[str, Any]],
    ) -> RuntimeTurnResult:
        ask: SuspendedAsk = session_state.suspended_ask
        intention_id = ask.intention_id
        answer = _classify_ask_response(req.user_turn)
        trace = dict(session_state.last_trace or {})
        trace["task_request_id"] = task_request_id
        trace["user_response"] = answer
        trace["intention_id"] = intention_id

        orig = str((session_state.last_trace or {}).get("original_user_turn") or "")

        if answer == "decline":
            session_state.declined_method_ids.add(ask.method_id)
            if ask.precondition:
                session_state.declined_preconditions.add(ask.precondition)
            session_state.suspended_ask = None
            # Re-enter selection with same parent intention (not a new goal restart).
            resumed = TaskRequest(
                user_turn=str(orig or req.user_turn),
                attachments=list(req.attachments or []),
                session=req.session,
                client_context=dict(req.client_context or {}),
                constraints=req.constraints,
                interaction_capabilities=dict(req.interaction_capabilities or {}),
                legacy_goal=req.legacy_goal,
            )
            session_state.active_intention_id = intention_id
            result = self.handle_turn(
                resumed,
                conversation_runner=conversation_runner,
                run_message=run_message if run_message is not None else resumed.user_turn,
                conversation_kwargs=conversation_kwargs,
            )
            result.status = TurnStatus.CONTINUED
            result.intention_id = intention_id
            result.acceptance_trace = {
                **(result.acceptance_trace or {}),
                "resumed_after": "user_declined",
                "declined_method": ask.method_id,
            }
            return result

        if answer == "accept":
            if ask.precondition:
                self.precondition_facts[ask.precondition] = True
            session_state.suspended_ask = None
            session_state.active_intention_id = intention_id
            resumed = TaskRequest(
                user_turn=str(orig or req.user_turn),
                attachments=list(req.attachments or []),
                session=req.session,
                client_context=dict(req.client_context or {}),
                constraints=req.constraints,
                interaction_capabilities=dict(req.interaction_capabilities or {}),
                legacy_goal=req.legacy_goal,
            )
            result = self.handle_turn(
                resumed,
                conversation_runner=conversation_runner,
                run_message=run_message if run_message is not None else resumed.user_turn,
                conversation_kwargs=conversation_kwargs,
            )
            result.status = TurnStatus.CONTINUED
            result.intention_id = intention_id
            result.acceptance_trace = {
                **(result.acceptance_trace or {}),
                "resumed_after": "user_accepted_prerequisite",
                "method": ask.method_id,
            }
            return result

        # Unclear — re-ask same suspended intention.
        return RuntimeTurnResult(
            status=TurnStatus.WAITING_FOR_USER,
            question=ask.question,
            message=ask.question,
            intention_id=intention_id,
            task_request_id=task_request_id,
            session_id=session_state.session_id,
            runtime_id=session_state.runtime_id,
            acceptance_trace=trace,
        )

    def _delegate_conversation(
        self,
        *,
        interpretation: Any,
        conversation_runner: ConversationRunner,
        run_message: Any,
        conversation_kwargs: Optional[Dict[str, Any]],
    ) -> Any:
        kwargs = dict(conversation_kwargs or {})
        # Move structured goal context ownership into runtime (not gateway classify).
        goal = getattr(interpretation, "goal", None)
        if goal is not None and str(getattr(goal, "kind", "") or "") != "unknown":
            try:
                block = goal.execution_context_block()
                if block and "system_message" not in kwargs:
                    kwargs["system_message"] = block
            except Exception:
                pass
        return conversation_runner(run_message, **kwargs)


def _legacy_message(legacy: Any) -> str:
    if legacy is None:
        return ""
    if isinstance(legacy, dict):
        return str(legacy.get("final_response") or legacy.get("response") or "")
    return str(getattr(legacy, "final_response", "") or getattr(legacy, "response", "") or "")


def _classify_ask_response(text: str) -> str:
    t = str(text or "").strip().lower()
    if not t:
        return "unclear"
    decline = {
        "no",
        "n",
        "nope",
        "decline",
        "don't",
        "dont",
        "not now",
        "never",
        "skip",
    }
    accept = {"yes", "y", "ok", "okay", "sure", "allow", "link", "accept", "please"}
    if t in decline or t.startswith("no ") or "don't" in t or "do not" in t:
        return "decline"
    if t in accept or t.startswith("yes"):
        return "accept"
    return "unclear"
