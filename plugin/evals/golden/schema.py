"""Schemas for the module-layered golden corpus.

Gold is eval-only. Fields scored here must never be filled from the recorded
model reply for the same field (same discipline as ``annotations.py``).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

GOLDEN_VERSION = "v1"
GOLDEN_MODULES = (
    "perceive",
    "critic",
    "meta_action",
    "brain",
    "actor",
    "brain_actor_handoff",
    "reflect",
    # Cross-module recoveries (perceptor→brain→actor / surprise→reflect→act).
    "flow",
    # UI recoverability: wrong actuation aftermath → revert_effects → re-act.
    "ui",
)

# Live runs that must leave goldens (failure *and* success). Agents should append
# cases under the right module or flow/*.jsonl and bump _manifest.json counts.
LIVE_GOLDEN_PROMOTION_RULE = (
    "After every live run: freeze each new failure and each new success as a "
    "golden (module for single-layer, flow for cross-module). Never leave a "
    "diagnosed stall without a case id tagged with the run stamp."
)

DEFAULT_GOLDEN_DIR = "plugin/evals/golden/corpus"
DEFAULT_VERSION_DIR = f"{DEFAULT_GOLDEN_DIR}/{GOLDEN_VERSION}"

SOURCE_MANUAL = "manual"
SOURCE_CONTRACT = "contract"
SOURCE_OUTCOME = "outcome"
SOURCE_FAILURE = "failure"  # promoted live stall


@dataclass
class GoldenCase:
    """One frozen input → gold decision-structure pair for a single module."""

    id: str
    module: str
    input: Dict[str, Any] = field(default_factory=dict)
    gold: Dict[str, Any] = field(default_factory=dict)
    source: str = SOURCE_MANUAL
    note: str = ""
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "module": self.module,
            "input": self.input,
            "gold": self.gold,
            "source": self.source,
            "note": self.note,
            "tags": list(self.tags),
        }

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "GoldenCase":
        return cls(
            id=str(raw.get("id") or ""),
            module=str(raw.get("module") or ""),
            input=dict(raw.get("input") or {}),
            gold=dict(raw.get("gold") or {}),
            source=str(raw.get("source") or SOURCE_MANUAL),
            note=str(raw.get("note") or ""),
            tags=[str(t) for t in (raw.get("tags") or []) if str(t).strip()],
        )


def version_dir(root: str = DEFAULT_GOLDEN_DIR, version: str = GOLDEN_VERSION) -> Path:
    return Path(root) / version


def module_path(
    module: str,
    *,
    root: str = DEFAULT_GOLDEN_DIR,
    version: str = GOLDEN_VERSION,
) -> Path:
    if module not in GOLDEN_MODULES:
        raise ValueError(f"unknown golden module {module!r}; expected one of {GOLDEN_MODULES}")
    return version_dir(root, version) / f"{module}.jsonl"


def load_manifest(
    root: str = DEFAULT_GOLDEN_DIR,
    version: str = GOLDEN_VERSION,
) -> Dict[str, Any]:
    path = version_dir(root, version) / "_manifest.json"
    if not path.is_file():
        return {"version": version, "error": f"missing {path}"}
    return json.loads(path.read_text(encoding="utf-8"))


def load_module_cases(
    module: str,
    *,
    root: str = DEFAULT_GOLDEN_DIR,
    version: str = GOLDEN_VERSION,
) -> List[GoldenCase]:
    path = module_path(module, root=root, version=version)
    if not path.is_file():
        return []
    cases: List[GoldenCase] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_no}: {exc}") from exc
        case = GoldenCase.from_dict(raw)
        if case.module and case.module != module:
            raise ValueError(f"{path}:{line_no}: module mismatch {case.module!r} != {module!r}")
        case.module = module
        if not case.id:
            raise ValueError(f"{path}:{line_no}: missing id")
        cases.append(case)
    return cases


def load_all_cases(
    *,
    root: str = DEFAULT_GOLDEN_DIR,
    version: str = GOLDEN_VERSION,
    modules: Optional[Sequence[str]] = None,
) -> Dict[str, List[GoldenCase]]:
    wanted = tuple(modules) if modules else GOLDEN_MODULES
    return {m: load_module_cases(m, root=root, version=version) for m in wanted}


def write_jsonl(path: Path, cases: Iterable[GoldenCase]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(c.to_dict(), ensure_ascii=False, sort_keys=True) for c in cases]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return len(lines)
