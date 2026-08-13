"""Thin AgentRuntime — domain-generic turn orchestration.

Owns RuntimeState + MemorySystem one-way. Orchestrates:

    TaskRequest → interpretation → method providers → MethodFrontier decision
    → ASK (resumable) | execute_method(selected) | legacy conversation

No WhatsApp / forward_message branches. Ranking authority is MethodFrontier
(``decide_methods``), not a parallel scorer inside this module.

ASK acceptance grants permission to resolve a prerequisite; it does **not**
mark the precondition achieved until a resolver verifies the effect.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

from plugin.agent.executive.method_decision import decide_methods
from plugin.agent.executive.method_providers import (
    discover_methods,
    interpret_task_request,
)
from plugin.agent.ingress import SessionRef, TaskIngress, TaskRequest
from plugin.agent.memory.system import MemorySystem, NoopMemorySystem
from plugin.agent.runtime.method_executors import execute_method
from plugin.agent.runtime.prerequisite_resolver import resolve_prerequisite
from plugin.agent.runtime.session_store import SuspendedAsk, get_or_create_session
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
        execution_context: Optional[Dict[str, Any]] = None,
    ) -> RuntimeTurnResult:
        # Composition root (providers/executors) is owned by process startup /
        # ClientAdapter — not by handle_turn — so tests can control registries.
        req = TaskIngress.normalize(request)
        self.task_request = req
        if req.session is not None:
            self.session = req.session
        sid = self.session.session_id if self.session else "anonymous"
        session_state = get_or_create_session(sid)
        task_request_id = uuid.uuid4().hex[:12]
        intention_id = session_state.active_intention_id or uuid.uuid4().hex[:12]
        session_state.active_intention_id = intention_id

        if session_state.suspended_ask is not None:
            return self._resume_ask(
                req,
                session_state=session_state,
                task_request_id=task_request_id,
                conversation_runner=conversation_runner,
                run_message=run_message,
                conversation_kwargs=conversation_kwargs,
                execution_context=execution_context,
            )

        interpretation = interpret_task_request(req)
        specs, provider_errors = discover_methods(
            interpretation, constraints=req.constraints
        )
        decision = decide_methods(
            specs,
            constraints=req.constraints,
            precondition_facts=session_state.precondition_facts,
            declined_method_ids=session_state.declined_method_ids,
            declined_preconditions=session_state.declined_preconditions,
            intention_id=intention_id,
            desired_effect=",".join(interpretation.desired_effects) or interpretation.goal_kind,
        )

        candidate_trace = []
        for mid, spec in decision.frontier.catalog.items():
            score = 0.0
            for rid, sc in decision.ranked_executable:
                if rid == mid:
                    score = float(sc)
                    break
            if score == 0.0 and mid in decision.availability_by_id:
                # Still report score for non-executable via frontier policy.
                from plugin.agent.executive.intention_frame import (
                    ScoringPolicy,
                    score_method,
                )

                score = score_method(spec, ScoringPolicy.for_meta("act"))
            candidate_trace.append(
                {
                    "id": mid,
                    "substrate": getattr(spec, "substrate", ""),
                    "provider": getattr(spec, "provider", ""),
                    "readiness": getattr(spec, "readiness", ""),
                    "quality": score,
                    "availability": decision.availability_by_id.get(mid),
                    "reason": decision.reason_by_id.get(mid),
                }
            )
        candidate_trace.sort(key=lambda e: float(e["quality"]), reverse=True)

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
            "candidate_methods": candidate_trace,
            "ranking_authority": "MethodFrontier.rank_eligible",
            "provider_errors": list(provider_errors),
            "constraints": {
                "allowed_substrates": list(req.constraints.allowed_substrates or ()),
                "forced_substrate": req.constraints.forced_substrate,
            },
        }
        session_state.original_user_turn = req.user_turn
        session_state.last_trace = trace

        if decision.should_ask and decision.ask_method_id:
            question = (
                f"A better method ({decision.ask_method_id}) needs prerequisite "
                f"'{decision.ask_precondition or 'access'}'. Allow me to establish "
                f"it so I can proceed without a more disruptive approach?"
            )
            session_state.suspended_ask = SuspendedAsk(
                intention_id=intention_id,
                method_id=decision.ask_method_id,
                precondition=decision.ask_precondition,
                question=question,
                parent_effect=",".join(interpretation.desired_effects),
            )
            trace["ASK"] = question
            trace["missing_precondition"] = decision.ask_precondition
            trace["method_availability"] = "missing_precondition"
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

        if decision.selected_method_id:
            spec = decision.frontier.catalog[decision.selected_method_id]
            exec_ctx = {
                "goal": interpretation.goal,
                "runtime_state": self.runtime_state,
                "task_request": req,
                "interpretation": interpretation,
                "memory": self.memory,
                **dict(execution_context or {}),
            }
            exec_result = execute_method(spec, context=exec_ctx)
            trace["selected_method"] = spec.id
            trace["selected_substrate"] = getattr(spec, "substrate", "")
            trace["executor_id"] = exec_result.executor_id
            trace["executor_status"] = exec_result.status
            trace["dispatched_executor"] = True
            session_state.last_trace = trace
            return RuntimeTurnResult(
                status=TurnStatus.COMPLETED if exec_result.ok else TurnStatus.FAILED,
                message=exec_result.detail,
                intention_id=intention_id,
                selected_method=str(spec.id),
                selected_substrate=str(getattr(spec, "substrate", "") or ""),
                task_request_id=task_request_id,
                session_id=sid,
                runtime_id=session_state.runtime_id,
                acceptance_trace=trace,
                legacy_result=exec_result.payload,
                interpretation=interpretation,
            )

        # No executable method — migration path: legacy conversational engine.
        if conversation_runner is not None:
            legacy = self._delegate_conversation(
                interpretation=interpretation,
                conversation_runner=conversation_runner,
                run_message=run_message if run_message is not None else req.user_turn,
                conversation_kwargs=conversation_kwargs,
            )
            trace["selected_method"] = ""
            trace["selected_substrate"] = "conversation_legacy"
            trace["dispatched_executor"] = False
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
        execution_context: Optional[Dict[str, Any]],
    ) -> RuntimeTurnResult:
        ask: SuspendedAsk = session_state.suspended_ask
        intention_id = ask.intention_id
        answer = _classify_ask_response(req.user_turn)
        trace = dict(session_state.last_trace or {})
        trace["task_request_id"] = task_request_id
        trace["user_response"] = answer
        trace["intention_id"] = intention_id
        orig = session_state.original_user_turn or req.user_turn

        if answer == "decline":
            session_state.declined_method_ids.add(ask.method_id)
            if ask.precondition:
                session_state.declined_preconditions.add(ask.precondition)
            session_state.suspended_ask = None
            session_state.active_intention_id = intention_id
            resumed = TaskRequest(
                user_turn=str(orig),
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
                execution_context=execution_context,
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
            # Permission only — do NOT mark precondition true here.
            ask.permission_granted = True
            resolve = resolve_prerequisite(
                ask.precondition,
                permission_granted=True,
                context={
                    "method_id": ask.method_id,
                    "intention_id": intention_id,
                    "session_id": session_state.session_id,
                },
            )
            trace["prerequisite_resolve"] = {
                "status": resolve.status,
                "precondition": resolve.precondition,
                "detail": resolve.detail,
            }
            if resolve.status == "achieved":
                session_state.precondition_facts[ask.precondition] = True
                session_state.suspended_ask = None
                session_state.active_intention_id = intention_id
                resumed = TaskRequest(
                    user_turn=str(orig),
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
                    run_message=run_message
                    if run_message is not None
                    else resumed.user_turn,
                    conversation_kwargs=conversation_kwargs,
                    execution_context=execution_context,
                )
                result.status = TurnStatus.CONTINUED
                result.intention_id = intention_id
                result.acceptance_trace = {
                    **(result.acceptance_trace or {}),
                    "resumed_after": "prerequisite_achieved",
                    "method": ask.method_id,
                    "permission_granted": True,
                }
                return result

            # Resolver failed / unsupported / pending — keep parent; do not fake success.
            if resolve.status == "failed":
                session_state.suspended_ask = None
                session_state.declined_method_ids.add(ask.method_id)
                session_state.active_intention_id = intention_id
                resumed = TaskRequest(
                    user_turn=str(orig),
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
                    run_message=run_message
                    if run_message is not None
                    else resumed.user_turn,
                    conversation_kwargs=conversation_kwargs,
                    execution_context=execution_context,
                )
                result.status = TurnStatus.CONTINUED
                result.intention_id = intention_id
                result.acceptance_trace = {
                    **(result.acceptance_trace or {}),
                    "resumed_after": "prerequisite_failed",
                    "method": ask.method_id,
                    "permission_granted": True,
                    "precondition_achieved": False,
                }
                return result

            # pending / unsupported — remain WAITING or re-ask
            return RuntimeTurnResult(
                status=TurnStatus.WAITING_FOR_USER,
                question=ask.question,
                message=(
                    f"Permission noted, but prerequisite '{ask.precondition}' is not "
                    f"verified yet ({resolve.status}: {resolve.detail})."
                ),
                intention_id=intention_id,
                task_request_id=task_request_id,
                session_id=session_state.session_id,
                runtime_id=session_state.runtime_id,
                acceptance_trace=trace,
            )

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
    return str(
        getattr(legacy, "final_response", "") or getattr(legacy, "response", "") or ""
    )


def _classify_ask_response(text: str) -> str:
    t = str(text or "").strip().lower()
    if not t:
        return "unclear"
    if t in {"no", "n", "nope", "decline", "skip"} or t.startswith("no ") or "don't" in t or "do not" in t or t == "not now" or t == "never":
        return "decline"
    if t in {"yes", "y", "ok", "okay", "sure", "allow", "link", "accept", "please"} or t.startswith("yes"):
        return "accept"
    return "unclear"
