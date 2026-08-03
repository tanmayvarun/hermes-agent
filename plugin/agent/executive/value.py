"""One information-value function the executive scores moves with.

The design asks for a single scoring function of the form

    value = P(progress)·progress_value
          + alpha·information_gain
          + beta·reversibility
          - gamma·risk
          - delta·cost
          - epsilon·repeat_penalty

Before this, value signals were scattered: the policy layer had its own
weights, the meta-action selector used fixed constants, and nothing combined
progress with information gain and a repeat penalty in one place. This module is
that one place, so the meta-action selector and any capability ranker apply the
same trade-off rather than three different ones.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

# Weights for the linear combination. Deliberately modest on information gain so
# the agent does not become endlessly curious at the expense of finishing.
ALPHA_INFO = 0.6
BETA_REVERSIBLE = 0.15
GAMMA_RISK = 0.7
DELTA_COST = 0.2
EPSILON_REPEAT = 0.8

_COST_UNIT = {"low": 0.1, "medium": 0.4, "high": 0.8}


@dataclass
class ValueInputs:
    """Everything the value of a move depends on, all 0..1 unless noted."""

    progress_probability: float = 0.0  # P(this advances the goal)
    progress_value: float = 1.0  # how much reaching it is worth
    information_gain: float = 0.0  # expected reduction in blocking uncertainty
    reversibility: float = 1.0  # 1 fully reversible, 0 irreversible
    risk: float = 0.0  # chance/severity of an unrecoverable wrong outcome
    cost: str = "low"  # low | medium | high (mapped to a unit cost)
    repeated: bool = False  # this move only re-tries something already settled


def action_value(inp: ValueInputs) -> float:
    """The scalar the executive maximises when choosing a move."""
    cost_unit = _COST_UNIT.get(str(inp.cost or "low").lower(), 0.1)
    score = (
        max(0.0, min(1.0, inp.progress_probability)) * float(inp.progress_value)
        + ALPHA_INFO * max(0.0, min(1.0, inp.information_gain))
        + BETA_REVERSIBLE * max(0.0, min(1.0, inp.reversibility))
        - GAMMA_RISK * max(0.0, min(1.0, inp.risk))
        - DELTA_COST * cost_unit
        - (EPSILON_REPEAT if inp.repeated else 0.0)
    )
    return round(score, 4)


def value_breakdown(inp: ValueInputs) -> Dict[str, float]:
    """The component contributions, for logging why a move scored as it did."""
    cost_unit = _COST_UNIT.get(str(inp.cost or "low").lower(), 0.1)
    return {
        "progress": round(inp.progress_probability * inp.progress_value, 4),
        "information": round(ALPHA_INFO * inp.information_gain, 4),
        "reversibility": round(BETA_REVERSIBLE * inp.reversibility, 4),
        "risk": round(-GAMMA_RISK * inp.risk, 4),
        "cost": round(-DELTA_COST * cost_unit, 4),
        "repeat": round(-EPSILON_REPEAT if inp.repeated else 0.0, 4),
        "total": action_value(inp),
    }
