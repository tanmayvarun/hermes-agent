"""Schemas for phenomenon-layered golden fixtures.

Gold is eval-only. Prefer freezing production packets (AX / world / intention /
capability inventory) over hand-cleaned prompts.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

PHENOMENA_VERSION = "v1"

# Layer families — organized by phenomenon, not by app.
PHENOMENON_FAMILIES = (
    "warning_vs_blocker",
    "executability",
    "prerequisite_children",
    "effect_resolution",
    "effect_verification",
    "resumption",
    "trajectories",
)

DEFAULT_PHENOMENA_DIR = "plugin/evals/phenomena/corpus"
DEFAULT_CANDIDATES_DIR = "plugin/evals/phenomena/eval_candidates"

# Hard-contract invariants (zero-regression). Model-quality metrics are separate.
HARD_CONTRACT_TAGS = frozenset(
    {
        "hard_contract",
        "warning_no_auto_suspend",
        "no_duplicate_child",
        "execution_ok_ne_effect",
        "no_premature_resume",
        "no_unsafe_user_cleanup",
    }
)


@dataclass
class GoldenFixture:
    """Frozen environment + executive context → expected semantics at one layer."""

    fixture_id: str
    family: str
    phenomenon: str = "environmental_blocker"
    source_run: str = ""
    app: str = ""
    note: str = ""
    tags: List[str] = field(default_factory=list)

    # Raw / production-shaped evidence (paths or inline).
    observation_texts: List[str] = field(default_factory=list)
    system_facts: Dict[str, Any] = field(default_factory=dict)
    view: Dict[str, Any] = field(default_factory=dict)
    features: Dict[str, Any] = field(default_factory=dict)
    parent_intention: Dict[str, Any] = field(default_factory=dict)
    world_before: Dict[str, Any] = field(default_factory=dict)
    resources: List[Dict[str, Any]] = field(default_factory=list)
    offered_capabilities: List[str] = field(default_factory=list)

    # Optional artifact refs (screenshots stay out of git when large).
    artifacts: Dict[str, str] = field(default_factory=dict)

    # Expected semantics for this layer.
    gold: Dict[str, Any] = field(default_factory=dict)
    forbidden: List[str] = field(default_factory=list)

    # Trajectory frames (family=trajectories only).
    frames: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "family": self.family,
            "phenomenon": self.phenomenon,
            "source_run": self.source_run,
            "app": self.app,
            "note": self.note,
            "tags": list(self.tags),
            "observation_texts": list(self.observation_texts),
            "system_facts": dict(self.system_facts),
            "view": dict(self.view),
            "features": dict(self.features),
            "parent_intention": dict(self.parent_intention),
            "world_before": dict(self.world_before),
            "resources": list(self.resources),
            "offered_capabilities": list(self.offered_capabilities),
            "artifacts": dict(self.artifacts),
            "gold": dict(self.gold),
            "forbidden": list(self.forbidden),
            "frames": list(self.frames),
        }

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "GoldenFixture":
        return cls(
            fixture_id=str(raw.get("fixture_id") or raw.get("id") or ""),
            family=str(raw.get("family") or ""),
            phenomenon=str(raw.get("phenomenon") or "environmental_blocker"),
            source_run=str(raw.get("source_run") or ""),
            app=str(raw.get("app") or ""),
            note=str(raw.get("note") or ""),
            tags=[str(t) for t in (raw.get("tags") or []) if str(t).strip()],
            observation_texts=[
                str(t) for t in (raw.get("observation_texts") or []) if str(t).strip()
            ],
            system_facts=dict(raw.get("system_facts") or {}),
            view=dict(raw.get("view") or {}),
            features=dict(raw.get("features") or {}),
            parent_intention=dict(raw.get("parent_intention") or {}),
            world_before=dict(raw.get("world_before") or {}),
            resources=[
                dict(r) for r in (raw.get("resources") or []) if isinstance(r, dict)
            ],
            offered_capabilities=[
                str(c) for c in (raw.get("offered_capabilities") or []) if str(c).strip()
            ],
            artifacts={
                str(k): str(v)
                for k, v in dict(raw.get("artifacts") or {}).items()
                if str(v).strip()
            },
            gold=dict(raw.get("gold") or {}),
            forbidden=[str(f) for f in (raw.get("forbidden") or []) if str(f).strip()],
            frames=[
                dict(fr) for fr in (raw.get("frames") or []) if isinstance(fr, dict)
            ],
        )


def version_dir(root: str = DEFAULT_PHENOMENA_DIR, version: str = PHENOMENA_VERSION) -> Path:
    return Path(root) / version


def family_dir(
    family: str,
    *,
    root: str = DEFAULT_PHENOMENA_DIR,
    version: str = PHENOMENA_VERSION,
) -> Path:
    if family not in PHENOMENON_FAMILIES:
        raise ValueError(
            f"unknown phenomenon family {family!r}; expected one of {PHENOMENON_FAMILIES}"
        )
    return version_dir(root, version) / family


def load_manifest(
    root: str = DEFAULT_PHENOMENA_DIR,
    version: str = PHENOMENA_VERSION,
) -> Dict[str, Any]:
    path = version_dir(root, version) / "_manifest.json"
    if not path.is_file():
        return {"version": version, "error": f"missing {path}"}
    return json.loads(path.read_text(encoding="utf-8"))


def load_family_fixtures(
    family: str,
    *,
    root: str = DEFAULT_PHENOMENA_DIR,
    version: str = PHENOMENA_VERSION,
) -> List[GoldenFixture]:
    d = family_dir(family, root=root, version=version)
    if not d.is_dir():
        return []
    out: List[GoldenFixture] = []
    for path in sorted(d.glob("*.json")):
        if path.name.startswith("_"):
            continue
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            continue
        fix = GoldenFixture.from_dict(raw)
        if not fix.family:
            fix.family = family
        if not fix.fixture_id:
            fix.fixture_id = path.stem
        out.append(fix)
    return out


def load_all_fixtures(
    *,
    root: str = DEFAULT_PHENOMENA_DIR,
    version: str = PHENOMENA_VERSION,
) -> Dict[str, List[GoldenFixture]]:
    return {
        fam: load_family_fixtures(fam, root=root, version=version)
        for fam in PHENOMENON_FAMILIES
    }


def write_fixture(
    fixture: GoldenFixture,
    *,
    root: str = DEFAULT_PHENOMENA_DIR,
    version: str = PHENOMENA_VERSION,
) -> Path:
    d = family_dir(fixture.family, root=root, version=version)
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{fixture.fixture_id}.json"
    path.write_text(
        json.dumps(fixture.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path
