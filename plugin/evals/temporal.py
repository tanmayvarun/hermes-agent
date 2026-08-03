"""Temporal-consistency layer: is the world model steady over a run?

The other eval layers score a single frame. The failures that hurt most in
practice are not single wrong frames but *instability across* frames: the agent
believes it is in Pallavi's chat, then a group thread, then Pallavi again; a
message it had a firm id for gets a new id next look; the surface oscillates
between search and conversation; the task phase slides backwards for no reason
the screen justifies.

This module reads a run's own JSONL log (as the closed-loop layer does, and for
the same reason -- these are live runs that cannot be honestly replayed offline)
and measures four things over the frame sequence:

- belief_flip_rate            : open-conversation beliefs that revert (A→B→A)
- object_identity_continuity  : ids that keep the same label across looks
- surface_stability           : surfaces that do not oscillate
- unjustified_phase_regression: phase slides back with no surface change to
                                 justify it

These are exactly the temporal properties the ExecutiveWorkspace was built to
protect (its ``_belief_flips`` / ``_phase_regressions`` counters), so this layer
is how a regression in that protection shows up in the eval report.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

# Frame-carrying record kinds, in the vocabulary the controller logs.
_SURFACE_KINDS = {"post_world_patch", "post_transition_settled_view", "observation_fused"}

# Forward phase order. Unknown phases rank -1 and are skipped, so a domain we do
# not have a ladder for simply contributes no phase-regression signal rather
# than false positives.
_FORWARD_PHASE_RANK = {
    "open_source": 0,
    "reach_source": 0,
    "find_link": 1,
    "hunt_content": 1,
    "open_forward": 2,
    "act_on_content": 2,
    "invoke_forward": 3,
    "pick_dest": 4,
    "choose_destination": 4,
    "confirm": 5,
    "committed": 5,
    "done": 6,
    "verified": 6,
}


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _records(path: Path) -> Iterable[Dict[str, Any]]:
    try:
        with path.open() as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except ValueError:
                    continue
    except OSError:
        return


@dataclass
class TemporalTrace:
    run: str
    frames: int = 0
    belief_flips: int = 0
    belief_transitions: int = 0
    surface_oscillations: int = 0
    surface_transitions: int = 0
    identity_breaks: int = 0
    identity_observations: int = 0
    unjustified_regressions: int = 0
    phase_transitions: int = 0
    examples: List[str] = field(default_factory=list)

    @property
    def belief_flip_rate(self) -> float:
        return round(self.belief_flips / self.belief_transitions, 4) if self.belief_transitions else 0.0

    @property
    def surface_stability(self) -> float:
        if not self.surface_transitions:
            return 1.0
        return round(1.0 - self.surface_oscillations / self.surface_transitions, 4)

    @property
    def object_identity_continuity(self) -> float:
        if not self.identity_observations:
            return 1.0
        return round(1.0 - self.identity_breaks / self.identity_observations, 4)

    @property
    def unjustified_phase_regression_rate(self) -> float:
        return (
            round(self.unjustified_regressions / self.phase_transitions, 4)
            if self.phase_transitions
            else 0.0
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run": self.run,
            "frames": self.frames,
            "belief_flip_rate": self.belief_flip_rate,
            "surface_stability": self.surface_stability,
            "object_identity_continuity": self.object_identity_continuity,
            "unjustified_phase_regression_rate": self.unjustified_phase_regression_rate,
            "examples": self.examples[:6],
        }


def analyse_temporal(path: str | Path) -> TemporalTrace:
    """Measure how steadily one run's beliefs held across its frames."""
    file = Path(path)
    trace = TemporalTrace(run=file.stem)

    surfaces: List[str] = []
    conversations: List[str] = []
    phases: List[int] = []
    # Surface at the frame each phase reading was taken, to judge justification.
    phase_surface: List[str] = []
    id_to_label: Dict[int, str] = {}

    last_surface = ""

    for record in _records(file):
        kind = str(record.get("kind") or "")

        if kind in _SURFACE_KINDS:
            trace.frames += 1
            surface = _norm(record.get("screen") or record.get("whatsapp_screen"))
            if surface:
                surfaces.append(surface)
                last_surface = surface
            conversations.append(_norm(record.get("open_conversation")))

        elif kind == "forward_task":
            phase = _norm(record.get("forward_phase"))
            rank = _FORWARD_PHASE_RANK.get(phase, -1)
            if rank >= 0:
                phases.append(rank)
                phase_surface.append(last_surface)

        elif kind == "world_patch":
            for entity in record.get("entities") or []:
                if not isinstance(entity, dict):
                    continue
                ent_id = entity.get("id")
                label = _norm(entity.get("label"))
                if ent_id is None or not label:
                    continue
                trace.identity_observations += 1
                prior = id_to_label.get(int(ent_id))
                if prior is not None and prior != label:
                    trace.identity_breaks += 1
                    trace.examples.append(f"id {ent_id}: {prior!r} -> {label!r}")
                id_to_label[int(ent_id)] = label

    _score_oscillation(surfaces, trace, "surface")
    _score_belief_flips(conversations, trace)
    _score_phase_regressions(phases, phase_surface, trace)
    return trace


def _score_oscillation(seq: Sequence[str], trace: TemporalTrace, _label: str) -> None:
    for i in range(1, len(seq)):
        if seq[i] == seq[i - 1]:
            continue
        trace.surface_transitions += 1
        if i >= 2 and seq[i] == seq[i - 2]:
            trace.surface_oscillations += 1
            trace.examples.append(f"surface {seq[i-2]}->{seq[i-1]}->{seq[i]}")


def _score_belief_flips(seq: Sequence[str], trace: TemporalTrace) -> None:
    # Only non-empty beliefs count: an empty open_conversation is "unknown", not
    # a claim, so moving off and back onto it is not a flip.
    for i in range(1, len(seq)):
        if not seq[i] or seq[i] == seq[i - 1]:
            continue
        trace.belief_transitions += 1
        if i >= 2 and seq[i] == seq[i - 2] and seq[i - 1]:
            trace.belief_flips += 1
            trace.examples.append(f"belief {seq[i-2]}->{seq[i-1]}->{seq[i]}")


def _score_phase_regressions(
    ranks: Sequence[int], surface_at: Sequence[str], trace: TemporalTrace
) -> None:
    for i in range(1, len(ranks)):
        if ranks[i] == ranks[i - 1]:
            continue
        trace.phase_transitions += 1
        if ranks[i] < ranks[i - 1]:
            # A regression is justified only if the screen itself moved back:
            # the surface at this reading differs from the previous one.
            surface_changed = (
                i < len(surface_at)
                and surface_at[i]
                and surface_at[i] != surface_at[i - 1]
            )
            if not surface_changed:
                trace.unjustified_regressions += 1
                trace.examples.append(f"phase rank {ranks[i-1]}->{ranks[i]} with no surface change")


def analyse_temporal_runs(paths: Sequence[str | Path]) -> List[TemporalTrace]:
    return [analyse_temporal(path) for path in paths]


def summarize_temporal(traces: Sequence[TemporalTrace]) -> Dict[str, Any]:
    total = len(traces)
    if not total:
        return {"runs": 0}

    def _mean(getter) -> float:
        return round(sum(getter(t) for t in traces) / total, 4)

    return {
        "runs": total,
        "belief_flip_rate": _mean(lambda t: t.belief_flip_rate),
        "surface_stability": _mean(lambda t: t.surface_stability),
        "object_identity_continuity": _mean(lambda t: t.object_identity_continuity),
        "unjustified_phase_regression_rate": _mean(lambda t: t.unjustified_phase_regression_rate),
        "runs_detail": [t.to_dict() for t in traces],
    }
