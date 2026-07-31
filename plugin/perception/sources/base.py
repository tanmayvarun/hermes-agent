"""PerceptionSource protocol."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Protocol, runtime_checkable

from plugin.perception.observation import Observation


@dataclass
class ObservationBundle:
    source_id: str
    observation: Observation
    latency_ms: float = 0.0
    coverage_self: float = 1.0
    degraded: bool = False
    raw_meta: Dict[str, Any] = field(default_factory=dict)


def format_observation_raw_summary(obs: Observation, *, max_nodes: int = 10, max_message_like: int = 6) -> str:
    nodes = list(obs.nodes or [])
    lines = [
        f"app={obs.app_name!r} window={obs.window_name!r} source={obs.source!r}",
        f"nodes={len(nodes)} coverage={obs.coverage!r} degraded={obs.degraded!r} screenshot={obs.screenshot_path!r}",
    ]
    message_like: list[str] = []
    for n in nodes:
        text = (n.name or n.description or "").strip()
        if not text:
            continue
        low = text.lower()
        if any(token in low for token in ("message", "sent to", "received from", "link", "composer", "search", "input", "field")):
            message_like.append(text[:160])
        if len(message_like) >= max_message_like:
            break
    if message_like:
        lines.append("message_like=")
        lines.extend(f"  - {item}" for item in message_like)
    if nodes:
        lines.append("raw_nodes=")
        for i, n in enumerate(nodes[:max_nodes], start=1):
            text = (n.name or n.description or "").strip()
            value = (n.value or "").strip() if n.value is not None else ""
            bbox = tuple(round(float(v), 1) for v in (n.bbox or (0.0, 0.0, 0.0, 0.0)))
            lines.append(
                f"  {i:02d}. role={n.role or 'unknown'} label={text!r}"
                + (f" value={value!r}" if value else "")
                + f" enabled={n.enabled!r} bbox={bbox}"
            )
        if len(nodes) > max_nodes:
            lines.append(f"  ... {len(nodes) - max_nodes} more nodes")
    return "\n".join(lines)


@runtime_checkable
class PerceptionSource(Protocol):
    source_id: str

    def observe(self, app: str) -> ObservationBundle: ...


def timed_observe(source_id: str, fn, app: str) -> ObservationBundle:
    t0 = time.time()
    try:
        obs: Observation = fn(app)
    except Exception as e:
        empty = Observation(
            timestamp=time.time(),
            app_name=app,
            window_name="",
            nodes=[],
            source=source_id,
            coverage=0.0,
            degraded=True,
            meta={"error": str(e)},
        )
        return ObservationBundle(
            source_id=source_id,
            observation=empty,
            latency_ms=(time.time() - t0) * 1000,
            coverage_self=0.0,
            degraded=True,
            raw_meta={"error": str(e)},
        )
    cov = obs.coverage if obs.coverage is not None else (1.0 if obs.nodes else 0.0)
    raw_summary = format_observation_raw_summary(obs)
    return ObservationBundle(
        source_id=source_id,
        observation=obs,
        latency_ms=(time.time() - t0) * 1000,
        coverage_self=float(cov),
        degraded=bool(obs.degraded),
        raw_meta={**dict(obs.meta or {}), "raw_summary": raw_summary},
    )
