"""Thin AffordanceCommitment ledger — executive stickiness, not a second world model.

Stores what the executive remains committed to (method + patient + desired effect).
Derives known / availability / grounded / executable from existing authorities:

- IntentionFrame / MethodSpec — semantic method eligibility
- Affordance frontier / inventory — observed presence
- last_grounded_affordance_set — executable substrate
"""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple


AVAIL_OBSERVED = "observed"
AVAIL_LATENT = "latent"
AVAIL_UNKNOWN = "unknown"

RECOVERY_IDLE = "idle"
RECOVERY_LOCATING = "locating"
RECOVERY_RESTORING_SURFACE = "restoring_surface"
RECOVERY_EXHAUSTED = "exhausted"

STRATEGY_ROI = "roi_perceive"
STRATEGY_AX = "ax_locate"
STRATEGY_OCR = "ocr_locate"
STRATEGY_VLM = "vlm_locate"
STRATEGY_RE_REVEAL = "re_reveal"

_OVERLAY_SURFACES = frozenset(
    {"context_menu", "action_menu", "selection_mode", "forward_picker", "destination_picker"}
)


@dataclass
class AffordanceCommitment:
    """Executive commitment refs + recovery state only (no free-form stage)."""

    commitment_id: str
    intention_id: str = ""
    semantic_method_id: str = ""
    desired_effect: str = ""
    patient_ref: str = ""
    affordance_ref: str = ""
    owner_surface_expected: str = ""
    label: str = ""
    invalid_grounding_keys: List[str] = field(default_factory=list)
    grounding_attempts: List[Dict[str, Any]] = field(default_factory=list)
    grounding_recovery_state: str = RECOVERY_IDLE

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_any(cls, raw: Any) -> Optional["AffordanceCommitment"]:
        if isinstance(raw, AffordanceCommitment):
            return raw
        if not isinstance(raw, dict):
            return None
        cid = str(raw.get("commitment_id") or "").strip()
        if not cid:
            return None
        return cls(
            commitment_id=cid,
            intention_id=str(raw.get("intention_id") or ""),
            semantic_method_id=str(raw.get("semantic_method_id") or ""),
            desired_effect=str(raw.get("desired_effect") or ""),
            patient_ref=str(raw.get("patient_ref") or ""),
            affordance_ref=str(raw.get("affordance_ref") or ""),
            owner_surface_expected=str(raw.get("owner_surface_expected") or ""),
            label=str(raw.get("label") or ""),
            invalid_grounding_keys=[
                str(x) for x in (raw.get("invalid_grounding_keys") or []) if str(x)
            ],
            grounding_attempts=[
                dict(x) for x in (raw.get("grounding_attempts") or []) if isinstance(x, dict)
            ],
            grounding_recovery_state=str(
                raw.get("grounding_recovery_state") or RECOVERY_IDLE
            ),
        )


def semantic_method_id(family: str, label: str) -> str:
    fam = str(family or "").strip().lower()
    lab = str(label or "").strip()
    return f"{fam}:{lab}" if fam and lab else (fam or lab)


def grounding_key_for_point(point: Any) -> str:
    if not isinstance(point, (list, tuple)) or len(point) < 2:
        return ""
    try:
        x, y = float(point[0]), float(point[1])
    except (TypeError, ValueError):
        return ""
    return f"pt:{x:.1f},{y:.1f}"


def _norm_label(text: str) -> str:
    return " ".join(str(text or "").strip().lower().split())


def _label_match(a: str, b: str) -> bool:
    na, nb = _norm_label(a), _norm_label(b)
    if not na or not nb:
        return False
    return na == nb or na in nb or nb in na


def list_commitments(state: Any) -> List[AffordanceCommitment]:
    raw = getattr(state, "affordance_commitments", None) or []
    out: List[AffordanceCommitment] = []
    for item in raw:
        c = AffordanceCommitment.from_any(item)
        if c is not None:
            out.append(c)
    return out


def save_commitments(state: Any, commitments: Sequence[AffordanceCommitment]) -> None:
    try:
        state.affordance_commitments = [c.to_dict() for c in commitments]
    except Exception:
        pass


def active_commitment(state: Any) -> Optional[AffordanceCommitment]:
    cid = str(getattr(state, "grounding_reground_commitment_id", "") or "").strip()
    items = list_commitments(state)
    if cid:
        for c in items:
            if c.commitment_id == cid:
                return c
    # Fall back to most recent non-exhausted commitment for active intention.
    for c in reversed(items):
        if c.grounding_recovery_state != RECOVERY_EXHAUSTED:
            return c
    return items[-1] if items else None


def upsert_commitment(
    state: Any,
    *,
    intention_id: str = "",
    family: str = "invoke_affordance",
    label: str = "",
    desired_effect: str = "",
    patient_ref: str = "",
    affordance_ref: str = "",
    owner_surface_expected: str = "context_menu",
) -> AffordanceCommitment:
    """Create or refresh a commitment for this intention+method+patient."""
    lab = str(label or "").strip()
    method_id = semantic_method_id(family, lab)
    patient = str(patient_ref or "").strip()
    items = list_commitments(state)
    for c in items:
        if (
            c.semantic_method_id == method_id
            and _norm_label(c.patient_ref) == _norm_label(patient)
            and (
                not intention_id
                or not c.intention_id
                or c.intention_id == intention_id
            )
        ):
            if intention_id:
                c.intention_id = intention_id
            if desired_effect:
                c.desired_effect = desired_effect
            if affordance_ref:
                c.affordance_ref = affordance_ref
            if owner_surface_expected:
                c.owner_surface_expected = owner_surface_expected
            if lab:
                c.label = lab
            save_commitments(state, items)
            return c
    c = AffordanceCommitment(
        commitment_id=f"ac_{uuid.uuid4().hex[:12]}",
        intention_id=str(intention_id or ""),
        semantic_method_id=method_id,
        desired_effect=str(desired_effect or ""),
        patient_ref=patient,
        affordance_ref=str(affordance_ref or ""),
        owner_surface_expected=str(owner_surface_expected or "context_menu"),
        label=lab,
    )
    items.append(c)
    # Cap ledger size.
    if len(items) > 8:
        items = items[-8:]
    save_commitments(state, items)
    return c


def _doc_objects(state: Any) -> List[Dict[str, Any]]:
    doc = getattr(state, "unified_world_document", None) or {}
    if not isinstance(doc, dict):
        return []
    objs = doc.get("objects") or []
    return [o for o in objs if isinstance(o, dict)]


def _current_surface(state: Any) -> str:
    doc = getattr(state, "unified_world_document", None) or {}
    if isinstance(doc, dict):
        surf = str(doc.get("surface") or doc.get("screen") or "").strip().lower()
        if surf:
            return surf
    return str(getattr(state, "last_surface", "") or "").strip().lower()


def _object_has_geometry(obj: Dict[str, Any]) -> bool:
    pt = obj.get("point") or obj.get("target_point")
    if isinstance(pt, (list, tuple)) and len(pt) >= 2:
        return True
    bounds = obj.get("bounds")
    if isinstance(bounds, (list, tuple)) and len(bounds) >= 4:
        return True
    if isinstance(bounds, dict) and bounds:
        return True
    acts = obj.get("actuators") or []
    return bool(acts)


def _find_label_object(
    state: Any, *, label: str, patient_ref: str = ""
) -> Optional[Dict[str, Any]]:
    lab = str(label or "").strip()
    if not lab:
        return None
    patient = _norm_label(patient_ref)
    candidates = [
        o
        for o in _doc_objects(state)
        if _label_match(str(o.get("text") or o.get("label") or ""), lab)
    ]
    if not candidates:
        return None
    if patient:
        # Prefer objects whose patient/source refs align when present.
        for o in candidates:
            blob = " ".join(
                str(o.get(k) or "")
                for k in ("patient", "patient_ref", "source", "belongs_to", "owner")
            )
            if patient in _norm_label(blob):
                return o
    return candidates[0]


def derive_availability(state: Any, commitment: AffordanceCommitment) -> str:
    """observed | latent | unknown from owner surface + label presence."""
    surface = _current_surface(state)
    expected = str(commitment.owner_surface_expected or "").strip().lower()
    obj = _find_label_object(
        state, label=commitment.label or commitment.semantic_method_id.split(":")[-1],
        patient_ref=commitment.patient_ref,
    )
    if obj is not None and (not expected or surface == expected or surface in _OVERLAY_SURFACES):
        return AVAIL_OBSERVED
    if commitment.commitment_id:
        # Known commitment but control/surface gone → latent (re-reveal owed).
        if expected and surface and surface != expected and surface not in _OVERLAY_SURFACES:
            return AVAIL_LATENT
        if obj is None and expected:
            return AVAIL_LATENT
    return AVAIL_UNKNOWN


def derive_grounded(state: Any, commitment: AffordanceCommitment) -> bool:
    lab = commitment.label or (
        commitment.semantic_method_id.split(":")[-1]
        if ":" in commitment.semantic_method_id
        else ""
    )
    obj = _find_label_object(state, label=lab, patient_ref=commitment.patient_ref)
    if obj is None:
        return False
    if not _object_has_geometry(obj):
        return False
    gkey = grounding_key_for_point(obj.get("point") or obj.get("target_point"))
    if gkey and gkey in set(commitment.invalid_grounding_keys or []):
        return False
    return True


def derive_executable(state: Any, commitment: AffordanceCommitment) -> bool:
    lab = _norm_label(
        commitment.label
        or (
            commitment.semantic_method_id.split(":")[-1]
            if ":" in commitment.semantic_method_id
            else ""
        )
    )
    patient = _norm_label(commitment.patient_ref)
    for aff in getattr(state, "last_grounded_affordance_set", None) or []:
        if not isinstance(aff, dict):
            continue
        alab = _norm_label(str(aff.get("target_label") or aff.get("label") or ""))
        if not alab or not _label_match(alab, lab):
            continue
        if patient:
            blob = _norm_label(
                " ".join(
                    str(aff.get(k) or "")
                    for k in ("patient_ref", "patient", "source", "owner")
                )
            )
            # If patient metadata present and mismatches, reject.
            if blob and patient not in blob and blob not in patient:
                # Still accept when affordance set items lack patient metadata.
                if any(aff.get(k) for k in ("patient_ref", "patient", "source", "owner")):
                    continue
        gkey = grounding_key_for_point(
            (aff.get("actuators") or [{}])[0].get("point")
            if isinstance(aff.get("actuators"), list) and aff.get("actuators")
            else aff.get("point")
        )
        if gkey and gkey in set(commitment.invalid_grounding_keys or []):
            continue
        return True
    return False


def commitment_view(state: Any, commitment: AffordanceCommitment) -> Dict[str, Any]:
    avail = derive_availability(state, commitment)
    grounded = derive_grounded(state, commitment)
    executable = derive_executable(state, commitment)
    return {
        "commitment_id": commitment.commitment_id,
        "known": True,
        "availability": avail,
        "grounded": bool(grounded),
        "executable": bool(executable),
        "semantic_method_id": commitment.semantic_method_id,
        "desired_effect": commitment.desired_effect,
        "patient_ref": commitment.patient_ref,
        "label": commitment.label,
        "recovery_state": commitment.grounding_recovery_state,
    }


def evidence_indicates_grounding_failure(
    *,
    pred_error: Optional[Dict[str, Any]] = None,
    point: Any = None,
    intended_bounds: Any = None,
    intended_point: Any = None,
    surface_before: str = "",
    surface_after: str = "",
    click_audit: Optional[Dict[str, Any]] = None,
    message: str = "",
) -> Tuple[bool, str]:
    """True only when evidence says the grounding hypothesis was bad.

    Effect absence alone is insufficient.
    """
    reasons: List[str] = []
    err = pred_error if isinstance(pred_error, dict) else {}
    audit = click_audit if isinstance(click_audit, dict) else {}
    msg = str(message or err.get("verdict") or err.get("message") or "").lower()
    status_bits = " ".join(
        str(x or "").lower()
        for x in (
            msg,
            audit.get("status"),
            audit.get("reason"),
            err.get("geometry_mismatch"),
            err.get("failure_class"),
        )
    )

    for tok in (
        "outside task window",
        "off_task_window",
        "stale_coordinate_frame",
        "unknown_coordinate_frame",
        "grounding_uncertain",
        "inconclusive_grounding",
        "invalid_coordinate",
        "geometry_mismatch",
        "off_target",
        "wrong_object",
        "hit_different",
    ):
        if tok in status_bits:
            reasons.append(tok)

    if audit.get("grounding_uncertain") or audit.get("off_task_window"):
        reasons.append("audit_grounding_flag")

    # Point clearly outside intended bounds → grounding.
    if (
        isinstance(point, (list, tuple))
        and len(point) >= 2
        and isinstance(intended_bounds, (list, tuple))
        and len(intended_bounds) >= 4
    ):
        try:
            x, y = float(point[0]), float(point[1])
            x0, y0, x1, y1 = [float(v) for v in intended_bounds[:4]]
            # Support (x,y,w,h) as well as (x0,y0,x1,y1).
            if x1 < 2000 and y1 < 2000 and x1 > x0 and y1 > y0:
                # likely x0,y0,x1,y1
                inside = x0 <= x <= x1 and y0 <= y <= y1
            else:
                inside = x0 <= x <= x0 + x1 and y0 <= y <= y0 + y1
            if not inside:
                reasons.append("point_outside_intended_bounds")
        except (TypeError, ValueError):
            pass

    # Weak / mismatched provenance: click point far from intended control point.
    if (
        isinstance(point, (list, tuple))
        and len(point) >= 2
        and isinstance(intended_point, (list, tuple))
        and len(intended_point) >= 2
    ):
        try:
            dx = float(point[0]) - float(intended_point[0])
            dy = float(point[1]) - float(intended_point[1])
            if (dx * dx + dy * dy) ** 0.5 > 120.0:
                reasons.append("point_far_from_intended_control")
        except (TypeError, ValueError):
            pass

    # Overlay expected but point sits in left-rail search band while control was
    # conversation/menu — classic live 141617 Forward @ (560,290).
    if isinstance(point, (list, tuple)) and len(point) >= 2:
        try:
            x = float(point[0])
            before = str(surface_before or "").strip().lower()
            if before in _OVERLAY_SURFACES or "context_menu" in str(
                err.get("expected_surface") or err.get("predicted") or ""
            ).lower():
                # WhatsApp left pane search results commonly < 700px.
                if x < 700.0 and (
                    "forward" in str(err.get("target") or msg).lower()
                    or "menu" in before
                    or "context_menu" in before
                ):
                    reasons.append("point_in_sidebar_while_menu_verb_expected")
        except (TypeError, ValueError):
            pass

    if reasons:
        return True, ",".join(reasons[:4])
    return False, ""


def invalidate_grounding_hypothesis(
    state: Any,
    commitment: AffordanceCommitment,
    *,
    point: Any = None,
    grounding_key: str = "",
    strategy: str = "",
    outcome: str = "miss",
    capture_id: str = "",
) -> AffordanceCommitment:
    key = str(grounding_key or grounding_key_for_point(point) or "").strip()
    items = list_commitments(state)
    for c in items:
        if c.commitment_id != commitment.commitment_id:
            continue
        if key and key not in c.invalid_grounding_keys:
            c.invalid_grounding_keys.append(key)
            c.invalid_grounding_keys = c.invalid_grounding_keys[-16:]
        c.grounding_attempts.append(
            {
                "strategy": str(strategy or "point_invoke"),
                "capture_id": str(capture_id or ""),
                "outcome": str(outcome or "miss"),
                "grounding_key": key,
                "ts": time.time(),
            }
        )
        c.grounding_attempts = c.grounding_attempts[-24:]
        save_commitments(state, items)
        return c
    return commitment


def arm_grounding_recovery(
    state: Any,
    commitment: AffordanceCommitment,
    *,
    reason: str = "",
) -> None:
    """Scope reground debt to this commitment/patient/method."""
    avail = derive_availability(state, commitment)
    items = list_commitments(state)
    for c in items:
        if c.commitment_id != commitment.commitment_id:
            continue
        if avail == AVAIL_LATENT:
            c.grounding_recovery_state = RECOVERY_RESTORING_SURFACE
        else:
            c.grounding_recovery_state = RECOVERY_LOCATING
        break
    save_commitments(state, items)
    try:
        state.grounding_reground_only = True
        state.grounding_reground_commitment_id = commitment.commitment_id
        state.grounding_reground_target = str(commitment.label or "")
        state.grounding_reground_patient_ref = str(commitment.patient_ref or "")
        state.grounding_reground_method_id = str(commitment.semantic_method_id or "")
        state.grounding_reground_owner_surface = str(
            commitment.owner_surface_expected or ""
        )
        state.must_executive_reperceive = True
        closure = dict(getattr(state, "last_effect_closure", None) or {})
        closure["grounding_repair"] = "commitment_reground"
        closure["commitment_id"] = commitment.commitment_id
        closure["availability"] = avail
        if reason:
            closure["grounding_evidence"] = reason
        # Latent → re-reveal; observed ungrounded → locate (not explore thrash).
        if avail == AVAIL_LATENT:
            closure["recovery"] = "re_reveal_for_commitment"
            if not str(getattr(state, "reveal_prefer_capability", "") or "").strip():
                state.reveal_prefer_capability = "reveal_actions"
        else:
            closure["recovery"] = "locate_committed_affordance"
        state.last_effect_closure = closure
    except Exception:
        pass


def clear_grounding_recovery(state: Any) -> None:
    cid = str(getattr(state, "grounding_reground_commitment_id", "") or "")
    items = list_commitments(state)
    for c in items:
        if not cid or c.commitment_id == cid:
            if c.grounding_recovery_state in {
                RECOVERY_LOCATING,
                RECOVERY_RESTORING_SURFACE,
            }:
                c.grounding_recovery_state = RECOVERY_IDLE
    save_commitments(state, items)
    try:
        state.grounding_reground_only = False
        state.grounding_reground_commitment_id = ""
        state.grounding_reground_target = ""
        state.grounding_reground_patient_ref = ""
        state.grounding_reground_method_id = ""
        state.grounding_reground_owner_surface = ""
    except Exception:
        pass


def patient_click_allowed_for_commitment(
    state: Any,
    *,
    family: str = "",
    target_label: str = "",
) -> bool:
    """True only when patient click is the explicit re-reveal recovery strategy."""
    c = active_commitment(state)
    if c is None:
        return True  # no commitment → existing policy
    if derive_executable(state, c):
        return True
    fam = str(family or "").strip().lower()
    avail = derive_availability(state, c)
    restoring = (
        bool(getattr(state, "grounding_reground_only", False))
        and (
            avail == AVAIL_LATENT
            or c.grounding_recovery_state == RECOVERY_RESTORING_SURFACE
        )
    )
    if restoring and fam in {
        "reveal_actions",
        "select_content",
        "right_click",
        "context_click",
    }:
        return True
    # Known-ungrounded commitment: geometry must not silently change intent.
    return False


def forbids_patient_substitute(
    state: Any,
    *,
    family: str = "",
    semantic_target: str = "",
) -> bool:
    """Hierarchical gate: committed method must not be replaced by grounded patient."""
    c = active_commitment(state)
    if c is None:
        return False
    if derive_executable(state, c):
        return False
    fam = str(family or "").strip().lower()
    if fam in {
        "invoke_affordance",
        "select_content",
        "reveal_actions",
        "right_click",
        "context_click",
    }:
        return not patient_click_allowed_for_commitment(state, family=fam)
    return False


def forbids_wrong_locus(
    state: Any,
    *,
    family: str = "",
    semantic_target: str = "",
    field_role: str = "",
    target_kind: str = "",
    brief: Any = None,
) -> bool:
    """General wrong-locus gate: field + container + patient.

    Patient path keeps ``forbids_patient_substitute`` behavior. Field/container
    paths consult ``locus_contract.wrong_locus_forbidden``.
    """
    fam = str(family or "").strip().lower()
    if forbids_patient_substitute(
        state, family=fam, semantic_target=semantic_target
    ):
        return True
    try:
        from plugin.agent.capabilities.locus_contract import wrong_locus_forbidden

        bad, _, _ = wrong_locus_forbidden(
            fam,
            brief=brief,
            state=state,
            field_role=field_role,
            label=str(semantic_target or ""),
            target_kind=target_kind,
        )
        return bool(bad)
    except Exception:
        return False


def next_grounding_strategy(state: Any, commitment: AffordanceCommitment) -> str:
    """Pick next strategy from availability + prior outcomes (ladder this pass)."""
    avail = derive_availability(state, commitment)
    tried = {
        (
            str(a.get("strategy") or ""),
            str(a.get("outcome") or ""),
        )
        for a in (commitment.grounding_attempts or [])
    }
    failed = {
        str(a.get("strategy") or "")
        for a in (commitment.grounding_attempts or [])
        if str(a.get("outcome") or "") in {"miss", "fail", "wrong_point"}
    }
    if avail == AVAIL_LATENT:
        if STRATEGY_RE_REVEAL not in failed:
            return STRATEGY_RE_REVEAL
        return STRATEGY_RE_REVEAL  # keep restoring until surface returns
    # observed / unknown → locate ladder
    for strat in (STRATEGY_ROI, STRATEGY_AX, STRATEGY_OCR, STRATEGY_VLM):
        if strat not in failed:
            return strat
    if STRATEGY_RE_REVEAL not in failed:
        return STRATEGY_RE_REVEAL
    return STRATEGY_ROI


def note_strategy_attempt(
    state: Any,
    commitment: AffordanceCommitment,
    *,
    strategy: str,
    outcome: str,
    grounding_key: str = "",
    capture_id: str = "",
) -> None:
    invalidate_grounding_hypothesis(
        state,
        commitment,
        grounding_key=grounding_key,
        strategy=strategy,
        outcome=outcome,
        capture_id=capture_id,
    )


def commitment_satisfied_by_label_patient(
    commitment: AffordanceCommitment,
    *,
    label: str,
    patient_ref: str,
) -> bool:
    """Same label on a different patient must not satisfy the commitment."""
    if not _label_match(commitment.label or commitment.semantic_method_id, label):
        return False
    cp = _norm_label(commitment.patient_ref)
    pp = _norm_label(patient_ref)
    if not cp:
        return True
    if not pp:
        return False
    return cp == pp or cp in pp or pp in cp


def handle_failed_committed_action(
    state: Any,
    *,
    family: str,
    target: str,
    point: Any = None,
    pred_error: Optional[Dict[str, Any]] = None,
    intended_bounds: Any = None,
    intended_point: Any = None,
    click_audit: Optional[Dict[str, Any]] = None,
    surface_before: str = "",
    surface_after: str = "",
) -> Dict[str, Any]:
    """Generic: if failure matches active commitment and evidence→GROUNDING, recover.

    Returns a small result dict for logging; empty if not applicable.
    """
    c = active_commitment(state)
    # Also match by method id when reground id unset but commitment exists.
    if c is None:
        items = list_commitments(state)
        method = semantic_method_id(family, target)
        for item in reversed(items):
            if item.semantic_method_id == method or _label_match(item.label, target):
                c = item
                break
    if c is None:
        return {}
    # Must correspond to this commitment's method/label.
    if not (
        _label_match(c.label, target)
        or semantic_method_id(family, target) == c.semantic_method_id
        or str(family or "").strip().lower() in c.semantic_method_id
    ):
        return {}

    is_grounding, reason = evidence_indicates_grounding_failure(
        pred_error=pred_error,
        point=point,
        intended_bounds=intended_bounds,
        intended_point=intended_point,
        surface_before=surface_before or str(
            (pred_error or {}).get("expected_surface")
            or (pred_error or {}).get("predicted")
            or ""
        ),
        surface_after=surface_after,
        click_audit=click_audit,
        message=str((pred_error or {}).get("verdict") or ""),
    )
    if not is_grounding:
        return {
            "commitment_id": c.commitment_id,
            "classified": "not_grounding",
            "reason": "effect_absent_without_grounding_evidence",
        }

    c = invalidate_grounding_hypothesis(
        state, c, point=point, strategy="point_invoke", outcome="wrong_point"
    )
    arm_grounding_recovery(state, c, reason=reason)
    return {
        "commitment_id": c.commitment_id,
        "classified": "grounding",
        "attempt_validity": "inconclusive_grounding",
        "failure_class": "grounding",
        "reason": reason,
        "availability": derive_availability(state, c),
        "preserve_semantic_method": c.semantic_method_id,
    }


def ensure_commitment_from_menu_observation(
    state: Any,
    *,
    label: str,
    patient_ref: str = "",
    affordance_ref: str = "",
    desired_effect: str = "",
    owner_surface: str = "context_menu",
    intention_id: str = "",
) -> Optional[AffordanceCommitment]:
    """When a goal menu verb is observed (even label-only), stick the commitment."""
    lab = str(label or "").strip()
    if not lab:
        return None
    # Infer intention id from active frame when omitted.
    iid = str(intention_id or "")
    if not iid:
        try:
            from plugin.agent.executive.intention_frame import active_intention_frame

            iframe = active_intention_frame(state)
            iid = str(getattr(getattr(iframe, "intention", None), "id", "") or "")
        except Exception:
            iid = ""
    effect = str(desired_effect or "").strip()
    if not effect and _norm_label(lab) in {"forward", "share"}:
        effect = "forward_picker"
    return upsert_commitment(
        state,
        intention_id=iid,
        family="invoke_affordance",
        label=lab,
        desired_effect=effect,
        patient_ref=patient_ref,
        affordance_ref=affordance_ref,
        owner_surface_expected=owner_surface or "context_menu",
    )
