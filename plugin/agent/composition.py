"""Application composition root — register domain adapters outside core.

Generic executive / binder / grounder must never import WhatsApp / Gmail / etc.
Composition loads available adapters at runtime start.
"""

from __future__ import annotations

from typing import Any, Dict, List

_COMPOSED = False
_COMPOSITION_DIAGNOSTICS: List[Dict[str, Any]] = []


def composition_diagnostics() -> List[Dict[str, Any]]:
    return list(_COMPOSITION_DIAGNOSTICS)


def compose_domain_adapters() -> None:
    """Idempotent registration of domain IdentityEvidenceProviders + method providers."""
    global _COMPOSED
    if _COMPOSED:
        return
    try:
        from plugin.agent.identity_evidence.whatsapp import (
            ensure_whatsapp_provider_registered,
        )

        ensure_whatsapp_provider_registered()
        _COMPOSITION_DIAGNOSTICS.append(
            {"event": "identity_provider_composition", "provider": "whatsapp", "ok": True}
        )
    except Exception as exc:
        _COMPOSITION_DIAGNOSTICS.append(
            {
                "event": "identity_provider_composition",
                "provider": "whatsapp",
                "ok": False,
                "exception": f"{type(exc).__name__}: {exc}",
            }
        )
    try:
        from plugin.agent.providers.computer_use import (
            ensure_computer_use_provider_registered,
        )

        diag = dict(ensure_computer_use_provider_registered() or {})
        diag.setdefault("event", "computer_use_composition")
        diag.setdefault("ok", bool(diag.get("runnable")))
        _COMPOSITION_DIAGNOSTICS.append(diag)
    except Exception as exc:
        _COMPOSITION_DIAGNOSTICS.append(
            {
                "event": "computer_use_composition",
                "ok": False,
                "runnable": False,
                "substrate_composed": False,
                "provider_registered": False,
                "executor_registered": False,
                "reason": "composition_exception",
                "exception": f"{type(exc).__name__}: {exc}",
            }
        )
    _COMPOSED = True


def reset_composition_for_tests() -> None:
    """Test helper — allow re-compose after clearing registries."""
    global _COMPOSED
    _COMPOSED = False
    _COMPOSITION_DIAGNOSTICS.clear()
    try:
        from plugin.agent.runtime.computer_use_substrate import (
            install_computer_use_substrate,
        )

        install_computer_use_substrate(None)
    except Exception:
        pass
