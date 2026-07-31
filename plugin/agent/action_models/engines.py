"""Model-family adapters for action-prior backends."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .base import ActionModelRun, ActionProposal


def _proposal_from_mapping(mapping: Dict[str, Any], *, model_id: str, index: int) -> ActionProposal:
    coord = mapping.get("coordinate") or mapping.get("coords") or mapping.get("point")
    if isinstance(coord, (list, tuple)) and len(coord) >= 2:
        try:
            coord_val = (float(coord[0]), float(coord[1]))
        except (TypeError, ValueError):
            coord_val = None
    else:
        coord_val = None
    confidence = mapping.get("confidence", mapping.get("score", 0.0))
    risk = mapping.get("risk", 0.0)
    try:
        conf_f = float(confidence or 0.0)
    except (TypeError, ValueError):
        conf_f = 0.0
    try:
        risk_f = float(risk or 0.0)
    except (TypeError, ValueError):
        risk_f = 0.0
    return ActionProposal(
        action_family=str(mapping.get("action_family") or mapping.get("family") or ""),
        semantic_target=str(mapping.get("semantic_target") or mapping.get("target") or ""),
        action=str(mapping.get("action") or ""),
        confidence=conf_f,
        risk=risk_f,
        reversible=bool(mapping.get("reversible", True)),
        reason=str(mapping.get("reason") or mapping.get("rationale") or ""),
        coordinate=coord_val,
        model_id=str(mapping.get("model_id") or model_id),
        predicted_state=str(mapping.get("predicted_state") or mapping.get("predicted_next_state") or ""),
        meta=dict(mapping.get("meta") or {}),
    )


def proposals_from_payload(payload: Any, *, model_id: str = "") -> List[ActionProposal]:
    if isinstance(payload, dict):
        candidates = payload.get("proposals") or payload.get("actions") or payload.get("candidates") or []
        if isinstance(candidates, list):
            return [_proposal_from_mapping(item, model_id=model_id, index=i) for i, item in enumerate(candidates) if isinstance(item, dict)]
        return [_proposal_from_mapping(payload, model_id=model_id, index=0)]
    if isinstance(payload, (list, tuple)):
        return [_proposal_from_mapping(item, model_id=model_id, index=i) for i, item in enumerate(payload) if isinstance(item, dict)]
    return []


class ActionPriorAdapter:
    """Generic callable-backed action-prior wrapper."""

    model_id = "action-prior"

    def __init__(self, *, model_id: str = "action-prior", propose_fn: Optional[Callable[..., Any]] = None) -> None:
        self.model_id = model_id
        self.propose_fn = propose_fn

    def propose(
        self,
        *,
        goal: Any,
        world: Any,
        features: Any,
        candidates: Sequence[Any] = (),
        use_case: str = "",
    ) -> ActionModelRun:
        if self.propose_fn is None:
            return ActionModelRun(
                model_id=self.model_id,
                use_case=use_case,
                proposals=[],
                degraded=True,
                meta={"error": "action prior unavailable"},
            )
        raw = self.propose_fn(goal=goal, world=world, features=features, candidates=list(candidates), use_case=use_case)
        return ActionModelRun(
            model_id=self.model_id,
            use_case=use_case,
            proposals=proposals_from_payload(raw, model_id=self.model_id),
            meta={"raw_type": type(raw).__name__},
            degraded=False,
        )


class CallableActionPrior(ActionPriorAdapter):
    """Alias for readability."""


class UITARSActionPrior(ActionPriorAdapter):
    model_id = "ui-tars"


class ShowUIActionPrior(ActionPriorAdapter):
    model_id = "showui"


class OSAtlasGroundingPrior(ActionPriorAdapter):
    model_id = "os-atlas"


class OpenAIComputerUsePrior(ActionPriorAdapter):
    model_id = "openai-computer-use"


class GeminiComputerUsePrior(ActionPriorAdapter):
    model_id = "gemini-computer-use"


class AnthropicComputerUsePrior(ActionPriorAdapter):
    model_id = "anthropic-computer-use"
