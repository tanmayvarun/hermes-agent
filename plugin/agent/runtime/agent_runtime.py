"""Thin AgentRuntime — domain-generic turn orchestration.

Owns RuntimeState + MemorySystem one-way. Orchestrates:

    TaskRequest → ContextActivation (BrainWorkspace) → interpretation
    → method providers → MethodFrontier decision
    → ASK (resumable) | execute_method(selected) | legacy conversation

Slice 1: associative ContextActivation runs before Goal interpret; it does
**not** commit identity (RoleBinder / recipient_binding remain separate).

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
from plugin.agent.runtime.prerequisite_resolver import (
    ask_prompt_for_precondition,
    resolve_prerequisite,
)
from plugin.agent.runtime.session_store import SuspendedAsk, get_or_create_session
from plugin.agent.runtime.state import RuntimeState
from plugin.agent.runtime.error_codes import infer_error_code
from plugin.agent.runtime.invariants import (
    CuSetupBlockerAskPolicy,
    TaskOutcomeContractPolicy,
)
from plugin.agent.runtime.task_tracker import (
    PHASE_AWAITING_USER,
    PHASE_COMPUTER_USE,
    PHASE_EXECUTING,
    PHASE_FINISHING,
    PHASE_INTERPRETING,
    PHASE_SELECTING_METHOD,
    STATUS_FAILED,
    final_status_from_turn,
    get_task_tracker,
)
from plugin.agent.runtime.turn_result import RuntimeTurnResult, TurnStatus


ConversationRunner = Callable[..., Any]
TaskUpdateCallback = Callable[[Dict[str, Any]], None]


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
        on_task_update: Optional[TaskUpdateCallback] = None,
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

        exec_ctx_base = dict(execution_context or {})
        update_cb: Optional[TaskUpdateCallback] = on_task_update or exec_ctx_base.get(
            "task_status_callback"
        )
        tracker = get_task_tracker()
        tracker.start(
            task_request_id=task_request_id,
            session_id=sid,
            prompt=str(req.user_turn or ""),
            on_update=update_cb,
        )
        settled = False

        def _phase(phase: str, **kwargs: Any) -> None:
            tracker.note_phase(
                task_request_id, phase, on_update=update_cb, **kwargs
            )

        def _finish(result: RuntimeTurnResult) -> RuntimeTurnResult:
            nonlocal settled
            # I1: every handle_turn exit settles exactly once.
            if not TaskOutcomeContractPolicy.should_settle(settled):
                return result
            settled = True
            final = final_status_from_turn(result.status)
            phase = TaskOutcomeContractPolicy.phase_for_status(final)
            summary = str(result.message or result.question or "")[:240]
            error_code = infer_error_code(
                final_status=final,
                ui_hints=dict(result.ui_hints or {}),
                payload=dict(result.acceptance_trace or {}),
            )
            tracker.settle(
                task_request_id,
                status=final,
                summary=summary,
                error_code=error_code,
                phase=phase,
                on_update=update_cb,
            )
            return result

        # Propagate task id + callback into executors (CU phase notes).
        exec_ctx_base["task_request_id"] = task_request_id
        if update_cb is not None:
            exec_ctx_base["task_status_callback"] = update_cb
        execution_context = exec_ctx_base

        try:
            return self._handle_turn_body(
                req,
                session_state=session_state,
                sid=sid,
                task_request_id=task_request_id,
                intention_id=intention_id,
                conversation_runner=conversation_runner,
                run_message=run_message,
                conversation_kwargs=conversation_kwargs,
                execution_context=execution_context,
                phase=_phase,
                finish=_finish,
            )
        except Exception as exc:
            if not settled:
                settled = True
                tracker.settle(
                    task_request_id,
                    status=STATUS_FAILED,
                    error=f"{type(exc).__name__}: {exc}",
                    error_code="execution_failed",
                    phase=PHASE_FINISHING,
                    on_update=update_cb,
                )
            raise

    def _handle_turn_body(
        self,
        req: TaskRequest,
        *,
        session_state: Any,
        sid: str,
        task_request_id: str,
        intention_id: str,
        conversation_runner: Optional[ConversationRunner],
        run_message: Any,
        conversation_kwargs: Optional[Dict[str, Any]],
        execution_context: Optional[Dict[str, Any]],
        phase: Callable[..., None],
        finish: Callable[[RuntimeTurnResult], RuntimeTurnResult],
    ) -> RuntimeTurnResult:
        if session_state.suspended_ask is not None:
            return finish(
                self._resume_ask(
                    req,
                    session_state=session_state,
                    task_request_id=task_request_id,
                    conversation_runner=conversation_runner,
                    run_message=run_message,
                    conversation_kwargs=conversation_kwargs,
                    execution_context=execution_context,
                )
            )

        phase(PHASE_INTERPRETING)

        # Slice 1B: persistent BrainWorkspace + activation fed into interpret.
        activation_trace: Dict[str, Any] = {}
        workspace = None
        try:
            from plugin.agent.brain.context_activation import activate_context
            from plugin.agent.brain.workspace import BrainWorkspace

            prior = getattr(session_state, "brain_workspace", None)
            if prior is None or not isinstance(prior, BrainWorkspace):
                prior = BrainWorkspace(session_ref=sid)
            # Carry L1 working context; client is additive only.
            wc_in = dict(prior.working_context or {})
            client = (req.client_context or {}).get("client")
            if client:
                wc_in["client"] = client
            workspace = activate_context(
                self.memory,
                raw_turn=str(req.user_turn or ""),
                session_ref=sid,
                working_context=wc_in,
                workspace=prior,
            )
            session_state.brain_workspace = workspace
            activation_trace = workspace.activation_trace()
        except Exception as exc:
            activation_trace = {"status": "error", "error": str(exc), "committed": False}

        interpretation = interpret_task_request(req, brain_workspace=workspace)

        # Personal-entity resolution BEFORE MethodFrontier / substrate choice.
        recipient_trace: Dict[str, Any] = {}
        _goal_kind = ""
        _effects: list = []
        try:
            from plugin.agent.memory.recipient_binding import (
                resolve_recipient_before_methods,
            )

            boot_state = ""
            if hasattr(self.memory, "get_bootstrap_state"):
                boot_state = str(self.memory.get_bootstrap_state() or "")
            rr = resolve_recipient_before_methods(
                self.memory,
                goal=interpretation.goal,
                desired_effects=list(interpretation.desired_effects or []),
                channel="whatsapp",
                bootstrap_state=boot_state,
            )
            recipient_trace = {
                "status": rr.status,
                "surface_form": rr.surface_form,
                "entity_id": rr.entity_id,
                "channel_external_id": rr.channel_external_id,
                "reason": rr.reason,
                "bootstrap_state": rr.bootstrap_state,
            }
            if rr.status == "ask":
                question = rr.question or f"Which '{rr.surface_form}' did you mean?"
                session_state.suspended_ask = SuspendedAsk(
                    intention_id=intention_id,
                    method_id="memory_entity_resolution",
                    precondition="entity_resolution",
                    question=question,
                    parent_effect=",".join(interpretation.desired_effects),
                    interpretation_notes={
                        "surface_form": rr.surface_form,
                        "alternatives": list(rr.alternatives or []),
                        "entity_id": rr.entity_id,
                    },
                )
                phase(PHASE_AWAITING_USER, status="waiting_for_user")
                return finish(
                    RuntimeTurnResult(
                        status=TurnStatus.WAITING_FOR_USER,
                        question=question,
                        message=question,
                        intention_id=intention_id,
                        task_request_id=task_request_id,
                        session_id=sid,
                        runtime_id=session_state.runtime_id,
                        acceptance_trace={
                            "context_activation": activation_trace,
                            "recipient_resolution": recipient_trace,
                            "ASK": question,
                        },
                        interpretation=interpretation,
                    )
                )
        except Exception as exc:
            # Fail closed for recipient-bearing externally visible actions.
            recipient_trace = {"status": "error", "error": str(exc)}
            _goal_kind = str(
                getattr(getattr(interpretation, "goal", None), "kind", "") or ""
            ).lower()
            _effects = list(interpretation.desired_effects or [])
            _surface = str(
                getattr(getattr(interpretation, "goal", None), "contact", "")
                or getattr(getattr(interpretation, "goal", None), "recipient", "")
                or getattr(getattr(interpretation, "goal", None), "target_contact", "")
                or ""
            ).strip()
            _recipient_action = bool(_surface) and (
                "forward" in _goal_kind
                or "send" in _goal_kind
                or any("send" in str(e) or "forward" in str(e) for e in _effects)
            )
            if _recipient_action:
                question = (
                    f"I couldn't safely resolve who '{_surface}' refers to "
                    f"(memory error). Which contact should I use?"
                )
                session_state.suspended_ask = SuspendedAsk(
                    intention_id=intention_id,
                    method_id="memory_entity_resolution",
                    precondition="entity_resolution",
                    question=question,
                    parent_effect=",".join(_effects),
                    interpretation_notes={
                        "surface_form": _surface,
                        "error": str(exc),
                        "fail_closed": True,
                    },
                )
                phase(PHASE_AWAITING_USER, status="waiting_for_user")
                return finish(
                    RuntimeTurnResult(
                        status=TurnStatus.WAITING_FOR_USER,
                        question=question,
                        message=question,
                        intention_id=intention_id,
                        task_request_id=task_request_id,
                        session_id=sid,
                        runtime_id=session_state.runtime_id,
                        acceptance_trace={
                            "context_activation": activation_trace,
                            "recipient_resolution": recipient_trace,
                            "ASK": question,
                        },
                        interpretation=interpretation,
                    )
                )

        phase(PHASE_SELECTING_METHOD)
        specs, provider_errors = discover_methods(
            interpretation, constraints=req.constraints
        )
        decision = decide_methods(
            specs,
            constraints=req.constraints,
            precondition_facts=session_state.precondition_facts,
            declined_method_ids=session_state.declined_method_ids,
            declined_preconditions=session_state.declined_preconditions,
            blocked_method_ids=session_state.blocked_method_ids,
            failed_preconditions=session_state.failed_preconditions,
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
            "context_activation": activation_trace,
            "goal_interpretation": {
                "goal_kind": interpretation.goal_kind,
                "desired_effects": list(interpretation.desired_effects),
                "activated_context_consumed": bool(
                    (getattr(interpretation, "notes", None) or {}).get(
                        "activated_context"
                    )
                ),
                "l1_preferred_entity": (getattr(interpretation, "notes", None) or {}).get(
                    "l1_preferred_entity"
                ),
            },
            "recipient_resolution": recipient_trace,
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
            pre = str(decision.ask_precondition or "access")
            # Consent copy is owned by the precondition resolver (domain adapter).
            question = ask_prompt_for_precondition(pre)
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
            phase(PHASE_AWAITING_USER, status="waiting_for_user")
            return finish(
                RuntimeTurnResult(
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
            )

        if decision.selected_method_id:
            spec = decision.frontier.catalog[decision.selected_method_id]
            substrate = str(getattr(spec, "substrate", "") or "")
            phase(
                PHASE_COMPUTER_USE
                if "computer" in substrate.lower()
                else PHASE_EXECUTING,
                selected_method=str(spec.id),
            )
            exec_ctx = {
                "goal": interpretation.goal,
                "runtime_state": self.runtime_state,
                "task_request": req,
                "interpretation": interpretation,
                "memory": self.memory,
                "session_state": session_state,
                "precondition_facts": dict(session_state.precondition_facts),
                "session_id": sid,
                **dict(execution_context or {}),
            }
            exec_result = execute_method(spec, context=exec_ctx)
            trace["selected_method"] = spec.id
            trace["selected_substrate"] = getattr(spec, "substrate", "")
            trace["executor_id"] = exec_result.executor_id
            trace["executor_status"] = exec_result.status
            trace["dispatched_executor"] = True
            _exec_payload = (
                dict(exec_result.payload)
                if isinstance(exec_result.payload, dict)
                else {}
            )
            if _exec_payload.get("error_code"):
                trace["error_code"] = str(_exec_payload.get("error_code"))
            if isinstance(_exec_payload.get("gate"), dict) and _exec_payload["gate"].get(
                "error_code"
            ):
                trace["error_code"] = str(_exec_payload["gate"]["error_code"])
            session_state.last_trace = trace

            if not exec_result.ok:
                payload = dict(exec_result.payload or {})
                fallback = str(payload.get("fallback") or "").strip()
                ask_pre = str(
                    payload.get("ask_precondition")
                    or payload.get("missing_precondition")
                    or ""
                ).strip()
                # Executor-owned recover ASK (any domain): ask then resolve.
                if fallback == "ask_prerequisite" and ask_pre:
                    # I4: skip re-ASK when precondition already verified this session.
                    if CuSetupBlockerAskPolicy.should_skip_reask(
                        precondition=ask_pre,
                        precondition_facts=session_state.precondition_facts,
                    ):
                        fallback = "next_method"
                    else:
                        question = str(payload.get("ask_question") or "").strip() or (
                            ask_prompt_for_precondition(ask_pre)
                        )
                        session_state.precondition_facts.pop(ask_pre, None)
                        ui_hints: Dict[str, Any] = {}
                        raw_hints = payload.get("ui_hints")
                        if isinstance(raw_hints, dict):
                            ui_hints = dict(raw_hints)
                            trace["ui_hints"] = {
                                k: ui_hints.get(k)
                                for k in ("kind", "blocker", "app", "title")
                                if k in ui_hints
                            }
                        notes: Dict[str, Any] = {}
                        if ui_hints:
                            notes["ui_hints"] = ui_hints
                        if ui_hints.get("app"):
                            notes["app"] = ui_hints.get("app")
                        if _exec_payload.get("error_code") and not ui_hints.get(
                            "error_code"
                        ):
                            ui_hints["error_code"] = str(_exec_payload["error_code"])
                        session_state.suspended_ask = SuspendedAsk(
                            intention_id=intention_id,
                            method_id=str(spec.id),
                            precondition=ask_pre,
                            question=question,
                            parent_effect=",".join(interpretation.desired_effects),
                            interpretation_notes=notes,
                        )
                        trace["ASK"] = question
                        trace["missing_precondition"] = ask_pre
                        trace["method_availability"] = "missing_precondition"
                        trace["executor_recover_ask"] = True
                        phase(PHASE_AWAITING_USER, status="waiting_for_user")
                        return finish(
                            RuntimeTurnResult(
                                status=TurnStatus.WAITING_FOR_USER,
                                question=question,
                                message=question,
                                intention_id=intention_id,
                                task_request_id=task_request_id,
                                session_id=sid,
                                runtime_id=session_state.runtime_id,
                                acceptance_trace=trace,
                                interpretation=interpretation,
                                ui_hints=ui_hints,
                            )
                        )

                # Capability / substrate gap → next ranked method (generic).
                if fallback in {"next_method", "computer_use"}:
                    session_state.blocked_method_ids.add(str(spec.id))
                    fallback_meta = {
                        "from_method": str(spec.id),
                        "status": exec_result.status,
                        "detail": exec_result.detail,
                        "fallback": fallback,
                    }
                    trace["executor_fallback"] = fallback_meta
                    session_state.last_trace = trace
                    nested = self.handle_turn(
                        req,
                        conversation_runner=conversation_runner,
                        run_message=run_message,
                        conversation_kwargs=conversation_kwargs,
                        execution_context=execution_context,
                    )
                    nested_trace = dict(nested.acceptance_trace or {})
                    nested_trace.setdefault("executor_fallback", fallback_meta)
                    nested.ui_hints = {}
                    nested.acceptance_trace = nested_trace
                    return finish(nested)

            return finish(
                RuntimeTurnResult(
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
            )

        # No executable method — migration path: legacy conversational engine.
        if conversation_runner is not None:
            phase(PHASE_EXECUTING, summary="conversation")
            legacy = self._delegate_conversation(
                interpretation=interpretation,
                conversation_runner=conversation_runner,
                run_message=run_message if run_message is not None else req.user_turn,
                conversation_kwargs=conversation_kwargs,
            )
            trace["selected_method"] = ""
            trace["selected_substrate"] = "conversation_legacy"
            trace["dispatched_executor"] = False
            return finish(
                RuntimeTurnResult(
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
            )
        return finish(
            RuntimeTurnResult(
                status=TurnStatus.COMPLETED,
                intention_id=intention_id,
                task_request_id=task_request_id,
                session_id=sid,
                runtime_id=session_state.runtime_id,
                acceptance_trace=trace,
                interpretation=interpretation,
            )
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

        # Accept, or re-poll after permission while QR/link is still pending.
        should_resolve = answer == "accept" or (
            ask.permission_granted and answer != "decline"
        )
        if should_resolve:
            # Permission only — do NOT mark precondition true here.
            ask.permission_granted = True
            resolve_ctx = {
                "method_id": ask.method_id,
                "intention_id": intention_id,
                "session_id": session_state.session_id,
            }
            prior_pairing = str(
                (ask.interpretation_notes or {}).get("pairing_id") or ""
            ).strip()
            if prior_pairing:
                resolve_ctx["pairing_id"] = prior_pairing
            prior_hints = (ask.interpretation_notes or {}).get("ui_hints")
            if isinstance(prior_hints, dict) and prior_hints:
                resolve_ctx["ui_hints"] = dict(prior_hints)
            if (ask.interpretation_notes or {}).get("app"):
                resolve_ctx["app"] = ask.interpretation_notes.get("app")
            resolve = resolve_prerequisite(
                ask.precondition,
                permission_granted=True,
                context=resolve_ctx,
            )
            evidence = dict(resolve.evidence or {})
            if evidence.get("pairing_id"):
                ask.interpretation_notes["pairing_id"] = evidence["pairing_id"]
            if evidence.get("kind") == "user_setup_blocker" or evidence.get("blocker"):
                ask.interpretation_notes["ui_hints"] = _ui_hints_from_resolve_evidence(
                    evidence
                )
            trace["prerequisite_resolve"] = {
                "status": resolve.status,
                "precondition": resolve.precondition,
                "detail": resolve.detail,
                "evidence_kind": evidence.get("kind"),
            }
            ui_hints = _ui_hints_from_resolve_evidence(evidence)
            if not ui_hints and isinstance(prior_hints, dict):
                ui_hints = dict(prior_hints)
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
                result.ui_hints = {}  # clear Link-a-device QR after successful scan
                result.acceptance_trace = {
                    **(result.acceptance_trace or {}),
                    "resumed_after": "prerequisite_achieved",
                    "method": ask.method_id,
                    "permission_granted": True,
                }
                return result

            # Resolver-owned failure policy (domain adapters set this).
            if resolve.status == "failed":
                policy = str(
                    getattr(resolve, "failure_policy", "")
                    or evidence.get("failure_policy")
                    or ""
                ).strip()
                if policy == "fallback_next_method":
                    session_state.suspended_ask = None
                    session_state.blocked_method_ids.add(ask.method_id)
                    session_state.failed_preconditions.add(ask.precondition)
                    session_state.declined_preconditions.add(ask.precondition)
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
                    result.ui_hints = {}
                    result.acceptance_trace = {
                        **(result.acceptance_trace or {}),
                        "resumed_after": "prerequisite_failed_fallback",
                        "method": ask.method_id,
                        "permission_granted": True,
                        "precondition_achieved": False,
                        "detail": resolve.detail,
                    }
                    return result
                if policy == "keep_ask":
                    pending_msg = _pending_prerequisite_message(
                        ask.precondition, resolve, ui_hints
                    )
                    return RuntimeTurnResult(
                        status=TurnStatus.WAITING_FOR_USER,
                        question=ask.question,
                        message=pending_msg,
                        intention_id=intention_id,
                        task_request_id=task_request_id,
                        session_id=session_state.session_id,
                        runtime_id=session_state.runtime_id,
                        acceptance_trace={
                            **trace,
                            "prerequisite_failed_kept_ask": True,
                            "detail": resolve.detail,
                        },
                        ui_hints=ui_hints,
                    )
                session_state.suspended_ask = None
                session_state.blocked_method_ids.add(ask.method_id)
                if ask.precondition:
                    session_state.failed_preconditions.add(ask.precondition)
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
                    "availability": "temporarily_unavailable",
                }
                return result

            # pending / unsupported — remain WAITING; surface resolver ui_hints
            pending_msg = _pending_prerequisite_message(ask.precondition, resolve, ui_hints)
            return RuntimeTurnResult(
                status=TurnStatus.WAITING_FOR_USER,
                question=ask.question,
                message=pending_msg,
                intention_id=intention_id,
                task_request_id=task_request_id,
                session_id=session_state.session_id,
                runtime_id=session_state.runtime_id,
                acceptance_trace=trace,
                ui_hints=ui_hints,
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
    if t in {
        "yes",
        "y",
        "ok",
        "okay",
        "sure",
        "allow",
        "link",
        "accept",
        "please",
        "done",
        "scanned",
        "linked",
        "connected",
        "continue",
    } or t.startswith("yes"):
        return "accept"
    return "unclear"


def _ui_hints_from_resolve_evidence(evidence: Dict[str, Any]) -> Dict[str, Any]:
    """Pass through resolver-owned rich UI hints (any domain)."""
    if not evidence:
        return {}
    nested = evidence.get("ui_hints")
    if isinstance(nested, dict) and nested:
        return {k: v for k, v in nested.items() if v is not None and v != ""}
    # Common interactive fields resolvers may put directly on evidence.
    hints: Dict[str, Any] = {}
    for key in (
        "kind",
        "status",
        "pairing_id",
        "expires_at",
        "qr_payload",
        "setup_url",
        "deep_link",
        "blocker",
        "app",
        "title",
        "body",
        "cta",
    ):
        val = evidence.get(key)
        if val is not None and val != "":
            hints[key] = val
    return hints


def _pending_prerequisite_message(
    precondition: str, resolve: Any, ui_hints: Dict[str, Any]
) -> str:
    owned = str(getattr(resolve, "user_message", "") or "").strip()
    if owned:
        return owned
    return (
        f"Permission noted, but prerequisite '{precondition}' is not "
        f"verified yet ({getattr(resolve, 'status', '?')}: "
        f"{getattr(resolve, 'detail', '')})."
    )
