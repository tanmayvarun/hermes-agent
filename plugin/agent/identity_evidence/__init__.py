"""Domain IdentityEvidenceProviders.

Core role-binding consumes typed evidence only. Adapters live here.
"""

from plugin.agent.identity_evidence.whatsapp import (
    WhatsAppUIEvidenceProvider,
    ensure_whatsapp_provider_registered,
)

__all__ = [
    "WhatsAppUIEvidenceProvider",
    "ensure_whatsapp_provider_registered",
]
