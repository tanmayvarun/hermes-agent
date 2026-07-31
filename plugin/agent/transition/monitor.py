"""TransitionMonitor — detect meaningful world change after an action."""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, Optional, Set

from plugin.agent.transition.types import TransitionResult
from plugin.perception.observation import Observation
from plugin.worldmodel.model import WorldModel


ObserveFn = Callable[[], Observation]
WaitFn = Callable[[float, str], None]


def entity_label_set(world: WorldModel, *, limit: int = 400) -> Set[str]:
    out: Set[str] = set()
    for e in list(world.entities.values())[:limit]:
        if not getattr(e, "visible", True):
            continue
        lab = (e.label or "").strip().lower()
        if lab:
            out.add(lab)
        role = (e.semantic_role or "").strip().lower()
        if role and role != lab:
            out.add(role)
    return out


def jaccard(a: Set[str], b: Set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 1.0


def world_fingerprint(world: WorldModel, view: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    labels = entity_label_set(world)
    view = view or {}
    return {
        "labels": labels,
        "signature": str(view.get("world_signature") or view.get("screen") or ""),
        "screen": str(view.get("screen") or ""),
        "search_query": str(view.get("search_query") or ""),
        "open_conversation": str(view.get("open_conversation") or ""),
        "call_state": str(view.get("call_state") or ""),
        "dialogs": tuple(sorted(str(d) for d in (view.get("unexpected_dialogs") or [])[:8])),
        "entity_count": len(labels),
    }


def compare_fingerprints(before: Dict[str, Any], after: Dict[str, Any]) -> TransitionResult:
    reasons: list = []
    score = 0.0

    lab_b: Set[str] = before.get("labels") or set()
    lab_a: Set[str] = after.get("labels") or set()
    jac = jaccard(lab_b, lab_a)
    entity_delta = 1.0 - jac
    if entity_delta >= 0.08:
        reasons.append("entity_set_changed")
        score += min(0.55, entity_delta)

    if (before.get("signature") or "") != (after.get("signature") or ""):
        reasons.append("world_signature_changed")
        score += 0.25

    if (before.get("screen") or "") != (after.get("screen") or ""):
        reasons.append("screen_bucket_changed")
        score += 0.2

    if (before.get("search_query") or "") != (after.get("search_query") or ""):
        reasons.append("search_query_changed")
        score += 0.15

    if (before.get("open_conversation") or "") != (after.get("open_conversation") or ""):
        reasons.append("open_conversation_changed")
        score += 0.3

    if (before.get("call_state") or "") != (after.get("call_state") or ""):
        reasons.append("call_state_changed")
        score += 0.35

    if (before.get("dialogs") or ()) != (after.get("dialogs") or ()):
        reasons.append("overlay_or_dialog_changed")
        score += 0.2

    count_delta = abs(int(after.get("entity_count") or 0) - int(before.get("entity_count") or 0))
    if count_delta >= 8:
        reasons.append("entity_count_shifted")
        score += min(0.2, count_delta / 100.0)

    score = min(1.0, score)
    changed = score >= 0.12 or bool(reasons)
    # Stabilized if we have a coherent after fingerprint (caller may re-check)
    stabilized = True
    return TransitionResult(
        changed=changed and score >= 0.08,
        stabilized=stabilized,
        change_score=round(score, 4),
        reasons=reasons,
    )


class TransitionMonitor:
    """
    Poll observe until a meaningful change appears and the UI settles, or timeout.
    Perception stays as-is — this only schedules re-observation.
    """

    def __init__(
        self,
        *,
        change_threshold: float = 0.12,
        poll_s: float = 0.35,
        timeout_s: float = 2.5,
        stabilize_polls: int = 2,
    ) -> None:
        self.change_threshold = change_threshold
        self.poll_s = poll_s
        self.timeout_s = timeout_s
        self.stabilize_polls = stabilize_polls

    def wait_for_change_or_stability(
        self,
        *,
        before_fp: Dict[str, Any],
        observe: ObserveFn,
        ingest: Callable[[Observation], WorldModel],
        view_fn: Callable[[WorldModel], Dict[str, Any]],
        wait_fn: Optional[WaitFn] = None,
        min_settle_s: float = 0.4,
    ) -> tuple[TransitionResult, WorldModel, Dict[str, Any]]:
        def _wait(seconds: float, reason: str) -> None:
            if wait_fn:
                wait_fn(seconds, reason)
            else:
                time.sleep(seconds)

        _wait(min_settle_s, "transition settle")
        deadline = time.time() + self.timeout_s
        last_fp = before_fp
        last_world: Optional[WorldModel] = None
        last_view: Dict[str, Any] = {}
        best = TransitionResult(changed=False, stabilized=False, change_score=0.0, timed_out=False)
        stable_hits = 0
        polls = 0

        while time.time() < deadline:
            polls += 1
            obs = observe()
            world = ingest(obs)
            view = view_fn(world)
            fp = world_fingerprint(world, view)
            cmp = compare_fingerprints(before_fp, fp)
            cmp.polls = polls
            last_world = world
            last_view = view
            last_fp = fp

            if cmp.change_score >= best.change_score:
                best = cmp

            if cmp.change_score >= self.change_threshold:
                # Require a second similar poll for stability
                stable_hits += 1
                if stable_hits >= self.stabilize_polls:
                    best.changed = True
                    best.stabilized = True
                    best.polls = polls
                    return best, world, view
            else:
                stable_hits = 0

            _wait(self.poll_s, "transition poll")

        # Timeout: return last world even if unchanged
        best.polls = polls
        best.timed_out = True
        best.stabilized = True  # stopped changing / gave up
        if last_world is None:
            obs = observe()
            last_world = ingest(obs)
            last_view = view_fn(last_world)
            best = compare_fingerprints(before_fp, world_fingerprint(last_world, last_view))
            best.polls = polls + 1
            best.timed_out = True
            best.stabilized = True
        return best, last_world, last_view
