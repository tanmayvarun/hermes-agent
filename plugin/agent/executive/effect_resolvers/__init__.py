"""Effect → method adapters (domain-specific applicability)."""

from __future__ import annotations

from typing import Dict, List

from plugin.agent.executive.blocking import ResolvedMethod
from plugin.agent.executive.effect_resolvers import storage as storage_resolver


def effect_method_catalog() -> Dict[str, List[ResolvedMethod]]:
    """Merge domain resolvers into a prefix → methods map."""
    catalog: Dict[str, List[ResolvedMethod]] = {}
    catalog.update(storage_resolver.STORAGE_EFFECT_METHODS)
    # Stubs for future adapters — registered so SPECIFICATION fixtures can
    # resolve methods, but detectors are not yet production-wired.
    catalog.update(
        {
            "authenticated:is_true": [
                ResolvedMethod(
                    capability="authenticate", applicable_if="auth_flow_available"
                )
            ],
            "permission_granted:is_true": [
                ResolvedMethod(
                    capability="obtain_permission",
                    applicable_if="permission_prompt_available",
                )
            ],
            "dependency_present:is_true": [
                ResolvedMethod(
                    capability="install_dependency",
                    applicable_if="dependency_installable",
                )
            ],
        }
    )
    return catalog
