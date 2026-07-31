"""Canonical model contract helpers.

The desktop UI, gateway, and CLI should all reason about the same runtime
binding.  This module turns the active config into a compact contract record
with a stable fingerprint so callers can detect when a composer default has
gone stale without guessing from model/provider strings alone.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any, Mapping, Optional

from hermes_cli.config import load_config


@dataclass(frozen=True)
class ModelContract:
    provider: str = ""
    model: str = ""
    base_url: str = ""
    api_mode: str = ""
    context_length: int = 0
    source: str = "config"
    fingerprint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _normalize_contract_payload(contract: ModelContract) -> dict[str, Any]:
    return {
        "api_mode": contract.api_mode,
        "base_url": contract.base_url,
        "context_length": int(contract.context_length or 0),
        "model": contract.model,
        "provider": contract.provider,
        "source": contract.source,
    }


def contract_fingerprint(contract: ModelContract) -> str:
    payload = json.dumps(_normalize_contract_payload(contract), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _model_section(config: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(config, Mapping):
        return {}
    model_cfg = config.get("model")
    if isinstance(model_cfg, dict):
        return dict(model_cfg)
    if isinstance(model_cfg, str) and model_cfg.strip():
        return {"default": model_cfg.strip()}
    return {}


def resolve_model_contract(
    config: Mapping[str, Any] | None = None,
    *,
    source: str = "config",
) -> ModelContract:
    """Resolve the active model contract from a config mapping.

    ``config`` may be the full config record or a model subsection.
    """
    if config is None:
        try:
            config = load_config()
        except Exception:
            config = {}

    model_cfg = _model_section(config)
    model = str(model_cfg.get("default") or model_cfg.get("model") or "").strip()
    provider = str(model_cfg.get("provider") or "").strip()
    base_url = str(model_cfg.get("base_url") or "").strip()
    api_mode = str(model_cfg.get("api_mode") or "").strip()
    context_length = 0
    raw_ctx = model_cfg.get("context_length")
    if isinstance(raw_ctx, int) and raw_ctx > 0:
        context_length = raw_ctx
    else:
        try:
            context_length = int(raw_ctx or 0)
        except (TypeError, ValueError):
            context_length = 0
        if context_length < 0:
            context_length = 0

    contract = ModelContract(
        provider=provider,
        model=model,
        base_url=base_url,
        api_mode=api_mode,
        context_length=context_length,
        source=source,
    )
    return ModelContract(**{**contract.to_dict(), "fingerprint": contract_fingerprint(contract)})
