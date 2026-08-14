"""Capability/effect implication registry for prerequisite retirement.

Generic intention machinery asks: do accumulated effect evidence satisfy
``child.success_predicate``? Domain knowledge (Forward, forward_picker, …)
lives here — not in ``intention_frame.py``.

Evidence is fail-closed:
  no authoritative execution/effect result ≠ successful downstream action
  motor/execution ok alone ≠ verified expected effect
  foreign-attempt trajectory grades ≠ current capability verification
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence, Set, Tuple


@dataclass(frozen=True)
class EffectEvidence:
    """Verified world/effect facts and the predicates they imply."""

    achieved: Tuple[str, ...] = ()
    implies: Tuple[str, ...] = ()
    source: str = ""
    attempt_id: str = ""


# Verified surfaces → achieved effects + prerequisite implications.
# Current authoritative world surface needs no attempt bookkeeping.
_SURFACE_IMPLICATIONS: Dict[str, EffectEvidence] = {
    "forward_picker": EffectEvidence(
        achieved=("forward_surface_open", "forward_route_discovered"),
        implies=("source_object_selected",),
        source="world_surface",
    ),
    "destination_picker": EffectEvidence(
        achieved=("forward_surface_open", "forward_route_discovered"),
        implies=("source_object_selected",),
        source="world_surface",
    ),
    "selection_mode": EffectEvidence(
        achieved=("selection_surface_open",),
        implies=("source_object_selected",),
        source="world_surface",
    ),
    "context_menu": EffectEvidence(
        achieved=("message_action_surface_visible",),
        implies=(),
        source="world_surface",
    ),
    "action_menu": EffectEvidence(
        achieved=("message_action_surface_visible",),
        implies=(),
        source="world_surface",
    ),
}


@dataclass(frozen=True)
class CapabilityEffectImplication:
    """Capability invoke → implications when a *specific* effect is verified.

    Generic trajectory grades (``progress``) are never sufficient. Require an
    authoritative destination/forward surface or a named effect predicate.
    """

    capability: str
    target_match: Tuple[str, ...]
    target_prefixes: Tuple[str, ...] = ()
    require_surfaces: Tuple[str, ...] = ()
    require_effect_predicates: Tuple[str, ...] = ()
    implies: Tuple[str, ...] = ()
    achieved: Tuple[str, ...] = ()


_CAPABILITY_IMPLICATIONS: Tuple[CapabilityEffectImplication, ...] = (
    CapabilityEffectImplication(
        capability="invoke_affordance",
        target_match=("forward", "share"),
        target_prefixes=("forward",),
        require_surfaces=("forward_picker", "destination_picker"),
        require_effect_predicates=(
            "forward_surface_open",
            "forward_route_discovered",
        ),
        implies=("source_object_selected",),
        achieved=("forward_route_discovered", "forward_invoked"),
    ),
)


def register_surface_implication(surface: str, evidence: EffectEvidence) -> None:
    """Test/extension hook: register a surface → implication mapping."""
    key = str(surface or "").strip().lower()
    if key:
        _SURFACE_IMPLICATIONS[key] = evidence


def execution_authoritatively_ok(result: Any) -> bool:
    """Fail-closed: missing/malformed result is not success."""
    if not isinstance(result, dict) or not result:
        return False
    if result.get("ok") is not True:
        return False
    status = str(result.get("status") or "").strip().lower()
    if status in {"geometry_mismatch", "fail", "failed", "error"}:
        return False
    return True


def _attempt_id_of(obj: Any) -> str:
    if obj is None:
        return ""
    if isinstance(obj, dict):
        return str(
            obj.get("attempt_id")
            or obj.get("effect_attempt_id")
            or obj.get("action_attempt_id")
            or ""
        ).strip()
    return str(getattr(obj, "attempt_id", "") or "").strip()


def causal_attempt_id(state: Any, step: Any = None) -> str:
    """Authoritative attempt id for the current plan step, or empty."""
    if step is None and state is not None:
        step = getattr(state, "last_plan_step", None)
    aid = _attempt_id_of(step)
    if aid:
        return aid
    if state is None:
        return ""
    return str(
        getattr(state, "last_effect_attempt_id", "")
        or getattr(state, "active_attempt_id", "")
        or ""
    ).strip()


def evidence_is_attempt_scoped(state: Any, step: Any = None) -> bool:
    """True when step attempt_id matches ≥1 non-empty effect-side attempt_id.

    Fail closed on:
    - missing step attempt_id
    - any conflicting effect-side id
    - **no** effect-side id present ("no conflicts" is not alignment)

    Surface-only world facts do not go through this gate.
    """
    if state is None:
        return False
    if step is None:
        step = getattr(state, "last_plan_step", None)
    step_id = _attempt_id_of(step)
    if not step_id:
        return False
    result = getattr(state, "last_result", None)
    attrib = getattr(state, "last_attribution", None)
    closure = getattr(state, "last_effect_closure", None)
    result_id = _attempt_id_of(result)
    attrib_id = _attempt_id_of(attrib)
    closure_id = _attempt_id_of(closure)
    effect_id = str(getattr(state, "last_effect_attempt_id", "") or "").strip()

    aligned_ids = [result_id, attrib_id, closure_id, effect_id]
    for aid in aligned_ids:
        if aid and aid != step_id:
            return False
    # Absence of every effect-side id is uncertainty — fail closed.
    if not any(aid == step_id for aid in aligned_ids if aid):
        return False
    return True


def _predicates_from_bag(bag: Any) -> Set[str]:
    preds: Set[str] = set()
    if not isinstance(bag, dict):
        return preds
    for field in (
        "verified_effect_predicates",
        "achieved_effects",
        "effect_predicates",
    ):
        raw = bag.get(field)
        if isinstance(raw, (list, tuple, set)):
            for item in raw:
                t = str(item or "").strip().lower()
                if t:
                    preds.add(t)
    single = str(
        bag.get("verified_effect") or bag.get("effect_predicate") or ""
    ).strip().lower()
    if single:
        preds.add(single)
    return preds


def verified_effect_predicates(
    state: Any,
    world: Optional[Dict[str, Any]] = None,
    *,
    attempt_id: str = "",
) -> Set[str]:
    """Named effect predicates from current world and *aligned* effect records.

    Attribution/closure bags contribute only when their attempt_id matches
    ``attempt_id`` (fail closed when attempt_id empty — no bag predicates).
    Current world-doc facts always count (authoritative observation).
    """
    preds: Set[str] = set()
    doc = world if isinstance(world, dict) else {}
    for key in (
        "forward_surface_open",
        "forward_route_discovered",
        "selection_surface_open",
        "message_action_surface_visible",
        "source_object_selected",
    ):
        if bool(doc.get(key)):
            preds.add(key)
    if state is None or not str(attempt_id or "").strip():
        return preds
    step_id = str(attempt_id).strip()
    for bag_name in ("last_attribution", "last_effect_closure"):
        bag = getattr(state, bag_name, None)
        if not isinstance(bag, dict):
            continue
        bag_id = _attempt_id_of(bag)
        if not bag_id or bag_id != step_id:
            continue
        preds |= _predicates_from_bag(bag)
    return preds


def effect_verified(
    state: Any,
    *,
    world: Optional[Dict[str, Any]] = None,
    require_surfaces: Sequence[str] = (),
    require_effect_predicates: Sequence[str] = (),
    require_attempt_scoped: bool = False,
    allow_surface_alone: bool = True,
) -> bool:
    """True when a required surface or *named* effect predicate is present.

    Generic trajectory grades (``progress``, ``verified``) are never enough.
    When ``require_attempt_scoped`` is True, attribution/closure predicates are
    only consulted if attempt ids positively align. Current world surface may
    still count when ``allow_surface_alone`` (default True for world facts).
    """
    doc = world if isinstance(world, dict) else {}
    surface = str(doc.get("surface") or doc.get("screen") or "").strip().lower()
    need_surf = {str(s).strip().lower() for s in require_surfaces if str(s).strip()}
    need_pred = {
        str(p).strip().lower() for p in require_effect_predicates if str(p).strip()
    }
    if allow_surface_alone and need_surf and surface in need_surf:
        return True
    if not need_pred:
        return False
    # World-doc predicates are authoritative observation (not action attribution).
    world_preds = {p for p in need_pred if bool(doc.get(p))}
    if world_preds:
        return True
    if require_attempt_scoped and not evidence_is_attempt_scoped(state):
        return False
    step = getattr(state, "last_plan_step", None) if state is not None else None
    step_id = _attempt_id_of(step)
    preds = verified_effect_predicates(state, doc, attempt_id=step_id)
    return bool(preds & need_pred)


def _target_matches(target: str, spec: CapabilityEffectImplication) -> bool:
    t = str(target or "").strip().lower()
    if not t:
        return False
    if t in set(spec.target_match):
        return True
    for prefix in spec.target_prefixes:
        p = str(prefix or "").strip().lower()
        if p and t.startswith(p):
            return True
    return False


def collect_effect_evidence(
    state: Any = None,
    world: Optional[Dict[str, Any]] = None,
) -> EffectEvidence:
    """Merge surface + attempt-scoped capability implications (fail-closed)."""
    doc = world if isinstance(world, dict) else {}
    surface = str(doc.get("surface") or doc.get("screen") or "").strip().lower()
    achieved: Set[str] = set()
    implies: Set[str] = set()
    sources: list[str] = []
    attempt_id = ""

    surf_ev = _SURFACE_IMPLICATIONS.get(surface)
    if surf_ev is not None:
        achieved.update(surf_ev.achieved)
        implies.update(surf_ev.implies)
        if surf_ev.source:
            sources.append(surf_ev.source)

    step = getattr(state, "last_plan_step", None) if state is not None else None
    result = getattr(state, "last_result", None) if state is not None else None
    if step is not None and execution_authoritatively_ok(result):
        fam = str(getattr(step, "action_family", "") or "").strip().lower()
        target = str(
            getattr(step, "semantic_target", None)
            or getattr(step, "text", None)
            or getattr(step, "action", None)
            or ""
        ).strip().lower()
        aligned = evidence_is_attempt_scoped(state, step)
        attempt_id = causal_attempt_id(state, step) if aligned else ""
        for spec in _CAPABILITY_IMPLICATIONS:
            if fam != spec.capability:
                continue
            if not _target_matches(target, spec):
                continue
            # Capability implications that rely on attribution/closure predicates
            # require attempt alignment. Surface match on the *current* world is
            # enough without attribution (authoritative observation).
            surface_ok = surface in {
                str(s).strip().lower() for s in spec.require_surfaces if str(s).strip()
            }
            if not surface_ok and not aligned:
                continue
            if not effect_verified(
                state,
                world=doc,
                require_surfaces=spec.require_surfaces,
                require_effect_predicates=spec.require_effect_predicates,
                require_attempt_scoped=not surface_ok,
            ):
                continue
            achieved.update(spec.achieved)
            implies.update(spec.implies)
            sources.append(f"capability:{spec.capability}")

    # Authoritative task predicates already latched (not inferred from motor).
    try:
        if state is not None:
            feats = getattr(state, "last_features", None)
            extras = getattr(feats, "extras", None) if feats is not None else None
            if not isinstance(extras, dict) and isinstance(feats, dict):
                extras = feats.get("extras") or {}
            ft = extras.get("forward_task") if isinstance(extras, dict) else None
            if isinstance(ft, dict):
                preds = ft.get("predicates") or {}
                if isinstance(preds, dict) and preds.get("source_object_selected") is True:
                    implies.add("source_object_selected")
                    sources.append("task_predicate")
    except Exception:
        pass

    return EffectEvidence(
        achieved=tuple(sorted(achieved)),
        implies=tuple(sorted(implies)),
        source="+".join(sources),
        attempt_id=attempt_id,
    )


def annotate_world_with_effect_evidence(
    state: Any,
    world: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return a world dict enriched with implied predicates from evidence."""
    doc: Dict[str, Any] = dict(world) if isinstance(world, dict) else {}
    evidence = collect_effect_evidence(state, doc)
    if evidence.implies or evidence.achieved:
        doc["effect_evidence"] = {
            "achieved": list(evidence.achieved),
            "implies": list(evidence.implies),
            "source": evidence.source,
            "attempt_id": evidence.attempt_id,
        }
    for pred in evidence.implies:
        doc[pred] = True
        if pred == "source_object_selected":
            doc["downstream_implies_source_selected"] = True
    for ach in evidence.achieved:
        doc[ach] = True
        if ach == "forward_invoked":
            doc["forward_invoked_ok"] = True
        if ach == "forward_route_discovered":
            doc.setdefault("forward_route_discovered", True)
    return doc


def predicate_satisfied_by_evidence(
    predicate: str,
    *,
    world: Optional[Dict[str, Any]] = None,
    evidence: Optional[EffectEvidence] = None,
) -> bool:
    """Generic check: world fact, achieved effect, or implication."""
    pred = str(predicate or "").strip()
    if not pred:
        return True
    doc = world if isinstance(world, dict) else {}
    if bool(doc.get(pred)):
        return True
    ev = evidence
    if ev is None:
        packed = doc.get("effect_evidence") if isinstance(doc.get("effect_evidence"), dict) else None
        if packed:
            ev = EffectEvidence(
                achieved=tuple(packed.get("achieved") or ()),
                implies=tuple(packed.get("implies") or ()),
                source=str(packed.get("source") or ""),
                attempt_id=str(packed.get("attempt_id") or ""),
            )
    if ev is None:
        return False
    if pred in ev.implies or pred in ev.achieved:
        return True
    aliases = {
        "forward_affordance_grounded": (
            "forward_route_discovered",
            "forward_surface_open",
            "forward_invoked",
        ),
        "usable_forwarding_route_discovered": (
            "forward_route_discovered",
            "forward_surface_open",
        ),
        "a grounded forwarding route is discovered": (
            "forward_route_discovered",
            "forward_surface_open",
        ),
        "message_action_surface_visible": ("message_action_surface_visible",),
    }
    for alt in aliases.get(pred.lower(), ()):
        if alt in ev.achieved or alt in ev.implies or bool(doc.get(alt)):
            return True
    return False


def _semantic_container_locus(
    state: Any = None,
    *,
    world: Optional[Dict[str, Any]] = None,
) -> str:
    """App-agnostic semantic locus: conversation/folder/tab/workspace identity."""
    doc = world if isinstance(world, dict) else {}
    for key in (
        "semantic_container",
        "open_conversation",
        "open_container",
        "workspace",
        "document_id",
        "active_tab",
        "folder",
    ):
        val = str(doc.get(key) or "").strip()
        if val:
            return val[:120]
    if state is None:
        return ""
    # Execution-state / task binding fallthroughs.
    for attr in ("last_open_conversation", "open_conversation"):
        val = str(getattr(state, attr, "") or "").strip()
        if val:
            return val[:120]
    try:
        feats = getattr(state, "last_features", None)
        extras = getattr(feats, "extras", None) if feats is not None else None
        if not isinstance(extras, dict) and isinstance(feats, dict):
            extras = feats.get("extras") or {}
        if isinstance(extras, dict):
            for key in (
                "open_conversation",
                "semantic_container",
                "workspace",
            ):
                val = str(extras.get(key) or "").strip()
                if val:
                    return val[:120]
            ft = extras.get("forward_task")
            if isinstance(ft, dict):
                bindings = ft.get("bindings") or {}
                conv = bindings.get("source_conversation") or {}
                if isinstance(conv, dict):
                    val = str(
                        conv.get("resolved_label") or conv.get("label") or ""
                    ).strip()
                    if val:
                        return val[:120]
    except Exception:
        pass
    return ""


def method_context_from_state(
    state: Any = None,
    *,
    world: Optional[Dict[str, Any]] = None,
) -> Any:
    """Build a MethodContext from surface + semantic locus / selection facts."""
    from plugin.agent.executive.intention_frame import MethodContext

    doc = world if isinstance(world, dict) else {}
    surface = str(
        doc.get("surface")
        or doc.get("screen")
        or (getattr(state, "last_surface", "") if state is not None else "")
        or ""
    ).strip().lower()
    selected = bool(
        doc.get("source_object_selected")
        or doc.get("target_selected")
        or doc.get("downstream_implies_source_selected")
    )
    action_surface = surface in {
        "context_menu",
        "action_menu",
        "selection_mode",
        "forward_picker",
        "destination_picker",
    }
    return MethodContext(
        surface=surface,
        semantic_container=_semantic_container_locus(state, world=doc),
        target_selected=selected,
        action_surface_visible=action_surface,
        overlay=surface if action_surface else "",
    )


def scoped_method_avoid_key(
    family: str,
    target: str = "",
    *,
    intention_id: str = "",
    world_signature: str = "",
) -> str:
    """Method+target failure key scoped to intention and world signature."""
    fam = str(family or "").strip().lower()
    tgt = str(target or "").strip().lower()
    intent = str(intention_id or "").strip()
    sig = str(world_signature or "").strip()
    return f"{fam}|{tgt}|intent={intent}|sig={sig}"


def grounded_motor_avoid_key(
    family: str,
    target: str = "",
    point: Any = None,
    *,
    world_signature: str = "",
) -> str:
    """Point-specific avoid key, scoped to the current world signature."""
    from plugin.agent.brain import motor_fingerprint

    base = motor_fingerprint(family, target, point)
    if not base or base == "||":
        return ""
    return f"{base}|sig={str(world_signature or '').strip()}"


def avoid_key_blocks_method(
    avoid_keys: Sequence[str],
    *,
    family: str,
    target: str,
    intention_id: str = "",
    world_signature: str = "",
    point_key: str = "",
    point: Any = None,
) -> bool:
    """True when a world-scoped point key or scoped method key is in avoid set."""
    avoid = {str(k) for k in (avoid_keys or []) if str(k).strip()}
    # Prefer explicitly passed point_key; else build world-scoped grounded key.
    pk = str(point_key or "").strip()
    if not pk and point is not None:
        pk = grounded_motor_avoid_key(
            family, target, point, world_signature=world_signature
        )
    elif pk and "|sig=" not in pk and world_signature:
        pk = f"{pk}|sig={world_signature}"
    if pk and pk in avoid:
        return True
    scoped = scoped_method_avoid_key(
        family,
        target,
        intention_id=intention_id,
        world_signature=world_signature,
    )
    if scoped in avoid:
        return True
    # Legacy bare method keys (fam|tgt|) — only when signature was empty.
    bare = f"{str(family or '').strip().lower()}|{str(target or '').strip().lower()}|"
    if bare in avoid and not world_signature:
        return True
    return False
