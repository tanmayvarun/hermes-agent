"""The frozen screen-state corpus.

A single end-to-end success rate says something broke, never where. Diagnosing
the layers separately needs the same screens available to every layer, frozen
so a score moves only when the system does.

Fixtures are harvested from real recorded frames of the zarooratwala run --
the exact multimodal packet the model was given and the reply it produced --
and stored without their screenshots. The images are hundreds of megabytes and
regenerable from the recording directory; the packet, the reply and the
AX-derived shadow state are what the offline metrics read. A fixture that
needs pixels says so through ``screenshot.available`` rather than silently
scoring a frame the metric could not see.

Discipline this file exists to enforce: every discovered failure becomes a
permanent fixture. Traits mark the failure classes so a harvest can be checked
for coverage instead of hoping the sample happened to include them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

CORPUS_VERSION = 1

DEFAULT_RECORD_DIR = "plugin/experiments/fixtures/perceptor/live_forward"
DEFAULT_CORPUS_DIR = "plugin/evals/fixtures"

# Failure classes worth keeping on purpose. A harvest that contains none of
# these is a happy-path sample, and happy paths do not catch regressions.
TRAIT_SHELL_ONLY = "shell_only"           # AX sees the window and nothing else
TRAIT_NO_AX_CONTENT = "no_ax_content"     # zero app content nodes
TRAIT_NO_SCREENSHOT = "no_screenshot"     # the model had to answer blind
TRAIT_REPEATED_READING = "repeated_reading"  # screen unchanged after an action
TRAIT_LAST_ACTION_FAILED = "last_action_failed"
TRAIT_SURFACE_DISPUTED = "surface_disputed"  # model and AX disagree on surface
TRAIT_HAS_OBJECTS = "has_objects"
TRAIT_TARGET_VISIBLE = "target_visible"
# Recorded before the unified packet existed; a different contract entirely.
TRAIT_LEGACY_PACKET = "legacy_packet"

FAILURE_TRAITS: Tuple[str, ...] = (
    TRAIT_SHELL_ONLY,
    TRAIT_NO_AX_CONTENT,
    TRAIT_NO_SCREENSHOT,
    TRAIT_REPEATED_READING,
    TRAIT_LAST_ACTION_FAILED,
    TRAIT_SURFACE_DISPUTED,
)


@dataclass
class Fixture:
    """One frozen screen state, with everything a metric may read."""

    id: str
    phase: str
    packet: Dict[str, Any]
    response: Optional[Dict[str, Any]] = None
    shadow: Dict[str, Any] = field(default_factory=dict)
    screenshot: Dict[str, Any] = field(default_factory=dict)
    annotation: Dict[str, Any] = field(default_factory=dict)
    traits: Tuple[str, ...] = ()
    source: Dict[str, Any] = field(default_factory=dict)

    # --- convenient views over the packet, so metrics do not all re-dig ---

    @property
    def goal(self) -> Dict[str, Any]:
        return dict(self.packet.get("goal") or {})

    @property
    def observation(self) -> Dict[str, Any]:
        return dict(self.packet.get("observation") or {})

    @property
    def ax_evidence(self) -> List[Dict[str, Any]]:
        return [n for n in (self.observation.get("ax_evidence") or []) if isinstance(n, dict)]

    @property
    def prior_document(self) -> Dict[str, Any]:
        return dict(self.packet.get("world_model") or {})

    @property
    def document(self) -> Dict[str, Any]:
        return dict((self.response or {}).get("world_model") or {})

    @property
    def next_action(self) -> Dict[str, Any]:
        return dict((self.response or {}).get("next_action") or {})

    @property
    def next_actions(self) -> List[Dict[str, Any]]:
        ranked = [a for a in ((self.response or {}).get("next_actions") or []) if isinstance(a, dict)]
        if ranked:
            return ranked
        head = self.next_action
        return [head] if head else []

    @property
    def objects(self) -> List[Dict[str, Any]]:
        return [o for o in (self.document.get("objects") or []) if isinstance(o, dict)]

    @property
    def confidence(self) -> float:
        try:
            return float((self.response or {}).get("confidence") or 0.0)
        except (TypeError, ValueError):
            return 0.0

    @property
    def has_screenshot(self) -> bool:
        return bool(self.screenshot.get("recorded"))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "corpus_version": CORPUS_VERSION,
            "id": self.id,
            "phase": self.phase,
            "traits": list(self.traits),
            "source": self.source,
            "screenshot": self.screenshot,
            "packet": self.packet,
            "response": self.response,
            "shadow_task_state": self.shadow,
            "annotation": self.annotation,
        }

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "Fixture":
        return cls(
            id=str(raw.get("id") or ""),
            phase=str(raw.get("phase") or ""),
            packet=dict(raw.get("packet") or {}),
            response=raw.get("response") if isinstance(raw.get("response"), dict) else None,
            shadow=dict(raw.get("shadow_task_state") or {}),
            screenshot=dict(raw.get("screenshot") or {}),
            annotation=dict(raw.get("annotation") or {}),
            traits=tuple(str(t) for t in (raw.get("traits") or [])),
            source=dict(raw.get("source") or {}),
        )


def model_surface(fixture: Fixture) -> str:
    return str(fixture.document.get("surface") or "").strip().lower()


def shadow_surface(fixture: Fixture) -> str:
    """The AX-derived screen label, which was never shown to the model.

    Independence is the whole point: a ground truth taken from the reply being
    scored would make every metric agree with itself.
    """
    raw = str(fixture.shadow.get("wa_screen") or "").strip().lower()
    aliases = {
        "list": "chat_list",
        "search_results": "search",
        "chat": "conversation",
        "picker": "forward_picker",
        "unknown": "",
        "": "",
    }
    return aliases.get(raw, raw)


def traits_for(frame: Dict[str, Any]) -> Tuple[str, ...]:
    packet = frame.get("packet") or {}
    observation = packet.get("observation") or {}
    response = frame.get("response") or {}
    document = response.get("world_model") or {}
    shadow = frame.get("shadow_task_state") or {}
    found: List[str] = []

    if "observation" not in packet:
        found.append(TRAIT_LEGACY_PACKET)
    node_count = int(observation.get("ax_node_count") or 0)
    content = int(observation.get("ax_content_node_count") or 0)
    if content == 0:
        found.append(TRAIT_NO_AX_CONTENT)
    if content == 0 and node_count <= 3:
        found.append(TRAIT_SHELL_ONLY)
    if not frame.get("screenshot"):
        found.append(TRAIT_NO_SCREENSHOT)
    if int(packet.get("identical_readings_in_a_row") or 0) > 1:
        found.append(TRAIT_REPEATED_READING)
    result = ((packet.get("last_action") or {}).get("result") or {})
    if result and result.get("ok") is False:
        found.append(TRAIT_LAST_ACTION_FAILED)
    if document.get("objects"):
        found.append(TRAIT_HAS_OBJECTS)
    if (response.get("observed_state") or {}).get("target_object_visible"):
        found.append(TRAIT_TARGET_VISIBLE)

    ax_screen = str(shadow.get("wa_screen") or "").strip().lower()
    model_screen = str(document.get("surface") or "").strip().lower()
    if ax_screen and model_screen and content > 0:
        normalized = {"list": "chat_list", "search_results": "search", "chat": "conversation"}
        if normalized.get(ax_screen, ax_screen) != model_screen:
            found.append(TRAIT_SURFACE_DISPUTED)
    return tuple(found)


def bucket_of(frame: Dict[str, Any]) -> str:
    """Where a frame belongs in the corpus: the task stage it was taken in."""
    phase = str((frame.get("shadow_task_state") or {}).get("phase") or "").strip().upper()
    surface = str(
        ((frame.get("response") or {}).get("world_model") or {}).get("surface") or ""
    ).strip().lower()
    if surface == "forward_picker":
        return "select_destination"
    if surface == "context_menu":
        return "open_forward"
    if phase in {"PRECLEAR", ""} and surface in {"", "blank"}:
        return "preclear"
    if surface == "conversation":
        return "find_link"
    if phase == "FIND_LINK":
        return "find_link"
    if surface in {"search", "chat_list"}:
        return "open_source"
    return "open_source"


def load_frames(directory: str | Path) -> List[Dict[str, Any]]:
    """Read recorded perceptor frames, newest last."""
    root = Path(directory)
    frames: List[Dict[str, Any]] = []
    for path in sorted(root.glob("frame_*.json")):
        try:
            frames.append(json.loads(path.read_text()))
        except (OSError, ValueError):
            continue
    return frames


def fixture_from_frame(frame: Dict[str, Any], *, run: str = "") -> Fixture:
    index = int(frame.get("frame") or 0)
    bucket = bucket_of(frame)
    packet = dict(frame.get("packet") or {})
    image_size = (packet.get("observation") or {}).get("image_size") or []
    return Fixture(
        id=f"{bucket}/frame_{index:04d}",
        phase=bucket,
        packet=packet,
        response=frame.get("response") if isinstance(frame.get("response"), dict) else None,
        shadow=dict(frame.get("shadow_task_state") or {}),
        screenshot={
            "recorded": bool(frame.get("screenshot")),
            "name": str(frame.get("screenshot") or ""),
            "image_size": list(image_size),
        },
        traits=traits_for(frame),
        source={
            "run": run,
            "frame": index,
            "captured_at": str(frame.get("captured_at") or ""),
        },
    )


def select_frames(
    frames: Sequence[Dict[str, Any]],
    *,
    per_bucket: int = 8,
    per_trait: int = 3,
) -> List[Dict[str, Any]]:
    """Pick a small, deliberately unbalanced sample.

    Even coverage of a run would be mostly the states it spent longest in --
    which is to say the states where it was stuck, repeating itself. The sample
    is capped per stage so every stage is represented, then topped up per
    failure trait so the interesting minority survives.
    """
    # Frames recorded under the pre-unified packet have no observation block
    # at all. Freezing them would be freezing a contract nothing implements.
    frames = [f for f in frames if isinstance((f.get("packet") or {}).get("observation"), dict)]
    chosen: Dict[int, Dict[str, Any]] = {}
    counts: Dict[str, int] = {}
    for frame in frames:
        bucket = bucket_of(frame)
        if counts.get(bucket, 0) >= per_bucket:
            continue
        counts[bucket] = counts.get(bucket, 0) + 1
        chosen[int(frame.get("frame") or 0)] = frame

    trait_counts: Dict[str, int] = {}
    for frame in frames:
        marks = traits_for(frame)
        for trait in FAILURE_TRAITS:
            if trait not in marks:
                continue
            if trait_counts.get(trait, 0) >= per_trait:
                continue
            trait_counts[trait] = trait_counts.get(trait, 0) + 1
            chosen[int(frame.get("frame") or 0)] = frame
    return [chosen[key] for key in sorted(chosen)]


def coverage_report(fixtures: Sequence[Fixture]) -> Dict[str, Any]:
    """What the corpus contains, so a gap is visible before it hides a bug."""
    phases: Dict[str, int] = {}
    traits: Dict[str, int] = {}
    for fixture in fixtures:
        phases[fixture.phase] = phases.get(fixture.phase, 0) + 1
        for trait in fixture.traits:
            traits[trait] = traits.get(trait, 0) + 1
    missing = [t for t in FAILURE_TRAITS if t not in traits]
    return {
        "count": len(fixtures),
        "phases": dict(sorted(phases.items())),
        "traits": dict(sorted(traits.items())),
        "missing_failure_traits": missing,
        "with_screenshot": sum(1 for f in fixtures if f.has_screenshot),
        "with_response": sum(1 for f in fixtures if f.response),
    }


def write_fixture(root: str | Path, fixture: Fixture) -> Path:
    path = Path(root) / f"{fixture.id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(fixture.to_dict(), indent=2, ensure_ascii=False) + "\n")
    return path


def load_fixtures(root: str | Path = DEFAULT_CORPUS_DIR) -> List[Fixture]:
    base = Path(root)
    out: List[Fixture] = []
    for path in sorted(base.rglob("*.json")):
        if path.name.startswith("_"):
            continue
        try:
            raw = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if not isinstance(raw, dict) or "packet" not in raw:
            continue
        out.append(Fixture.from_dict(raw))
    return out


def fixtures_by_phase(fixtures: Iterable[Fixture]) -> Dict[str, List[Fixture]]:
    out: Dict[str, List[Fixture]] = {}
    for fixture in fixtures:
        out.setdefault(fixture.phase, []).append(fixture)
    return out
