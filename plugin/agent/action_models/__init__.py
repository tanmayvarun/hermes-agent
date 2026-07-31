"""Generic action-prior model adapters.

These adapters are intentionally broad enough to host UI-TARS, ShowUI,
OS-Atlas-style grounding models, and hosted computer-use APIs.
"""

from .base import ActionModel, ActionModelRun, ActionProposal, ActionModelStats
from .engines import (
    AnthropicComputerUsePrior,
    CallableActionPrior,
    GeminiComputerUsePrior,
    OpenAIComputerUsePrior,
    OSAtlasGroundingPrior,
    ShowUIActionPrior,
    UITARSActionPrior,
)
from .integration import collect_action_prior_runs, action_prior_bonus, maybe_collect_action_prior_runs
from .registry import clear_action_models, list_action_models, register_action_model
from .selector import ActionModelSelector, get_action_model_selector

__all__ = [
    "ActionModel",
    "ActionModelRun",
    "ActionModelSelector",
    "ActionModelStats",
    "ActionProposal",
    "AnthropicComputerUsePrior",
    "CallableActionPrior",
    "GeminiComputerUsePrior",
    "OSAtlasGroundingPrior",
    "OpenAIComputerUsePrior",
    "ShowUIActionPrior",
    "UITARSActionPrior",
    "action_prior_bonus",
    "clear_action_models",
    "collect_action_prior_runs",
    "list_action_models",
    "get_action_model_selector",
    "maybe_collect_action_prior_runs",
    "register_action_model",
]
