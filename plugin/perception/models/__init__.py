"""Generic screen-perception model adapters.

These adapters are intentionally model-family agnostic.  The core perception
stack can register OmniParser-like parsers, grounding-only models, or any other
screen-to-elements backend without baking app-specific policy into the leaf.
"""

from .base import ScreenElement, ScreenModelRun, ScreenParser, ScreenModelStats
from .engines import CallableScreenParser, OmniParserV2Parser, ScreenParserAdapter
from .recovery import maybe_recover_with_screen_models, recover_observation_with_screen_models
from .registry import clear_screen_models, list_screen_models, register_screen_model
from .selector import ScreenModelSelector, get_screen_model_selector

__all__ = [
    "CallableScreenParser",
    "OmniParserV2Parser",
    "ScreenElement",
    "ScreenModelRun",
    "ScreenModelSelector",
    "ScreenModelStats",
    "ScreenParser",
    "ScreenParserAdapter",
    "clear_screen_models",
    "list_screen_models",
    "get_screen_model_selector",
    "register_screen_model",
    "maybe_recover_with_screen_models",
    "recover_observation_with_screen_models",
]
