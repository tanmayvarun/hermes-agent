"""WhatsApp gateway method provider — preferred over ComputerUse for forwards.

READY when the Baileys bridge stack is present. Runtime precondition
``whatsapp_linked`` drives ASK → link-device QR (via prerequisite resolver).

Executor attempts a real gateway send when content + JID are known. Find-by-
``link_query`` / native forward are not on the bridge yet — those failures
signal AgentRuntime to fall through to ComputerUse (not fake success).
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional, Sequence, Tuple

from plugin.agent.executive.intention_frame import MethodSpec
from plugin.agent.executive.method_availability import MethodReadiness
from plugin.agent.executive.method_providers import TaskInterpretation
from plugin.agent.ingress import ExecutionConstraints
from plugin.agent.runtime.method_executors import MethodExecutionResult
from plugin.agent.runtime.prerequisite_resolver import (
    PrerequisiteResolveResult,
    register_prerequisite_resolver,
)

WHATSAPP_LINKED_PRECONDITION = "whatsapp_linked"
WHATSAPP_GATEWAY_METHOD_ID = "whatsapp_gateway_forward"
WHATSAPP_GATEWAY_SUBSTRATE = "whatsapp_gateway"

# Executor statuses that mean "live WA can't finish the effect — try next method".
# bridge_unavailable / not_linked are NOT here: those recover to link ASK first.
GATEWAY_FALLBACK_STATUSES = frozenset(
    {
        "search_unsupported",
        "cannot_resolve_target",
        "send_failed",
    }
)

_PHONE_RE = re.compile(r"^\+?\d{8,15}$")
_JID_RE = re.compile(r".+@(s\.whatsapp\.net|g\.us|lid)$", re.I)


class WhatsAppGatewayMethodProvider:
    """Advertises a READY WhatsApp gateway forward method when bridge exists."""

    provider_id = "whatsapp_gateway"

    def __init__(self, *, ready: bool = False, reason: str = "") -> None:
        self.ready = bool(ready)
        self.reason = str(reason or "")

    def discover(
        self,
        interpretation: TaskInterpretation,
        *,
        constraints: Optional[ExecutionConstraints] = None,
    ) -> Sequence[MethodSpec]:
        if not self.ready:
            return []
        effects = set(interpretation.desired_effects or [])
        kind = str(interpretation.goal_kind or "")
        if "forward_message" not in effects and "forward" not in kind:
            return []
        # Skip link ASK when a real Baileys account is already on disk OR the
        # HTTP bridge is live. (Bridge-down after pair-only is not "unlinked".)
        linked = False
        live = False
        try:
            from hermes_cli.whatsapp_pairing import is_whatsapp_linked, is_whatsapp_live

            linked = bool(is_whatsapp_linked())
            live = bool(is_whatsapp_live())
        except Exception:
            pass
        return [
            MethodSpec(
                id=WHATSAPP_GATEWAY_METHOD_ID,
                capability="forward_message",
                substrate=WHATSAPP_GATEWAY_SUBSTRATE,
                provider=self.provider_id,
                preconditions=[] if (linked or live) else [WHATSAPP_LINKED_PRECONDITION],
                readiness=MethodReadiness.READY.value,
                # Prefer over ComputerUse (higher reliability / lower interference).
                reliability=0.88,  # I3: MethodFrontierWaGatewayFirstPolicy floor
                latency=0.45,
                risk=0.35,
                cost=0.35,
                user_interference=0.35,
                semantic_precision=0.8,
            )
        ]


class WhatsAppLinkPrerequisiteResolver:
    """Starts Baileys --pair-json pairing and returns QR evidence while pending.

    Owns WhatsApp-specific consent copy and failure policy. AgentRuntime stays
    domain-generic and only honors ``failure_policy`` / ``user_message`` /
    ``evidence`` ui fields.
    """

    owned = frozenset({WHATSAPP_LINKED_PRECONDITION})

    def ask_prompt(self, precondition: str) -> Optional[str]:
        if str(precondition or "").strip() not in self.owned:
            return None
        return (
            "I can do this over WhatsApp (preferred) once this device is linked. "
            "Allow me to show a WhatsApp **Link a device** QR here so we can continue "
            "without falling back to Computer Use / other tools?"
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
            )

        from hermes_cli.whatsapp_pairing import (
            get_pairing,
            is_whatsapp_linked,
            is_whatsapp_live,
            linked_account_from_session,
            start_pairing,
            wait_for_qr_or_terminal,
        )

        # Phone already linked (pair-only may have exited; /health can be down).
        if is_whatsapp_live() or is_whatsapp_linked():
            from hermes_cli.whatsapp_pairing import ensure_whatsapp_bridge_running

            # Pair-only leaves no HTTP daemon — bring it up before continuing.
            bridge_ok, bridge_detail = ensure_whatsapp_bridge_running()
            account_id, account_name, account_phone = linked_account_from_session()
            return PrerequisiteResolveResult(
                status="achieved",
                precondition=key,
                detail=(
                    "bridge_connected"
                    if bridge_ok or is_whatsapp_live()
                    else f"creds_linked:{bridge_detail}"
                ),
                evidence={
                    "kind": "whatsapp_link_device",
                    "status": "connected",
                    "linked": True,
                    "bridge_running": bool(bridge_ok),
                    "bridge_detail": bridge_detail,
                    "account_id": account_id,
                    "account_name": account_name,
                    "account_phone": account_phone,
                },
            )

        ctx = dict(context or {})
        pairing_id = str(ctx.get("pairing_id") or "").strip()
        reset_attempted = bool(ctx.get("_session_reset_attempted"))

        def _start_and_wait(*, pid: str = "", timeout_s: float = 20.0) -> Dict[str, Any]:
            if pid:
                status_local = get_pairing(pid) or {}
                if not status_local:
                    # Resume/recreate WITHOUT wiping — user may have just scanned.
                    status_local = start_pairing(pairing_id=pid, force=True)
                else:
                    # Prefer detecting a completed scan over re-emitting QR.
                    status_local = wait_for_qr_or_terminal(pid, timeout_s=min(3.0, timeout_s))
                    if str(status_local.get("status") or "") in {
                        "connected",
                        "error",
                        "expired",
                        "cancelled",
                    }:
                        return status_local
                    if status_local.get("qr_payload"):
                        return status_local
                    # Pair process died after scan — creds may already be on disk.
                    if is_whatsapp_linked():
                        account_id, account_name, account_phone = linked_account_from_session()
                        return {
                            "status": "connected",
                            "pairing_id": pid,
                            "account_id": account_id,
                            "account_name": account_name,
                            "account_phone": account_phone,
                        }
                return wait_for_qr_or_terminal(
                    str(status_local.get("pairing_id") or pid), timeout_s=timeout_s
                )
            status_local = start_pairing(force=True)
            new_pid = str(status_local.get("pairing_id") or "")
            if new_pid:
                return wait_for_qr_or_terminal(new_pid, timeout_s=timeout_s)
            return status_local

        status = _start_and_wait(pid=pairing_id, timeout_s=20.0)
        pairing_id = str(status.get("pairing_id") or pairing_id or "")
        st = str(status.get("status") or "")
        err = str(status.get("error") or "").strip().lower()

        # logged_out / dead creds: wipe once and re-pair so QR can appear.
        if (
            not reset_attempted
            and not status.get("qr_payload")
            and st != "connected"
            and not is_whatsapp_linked()
            and (err == "logged_out" or st == "error")
        ):
            status = start_pairing(force=True, reset_session=True)
            pairing_id = str(status.get("pairing_id") or "")
            if pairing_id:
                status = wait_for_qr_or_terminal(pairing_id, timeout_s=20.0)
            st = str(status.get("status") or "")
            err = str(status.get("error") or "").strip().lower()
            reset_attempted = True

        # Linked on disk or pair-only connected — continue (clear QR in runtime).
        if st == "connected" or is_whatsapp_live() or is_whatsapp_linked():
            from hermes_cli.whatsapp_pairing import ensure_whatsapp_bridge_running

            bridge_ok, bridge_detail = ensure_whatsapp_bridge_running()
            account_id, account_name, account_phone = linked_account_from_session()
            return PrerequisiteResolveResult(
                status="achieved",
                precondition=key,
                detail="paired" if bridge_ok else f"paired:{bridge_detail}",
                evidence={
                    "kind": "whatsapp_link_device",
                    "pairing_id": pairing_id or status.get("pairing_id"),
                    "status": "connected",
                    "account_id": status.get("account_id") or account_id,
                    "account_name": status.get("account_name") or account_name,
                    "account_phone": status.get("account_phone") or account_phone,
                    "linked": True,
                    "bridge_running": bool(bridge_ok),
                    "bridge_detail": bridge_detail,
                },
            )

        evidence = {
            "kind": "whatsapp_link_device",
            "pairing_id": pairing_id or status.get("pairing_id"),
            "status": st or "starting",
            "qr_payload": status.get("qr_payload"),
            "expires_at": status.get("expires_at"),
            "account_id": status.get("account_id"),
            "account_name": status.get("account_name"),
            "account_phone": status.get("account_phone"),
            "error": status.get("error"),
            "session_reset_attempted": reset_attempted,
        }

        # QR TTL / cancelled → runtime falls through to next ranked method.
        if st in {"expired", "cancelled"}:
            return PrerequisiteResolveResult(
                status="failed",
                precondition=key,
                detail=str(status.get("error") or st),
                evidence={**evidence, "status": st, "qr_payload": None},
                failure_policy="fallback_next_method",
                user_message=(
                    "WhatsApp Link-a-device QR expired. Continuing with another "
                    "available method."
                ),
            )

        # Retryable pairing errors: keep ASK open so a fresh QR can appear.
        if st == "error" and reset_attempted and not status.get("qr_payload"):
            return PrerequisiteResolveResult(
                status="failed",
                precondition=key,
                detail=str(status.get("error") or "pairing_error"),
                evidence={**evidence, "qr_payload": None},
                failure_policy="keep_ask",
                user_message=(
                    "Previous WhatsApp link on this device expired. Starting a fresh "
                    "**Link a device** QR — reply **yes** again if it doesn’t appear, "
                    "or **not now** to use another method."
                ),
            )

        # Fresh QR / in-progress pairing — keep waiting (no fallthrough yet).
        if status.get("qr_payload") or st in {"starting", "waiting", "installing"}:
            user_message = (
                "Scan this QR with WhatsApp → Linked devices → Link a device. "
                "When the phone shows connected, reply **done** (or **yes**) so I can continue."
                if status.get("qr_payload")
                else (
                    "Starting WhatsApp **Link a device**… the QR will show here shortly. "
                    "Reply **done** after scanning, or **not now** for another method."
                )
            )
            return PrerequisiteResolveResult(
                status="pending",
                precondition=key,
                detail="awaiting_qr_scan",
                evidence=evidence,
                user_message=user_message,
            )

        # Do not treat stale/empty creds as achieved — keep waiting for a QR
        # or a real pair-only "connected" / live bridge signal above.
        return PrerequisiteResolveResult(
            status="pending",
            precondition=key,
            detail="awaiting_qr_scan",
            evidence=evidence,
            user_message=(
                "Starting WhatsApp **Link a device**… the QR will show here shortly. "
                "Reply **done** after scanning, or **not now** for another method."
            ),
        )


def _bridge_base_url() -> str:
    port = str(os.environ.get("WHATSAPP_BRIDGE_PORT") or "3000").strip() or "3000"
    return f"http://127.0.0.1:{port}"


def _goal_fields(context: Dict[str, Any]) -> Dict[str, str]:
    goal = context.get("goal")
    interp = context.get("interpretation")
    if goal is None and interp is not None:
        goal = getattr(interp, "goal", None)
    return {
        "link_query": str(getattr(goal, "link_query", "") or "").strip(),
        "contact": str(getattr(goal, "contact", "") or "").strip(),
        "recipient": str(getattr(goal, "recipient", "") or "").strip(),
        "target_contact": str(getattr(goal, "target_contact", "") or "").strip(),
        "message_body": str(getattr(goal, "message_body", "") or "").strip(),
        "kind": str(getattr(goal, "kind", "") or "").strip(),
    }


def _bridge_resolve_name(name: str) -> Tuple[str, str]:
    """Ask the local Baileys bridge to resolve a contact/chat display name."""
    raw = str(name or "").strip()
    if not raw:
        return "", "empty"
    url = f"{_bridge_base_url()}/resolve?name={urllib.parse.quote(raw)}"
    try:
        with urllib.request.urlopen(url, timeout=8) as resp:
            body = json.loads(resp.read().decode("utf-8", errors="replace") or "{}")
    except Exception as exc:
        return "", f"resolve_error:{exc}"
    jid = str((body or {}).get("chatId") or (body or {}).get("jid") or "").strip()
    how = str((body or {}).get("match") or "bridge_resolve").strip()
    if jid:
        return jid, how
    return "", str((body or {}).get("error") or "not_found")


def _resolve_target_jid(target: str) -> Tuple[str, str]:
    """Return (jid, detail). Empty jid means unresolved."""
    raw = str(target or "").strip()
    if not raw:
        return "", "empty_target"
    if _JID_RE.match(raw):
        return raw, "jid_literal"
    compact = re.sub(r"[\s\-()]", "", raw)
    if _PHONE_RE.match(compact):
        try:
            from gateway.whatsapp_identity import to_whatsapp_jid

            return to_whatsapp_jid(compact), "phone_literal"
        except Exception:
            digits = re.sub(r"\D+", "", compact)
            return f"{digits}@s.whatsapp.net", "phone_literal_fallback"
    try:
        from gateway.channel_directory import resolve_channel_name

        resolved = resolve_channel_name("whatsapp", raw)
        if resolved:
            return str(resolved), "channel_directory"
    except Exception:
        pass
    jid, how = _bridge_resolve_name(raw)
    if jid:
        return jid, how
    return "", "unresolved_name"


def _known_message_body(context: Dict[str, Any], link_query: str) -> str:
    """Only send when the turn already carries concrete content (not a search)."""
    for key in ("message_body", "forward_text", "message_text", "content"):
        val = context.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    fields = _goal_fields(context)
    body = str(fields.get("message_body") or "").strip()
    if body:
        return body
    # Never invent a URL from link_query alone — that would spam wrong content.
    _ = link_query
    return ""


def _bridge_send(chat_id: str, message: str) -> Tuple[bool, str, Dict[str, Any]]:
    url = f"{_bridge_base_url()}/send"
    payload = json.dumps({"chatId": chat_id, "message": message}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = json.loads(resp.read().decode("utf-8", errors="replace") or "{}")
            return True, "sent", body if isinstance(body, dict) else {"raw": body}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
        return False, f"http_{exc.code}:{detail[:240]}", {}
    except Exception as exc:
        return False, f"send_error:{exc}", {}


class WhatsAppGatewayForwardExecutor:
    """Execute gateway forward when possible; otherwise fail for CU fallback."""

    executor_id = "whatsapp_gateway_forward"
    substrates = (WHATSAPP_GATEWAY_SUBSTRATE,)

    def execute(self, spec: Any, *, context: Dict[str, Any]) -> MethodExecutionResult:
        from hermes_cli.whatsapp_pairing import (
            ensure_whatsapp_bridge_running,
            is_whatsapp_linked,
            linked_account_from_session,
            probe_bridge_connection,
        )
        from plugin.agent.runtime.executor_idempotency import (
            get_executor_idempotency_guard,
            make_effect_key,
        )
        from plugin.agent.runtime.integrity_gates import (
            GatewaySessionWritableGate,
            WhatsAppIdentityResolvedGate,
        )

        ctx = dict(context or {})
        task_request_id = str(ctx.get("task_request_id") or "").strip()
        session_id = ""
        req = ctx.get("task_request")
        if req is not None and getattr(req, "session", None) is not None:
            session_id = str(getattr(req.session, "session_id", "") or "")
        if not session_id:
            session_id = str(ctx.get("session_id") or "")

        writable = GatewaySessionWritableGate.require_writable(
            session_id=session_id or "anonymous",
            task_request_id=task_request_id or "anonymous",
        )
        if not writable.ok and not task_request_id:
            # Soft: anonymous/test contexts still run; only hard-fail empty session.
            pass

        live, health_detail = probe_bridge_connection()
        if not live and is_whatsapp_linked():
            # Pair-only left /health down — start the long-lived daemon first.
            live, health_detail = ensure_whatsapp_bridge_running()
        if not live:
            linked = bool(is_whatsapp_linked())
            gate = WhatsAppIdentityResolvedGate.require_linked(linked=linked)
            # Already linked on phone — don't re-ASK QR; use next method (CU).
            if linked:
                return MethodExecutionResult(
                    ok=False,
                    status="bridge_unavailable",
                    detail=(
                        "WhatsApp is linked on this device, but the messaging bridge "
                        f"could not be started ({health_detail}). Continuing with another method."
                    ),
                    payload={
                        "health": health_detail,
                        "fallback": "next_method",
                        "linked": True,
                        "ensure_bridge_attempted": True,
                        "gate": gate.to_payload(),
                    },
                    executor_id=self.executor_id,
                )
            return MethodExecutionResult(
                ok=False,
                status="bridge_unavailable",
                detail=(
                    "WhatsApp is not connected on this device "
                    f"({health_detail}). Link WhatsApp before using Computer Use."
                ),
                payload={
                    "health": health_detail,
                    "fallback": gate.fallback or "ask_prerequisite",
                    "ask_precondition": gate.ask_precondition or WHATSAPP_LINKED_PRECONDITION,
                    "ask_question": (
                        "I can do this over WhatsApp (preferred) once this device is linked. "
                        "Allow me to show a WhatsApp **Link a device** QR here so we can "
                        "continue without falling back to Computer Use / other tools?"
                    ),
                    "error_code": gate.error_code,
                    "gate": gate.to_payload(),
                },
                executor_id=self.executor_id,
            )

        fields = _goal_fields(ctx)
        link_query = fields["link_query"]
        target = fields["target_contact"] or fields["contact"]
        source = fields["contact"] or fields["recipient"]
        _id, name, phone = linked_account_from_session()
        account = {"id": _id, "name": name, "phone": phone}

        # Zaroorat-style: find link in a chat, then forward — not on bridge yet.
        if link_query:
            return MethodExecutionResult(
                ok=False,
                status="search_unsupported",
                detail=(
                    f"WhatsApp is linked, but the gateway cannot search chat history "
                    f"for '{link_query}'"
                    + (f" in {source}" if source else "")
                    + ". Falling back to Computer Use to find and forward it."
                ),
                payload={
                    "ok": False,
                    "fallback": "next_method",
                    "link_query": link_query,
                    "source_contact": source,
                    "target_contact": target,
                    "account": account,
                    "method_id": getattr(spec, "id", ""),
                },
                executor_id=self.executor_id,
            )

        body = _known_message_body(ctx, link_query)
        if not body:
            return MethodExecutionResult(
                ok=False,
                status="search_unsupported",
                detail=(
                    "WhatsApp gateway has no message body to send and no history "
                    "search. Falling back to Computer Use."
                ),
                payload={"ok": False, "fallback": "next_method", "account": account},
                executor_id=self.executor_id,
            )

        jid, how = _resolve_target_jid(target)
        if not jid:
            return MethodExecutionResult(
                ok=False,
                status="cannot_resolve_target",
                detail=(
                    f"Cannot resolve WhatsApp target '{target}' to a phone/JID "
                    f"({how}). Falling back to Computer Use."
                ),
                payload={
                    "ok": False,
                    "fallback": "next_method",
                    "target_contact": target,
                    "account": account,
                },
                executor_id=self.executor_id,
            )

        guard = get_executor_idempotency_guard()
        idem_key = make_effect_key(
            task_request_id=task_request_id or getattr(spec, "id", "") or "wa",
            effect="whatsapp_gateway_send",
            parts=(jid, body),
        )
        prior = guard.lookup(idem_key)
        if prior is not None:
            return guard.mark_replay(prior)

        ok, detail, resp = _bridge_send(jid, body)
        if not ok:
            return MethodExecutionResult(
                ok=False,
                status="send_failed",
                detail=f"WhatsApp /send failed ({detail}). Falling back to Computer Use.",
                payload={
                    "ok": False,
                    "fallback": "next_method",
                    "chat_id": jid,
                    "error": detail,
                    "account": account,
                },
                executor_id=self.executor_id,
            )
        result = MethodExecutionResult(
            ok=True,
            status="sent",
            detail=f"Sent via WhatsApp gateway to {jid} ({how}).",
            payload={
                "ok": True,
                "chat_id": jid,
                "resolve": how,
                "response": resp,
                "account": account,
                "method_id": getattr(spec, "id", ""),
            },
            executor_id=self.executor_id,
        )
        guard.remember_success(idem_key, result)
        return result


def ensure_whatsapp_gateway_provider_registered() -> dict:
    """Compose WhatsApp gateway method + link resolver when bridge is available."""
    from plugin.agent.executive.method_providers import register_method_provider
    from plugin.agent.runtime.method_executors import register_method_executor

    ready, reason = False, "unchecked"
    try:
        from hermes_cli.whatsapp_pairing import bridge_available

        ready, reason = bridge_available()
    except Exception as exc:
        ready, reason = False, f"probe_exception:{exc}"

    diagnostic = {
        "event": "whatsapp_gateway_composition",
        "ok": bool(ready),
        "ready": bool(ready),
        "reason": reason,
        "provider_registered": False,
        "executor_registered": False,
        "resolver_registered": False,
    }
    if not ready:
        return diagnostic

    register_method_provider(WhatsAppGatewayMethodProvider(ready=True, reason=reason))
    register_method_executor(WhatsAppGatewayForwardExecutor())
    register_prerequisite_resolver(WhatsAppLinkPrerequisiteResolver())
    diagnostic["provider_registered"] = True
    diagnostic["executor_registered"] = True
    diagnostic["resolver_registered"] = True
    diagnostic["ok"] = True
    return diagnostic
