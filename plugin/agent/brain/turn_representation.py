"""Provisional TurnRepresentation — before semantic commitment."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TurnRepresentation:
    """Intermediate interpretation — Goal is not the first rich semantic object."""

    raw_turn: str = ""
    detected_mentions: list[str] = field(default_factory=list)
    possible_entity_types: list[str] = field(default_factory=list)
    action_hints: list[str] = field(default_factory=list)
    objects: list[str] = field(default_factory=list)
    channels: list[str] = field(default_factory=list)
    temporal_cues: list[str] = field(default_factory=list)
    project_topic_cues: list[str] = field(default_factory=list)
    unresolved_references: list[dict[str, Any]] = field(default_factory=list)
    interpretation_status: str = "provisional"  # provisional | committed
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_turn": self.raw_turn,
            "detected_mentions": list(self.detected_mentions),
            "possible_entity_types": list(self.possible_entity_types),
            "action_hints": list(self.action_hints),
            "objects": list(self.objects),
            "channels": list(self.channels),
            "temporal_cues": list(self.temporal_cues),
            "project_topic_cues": list(self.project_topic_cues),
            "unresolved_references": list(self.unresolved_references),
            "interpretation_status": self.interpretation_status,
            "metadata": dict(self.metadata),
        }
