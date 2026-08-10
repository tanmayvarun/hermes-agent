"""Application composition root — register domain adapters outside core.

Generic executive / binder / grounder must never import WhatsApp / Gmail / etc.
Composition loads available adapters at runtime start.
"""

from __future__ import annotations

_COMPOSED = False


def compose_domain_adapters() -> None:
    """Idempotent registration of domain IdentityEvidenceProviders."""
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
    _COMPOSED = True
