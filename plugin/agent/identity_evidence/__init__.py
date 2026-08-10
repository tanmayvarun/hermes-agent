"""Domain IdentityEvidenceProviders.

Core role-binding consumes typed evidence only. Adapters live here.
Registration happens via ``plugin.agent.composition``, not on import.
"""

__all__ = [
    "WhatsAppUIEvidenceProvider",
    "ensure_whatsapp_provider_registered",
]


def __getattr__(name: str):
    if name in {"WhatsAppUIEvidenceProvider", "ensure_whatsapp_provider_registered"}:
        from plugin.agent.identity_evidence import whatsapp as _wa

        return getattr(_wa, name)
    raise AttributeError(name)
