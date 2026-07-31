"""Reference resolution — intent confidence over entities."""

from plugin.agent.resolver.memory import ResolutionMemory, get_resolution_memory
from plugin.agent.resolver.reference import ReferenceResolver, get_reference_resolver
from plugin.agent.resolver.resolution import AUTO_RESOLVE, OBSERVE_BAND, Resolution

__all__ = [
    "AUTO_RESOLVE",
    "OBSERVE_BAND",
    "Resolution",
    "ResolutionMemory",
    "ReferenceResolver",
    "get_reference_resolver",
    "get_resolution_memory",
]
