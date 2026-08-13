"""reveal_actions: affordance discovery as a perception sub-capability.

The question this answers about an object is: **"what can I do to this, right
now or after one probe, and how do I invoke each?"** It returns a structured,
grounded :class:`RevealResult` -- visible *and* latent actions -- rather than a
bare boolean from a single right-click.

Latent-action discovery requires *acting* (a right-click reveals a menu that
was not on screen), so this is **active perception (a PROBE)**, not a pure read.
"Idempotent / re-callable" therefore means **state-aware**: if the action
surface for the target is already open, we read and ground it instead of
gesturing again, so two calls yield the same set, not two menus.

Realization is a tiered ladder, cheapest first:

1. **read** (no side effect) -- assemble the actions already grounded in
   perception: the items on an open action_menu layer, AX supported-actions on
   the target, and the affordance frontier's observed actions. If the goal
   action is here, return it. Free.
2. **probe** (state-mutating, budgeted) -- if the goal action is latent, spend
   one gesture from an evidence-ordered ladder (hover -> context_click -> ...),
   ordered by the overlay's declared reveal_mode and the frontier, never by
   ``if app ==``.

After a probe we **hand off**: the revealed overlay layer is left active (so the
executive can invoke immediately) and its controls are grounded by the very next
perception frame as an action_menu layer -- which is exactly how the layered
perceptor closes the loop. See
``docs/design/layered-perception-and-affordance-discovery.md``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

from plugin.agent.capabilities.base import AddressableEntity, CapabilityOutcome
from plugin.agent.capabilities.invoke_affordance import is_irreversible_affordance
from plugin.agent.capabilities.open_entity import resolve_addressable
from plugin.agent.capabilities.pointer_runtime import PointerRuntime

logger = logging.getLogger(__name__)

RevealMode = Literal["context_click", "hover"]

# Surfaces / layer roles that ARE an object's action surface (a revealed menu).
_ACTION_SURFACES = {"context_menu", "action_menu", "share_sheet"}


def reveal_mode_for(overlay: Any) -> RevealMode:
    mode = str(getattr(overlay, "reveal_mode", "") or "context_click").strip().lower()
    return "hover" if mode == "hover" else "context_click"


@dataclass(frozen=True)
class Action:
    """One discovered affordance on the target, grounded when possible."""

    label: str
    invocation: str = "menu_path"  # direct|hover|context_click|menu_path|keyboard
    visibility: str = "visible"  # visible|latent
    target: Dict[str, Any] = field(default_factory=dict)  # {"point"} or {"entity_id"}
    reversible: bool = True
    confidence: float = 0.0

    @property
    def is_grounded(self) -> bool:
        return bool(self.target.get("point") or self.target.get("entity_id") is not None)

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "label": self.label,
            "invocation": self.invocation,
            "visibility": self.visibility,
            "confidence": round(float(self.confidence), 2),
        }
        if self.target:
            out["target"] = dict(self.target)
        if not self.reversible:
            out["reversible"] = False
        return out


@dataclass
class RevealResult:
    """The action set discovered for a target, plus how it was obtained."""

    ok: bool = True
    actions: List[Action] = field(default_factory=list)
    surface_opened: str = ""
    method: str = "read"  # read|hover|context_click|menu|keyboard
    escalated: bool = False  # a state-mutating probe was spent
    coverage: float = 0.0  # 0..1 self-estimate of how complete the set is
    message: str = ""
    evidence: Dict[str, Any] = field(default_factory=dict)

    def action_for(self, label: str) -> Optional[Action]:
        want = str(label or "").strip().lower()
        if not want:
            return None
        for action in self.actions:
            lbl = action.label.strip().lower()
            if lbl == want or want in lbl or lbl in want:
                return action
        return None

    def grounded_actions(self) -> List[Action]:
        return [a for a in self.actions if a.is_grounded]

    def to_outcome(self) -> CapabilityOutcome:
        """Back-compat envelope so dispatch and existing callers keep working."""
        evidence = dict(self.evidence)
        grounded = self.grounded_actions()
        # affordance_set substrate only when at least one control has geometry.
        # Motor-ok probe handoff without points is incomplete discovery — the
        # next perceive must ground menu items before invoke_affordance can run.
        if grounded:
            evidence["substrate"] = "affordance_set"
            evidence["incomplete_reveal"] = False
        elif evidence.get("handoff") or evidence.get("incomplete_reveal"):
            evidence["substrate"] = "addressable_entity"
            evidence["incomplete_reveal"] = True
            evidence.setdefault("discovery", "pending_perception")
        else:
            evidence.setdefault(
                "substrate",
                "affordance_set" if self.ok and self.actions else "addressable_entity",
            )
        evidence["method"] = self.method
        evidence["escalated"] = self.escalated
        evidence["actions"] = [a.to_dict() for a in self.actions]
        evidence["grounded_count"] = len(grounded)
        if self.surface_opened:
            evidence["surface_opened"] = self.surface_opened
        evidence["coverage"] = round(float(self.coverage), 2)
        return CapabilityOutcome(
            ok=self.ok,
            capability="reveal_actions",
            realization=self.method,
            message=self.message
            or (
                f"revealed {len(self.actions)} action(s)"
                if self.ok
                else "reveal_actions found nothing"
            ),
            evidence=evidence,
        )


# --- pure discovery core -----------------------------------------------------


def _layers(context: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [l for l in (context.get("layers") or []) if isinstance(l, dict)]


def action_surface_open(context: Optional[Dict[str, Any]]) -> bool:
    """Is the target's action surface (a revealed menu) already up?

    State-awareness lives here: when true, ``reveal_actions`` reads and grounds
    the existing menu instead of gesturing again, so it is idempotent.
    """
    if not isinstance(context, dict):
        return False
    surface = str(context.get("surface") or "").strip().lower()
    if surface in _ACTION_SURFACES:
        return True
    for layer in _layers(context):
        if str(layer.get("role") or "").strip().lower() in {"action_menu"}:
            return True
    return False


def _action_menu_layer(context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    for layer in _layers(context):
        if str(layer.get("role") or "").strip().lower() == "action_menu":
            return layer
    return None


def _point_of(obj: Dict[str, Any]) -> Optional[List[int]]:
    raw = obj.get("point") or obj.get("target_point")
    if isinstance(raw, (list, tuple)) and len(raw) >= 2:
        try:
            return [int(raw[0]), int(raw[1])]
        except (TypeError, ValueError):
            return None
    return None


def visible_actions_from_context(context: Optional[Dict[str, Any]]) -> List[Action]:
    """Ground the actions perception already knows about for the target.

    Sources, in order of grounding quality: the items on an open action_menu
    layer (each a grounded menu item), then the affordance frontier's observed
    actions. Nothing here gestures -- it reads what is already true.
    """
    if not isinstance(context, dict):
        return []
    out: List[Action] = []
    seen: set = set()

    menu = _action_menu_layer(context)
    if menu is not None:
        for obj in menu.get("objects") or []:
            if not isinstance(obj, dict):
                continue
            label = str(obj.get("text") or obj.get("label") or "").strip()
            if not label:
                continue
            key = label.lower()
            if key in seen:
                continue
            seen.add(key)
            point = _point_of(obj)
            target: Dict[str, Any] = {}
            if point:
                target["point"] = point
            space = str(obj.get("coordinate_space") or "").strip().lower()
            if space in {"screen", "image"}:
                target["coordinate_space"] = space
            geo = str(obj.get("geometry_source") or obj.get("source") or "").strip()
            if geo:
                target["geometry_source"] = geo[:40]
            owner = str(obj.get("owner_surface") or obj.get("surface") or "").strip()
            if owner:
                target["owner_surface"] = owner[:40]
            cid = str(
                obj.get("capture_id") or obj.get("grounding_capture_id") or ""
            ).strip()
            if cid:
                target["capture_id"] = cid[:80]
            fid = str(
                obj.get("frame_id") or obj.get("coordinate_frame_id") or ""
            ).strip()
            if fid:
                target["frame_id"] = fid[:80]
            out.append(
                Action(
                    label=label,
                    invocation="menu_path",
                    visibility="visible",
                    target=target,
                    reversible=not is_irreversible_affordance(label),
                    confidence=0.85 if point else 0.5,
                )
            )

    frontier = context.get("frontier")
    if isinstance(frontier, dict):
        for aff in frontier.get("observed_actions") or []:
            if not isinstance(aff, dict):
                continue
            label = str(aff.get("target_label") or "").strip()
            if not label or label.lower() in seen:
                continue
            fam = str(aff.get("family") or "")
            if fam not in {"invoke_affordance", "commit_irreversible"}:
                continue  # only object-action affordances, not open/select rows
            seen.add(label.lower())
            target: Dict[str, Any] = {}
            if aff.get("target_id") is not None:
                target["entity_id"] = aff.get("target_id")
            for act in aff.get("actuators") or []:
                if isinstance(act, dict) and act.get("point"):
                    target["point"] = list(act["point"])
                    break
            space = str(aff.get("coordinate_space") or "").strip().lower()
            if space in {"screen", "image"}:
                target["coordinate_space"] = space
            geo = str(aff.get("geometry_source") or "").strip()
            if geo:
                target["geometry_source"] = geo[:40]
            owner = str(aff.get("owner_surface") or "").strip()
            if owner:
                target["owner_surface"] = owner[:40]
            cid = str(aff.get("capture_id") or "").strip()
            if cid:
                target["capture_id"] = cid[:80]
            fid = str(aff.get("frame_id") or "").strip()
            if fid:
                target["frame_id"] = fid[:80]
            out.append(
                Action(
                    label=label,
                    invocation="direct",
                    visibility="visible",
                    target=target,
                    reversible=fam != "commit_irreversible",
                    confidence=float(aff.get("confidence") or 0.6),
                )
            )
    return out


def latent_actions_from_context(context: Optional[Dict[str, Any]]) -> List[Action]:
    """Actions the frontier expects behind a probe (ungrounded, carry trigger)."""
    if not isinstance(context, dict):
        return []
    frontier = context.get("frontier")
    if not isinstance(frontier, dict):
        return []
    out: List[Action] = []
    for aff in frontier.get("latent_actions") or []:
        if not isinstance(aff, dict):
            continue
        label = str(aff.get("target_label") or "").strip()
        if not label:
            continue
        out.append(
            Action(
                label=label,
                invocation="context_click",
                visibility="latent",
                target={},
                reversible=bool(aff.get("reversible", True)),
                confidence=float(aff.get("confidence") or 0.0),
            )
        )
    return out


def reveal_ladder(
    context: Optional[Dict[str, Any]], reveal_mode: RevealMode
) -> List[RevealMode]:
    """Evidence-ordered probe gestures, the declared reveal_mode first.

    The overlay's declared mode leads (a hover probe on a context-menu-only app
    is wasted motion); the alternative follows as a fallback. Order comes from
    data, never from ``if app ==``.
    """
    primary: RevealMode = "hover" if reveal_mode == "hover" else "context_click"
    other: RevealMode = "context_click" if primary == "hover" else "hover"
    return [primary, other]


# --- capability --------------------------------------------------------------


def reveal_actions(
    entity: AddressableEntity,
    runtime: PointerRuntime,
    *,
    mode: RevealMode = "context_click",
    context: Optional[Dict[str, Any]] = None,
    goal_action: str = "",
    probe_budget: int = 1,
) -> RevealResult:
    """Discover the action set on ``entity``: read if possible, probe if needed.

    Backwards compatible: called with just ``(entity, runtime)`` and no context
    it behaves like the original single-gesture probe (the ladder's first step),
    which is what the motor-composition tests assert. With a ``context`` it
    becomes state-aware -- reading an already-open menu, or short-circuiting when
    the goal action is already visible.
    """
    if not entity.label and entity.bounds is None:
        return RevealResult(
            ok=False,
            method="read",
            message="reveal_actions needs a label or a point",
        )

    # Tier 0 -- idempotent read. The action surface is already open: ground its
    # controls, do not gesture again.
    if action_surface_open(context):
        actions = visible_actions_from_context(context)
        return RevealResult(
            ok=True,
            actions=actions,
            surface_opened=str((context or {}).get("surface") or "context_menu"),
            method="read",
            escalated=False,
            coverage=0.9 if any(a.is_grounded for a in actions) else 0.5,
            message=f"read {len(actions)} action(s) from the open menu",
            evidence={"label": entity.label, "idempotent": True},
        )

    # Tier 1 -- read visible actions. If the goal action is already visible and
    # grounded, return it with no probe.
    visible = visible_actions_from_context(context)
    if goal_action:
        hit = next(
            (a for a in visible if goal_action.strip().lower() in a.label.strip().lower()),
            None,
        )
        if hit is not None and hit.is_grounded:
            return RevealResult(
                ok=True,
                actions=visible,
                method="read",
                escalated=False,
                coverage=0.8,
                message=f"{goal_action!r} already visible",
                evidence={"label": entity.label},
            )

    # Tier 2 -- probe. The goal action is latent (or unknown); spend one gesture.
    if probe_budget <= 0:
        return RevealResult(
            ok=False,
            actions=visible,
            method="read",
            escalated=False,
            coverage=0.3,
            message="goal action is latent but no probe budget remains",
            evidence={"label": entity.label},
        )

    ladder = reveal_ladder(context, mode)
    # Prefer execution_state probe mode after a prior incomplete reveal (153213)
    # so capability path and actor path share the same rotation.
    gesture = ladder[0]
    try:
        est = (context or {}).get("execution_state") if isinstance(context, dict) else None
        state_mode = current_reveal_probe_mode(est) if est is not None else ""
        if state_mode in {"context_click", "hover"}:
            gesture = state_mode
        elif state_mode == "select_content":
            return RevealResult(
                ok=False,
                actions=visible,
                method="read",
                escalated=False,
                coverage=0.3,
                message="reveal probe exhausted; prefer select_content path",
                evidence={"label": entity.label, "prefer": "select_content"},
            )
    except Exception:
        pass
    # Pre-motor locus: refuse input-region geometry (live 134636 composer band).
    try:
        from plugin.agent.capabilities.locus_contract import (
            point_locus_forbidden_for_capability,
        )

        cx = cy = None
        b = getattr(entity, "bounds", None)
        if isinstance(b, (list, tuple)) and len(b) >= 4:
            try:
                # Support xywh and x0y0x1y1.
                x0, y0, c, d = (float(b[0]), float(b[1]), float(b[2]), float(b[3]))
                if c > x0 and d > y0:
                    cx, cy = (x0 + c) / 2.0, (y0 + d) / 2.0
                else:
                    cx, cy = x0 + c / 2.0, y0 + d / 2.0
            except (TypeError, ValueError):
                cx = cy = None
        pt = getattr(entity, "point", None)
        if cx is None and isinstance(pt, (list, tuple)) and len(pt) >= 2:
            cx, cy = float(pt[0]), float(pt[1])
        ctx = context if isinstance(context, dict) else {}
        sg = ctx.get("scene_graph")
        objs = ctx.get("objects") if isinstance(ctx.get("objects"), list) else None
        if cx is not None and cy is not None:
            bad, why, _ = point_locus_forbidden_for_capability(
                "reveal_actions",
                (cx, cy),
                scene_graph=sg,
                objects=objs,
            )
            if bad:
                est = ctx.get("execution_state")
                if est is not None:
                    try:
                        from plugin.agent.executive.affordance_commitment import (
                            arm_wrong_point_grounding_recovery,
                        )

                        arm_wrong_point_grounding_recovery(
                            est,
                            family="reveal_actions",
                            label=str(getattr(entity, "label", "") or ""),
                            patient_ref=str(getattr(entity, "label", "") or ""),
                            point=(cx, cy),
                            why=why,
                        )
                    except Exception:
                        pass
                return RevealResult(
                    ok=False,
                    method=gesture,
                    escalated=False,
                    message=why,
                    evidence={
                        "label": getattr(entity, "label", ""),
                        "mode": gesture,
                        "grounding": "wrong_locus_input",
                    },
                )
    except Exception:
        pass
    try:
        runtime.activate(entity.app)
        if gesture == "hover":
            ok, message = runtime.hover(entity.app, entity.label or "entity", bounds=entity.bounds)
        else:
            ok, message = runtime.context_click(
                entity.app, entity.label or "entity", bounds=entity.bounds
            )
    except Exception as exc:
        logger.warning("reveal_actions probe failed: %s", exc)
        return RevealResult(
            ok=False,
            method=gesture,
            escalated=True,
            message=f"reveal probe failed: {exc}",
            evidence={"label": entity.label, "mode": gesture},
        )

    # Hand-off: leave the revealed surface open so the next perception frame
    # can ground menu items into affordance_set. Motor success alone is not
    # discovery completeness — latents here have no geometry yet.
    expected = latent_actions_from_context(context)
    if ok:
        _record_handoff(context, surface="context_menu")
    return RevealResult(
        ok=ok,
        actions=expected,
        surface_opened="context_menu" if ok else "",
        method=gesture,
        escalated=True,
        coverage=0.4 if ok else 0.0,
        message=(
            (message or f"probed {entity.label!r} via {gesture}")
            + ("; pending overlay ingest for affordance_set" if ok else "")
        ),
        evidence={
            "substrate": "addressable_entity",
            "label": entity.label,
            "mode": gesture,
            "had_bounds": entity.bounds is not None,
            "handoff": bool(ok),
            "incomplete_reveal": bool(ok),
            "discovery": "pending_perception" if ok else "probe_failed",
        },
    )


# Motor ladder after incomplete reveal (live 153213). Actor defaults to
# context_click; failed overlay ingest rotates — never re-probe the same gesture.
REVEAL_PROBE_LADDER = ("context_click", "hover", "select_content")


def reveal_motor_fingerprint(
    gesture: str,
    target: str = "",
    point: Any = None,
) -> str:
    """Gesture-scoped avoid key so hover remains admissible after context_click fails."""
    from plugin.agent.brain import motor_fingerprint

    g = str(gesture or "context_click").strip().lower() or "context_click"
    return motor_fingerprint(f"reveal_actions:{g}", target, point)


def current_reveal_probe_mode(execution_state: Any) -> str:
    mode = str(getattr(execution_state, "reveal_probe_mode", "") or "").strip().lower()
    if mode in REVEAL_PROBE_LADDER:
        return mode
    return "context_click"


def escalate_failed_reveal(
    execution_state: Any,
    *,
    target: str = "",
    point: Any = None,
    last_gesture: str = "",
) -> Dict[str, Any]:
    """Latch the failed reveal gesture and rotate to the next motor.

    Motor-ok context_click is not discovery. After TTL looks with no menu,
    re-issuing the same fingerprint loops OPEN_FORWARD forever (153213). This
    advances ``reveal_probe_mode``: context_click → hover → select_content.
    """
    status: Dict[str, Any] = {"escalated": False}
    if execution_state is None:
        return status
    gesture = (
        str(last_gesture or "").strip().lower()
        or current_reveal_probe_mode(execution_state)
    )
    if gesture not in REVEAL_PROBE_LADDER:
        gesture = "context_click"
    key = reveal_motor_fingerprint(gesture, target, point)
    try:
        keys = list(getattr(execution_state, "avoid_motor_keys", None) or [])
        if key and key not in keys:
            keys.append(key)
        # Also latch the legacy family-only key so older avoid checks still fire.
        from plugin.agent.brain import motor_fingerprint

        legacy = motor_fingerprint("reveal_actions", target, point)
        if legacy and legacy not in keys and legacy != "||":
            keys.append(legacy)
        execution_state.avoid_motor_keys = keys[-16:]
        execution_state.last_failed_motor_key = key or legacy
    except Exception:
        pass

    try:
        idx = REVEAL_PROBE_LADDER.index(gesture)
    except ValueError:
        idx = 0
    next_mode = REVEAL_PROBE_LADDER[min(idx + 1, len(REVEAL_PROBE_LADDER) - 1)]
    try:
        execution_state.reveal_probe_mode = next_mode
        if next_mode == "select_content":
            execution_state.reveal_prefer_capability = "select_content"
        else:
            # Stay on reveal_actions but with the next gesture.
            execution_state.reveal_prefer_capability = "reveal_actions"
    except Exception:
        pass
    # Advance IntentionFrame method ledger (METHOD_INEFFECTIVE under same intention).
    try:
        from plugin.agent.executive.intention_frame import (
            AttemptRecord,
            AttemptValidity,
            FailureClass,
            MethodOutcome,
            MethodStatus,
            active_intention_frame,
            apply_derived_status,
            mark_method_attempted,
            record_method_status,
        )

        iframe = active_intention_frame(execution_state)
        if iframe is not None:
            failed_mid = {
                "context_click": "reveal_context_click",
                "hover": "reveal_hover",
                "select_content": "select_then_toolbar",
            }.get(gesture, "reveal_context_click")
            mark_method_attempted(iframe, failed_mid)
            # Valid motor+obs miss → method ineffective (ledger alone does not block).
            record_method_status(
                iframe,
                failed_mid,
                MethodStatus.INEFFECTIVE.value,
                world_signature=str(getattr(iframe.intention, "scope", "") or ""),
            )
            iframe.attempts.append(
                AttemptRecord(
                    method_id=failed_mid,
                    execution_status="motor_ok",
                    observation_quality=0.9,
                    method_outcome=MethodOutcome.EFFECT_ABSENT.value,
                    failure_class=FailureClass.METHOD_INEFFECTIVE.value,
                    attempt_validity=AttemptValidity.VALID.value,
                    method_status=MethodStatus.INEFFECTIVE.value,
                    evidence_refs=[
                        "expected message action surface absent after settle"
                    ],
                )
            )
            iframe.pending_effect_verification = False
            apply_derived_status(iframe)
            status["intention_id"] = iframe.intention.id
            status["intention_status"] = iframe.status
            status["termination_reason"] = iframe.termination_reason
            status["eligible_methods"] = list(
                iframe.method_frontier.eligible_methods()
            )
    except Exception:
        pass
    status.update(
        {
            "escalated": True,
            "failed_gesture": gesture,
            "next_mode": next_mode,
            "avoid_key": key,
            "prefer_capability": str(
                getattr(execution_state, "reveal_prefer_capability", "") or ""
            ),
        }
    )
    return status


def note_reveal_probe_handoff(
    execution_state: Any,
    *,
    surface: str = "context_menu",
    ttl: int = 2,
    gesture: str = "",
) -> None:
    """Record that a reveal probe ran and the next perceive must ground affordance_set.

    The live loop often motors ``reveal_actions`` via the actor (context_click)
    rather than :func:`reveal_actions` itself; both paths must set this handoff
    so critic promote / phash-block / post-perceive completeness share one signal.

    Also opens/updates an EXPLORE ``IntentionFrame`` so the intention survives
    method failure (architect: intent-level retry, not sticky ACT).
    """
    if execution_state is None:
        return
    try:
        frame = int(getattr(execution_state, "unified_frame", 0) or 0)
        mode = str(gesture or "").strip().lower() or current_reveal_probe_mode(
            execution_state
        )
        execution_state.reveal_handoff = {
            "surface": surface,
            "ttl": int(ttl),
            "opened_frame": frame,
            "incomplete_reveal": True,
            "discovery": "pending_perception",
            "probe_gesture": mode,
        }
        # Keep probe mode aligned with the gesture that just ran.
        if mode in {"context_click", "hover"}:
            execution_state.reveal_probe_mode = mode
        execution_state.reveal_gesture_attempts = int(
            getattr(execution_state, "reveal_gesture_attempts", 0) or 0
        ) + 1
    except Exception:
        pass
    # Intention-frame bookkeeping (best-effort; never block handoff).
    try:
        from plugin.agent.executive.intention_frame import (
            active_intention_frame,
            motivated_perceive_packet,
            push_intention_frame,
            seed_reveal_explore_frame,
        )

        iframe = active_intention_frame(execution_state)
        if iframe is None or str(
            getattr(iframe.intention, "success_predicate", "") or ""
        ) != "forward_affordance_grounded":
            iframe = seed_reveal_explore_frame(
                triggering_uncertainty="forward_affordance_not_grounded"
            )
            push_intention_frame(execution_state, iframe)
        iframe.pending_effect_verification = True
        motivated_perceive_packet(
            iframe,
            purpose="effect_verification",
            question=(
                f"Did {mode or 'reveal'} expose a message action surface "
                "or grounded Forward affordance?"
            ),
            focus="source_message_neighborhood",
        )
    except Exception:
        pass


def _record_handoff(context: Optional[Dict[str, Any]], *, surface: str, ttl: int = 2) -> None:
    """Note the opened surface + a short TTL so a stale overlay can be reaped.

    Enforcement (auto-dismiss after TTL frames) is the controller's to add; the
    idempotent tier-0 read already prevents double-gesturing in the meantime.
    """
    if not isinstance(context, dict):
        return
    note_reveal_probe_handoff(context.get("execution_state"), surface=surface, ttl=ttl)


def reveal_from_request(
    request_arg: str, extras: dict, overlay: Any, runtime: PointerRuntime
) -> CapabilityOutcome:
    entity = resolve_addressable(request_arg, extras, overlay, app=str(extras.get("app") or ""))
    context = reveal_context_from_extras(extras)
    return reveal_actions(
        entity,
        runtime,
        mode=reveal_mode_for(overlay),
        context=context,
        goal_action=str(extras.get("goal_action") or ""),
    ).to_outcome()


def reveal_context_from_extras(extras: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Build the reveal context (surface/layers/frontier) from dispatch extras.

    The layer stack and frontier are what make discovery state-aware and
    groundable; this pulls them off the unified world document / world hints.
    """
    extras = extras or {}
    exec_state = extras.get("execution_state")
    document = extras.get("world_document")
    if not isinstance(document, dict) and exec_state is not None:
        document = getattr(exec_state, "unified_world_document", None)
    if not isinstance(document, dict) and extras.get("world") is not None:
        hints = getattr(extras.get("world"), "overlay_hints", None) or {}
        document = hints.get("unified_document") if isinstance(hints, dict) else None
    document = document if isinstance(document, dict) else {}
    context: Dict[str, Any] = {
        "surface": document.get("surface") or "",
        "layers": document.get("layers") or [],
        "objects": document.get("objects") or [],
        "execution_state": exec_state,
    }
    frontier = extras.get("frontier")
    if isinstance(frontier, dict):
        context["frontier"] = frontier
    return context
