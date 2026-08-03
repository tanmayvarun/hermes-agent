"""App overlay protocol."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from plugin.agent.features import StateFeatures
from plugin.agent.goal import Goal, GoalStatus
from plugin.worldmodel.entities.entity import Entity
from plugin.worldmodel.model import WorldModel


@runtime_checkable
class AppOverlay(Protocol):
    app_names: List[str]

    def features(self, world: WorldModel, goal: Goal, *, worldview_score: float = 1.0) -> StateFeatures: ...

    def evaluate_goal(self, goal: Goal, world: WorldModel) -> GoalStatus: ...

    def goal_progress(self, world: WorldModel, goal: Goal) -> Dict[str, Any]: ...

    def resolve_target(self, world: WorldModel, semantic: str, action: str) -> Optional[Entity]: ...

    def view_dict(self, world: WorldModel) -> Dict[str, Any]: ...


def content_locators(overlay: Any) -> "List[Any]":
    """Resolve the content-location realizations an overlay offers.

    locate_content is an affordance, not an app feature: every host can at least
    scroll-scan, and a host that declares a find chord (or contributes its own
    realizations) gets those first. Adding an app is therefore a *declaration* —
    a ``content_locators()`` method or a ``find_affordance`` attribute — not a
    new code path in the capability or its callers.
    """
    from plugin.agent.capabilities.locate_content import (
        FindAffordance,
        default_realizations,
    )

    own = getattr(overlay, "content_locators", None)
    # An overlay may contribute its own ordered realizations (e.g. a server-side
    # query). Guard against recursing into this very function if an overlay
    # aliases it.
    if callable(own) and getattr(own, "__func__", own) is not content_locators:
        return list(own())

    find = getattr(overlay, "find_affordance", None)
    if not isinstance(find, FindAffordance):
        find = None
    return default_realizations(find=find)
