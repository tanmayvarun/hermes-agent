"""Capability wrapper around the reusable Pipedream Connect client."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from agent.capabilities.base import Capability, CapabilityContext, CapabilityResult
from agent.pipedream_connect import PipedreamConnectClient


_CONNECT_RE = re.compile(r"\b(connect|link|authorize|authorize\s+app)\b", re.I)
_LIST_ACCOUNTS_RE = re.compile(r"\b(list|show|what\s+apps|connected\s+apps|accounts)\b", re.I)
_RUN_ACTION_RE = re.compile(r"\b(run\s+action|action|invoke\s+action)\b", re.I)
_WORKFLOW_RE = re.compile(r"\b(workflow|invoke\s+workflow|run\s+workflow)\b", re.I)


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _infer_operation(objective: str) -> str:
    text = _clean_text(objective)
    if _RUN_ACTION_RE.search(text):
        return "run_action"
    if _WORKFLOW_RE.search(text):
        return "invoke_workflow"
    if _LIST_ACCOUNTS_RE.search(text):
        return "list_accounts"
    if _CONNECT_RE.search(text):
        return "create_connect_token"
    return "status"


class PipedreamConnectCapability(Capability):
    name = "pipedream_connect"
    description = (
        "Create Pipedream Connect tokens, list connected accounts, run actions, "
        "and invoke workflows for the current user."
    )
    required_tools: List[str] = []

    def execute(self, ctx: CapabilityContext) -> CapabilityResult:
        extras = dict(ctx.extras or {})
        client = extras.get("client")
        if not isinstance(client, PipedreamConnectClient):
            client = PipedreamConnectClient.from_env(extras.get("env"))

        operation = _clean_text(extras.get("operation") or _infer_operation(ctx.objective))
        external_user_id = _clean_text(
            extras.get("external_user_id")
            or extras.get("user_id")
            or ctx.session_id
            or ctx.task_id
        )

        if not client.config.configured:
            return CapabilityResult(
                status="needs_input",
                capability=self.name,
                confidence=0.0,
                message="Pipedream is not configured. Set PIPEDREAM_PROJECT_ID and PIPEDREAM_API_TOKEN.",
                unresolved_questions=["Provide PIPEDREAM_PROJECT_ID and PIPEDREAM_API_TOKEN."],
            )

        try:
            if operation == "create_connect_token":
                if not external_user_id:
                    return CapabilityResult(
                        status="needs_input",
                        capability=self.name,
                        confidence=0.0,
                        message="external_user_id is required to create a Connect token",
                        unresolved_questions=["Provide an external_user_id for the user to connect."],
                    )
                response = client.create_connect_token(
                    external_user_id,
                    allowed_origins=extras.get("allowed_origins") or None,
                    error_redirect_uri=_clean_text(extras.get("error_redirect_uri") or ""),
                    expires_in=extras.get("expires_in"),
                    scope=_clean_text(extras.get("scope") or ""),
                    success_redirect_uri=_clean_text(extras.get("success_redirect_uri") or ""),
                    webhook_uri=_clean_text(extras.get("webhook_uri") or ""),
                    allow_progressive_scopes=bool(extras.get("allow_progressive_scopes")),
                )
                return CapabilityResult(
                    status="success",
                    capability=self.name,
                    output=response,
                    confidence=1.0,
                    message="Created a Pipedream Connect token.",
                    artifacts=[response.get("connect_link_url", "")] if isinstance(response, dict) and response.get("connect_link_url") else [],
                )

            if operation == "list_accounts":
                response = client.list_accounts(
                    external_user_id=external_user_id,
                    app=_clean_text(extras.get("app") or ""),
                    include_credentials=bool(extras.get("include_credentials", False)),
                    limit=extras.get("limit"),
                    after=_clean_text(extras.get("after") or ""),
                    before=_clean_text(extras.get("before") or ""),
                    oauth_app_id=_clean_text(extras.get("oauth_app_id") or ""),
                )
                return CapabilityResult(
                    status="success",
                    capability=self.name,
                    output=response,
                    confidence=0.95,
                    message="Fetched connected accounts.",
                )

            if operation == "run_action":
                action_id = _clean_text(extras.get("action_id") or "")
                if not action_id:
                    return CapabilityResult(
                        status="needs_input",
                        capability=self.name,
                        confidence=0.0,
                        message="action_id is required to run a Pipedream action",
                        unresolved_questions=["Provide the Pipedream action ID to run."],
                    )
                if not external_user_id:
                    return CapabilityResult(
                        status="needs_input",
                        capability=self.name,
                        confidence=0.0,
                        message="external_user_id is required to run a Connect action",
                        unresolved_questions=["Provide an external_user_id for the user."],
                    )
                response = client.run_action(
                    action_id,
                    external_user_id=external_user_id,
                    version=_clean_text(extras.get("version") or ""),
                    configured_props=extras.get("configured_props") or {},
                    dynamic_props_id=_clean_text(extras.get("dynamic_props_id") or ""),
                    stash_id=_clean_text(extras.get("stash_id") or ""),
                )
                return CapabilityResult(
                    status="success",
                    capability=self.name,
                    output=response,
                    confidence=0.95,
                    message="Ran the requested Pipedream action.",
                )

            if operation == "invoke_workflow":
                workflow_id = _clean_text(extras.get("workflow_id") or "")
                if not workflow_id:
                    return CapabilityResult(
                        status="needs_input",
                        capability=self.name,
                        confidence=0.0,
                        message="workflow_id is required to invoke a workflow",
                        unresolved_questions=["Provide the workflow ID to invoke."],
                    )
                response = client.invoke_workflow(workflow_id)
                return CapabilityResult(
                    status="success",
                    capability=self.name,
                    output=response,
                    confidence=0.9,
                    message="Invoked the workflow.",
                )

            return CapabilityResult(
                status="partial",
                capability=self.name,
                confidence=0.5,
                message="Pipedream is configured. Use create_connect_token, list_accounts, run_action, or invoke_workflow.",
                output={"config": client.summary()},
            )
        except Exception as exc:
            return CapabilityResult(
                status="failed",
                capability=self.name,
                confidence=0.0,
                message=str(exc),
                observations=[{"step": "pipedream_connect_error", "operation": operation}],
            )

