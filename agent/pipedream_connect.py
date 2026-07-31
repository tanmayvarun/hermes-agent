"""Reusable Pipedream Connect client.

This module centralizes the API wiring needed to:

* create Connect tokens for a specific external user
* list that user's connected accounts
* run Connect actions on behalf of the user
* invoke standard Pipedream workflows

Other modules should depend on this client rather than hand-rolling HTTP
requests so the auth shape, headers, and endpoint paths stay uniform.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = "https://api.pipedream.com/v1"
DEFAULT_PROJECT_ENVIRONMENT = "development"


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    if hasattr(value, "to_dict") and callable(value.to_dict):
        try:
            return _json_safe(value.to_dict())
        except Exception:
            pass
    if hasattr(value, "__dict__"):
        try:
            return _json_safe(vars(value))
        except Exception:
            pass
    return str(value)


@dataclass(frozen=True)
class PipedreamConnectConfig:
    project_id: str
    api_token: str
    environment: str = DEFAULT_PROJECT_ENVIRONMENT
    base_url: str = DEFAULT_BASE_URL

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None) -> "PipedreamConnectConfig":
        env_map = dict(env or os.environ)
        return cls(
            project_id=_clean_text(env_map.get("PIPEDREAM_PROJECT_ID") or ""),
            api_token=_clean_text(env_map.get("PIPEDREAM_API_TOKEN") or env_map.get("PIPEDREAM_TOKEN") or ""),
            environment=_clean_text(env_map.get("PIPEDREAM_PROJECT_ENVIRONMENT") or DEFAULT_PROJECT_ENVIRONMENT) or DEFAULT_PROJECT_ENVIRONMENT,
            base_url=_clean_text(env_map.get("PIPEDREAM_BASE_URL") or DEFAULT_BASE_URL) or DEFAULT_BASE_URL,
        )

    @property
    def configured(self) -> bool:
        return bool(self.project_id and self.api_token)


class PipedreamConnectClient:
    def __init__(self, config: PipedreamConnectConfig) -> None:
        self.config = config

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None) -> "PipedreamConnectClient":
        return cls(PipedreamConnectConfig.from_env(env))

    def _require_config(self) -> None:
        if not self.config.project_id:
            raise RuntimeError("PIPEDREAM_PROJECT_ID is required")
        if not self.config.api_token:
            raise RuntimeError("PIPEDREAM_API_TOKEN is required")

    def _headers(self, *, json_body: bool = False) -> Dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.config.api_token}",
            "x-pd-environment": self.config.environment,
        }
        if json_body:
            headers["Content-Type"] = "application/json"
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        query: Optional[Mapping[str, Any]] = None,
        body: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        self._require_config()
        url = self.config.base_url.rstrip("/") + "/" + path.lstrip("/")
        if query:
            query_string = urlencode([(key, str(value)) for key, value in query.items() if value is not None])
            if query_string:
                url = f"{url}?{query_string}"
        data = None
        if body is not None:
            data = json.dumps(_json_safe(body), ensure_ascii=False).encode("utf-8")
        request = Request(url, data=data, headers=self._headers(json_body=body is not None), method=method.upper())
        try:
            with urlopen(request, timeout=60) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Pipedream API {method.upper()} {path} failed with HTTP {exc.code}: {detail or exc.reason}"
            ) from exc
        except URLError as exc:
            raise RuntimeError(f"Pipedream API {method.upper()} {path} failed: {exc.reason}") from exc
        if not raw.strip():
            return {}
        try:
            payload = json.loads(raw)
        except Exception as exc:
            raise RuntimeError(f"Pipedream API {method.upper()} {path} returned non-JSON response") from exc
        if not isinstance(payload, dict):
            raise RuntimeError(f"Pipedream API {method.upper()} {path} returned unexpected payload")
        return payload

    def create_connect_token(
        self,
        external_user_id: str,
        *,
        allowed_origins: Optional[Sequence[str]] = None,
        error_redirect_uri: str = "",
        expires_in: Optional[int] = None,
        scope: str = "",
        success_redirect_uri: str = "",
        webhook_uri: str = "",
        allow_progressive_scopes: bool = False,
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {"external_user_id": external_user_id}
        if allowed_origins:
            body["allowed_origins"] = list(allowed_origins)
        if error_redirect_uri:
            body["error_redirect_uri"] = error_redirect_uri
        if expires_in is not None:
            body["expires_in"] = int(expires_in)
        if scope:
            body["scope"] = scope
        if success_redirect_uri:
            body["success_redirect_uri"] = success_redirect_uri
        if webhook_uri:
            body["webhook_uri"] = webhook_uri
        if allow_progressive_scopes:
            body["allow_progressive_scopes"] = True
        return self._request("POST", f"/connect/{self.config.project_id}/tokens", body=body)

    def list_accounts(
        self,
        *,
        external_user_id: str = "",
        app: str = "",
        include_credentials: bool = False,
        limit: Optional[int] = None,
        after: str = "",
        before: str = "",
        oauth_app_id: str = "",
    ) -> Dict[str, Any]:
        query: Dict[str, Any] = {}
        if external_user_id:
            query["external_user_id"] = external_user_id
        if app:
            query["app"] = app
        if include_credentials:
            query["include_credentials"] = "true"
        if limit is not None:
            query["limit"] = int(limit)
        if after:
            query["after"] = after
        if before:
            query["before"] = before
        if oauth_app_id:
            query["oauth_app_id"] = oauth_app_id
        return self._request("GET", f"/connect/{self.config.project_id}/accounts", query=query)

    def run_action(
        self,
        action_id: str,
        *,
        external_user_id: str,
        version: str = "",
        configured_props: Optional[Mapping[str, Any]] = None,
        dynamic_props_id: str = "",
        stash_id: str = "",
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {"id": action_id, "external_user_id": external_user_id}
        if version:
            body["version"] = version
        if configured_props:
            body["configured_props"] = dict(configured_props)
        if dynamic_props_id:
            body["dynamic_props_id"] = dynamic_props_id
        if stash_id:
            body["stash_id"] = stash_id
        return self._request("POST", f"/connect/{self.config.project_id}/actions/run", body=body)

    def invoke_workflow(self, workflow_id: str) -> Dict[str, Any]:
        return self._request("POST", f"/workflows/{workflow_id}/invoke")

    def summary(self) -> Dict[str, Any]:
        return {
            "project_id": self.config.project_id,
            "environment": self.config.environment,
            "configured": self.config.configured,
            "base_url": self.config.base_url,
        }

