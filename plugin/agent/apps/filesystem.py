"""A second domain for the executive loop: the macOS file system (Finder).

The point of this overlay is not feature-parity with WhatsApp; it is to prove
the executive machinery -- workspace, sufficiency, meta-actions, questions, the
capability registry -- is domain-general. Finder is a good second domain: it
has a searchable surface (the window), addressable entities (files/folders), a
reveal affordance (right-click), and a gated irreversible action (move to
Trash / overwrite), which maps onto the same capability substrates WhatsApp uses
without sharing any of WhatsApp's vocabulary.

Goal shapes it understands:
- ``fs_open_file``   : make a named file/folder reachable and open it.
- ``fs_locate_file`` : make a named file reachable (no open required).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from plugin.agent.apps.generic import GenericOverlay, _label_matches, _visible_entities
from plugin.agent.features import StateFeatures
from plugin.agent.goal import Goal, GoalStatus
from plugin.worldmodel.entities.entity import Entity
from plugin.worldmodel.model import WorldModel

FS_GOAL_KINDS = ("fs_open_file", "fs_locate_file")


class FilesystemOverlay(GenericOverlay):
    app_names: List[str] = ["finder", "Finder"]

    # Finder's find is Cmd+F and scopes to the current window/location.
    find_affordance = ("cmd", "f")
    dismiss_affordance = ("escape",)
    reveal_mode = "context_click"

    def affordance_priors(self, surface: str) -> List[Dict[str, Any]]:
        # The Trash/overwrite confirmation is the one gated control Finder hides
        # behind a chosen target, analogous to the picker's Send in WhatsApp.
        if str(surface or "").strip().lower() != "confirm_delete":
            return []
        return [
            {
                "id": "confirm_trash",
                "label": "Move to Trash",
                "family": "commit_irreversible",
                "available_after": "resolve_entity",
                "probability": 0.9,
                "basis": "finder confirm dialog enables the destructive button once a file is chosen",
            }
        ]

    def _target_name(self, goal: Goal) -> str:
        return (goal.link_query or goal.contact or goal.target_contact or "").strip()

    def _file_open(self, world: WorldModel, name: str) -> bool:
        """A quicklook/preview or an editor window for the file counts as open."""
        hints = getattr(world, "overlay_hints", None) or {}
        opened = str(hints.get("fs_opened_file") or "").strip().lower()
        return bool(name) and name.lower() in opened

    def features(
        self, world: WorldModel, goal: Goal, *, worldview_score: float = 1.0
    ) -> StateFeatures:
        ents = _visible_entities(world)
        name = self._target_name(goal)
        reachable = any(_label_matches(getattr(e, "label", ""), name) for e in ents)
        opened = self._file_open(world, name)
        progress = 1.0 if opened else (0.6 if reachable else 0.0)
        return StateFeatures(
            app=world.active_app or "finder",
            screen_kind=self._surface(world),
            screen_bucket="list",
            has_named_entity=reachable,
            conversation_open=opened,
            worldview_score=worldview_score,
            goal_progress=progress,
            extras={"fs_target": name, "fs_reachable": reachable, "fs_opened": opened},
        )

    def goal_progress(self, world: WorldModel, goal: Goal) -> Dict[str, Any]:
        f = self.features(world, goal)
        return {
            "progress": f.goal_progress,
            "bits": {
                "reachable": f.has_named_entity,
                "opened": f.conversation_open,
            },
            "features": f.to_dict(),
        }

    def evaluate_goal(self, goal: Goal, world: WorldModel) -> GoalStatus:
        name = self._target_name(goal)
        if not name:
            return GoalStatus(impossible=True, reason="no target file named in goal")
        ents = _visible_entities(world)
        reachable = any(_label_matches(getattr(e, "label", ""), name) for e in ents)
        opened = self._file_open(world, name)
        evidence = {"target": name, "reachable": reachable, "opened": opened}

        if goal.kind == "fs_locate_file":
            if reachable:
                return GoalStatus(succeeded=True, reason=f"{name} reachable", evidence=evidence)
            return GoalStatus(succeeded=False, reason=f"{name} not yet reachable", evidence=evidence)

        if goal.kind == "fs_open_file":
            if opened:
                return GoalStatus(succeeded=True, reason=f"{name} open", evidence=evidence)
            return GoalStatus(succeeded=False, reason=f"{name} not open yet", evidence=evidence)

        return GoalStatus(impossible=True, reason=f"unknown fs goal kind {goal.kind}")

    def resolve_target(
        self, world: WorldModel, semantic: str, action: str
    ) -> Optional[Entity]:
        # Files disambiguate by name; the generic label match is exactly right.
        return super().resolve_target(world, semantic, action)
