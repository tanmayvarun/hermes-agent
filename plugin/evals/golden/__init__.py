"""Module-layered golden corpus (eval-only, versioned).

See ``README.md`` and ``corpus/v1/_manifest.json``.
"""

from __future__ import annotations

from plugin.evals.golden.schema import (
    GOLDEN_MODULES,
    DEFAULT_GOLDEN_DIR,
    load_module_cases,
    load_manifest,
)

__all__ = [
    "GOLDEN_MODULES",
    "DEFAULT_GOLDEN_DIR",
    "load_module_cases",
    "load_manifest",
]
