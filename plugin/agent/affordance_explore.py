"""Current-node affordance closure after the critic accepts the world.

A UI *node* is the current interaction state: everything available now, including
controls hidden until a reversible stimulus (hover, dropdown, context-click).
Those reveals stay on the same node. The *next* node is one brain-chosen
transition away.

This handler runs **after** critic acceptance so probes target trusted objects.
It completes the same-node frontier before the brain picks a transition.

Multi-pass discovery (explore → capture → perceive → merge) is *scheduled* here
as a bounded relook signal when a reveal handoff is still incomplete after
post-accept promote. Motors stay outside the stage-1 VLM perceptor; OCR never
bypasses the world document into ``affordance_set``.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

NODE_SCOPE_CURRENT = "current"
NODE_SCOPE_TRANSITION = "transition"

# Families that leave the current node when invoked (not mere reveals).
_TRANSITION_FAMILIES = frozenset(
    {
        "open_entity",
        "compose_search_query",
        "type_query",
        "locate_content",
        "commit_irreversible",
        "scroll",
        "scroll_content",
        "press_escape",
        "dismiss_transient",
    }
)

# Same-node reversible stimuli that expose latent controls in place.
_SAME_NODE_PROBE_FAMILIES = frozenset(
    {
        "hover",
        "reveal_actions",
        "invoke_affordance",  # e.g. open a dropdown already on this surface
    }
)

# How many post-accept relooks (perceive passes) while reveal handoff is incomplete.
_DEFAULT_EXPLORE_BUDGET = 2


def node_closure_enabled() -> bool:
    raw = os.getenv("HERMES_PERCEPTION_NODE_CLOSURE", "1").strip().lower()
    return raw not in {"0", "false", "off", "no"}


def motorized_probes_enabled() -> bool:
    """Live hover/context-click during closure. Off by default until motors wire in."""
    raw = os.getenv("HERMES_PERCEPTION_EXPLORE", "0").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def explore_budget() -> int:
    raw = os.getenv("HERMES_AFFORDANCE_EXPLORE_BUDGET", "").strip()
    if raw.isdigit():
        return max(0, int(raw))
    return _DEFAULT_EXPLORE_BUDGET


def classify_node_scope(family: str, *, available_now: bool = True) -> str:
    fam = str(family or "").strip().lower().replace("-", "_")
    if fam in _TRANSITION_FAMILIES:
        return NODE_SCOPE_TRANSITION
    if fam in _SAME_NODE_PROBE_FAMILIES or not available_now:
        # Latent / probe reveals are same-node until the brain commits a transition.
        return NODE_SCOPE_CURRENT
    return NODE_SCOPE_CURRENT


def _tag_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(entry)
    family = str(out.get("family") or "")
    available_now = out.get("available_now", out.get("status") == "observed")
    if available_now is None:
        available_now = True
    out["node_scope"] = classify_node_scope(
        family, available_now=bool(available_now) and str(out.get("status") or "") != "latent"
    )
    if str(out.get("status") or "") in {"latent", "probe"}:
        out["node_scope"] = NODE_SCOPE_CURRENT
    return out


def _tag_frontier(frontier: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(frontier or {})
    for key in ("observed_actions", "latent_actions", "probe_actions"):
        items = [a for a in (out.get(key) or []) if isinstance(a, dict)]
        out[key] = [_tag_entry(a) for a in items]
    return out


def _fold_missing(
    frontier: Dict[str, Any],
    missing: Sequence[str],
) -> None:
    if not missing:
        return
    observed = list(frontier.get("observed_actions") or [])
    for note in missing[:6]:
        text = str(note or "").strip()
        if not text:
            continue
        observed.append(
            {
                "id": f"missing:{len(observed)}",
                "family": "observe",
                "status": "observed",
                "target_label": text[:80],
                "confidence": 0.4,
                "node_scope": NODE_SCOPE_CURRENT,
                "source": "missing_affordance_information",
                "evidence": [{"source": "perceptor", "detail": text[:120]}],
            }
        )
    frontier["observed_actions"] = observed


def _fold_recommended_probe(
    frontier: Dict[str, Any],
    probe: Optional[Dict[str, Any]],
) -> None:
    if not isinstance(probe, dict) or not probe.get("family"):
        return
    probes = list(frontier.get("probe_actions") or [])
    probes.insert(
        0,
        {
            "id": "recommended_probe",
            "family": str(probe.get("family") or ""),
            "status": "probe",
            "target_id": probe.get("target_id"),
            "target_label": str(probe.get("reason") or "")[:80],
            "may_reveal": [
                (m if isinstance(m, dict) else {"label": str(m)})
                for m in (probe.get("may_reveal") or [])[:4]
            ],
            "confidence": 0.55,
            "node_scope": NODE_SCOPE_CURRENT,
            "source": "perceptor_recommended_probe",
            "available_now": False,
        },
    )
    frontier["probe_actions"] = probes[:8]


def _fold_suggestions_as_hints(
    frontier: Dict[str, Any],
    suggestions: Sequence[Dict[str, Any]],
) -> None:
    """Suggestions do not execute; expose their targets as current-node hints."""
    if not suggestions:
        return
    observed = list(frontier.get("observed_actions") or [])
    seen = {
        (
            str(a.get("family") or ""),
            str(a.get("target_id") or ""),
            str(a.get("target_label") or a.get("text") or ""),
        )
        for a in observed
    }
    for sug in suggestions[:3]:
        if not isinstance(sug, dict) or not sug.get("family"):
            continue
        key = (
            str(sug.get("family") or ""),
            str(sug.get("target_id") or ""),
            str(sug.get("text") or sug.get("target_label") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        observed.append(
            {
                "id": f"suggestion:{sug.get('rank', len(observed))}",
                "family": str(sug.get("family") or ""),
                "status": "observed",
                "target_id": sug.get("target_id"),
                "target_label": str(sug.get("text") or sug.get("target_label") or "")[:80],
                "confidence": float(sug.get("confidence") or 0.5),
                "node_scope": classify_node_scope(str(sug.get("family") or "")),
                "source": "suggested_action",
                "why": str(sug.get("why") or "")[:160],
            }
        )
    frontier["observed_actions"] = observed


def _handoff_active(execution_state: Any) -> bool:
    handoff = getattr(execution_state, "reveal_handoff", None) if execution_state else None
    return isinstance(handoff, dict) and bool(str(handoff.get("surface") or "").strip())


def _run_post_accept_promote(
    execution_state: Any,
    accepted_world: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    try:
        from plugin.agent.world_critic import promote_frontier_after_accept

        return promote_frontier_after_accept(
            execution_state,
            accepted_document=accepted_world
            if isinstance(accepted_world, dict)
            else None,
        )
    except Exception as exc:
        logger.debug("post-accept promote in node closure skipped: %s", exc)
        return {"promoted": False, "grounded": 0}


def _tick_explore_budget(
    execution_state: Any,
    *,
    grounded_count: int,
) -> Dict[str, Any]:
    """Advance same-node explore budget while reveal handoff is incomplete.

    Returns ``needs_relook``, ``status``, and budget counters. Does not motor —
    schedules another perceive pass (forced overlay while handoff active).
    """
    out: Dict[str, Any] = {
        "needs_relook": False,
        "status": "soft_complete",
        "explore_used": 0,
        "explore_budget": explore_budget(),
    }
    if execution_state is None:
        return out
    if grounded_count > 0 or not _handoff_active(execution_state):
        out["status"] = "grounded" if grounded_count > 0 else "soft_complete"
        return out

    handoff = dict(getattr(execution_state, "reveal_handoff") or {})
    budget = int(handoff.get("explore_budget") or explore_budget())
    used = int(handoff.get("explore_used") or 0)
    out["explore_budget"] = budget
    out["explore_used"] = used
    if used < budget:
        handoff["explore_used"] = used + 1
        handoff["incomplete_reveal"] = True
        handoff["discovery"] = "pending_perception"
        try:
            execution_state.reveal_handoff = handoff
            execution_state.must_executive_reperceive = True
        except Exception:
            pass
        out["needs_relook"] = True
        out["explore_used"] = used + 1
        out["status"] = "needs_relook"
        return out

    handoff["failed_reveal"] = True
    handoff["status"] = "explore_exhausted"
    handoff["incomplete_reveal"] = True
    try:
        execution_state.reveal_handoff = handoff
    except Exception:
        pass
    out["status"] = "explore_exhausted"
    return out


def close_current_node_frontier(
    *,
    accepted_world: Optional[Dict[str, Any]] = None,
    passive_frontier: Optional[Dict[str, Any]] = None,
    proposal: Any = None,
    execution_state: Any = None,
) -> Dict[str, Any]:
    """Complete same-node affordances after critic acceptance.

    Returns a report: ``frontier``, ``needs_relook``, ``probes_run``, ``closure``.
    Always runs post-accept promote on the accepted world (timing fix). Motorized
    probes stay behind ``HERMES_PERCEPTION_EXPLORE``; without motors this still
    folds perceptor missing/probe/suggestion signals and schedules relooks while
    the explore budget remains under an incomplete reveal handoff.
    """
    if not node_closure_enabled():
        frontier = _tag_frontier(dict(passive_frontier or {}))
        if execution_state is not None:
            try:
                execution_state.last_affordance_frontier = frontier
            except Exception:
                pass
        return {
            "frontier": frontier,
            "needs_relook": False,
            "probes_run": [],
            "closure": "disabled",
        }

    frontier = _tag_frontier(dict(passive_frontier or {}))
    if not frontier and execution_state is not None:
        stored = getattr(execution_state, "last_affordance_frontier", None)
        if isinstance(stored, dict):
            frontier = _tag_frontier(dict(stored))

    missing: List[str] = []
    probe: Dict[str, Any] = {}
    suggestions: List[Dict[str, Any]] = []
    if proposal is not None:
        missing = [
            str(m)
            for m in (getattr(proposal, "missing_affordance_information", None) or [])
            if str(m).strip()
        ]
        probe = dict(getattr(proposal, "recommended_probe", None) or {})
        suggestions = [
            dict(s)
            for s in (getattr(proposal, "suggested_actions", None) or [])
            if isinstance(s, dict)
        ]

    _fold_missing(frontier, missing)
    _fold_recommended_probe(frontier, probe)
    _fold_suggestions_as_hints(frontier, suggestions)
    frontier = _tag_frontier(frontier)

    doc = accepted_world if isinstance(accepted_world, dict) else {}
    if not doc and execution_state is not None:
        raw = getattr(execution_state, "unified_world_document", None)
        if isinstance(raw, dict):
            doc = raw

    # Post-accept promote on the critic-accepted document (not the prior packet).
    promote_status = _run_post_accept_promote(execution_state, doc)
    grounded_count = int(promote_status.get("grounded") or 0)
    if execution_state is not None:
        try:
            from plugin.agent.affordance_frontier import grounded_affordance_set_of

            grounded_count = max(
                grounded_count, len(grounded_affordance_set_of(execution_state))
            )
        except Exception:
            pass

    explore = _tick_explore_budget(execution_state, grounded_count=grounded_count)
    needs_relook = bool(explore.get("needs_relook"))

    # Refresh frontier packet after promote may have published actuators.
    if execution_state is not None:
        stored = getattr(execution_state, "last_affordance_frontier", None)
        if isinstance(stored, dict) and (
            stored.get("observed_actions") or stored.get("latent_actions")
        ):
            frontier = _tag_frontier(dict(stored))
            _fold_missing(frontier, missing)
            _fold_recommended_probe(frontier, probe)
            _fold_suggestions_as_hints(frontier, suggestions)
            frontier = _tag_frontier(frontier)

    frontier["surface"] = str(frontier.get("surface") or doc.get("surface") or "")
    closure_status = str(explore.get("status") or "soft_complete")
    frontier["node_closure"] = {
        "status": closure_status,
        "same_node_observed": sum(
            1
            for a in (frontier.get("observed_actions") or [])
            if isinstance(a, dict) and a.get("node_scope") == NODE_SCOPE_CURRENT
        ),
        "same_node_latent": sum(
            1
            for a in (frontier.get("latent_actions") or [])
            if isinstance(a, dict) and a.get("node_scope") == NODE_SCOPE_CURRENT
        ),
        "same_node_probes": sum(
            1
            for a in (frontier.get("probe_actions") or [])
            if isinstance(a, dict) and a.get("node_scope") == NODE_SCOPE_CURRENT
        ),
        "motorized": False,
        "post_accept_promoted": bool(promote_status.get("promoted")),
        "grounded": grounded_count,
        "explore_used": explore.get("explore_used"),
        "explore_budget": explore.get("explore_budget"),
    }

    probes_run: List[Dict[str, Any]] = []
    if motorized_probes_enabled() and needs_relook and grounded_count == 0:
        # Placeholder: live hover/context-click will land here against accepted
        # object geometry. Until motors are wired, soft closure schedules relook.
        logger.info(
            "Node closure: motorized explore requested but not yet wired; "
            "scheduling relook under explore budget"
        )
        frontier["node_closure"]["status"] = "needs_relook_motors_pending"
        frontier["node_closure"]["motorized"] = False

    if explore.get("status") == "explore_exhausted" and not missing:
        missing_note = (
            "same-node explore budget exhausted without grounding Forward/menu controls"
        )
        _fold_missing(frontier, [missing_note])
        frontier = _tag_frontier(frontier)

    if execution_state is not None:
        try:
            execution_state.last_affordance_frontier = frontier
            execution_state.node_closure_report = {
                "needs_relook": needs_relook,
                "probes_run": probes_run,
                "closure": frontier.get("node_closure"),
            }
        except Exception:
            pass

    return {
        "frontier": frontier,
        "needs_relook": needs_relook,
        "probes_run": probes_run,
        "closure": frontier.get("node_closure"),
    }
