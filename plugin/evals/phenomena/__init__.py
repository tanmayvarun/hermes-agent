"""Phenomenon-organized golden curriculum from live failures.

WhatsApp/ZarooratWala is a discovery surface — fixtures are tagged by
*phenomenon* (environmental_blocker, prerequisite_child, …) and scored at the
layer where the failure occurred.
"""

from plugin.evals.phenomena.schema import (
    PHENOMENON_FAMILIES,
    GoldenFixture,
    load_all_fixtures,
    load_family_fixtures,
    load_manifest,
)

__all__ = [
    "PHENOMENON_FAMILIES",
    "GoldenFixture",
    "load_all_fixtures",
    "load_family_fixtures",
    "load_manifest",
]
