"""A neutral overlay for apps the agent has no specific knowledge of.

The registry used to hand back the WhatsApp overlay for *any* unrecognised app,
which quietly imposed WhatsApp's surface vocabulary, forward-picker priors and
call semantics on, say, Finder. That is the fallback bug this module fixes: an
unknown app now gets ``GenericOverlay``, which reads only what the world model
already knows and asserts nothing app-specific.

A domain overlay (WhatsApp, Filesystem) inherits this and overrides just the
parts where it genuinely knows more than the generic view.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from plugin.agent.features import StateFeatures
from plugin.agent.goal import Goal, GoalStatus
from plugin.worldmodel.entities.entity import Entity
from plugin.worldmodel.model import WorldModel


def _visible_entities(world: WorldModel) -> List[Entity]:
    try:
        return [e for e in world.entities.values() if getattr(e, "visible", True)]
    except AttributeError:
        return []


def _label_matches(label: str, needle: str) -> bool:
    label = (label or "").strip().lower()
    needle = (needle or "").strip().lower()
    return bool(needle) and needle in label


class GenericOverlay:
    """Reads the world model without assuming any particular app."""

    app_names: List[str] = ["*"]

    def affordance_priors(self, surface: str) -> List[Dict[str, Any]]:
        # The generic overlay knows no hidden controls; the frontier builder's
        # object priors are all that apply.
        return []

    # ------------------------------------------------------------------ view

    def view_dict(self, world: WorldModel) -> Dict[str, Any]:
        ents = _visible_entities(world)
        return {
            "app": world.active_app or "",
            "screen": self._surface(world),
            "open_conversation": "",
            "objects": [
                {
                    "id": getattr(e, "id", None),
                    "text": getattr(e, "label", ""),
                    "kind": getattr(e, "semantic_role", "") or getattr(e, "kind", ""),
                }
                for e in ents[:24]
            ],
        }

    def _surface(self, world: WorldModel) -> str:
        screen = getattr(world, "current_screen", None)
        if screen is not None and getattr(screen, "kind", ""):
            return str(screen.kind)
        return "unknown"

    # -------------------------------------------------------------- features

    def features(
        self, world: WorldModel, goal: Goal, *, worldview_score: float = 1.0
    ) -> StateFeatures:
        ents = _visible_entities(world)
        needle = (goal.contact or goal.target_contact or goal.link_query or "").strip()
        has_named = any(_label_matches(getattr(e, "label", ""), needle) for e in ents)
        return StateFeatures(
            app=world.active_app or "",
            screen_kind=self._surface(world),
            screen_bucket="unknown",
            has_named_entity=has_named,
            worldview_score=worldview_score,
            goal_progress=0.5 if has_named else 0.0,
        )

    # ------------------------------------------------------------ goal logic

    def goal_progress(self, world: WorldModel, goal: Goal) -> Dict[str, Any]:
        f = self.features(world, goal)
        return {"progress": f.goal_progress, "bits": {}, "features": f.to_dict()}

    def evaluate_goal(self, goal: Goal, world: WorldModel) -> GoalStatus:
        # A generic overlay cannot certify success for a domain it does not
        # understand; it reports "not yet" rather than guessing.
        if not _visible_entities(world) and not (world.active_app or ""):
            return GoalStatus(impossible=True, reason="world empty / no active app")
        return GoalStatus(succeeded=False, reason="generic overlay cannot certify success")

    def resolve_target(
        self, world: WorldModel, semantic: str, action: str
    ) -> Optional[Entity]:
        needle = (semantic or "").strip().lower()
        if not needle:
            return None
        best: Optional[Entity] = None
        for e in _visible_entities(world):
            if _label_matches(getattr(e, "label", ""), needle):
                best = e
                break
        return best
