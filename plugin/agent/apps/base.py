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
