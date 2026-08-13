"""Application composition root — register domain adapters outside core.

Generic executive / binder / grounder must never import WhatsApp / Gmail / etc.
Composition loads available adapters at runtime start.
"""

from __future__ import annotations

_COMPOSED = False


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
    except Exception:
        pass
    try:
        from plugin.agent.providers.computer_use import (
            ensure_computer_use_provider_registered,
        )

        ensure_computer_use_provider_registered()
    except Exception:
        pass
    _COMPOSED = True


def reset_composition_for_tests() -> None:
    """Test helper — allow re-compose after clearing registries."""
    global _COMPOSED
    _COMPOSED = False
