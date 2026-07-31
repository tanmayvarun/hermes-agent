"""Resolution Memory — successful past resolutions as evidence (not hardcoded aliases)."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, Tuple

from plugin.worldmodel.entities.normalize import _clean_label

DEFAULT_MEMORY_PATH = (
    Path(__file__).resolve().parents[2] / "experiments" / "runs" / "resolution_memory.jsonl"
)


def _norm(s: str) -> str:
    return _clean_label(s or "").lower()


@dataclass
class ResolutionMemory:
    """
    Stores observations: input query → resolved name → success.
    Confidence grows from repeated successes; no alias table.
    """

    path: Path = field(default_factory=lambda: DEFAULT_MEMORY_PATH)
    # query -> resolved_name -> {successes, last_ts, failures}
    _stats: Dict[str, Dict[str, Dict[str, float]]] = field(default_factory=dict)
    # resolved_name -> total successes (frequency across queries)
    _freq: Dict[str, float] = field(default_factory=dict)
    # resolved_name -> last success ts (recency)
    _last_success: Dict[str, float] = field(default_factory=dict)
    _loaded: bool = False

    def ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self.path.is_file():
            return
        try:
            for line in self.path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                self._ingest_event(ev, persist=False)
        except OSError:
            pass

    def _ingest_event(self, ev: Dict, *, persist: bool) -> None:
        q = _norm(str(ev.get("query") or ""))
        name = _norm(str(ev.get("resolved") or ev.get("resolved_name") or ""))
        if not q or not name:
            return
        ok = bool(ev.get("succeeded", True))
        ts = float(ev.get("ts") or time.time())
        slot = self._stats.setdefault(q, {}).setdefault(
            name, {"successes": 0.0, "failures": 0.0, "last_ts": 0.0}
        )
        if ok:
            slot["successes"] = float(slot["successes"]) + float(ev.get("weight") or 1.0)
            slot["last_ts"] = max(float(slot["last_ts"]), ts)
            self._freq[name] = self._freq.get(name, 0.0) + float(ev.get("weight") or 1.0)
            self._last_success[name] = max(self._last_success.get(name, 0.0), ts)
        else:
            slot["failures"] = float(slot["failures"]) + 1.0

    def record(
        self,
        query: str,
        resolved: str,
        *,
        succeeded: bool = True,
        weight: float = 1.0,
        source: str = "success",
        meta: Optional[Dict] = None,
    ) -> None:
        self.ensure_loaded()
        ev = {
            "ts": time.time(),
            "query": _norm(query),
            "resolved": _norm(resolved),
            "succeeded": succeeded,
            "weight": weight,
            "source": source,
            **(meta or {}),
        }
        self._ingest_event(ev, persist=True)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(ev) + "\n")
        except OSError:
            pass

    def history_score(self, query: str, candidate_name: str) -> Tuple[float, str]:
        """P(candidate | query) from past successes for this input string."""
        self.ensure_loaded()
        q = _norm(query)
        name = _norm(candidate_name)
        by_q = self._stats.get(q) or {}
        if not by_q:
            return 0.0, "no history for query"
        total = sum(float(v.get("successes") or 0.0) for v in by_q.values())
        if total <= 0:
            return 0.0, "no successes for query"
        hits = float((by_q.get(name) or {}).get("successes") or 0.0)
        if hits <= 0:
            return 0.0, f"history hits=0/{total:.0f}"
        # Laplace-ish
        score = (hits + 0.1) / (total + 0.1 * max(1, len(by_q)))
        return min(1.0, score), f"history hits={hits:.0f}/{total:.0f}"

    def frequency_score(self, candidate_name: str) -> Tuple[float, str]:
        self.ensure_loaded()
        name = _norm(candidate_name)
        if not self._freq:
            return 0.0, "no frequency data"
        mx = max(self._freq.values()) or 1.0
        v = self._freq.get(name, 0.0)
        return min(1.0, v / mx), f"freq={v:.0f} max={mx:.0f}"

    def recency_score(self, candidate_name: str, *, half_life_days: float = 14.0) -> Tuple[float, str]:
        self.ensure_loaded()
        name = _norm(candidate_name)
        ts = self._last_success.get(name)
        if not ts:
            return 0.0, "never resolved successfully"
        age_days = max(0.0, (time.time() - ts) / 86400.0)
        # exponential decay
        score = 0.5 ** (age_days / max(0.5, half_life_days))
        return float(score), f"age_days={age_days:.1f}"


_DEFAULT_MEMORY: Optional[ResolutionMemory] = None


def get_resolution_memory() -> ResolutionMemory:
    global _DEFAULT_MEMORY
    if _DEFAULT_MEMORY is None:
        _DEFAULT_MEMORY = ResolutionMemory()
    return _DEFAULT_MEMORY
