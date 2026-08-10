"""REFLECT as a capable recovery module — fault localization + repair.

Surprise (predicted transition absent / wrong) must not collapse to "look again".
REFLECT's job is to localize *where* the perceptor→brain→actor contract broke
and emit one actionable repair the brain can execute once.

Domain-general: WhatsApp Forward, Finder menus, and any UI affordance use the
same loci and repair kinds. Task-specific labels live only in evidence strings.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple


# Where in the pipeline the surprise most likely originated.
FAULT_LOCI = frozenset(
    {
        "perception",  # wrong pre-act world / reveal grounding
        "handoff",  # brain choice diverged from inventory geometry/label
        "actor",  # motor path / gesture / landed ≠ intended
        "world_semantics",  # world moved, but not to the predicted place
        "prediction",  # expectation itself was wrong / overconfident
        "unknown",
    }
)

# How the world responded relative to the prediction.
TRANSITION_CLASSES = frozenset(
    {
        "no_effect",
        "wrong_transition",
        "partial_transition",  # e.g. selection chrome instead of picker
        "occlusion",
        "stale",
        "matched",
        "unknown",
    }
)

# Closed cause set (superset of legacy surprise_explanation causes).
CAUSES = frozenset(
    {
        "wrong_target",
        "no_effect",
        "wrong_surface",
        "occlusion",
        "stale_geometry",
        "motor_miss",
        "motor_path",  # ok gesture, wrong backend path (background AXPress, …)
        "handoff_loss",  # prose≠point / family remap / geometry dropped
        "partial_effect",  # moved, but not to predicted surface
        "unknown",
    }
)

# What the brain should do once after diagnosis.
REPAIR_KINDS = frozenset(
    {
        "retry_with_corrected_geometry",
        "retry_same_affordance_different_motor",
        "follow_observed_transition",
        "re_ground_then_act",
        "backtrack_dismiss",
        "invoke_revert_effects",
        "reperceive",
    }
)

# Map repair → legacy recommended_next for older readers.
_REPAIR_TO_NEXT = {
    "retry_with_corrected_geometry": "act",
    "retry_same_affordance_different_motor": "act",
    "follow_observed_transition": "act",
    "re_ground_then_act": "act",
    "backtrack_dismiss": "explore",
    "invoke_revert_effects": "act",
    "reperceive": "reperceive",
}

# Legacy recommended_next values still accepted.
# recommended_next uses v1 meta vocabulary (explore replaces legacy backtrack meta).
NEXT_MOVES = frozenset({"act", "explore", "reperceive", "think", "search"})


@dataclass
class ReflectRepair:
    """One executable repair constraint for the brain after REFLECT."""

    kind: str = "reperceive"
    capability: str = ""
    target: str = ""
    geometry: Optional[List[float]] = None  # point [x,y]
    bounds: Optional[List[float]] = None
    motor_constraint: str = ""  # e.g. foreground_click, forbid_background_ax
    detail: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if self.geometry is None:
            d.pop("geometry", None)
        if self.bounds is None:
            d.pop("bounds", None)
        if not self.motor_constraint:
            d.pop("motor_constraint", None)
        return {k: v for k, v in d.items() if v not in (None, "", [], {})}


@dataclass
class ReflectDiagnosis:
    """Authoritative output of the REFLECT recovery module."""

    cause: str = "unknown"
    locus: str = "unknown"
    transition_class: str = "unknown"
    confidence: float = 0.0
    detail: str = ""
    evidence: List[str] = field(default_factory=list)
    repair: ReflectRepair = field(default_factory=ReflectRepair)
    do_not_repeat: List[str] = field(default_factory=list)
    # Legacy alias fields kept for surprise_explanation consumers.
    recommended_next: str = "reperceive"
    corrected_point: Optional[List[float]] = None
    source: str = ""  # model | runtime_seed | merged

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "cause": self.cause,
            "locus": self.locus,
            "transition_class": self.transition_class,
            "confidence": round(float(self.confidence), 3),
            "detail": self.detail[:300],
            "evidence": list(self.evidence)[:8],
            "repair": self.repair.to_dict(),
            "do_not_repeat": list(self.do_not_repeat)[:8],
            "recommended_next": self.recommended_next,
            "source": self.source,
        }
        if self.corrected_point is not None:
            out["corrected_point"] = list(self.corrected_point)
        return out

    def to_surprise_explanation(self) -> Dict[str, Any]:
        """Backward-compatible surprise_explanation dict (+ repair/locus)."""
        d = self.to_dict()
        # Keep the fields older code reads first-class.
        return d


def _xy(raw: Any) -> Optional[List[float]]:
    if not isinstance(raw, (list, tuple)) or len(raw) < 2:
        return None
    try:
        return [float(raw[0]), float(raw[1])]
    except (TypeError, ValueError):
        return None


def _norm(raw: Any) -> str:
    return str(raw or "").strip().lower().replace("-", "_")


def _clip_conf(raw: Any) -> float:
    try:
        return max(0.0, min(1.0, float(raw)))
    except (TypeError, ValueError):
        return 0.0


def normalize_repair(raw: Any) -> ReflectRepair:
    if not isinstance(raw, dict):
        return ReflectRepair()
    kind = _norm(raw.get("kind") or raw.get("repair_kind"))
    if kind not in REPAIR_KINDS:
        # Infer from legacy recommended_next / presence of geometry.
        nxt = _norm(raw.get("recommended_next"))
        if _xy(raw.get("geometry") or raw.get("corrected_point")):
            kind = "retry_with_corrected_geometry"
        elif nxt in {"backtrack", "explore"}:
            kind = "backtrack_dismiss"
        elif nxt == "act":
            kind = "re_ground_then_act"
        else:
            kind = "reperceive"
    geo = _xy(raw.get("geometry") or raw.get("corrected_point") or raw.get("point"))
    bounds = raw.get("bounds")
    b: Optional[List[float]] = None
    if isinstance(bounds, (list, tuple)) and len(bounds) >= 4:
        try:
            b = [float(x) for x in bounds[:4]]
        except (TypeError, ValueError):
            b = None
    return ReflectRepair(
        kind=kind,
        capability=_norm(raw.get("capability") or raw.get("family")).replace(" ", "_"),
        target=str(raw.get("target") or raw.get("label") or "").strip()[:120],
        geometry=geo,
        bounds=b,
        motor_constraint=str(raw.get("motor_constraint") or "").strip()[:80],
        detail=str(raw.get("detail") or "").strip()[:200],
    )


def normalize_reflect_diagnosis(raw: Any) -> ReflectDiagnosis:
    """Clamp model/runtime diagnosis to the closed ReflectDiagnosis schema."""
    if not isinstance(raw, dict) or not raw:
        return ReflectDiagnosis()

    cause = _norm(raw.get("cause"))
    if cause not in CAUSES:
        cause = "unknown"
    locus = _norm(raw.get("locus") or raw.get("fault_locus"))
    if locus not in FAULT_LOCI:
        locus = "unknown"
    tclass = _norm(raw.get("transition_class") or raw.get("transition"))
    if tclass not in TRANSITION_CLASSES:
        tclass = "unknown"

    repair_raw = raw.get("repair") if isinstance(raw.get("repair"), dict) else raw
    repair = normalize_repair(repair_raw)
    # If model only sent legacy fields, fold corrected_point into repair.
    corrected = _xy(raw.get("corrected_point"))
    if corrected and repair.geometry is None:
        repair.geometry = corrected
        if repair.kind == "reperceive":
            repair.kind = "retry_with_corrected_geometry"

    next_move = _norm(raw.get("recommended_next"))
    if next_move not in NEXT_MOVES:
        next_move = _REPAIR_TO_NEXT.get(repair.kind, "reperceive")
    # Repair kind wins when it implies a next move.
    implied = _REPAIR_TO_NEXT.get(repair.kind)
    if implied:
        next_move = implied

    evidence = [str(x)[:140] for x in (raw.get("evidence") or []) if str(x).strip()][:8]
    do_not = [str(x)[:80] for x in (raw.get("do_not_repeat") or []) if str(x).strip()][:8]

    return ReflectDiagnosis(
        cause=cause,
        locus=locus,
        transition_class=tclass,
        confidence=_clip_conf(raw.get("confidence")),
        detail=str(raw.get("detail") or "")[:300],
        evidence=evidence,
        repair=repair,
        do_not_repeat=do_not,
        recommended_next=next_move,
        corrected_point=corrected or repair.geometry,
        source=str(raw.get("source") or "model").strip()[:32],
    )


def diagnosis_is_authoritative(diagnosis: ReflectDiagnosis, *, floor: float = 0.85) -> bool:
    if diagnosis.cause == "unknown" and diagnosis.repair.kind == "reperceive":
        return False
    return float(diagnosis.confidence or 0.0) >= float(floor)


def _objects(doc: Any) -> List[Dict[str, Any]]:
    if not isinstance(doc, dict):
        return []
    return [o for o in (doc.get("objects") or []) if isinstance(o, dict)]


def _label_is_forward_cta(label: str) -> bool:
    """True for Forward CTA; false for 'Forwarded…' chat chrome."""
    text = str(label or "").strip().lower()
    text = re.sub(r"^[\s•·▪●◦\-–—]+", "", text).strip()
    if not text or text.startswith("forwarded"):
        return False
    return text in {"forward", "forward message", "forward messages"} or text.startswith(
        "forward "
    )


def _find_control(
    objects: Sequence[Dict[str, Any]],
    *,
    labels: Sequence[str],
    kinds: Sequence[str] = (),
) -> Optional[Dict[str, Any]]:
    want_labels = {str(x).strip().lower() for x in labels if str(x).strip()}
    want_kinds = {str(x).strip().lower() for x in kinds if str(x).strip()}
    want_forward = "forward" in want_labels
    for obj in objects:
        raw_label = str(obj.get("text") or obj.get("label") or "")
        text = " ".join(
            str(obj.get(k) or "") for k in ("text", "label", "id", "kind")
        ).lower()
        kind = str(obj.get("kind") or "").strip().lower()
        if want_forward and not _label_is_forward_cta(raw_label):
            # Avoid matching chat chrome "Forwarded: …" as the Forward CTA.
            if want_labels <= {"forward"}:
                continue
        if want_kinds and kind not in want_kinds and not any(k in kind for k in want_kinds):
            # still allow label hit
            if not any(lbl in text for lbl in want_labels):
                continue
        if any(lbl in text for lbl in want_labels):
            return obj
    return None


def _object_near_point(
    objects: Sequence[Dict[str, Any]],
    point: Optional[Sequence[float]],
    *,
    pad: float = 96.0,
) -> Optional[Dict[str, Any]]:
    """Nearest inventory object within ``pad`` of ``point``, preferring matches_goal."""
    if point is None or len(point) < 2:
        return None
    try:
        px, py = float(point[0]), float(point[1])
    except (TypeError, ValueError):
        return None
    best: Optional[Dict[str, Any]] = None
    best_d = float("inf")
    for obj in objects:
        op = _xy(obj.get("point"))
        if op is None:
            continue
        d = ((op[0] - px) ** 2 + (op[1] - py) ** 2) ** 0.5
        if d > pad:
            continue
        # Prefer goal-matched content over chrome at the same distance.
        score = d - (40.0 if obj.get("matches_goal") else 0.0)
        if score < best_d:
            best_d = score
            best = obj
    return best


def _executor_suggests_background_ax(message: str) -> bool:
    m = str(message or "").lower()
    return "in background" in m or "background (no foreground)" in m


def _selection_chrome_present(objects: Sequence[Dict[str, Any]], surface: str) -> bool:
    blob = " ".join(
        str(o.get("text") or o.get("label") or "") for o in objects
    ).lower()
    if "selected" in blob and "forward" in blob:
        return True
    if "selected" in blob:
        fwd = _find_control(
            objects,
            labels=("forward",),
            kinds=("button", "menu_item", "toolbar_button", "toolbar"),
        )
        if fwd is not None:
            return True
    return False


def _selection_consistency_from_packet(
    reflect_packet: Dict[str, Any],
    doc: Dict[str, Any],
) -> Dict[str, Any]:
    """Prefer packet-provided verdict; else compute from post_world + goal."""
    measured = reflect_packet.get("measured") if isinstance(reflect_packet.get("measured"), dict) else {}
    sel = measured.get("selection_consistency") or reflect_packet.get("selection_consistency")
    if isinstance(sel, dict) and "consistent" in sel:
        return sel
    try:
        from plugin.agent.capabilities.revert_effects import selection_consistency_error

        goal = reflect_packet.get("goal") if isinstance(reflect_packet.get("goal"), dict) else {}
        referents = []
        for key in ("link_query", "content_query", "goal_referents"):
            val = goal.get(key) if goal else None
            if isinstance(val, (list, tuple)):
                referents.extend(str(x) for x in val if str(x).strip())
            elif val:
                referents.append(str(val))
        for item in reflect_packet.get("goal_referents") or []:
            if str(item).strip():
                referents.append(str(item))
        action = reflect_packet.get("action") if isinstance(reflect_packet.get("action"), dict) else {}
        return selection_consistency_error(
            doc,
            goal_referents=referents,
            semantic_target=str(action.get("target") or action.get("text") or ""),
            selected_label=str(
                measured.get("selected_object_label")
                or goal.get("selected_object_label")
                or ""
            ),
        )
    except Exception:
        return {}


def seed_reflect_diagnosis_from_measured(
    reflect_packet: Dict[str, Any],
    *,
    post_document: Optional[Dict[str, Any]] = None,
) -> ReflectDiagnosis:
    """Runtime seed diagnosis from measured facts (no LLM).

    Used to (a) prefill discovery for the model and (b) fill a repair when the
    model returns weak/unknown. Tuned from zarooratwala 145239 Forward miss:
    predicted forward_picker, AXPress-in-background, landed in selection chrome.

    Live 132831: goal-inconsistent multi-select ("2 Selected" with non-goal
    content) must invoke_revert_effects — never follow toolbar Forward.
    """
    if not isinstance(reflect_packet, dict):
        return ReflectDiagnosis(source="runtime_seed")

    action = reflect_packet.get("action") if isinstance(reflect_packet.get("action"), dict) else {}
    expected = reflect_packet.get("expected") if isinstance(reflect_packet.get("expected"), dict) else {}
    actual = reflect_packet.get("actual") if isinstance(reflect_packet.get("actual"), dict) else {}
    measured = reflect_packet.get("measured") if isinstance(reflect_packet.get("measured"), dict) else {}

    exec_msg = str(action.get("executor_message") or measured.get("executor_message") or "")
    pred = _norm(expected.get("surface") or actual.get("predicted_surface"))
    obs = _norm(actual.get("observed_surface") or actual.get("surface"))
    matched = actual.get("matched")
    family = _norm(action.get("family") or action.get("action"))
    target = str(action.get("target") or action.get("text") or "").strip()

    doc = post_document if isinstance(post_document, dict) else {}
    if not doc:
        # Prefer post-world objects from packet if present.
        post = reflect_packet.get("post_world")
        if isinstance(post, dict):
            doc = post
    objects = _objects(doc)
    evidence: List[str] = []

    # --- Post-revert reselect (pending after successful revert_effects) ---
    pending = reflect_packet.get("pending_repair_after_revert")
    if isinstance(pending, dict) and pending.get("repair_kind") == "re_ground_then_act":
        if not _selection_chrome_present(objects, obs):
            hint = str(pending.get("target_hint") or target or "").strip()
            goal_obj = None
            for obj in objects:
                if obj.get("matches_goal") and _norm(obj.get("kind")) in {
                    "message",
                    "message_bubble",
                    "link",
                    "content",
                }:
                    goal_obj = obj
                    break
            geo = _xy((goal_obj or {}).get("point")) if goal_obj else None
            return ReflectDiagnosis(
                cause="partial_effect",
                locus="world_semantics",
                transition_class="matched",
                confidence=0.9,
                detail="Selection cleared by revert; re-ground and select goal content.",
                evidence=["pending_repair_after_revert", "selection_chrome_absent"],
                repair=ReflectRepair(
                    kind="re_ground_then_act",
                    capability=str(pending.get("capability") or "select_content"),
                    target=hint
                    or str((goal_obj or {}).get("text") or (goal_obj or {}).get("label") or ""),
                    geometry=geo,
                    detail="Reselect goal content with fresh inventory geometry",
                ),
                do_not_repeat=["follow_forward_after_bad_selection", "observe_while_goal_visible"],
                recommended_next="act",
                corrected_point=geo,
                source="runtime_seed",
            )

    # --- Branch unfit (typed blockers / barren search): backtrack ≡ revert ---
    try:
        from plugin.agent.capabilities.branch_fitness import (
            compute_branch_fitness,
            needed_evidence_kinds_for_goal,
        )

        goal = reflect_packet.get("goal") if isinstance(reflect_packet.get("goal"), dict) else {}
        refs = list(reflect_packet.get("goal_referents") or [])
        for key in ("link_query", "content_query"):
            if goal.get(key):
                refs.append(str(goal.get(key)))
        world = doc
        try:
            from plugin.agent.apps.registry import get_overlay

            overlay = get_overlay(str(goal.get("app") or "WhatsApp"), None)
            enrich = getattr(overlay, "enrich_world_document", None)
            if callable(enrich):
                world = enrich(doc)
        except Exception:
            world = doc
        fit = reflect_packet.get("branch_fitness")
        if not isinstance(fit, dict):
            fit = compute_branch_fitness(
                world,
                needed_kinds=needed_evidence_kinds_for_goal(
                    goal_kind="whatsapp_forward_message" if refs or goal.get("link_query") else ""
                ),
                goal_referents=refs,
            )
        if isinstance(fit, dict) and fit.get("admissible") is False and fit.get("blockers"):
            blocker_types = [
                str(b.get("type") or "")
                for b in (fit.get("blockers") or [])
                if isinstance(b, dict)
            ]
            return ReflectDiagnosis(
                cause="wrong_surface",
                locus="world_semantics",
                transition_class="wrong_transition",
                confidence=0.93,
                detail=(
                    "Branch unfit for goal progress (blocking chrome / barren evidence). "
                    "Backtrack/revert — do not keep gathering on this branch."
                ),
                evidence=[
                    "branch_unfit",
                    *[f"blocker={t}" for t in blocker_types[:4]],
                    str(fit.get("verdict") or "")[:160],
                ],
                repair=ReflectRepair(
                    kind="invoke_revert_effects",
                    capability="revert_effects",
                    detail="press_escape / clear typed blocking chrome",
                ),
                do_not_repeat=[
                    "act_on_unfit_branch",
                    "information_gathering_on_unfit_branch",
                    *[f"blocker|{t}" for t in blocker_types[:3]],
                ],
                recommended_next="explore",
                source="runtime_seed",
            )
    except Exception:
        pass

    # --- Wrong selection: revert before any follow-Forward partial success ---
    sel = _selection_consistency_from_packet(reflect_packet, doc)
    if isinstance(sel, dict) and sel.get("consistent") is False:
        evidence = [
            "wrong_selection",
            f"selection_count={sel.get('selection_count')}",
            str(sel.get("verdict") or "")[:160],
        ]
        return ReflectDiagnosis(
            cause="wrong_target",
            locus="actor" if measured.get("geometry_mismatch") else "world_semantics",
            transition_class="wrong_transition",
            confidence=0.92,
            detail=(
                "Selection chrome is goal-inconsistent (wrong multi-select). "
                "Invoke revert_effects to clear it — do not advance Forward."
            ),
            evidence=evidence + list(sel.get("reasons") or []),
            repair=ReflectRepair(
                kind="invoke_revert_effects",
                capability="revert_effects",
                target="",
                detail="Analyze forward leg → approve Escape clear-selection → execute",
            ),
            do_not_repeat=[
                "follow_forward_on_wrong_selection",
                "observe_while_wrong_selection",
                f"{family}|{target}|wrong_selection",
            ],
            recommended_next="act",
            source="runtime_seed",
        )

    # --- Motor path: background AXPress while predicting a chrome change ---
    if _executor_suggests_background_ax(exec_msg) and matched is False:
        evidence.append(f"executor_message={exec_msg[:120]}")
        evidence.append(f"predicted_surface={pred}")
        evidence.append(f"observed_surface={obs}")
        fwd = _find_control(
            objects,
            labels=("forward",),
            kinds=("button", "menu_item", "toolbar_button", "toolbar"),
        )
        if _selection_chrome_present(objects, obs) and fwd is not None:
            pt = _xy(fwd.get("point"))
            return ReflectDiagnosis(
                cause="partial_effect",
                locus="world_semantics",
                transition_class="partial_transition",
                confidence=0.9,
                detail=(
                    "Predicted picker/chrome change; motor used background AXPress and "
                    "world entered selection toolbar instead. Press the observed Forward control."
                ),
                evidence=evidence
                + [
                    "selection_chrome_present",
                    f"observed_forward={fwd.get('text') or fwd.get('label')}",
                ],
                repair=ReflectRepair(
                    kind="follow_observed_transition",
                    capability="invoke_affordance",
                    target=str(fwd.get("text") or fwd.get("label") or "Forward"),
                    geometry=pt,
                    bounds=(
                        [float(x) for x in fwd["bounds"][:4]]
                        if isinstance(fwd.get("bounds"), (list, tuple))
                        and len(fwd.get("bounds")) >= 4
                        else None
                    ),
                    motor_constraint="foreground_click",
                    detail="Click selection-toolbar Forward; forbid background AXPress",
                ),
                do_not_repeat=[
                    f"{family}|{target}|background_ax",
                    "observe_while_forward_visible",
                ],
                recommended_next="act",
                corrected_point=pt,
                source="runtime_seed",
            )
        return ReflectDiagnosis(
            cause="motor_path",
            locus="actor",
            transition_class="wrong_transition" if pred and obs and pred != obs else "no_effect",
            confidence=0.88,
            detail=(
                "Executor pressed the control in background; predicted surface did not "
                "appear. Retry the same affordance with a foreground click."
            ),
            evidence=evidence,
            repair=ReflectRepair(
                kind="retry_same_affordance_different_motor",
                capability=family or "invoke_affordance",
                target=target or "Forward",
                geometry=_xy(action.get("intended_point") or action.get("point")),
                motor_constraint="foreground_click",
                detail="Forbid background AXPress; require foreground pointer click",
            ),
            do_not_repeat=[f"{family}|{target}|background_ax"],
            recommended_next="act",
            corrected_point=_xy(action.get("intended_point")),
            source="runtime_seed",
        )

    # --- Predicted overlay missing, but Forward (etc.) already visible ---
    # Live 125715: matched can be true when one predicted control is present even
    # though the surface stayed conversation — still follow the observed CTA.
    overlay_pred = pred in {"context_menu", "forward_picker", "action_menu", "dialog"}
    if overlay_pred and obs and pred != obs:
        evidence = [f"predicted_surface={pred}", f"observed_surface={obs}"]
        fwd = _find_control(
            objects,
            labels=("forward",),
            kinds=("button", "menu_item", "toolbar_button", "toolbar"),
        )
        if fwd is not None or _selection_chrome_present(objects, obs):
            if fwd is None:
                fwd = _find_control(
                    objects,
                    labels=("forward",),
                    kinds=("button", "menu_item", "toolbar_button", "toolbar"),
                )
            if fwd is not None:
                pt = _xy(fwd.get("point"))
                return ReflectDiagnosis(
                    cause="partial_effect",
                    locus="world_semantics",
                    transition_class="partial_transition",
                    confidence=0.87,
                    detail=(
                        f"Expected '{pred}' but observed '{obs}' with Forward chrome. "
                        "Follow the observed transition."
                    ),
                    evidence=evidence
                    + [
                        "forward_visible_after_reveal",
                        f"observed_forward={fwd.get('text') or fwd.get('label')}",
                    ],
                    repair=ReflectRepair(
                        kind="follow_observed_transition",
                        capability="invoke_affordance",
                        target=str(fwd.get("text") or fwd.get("label") or "Forward"),
                        geometry=pt,
                        motor_constraint="foreground_click",
                        detail="Invoke visible Forward; do not retry the failed reveal latch",
                    ),
                    do_not_repeat=["observe_while_forward_visible", f"reveal|{target}"],
                    recommended_next="act",
                    corrected_point=pt,
                    source="runtime_seed",
                )
        # If geometry also mismatched, prefer landed-object / reperceive below
        # over a generic wrong_surface (live 125715 intended≠landed).
        geom_pending = False
        intended_probe = _xy(action.get("intended_point") or action.get("point"))
        landed_probe = _xy(
            action.get("motor_landed_point") or measured.get("motor_landed_point")
        )
        if intended_probe and landed_probe:
            d_probe = (
                (intended_probe[0] - landed_probe[0]) ** 2
                + (intended_probe[1] - landed_probe[1]) ** 2
            ) ** 0.5
            geom_pending = d_probe >= 80.0
        if matched is False and not geom_pending:
            return ReflectDiagnosis(
                cause="wrong_surface",
                locus="world_semantics",
                transition_class="wrong_transition",
                confidence=0.8,
                detail=f"Predicted '{pred}', observed '{obs}'.",
                evidence=evidence,
                repair=ReflectRepair(
                    kind="reperceive", detail="Need a clean reading of the new chrome"
                ),
                recommended_next="reperceive",
                source="runtime_seed",
            )

    # --- Geometry mismatch: motor landing is Attempt evidence, not object Grounding ---
    intended = _xy(action.get("intended_point") or action.get("point"))
    landed = _xy(action.get("motor_landed_point") or measured.get("motor_landed_point"))
    if intended and landed:
        dist = ((intended[0] - landed[0]) ** 2 + (intended[1] - landed[1]) ** 2) ** 0.5
        if dist >= 80.0:
            near = _object_near_point(objects, landed, pad=96.0)
            evidence = [
                f"intended_point={intended}",
                f"motor_landed_point={landed}",
                f"distance_px={round(dist, 1)}",
                "attempt_validity=inconclusive_grounding",
            ]
            near_label = ""
            if near is not None:
                near_label = str(near.get("text") or near.get("label") or "").strip()
                evidence.append(f"near_landed_object={near_label}")
            return ReflectDiagnosis(
                cause="wrong_target",
                locus="handoff" if measured.get("geometry_mismatch") else "actor",
                transition_class="no_effect",
                confidence=min(0.95, 0.7 + dist / 1000.0),
                detail=(
                    f"Motor landed {dist:.0f}px from intended"
                    + (f" near {near_label!r}" if near_label else "")
                    + "; do not adopt landing as object geometry — re-perceive then re-ground."
                ),
                evidence=evidence,
                repair=ReflectRepair(
                    kind="reperceive",
                    detail=(
                        "Geometry mismatch: Attempt.motor_point only; "
                        "forbid intended latch and landed-as-object rewrite"
                    ),
                ),
                do_not_repeat=[
                    f"{family}|{target}|{int(intended[0])},{int(intended[1])}",
                    f"{family}|{target}|{int(landed[0])},{int(landed[1])}",
                ],
                recommended_next="reperceive",
                corrected_point=None,
                source="runtime_seed",
            )

    # --- Non-overlay surface miss (preserve follow-Forward / wrong_surface) ---
    if matched is False and pred and obs and pred != obs and not overlay_pred:
        evidence = [f"predicted_surface={pred}", f"observed_surface={obs}"]
        if _selection_chrome_present(objects, obs):
            fwd = _find_control(
                objects,
                labels=("forward",),
                kinds=("button", "menu_item", "toolbar_button", "toolbar"),
            )
            if fwd is not None:
                pt = _xy(fwd.get("point"))
                return ReflectDiagnosis(
                    cause="partial_effect",
                    locus="world_semantics",
                    transition_class="partial_transition",
                    confidence=0.87,
                    detail=(
                        f"Expected '{pred}' but observed '{obs}' with selection/Forward chrome. "
                        "Follow the observed transition."
                    ),
                    evidence=evidence + ["selection_chrome_present"],
                    repair=ReflectRepair(
                        kind="follow_observed_transition",
                        capability="invoke_affordance",
                        target=str(fwd.get("text") or "Forward"),
                        geometry=pt,
                        motor_constraint="foreground_click",
                    ),
                    do_not_repeat=["observe_while_forward_visible", f"reveal|{target}"],
                    recommended_next="act",
                    corrected_point=pt,
                    source="runtime_seed",
                )
        return ReflectDiagnosis(
            cause="wrong_surface",
            locus="world_semantics",
            transition_class="wrong_transition",
            confidence=0.8,
            detail=f"Predicted '{pred}', observed '{obs}'.",
            evidence=evidence,
            repair=ReflectRepair(
                kind="reperceive", detail="Need a clean reading of the new chrome"
            ),
            recommended_next="reperceive",
            source="runtime_seed",
        )

    if measured.get("executor_ok") is False:
        return ReflectDiagnosis(
            cause="motor_miss",
            locus="actor",
            transition_class="no_effect",
            confidence=0.85,
            detail="Executor reported failure.",
            evidence=["executor_ok=false"],
            repair=ReflectRepair(kind="reperceive"),
            recommended_next="reperceive",
            source="runtime_seed",
        )

    return ReflectDiagnosis(source="runtime_seed")


def merge_diagnoses(
    model: ReflectDiagnosis,
    seed: ReflectDiagnosis,
) -> ReflectDiagnosis:
    """Prefer authoritative model repair; else promote runtime seed."""
    # Wrong selection is a hard policy: never advance Forward on bad multi-select
    # even if the model confidently proposes follow_observed_transition.
    if (
        seed.repair.kind == "invoke_revert_effects"
        and any("wrong_selection" in str(e) for e in seed.evidence)
        and model.repair.kind
        in {"follow_observed_transition", "reperceive", "backtrack_dismiss"}
    ):
        out = normalize_reflect_diagnosis(seed.to_dict())
        out.source = "merged_seed_wrong_selection"
        return out
    if diagnosis_is_authoritative(model) and model.repair.kind != "reperceive":
        out = normalize_reflect_diagnosis(model.to_dict())
        out.source = "merged_model"
        # Keep seed do_not_repeat extras.
        for key in seed.do_not_repeat:
            if key not in out.do_not_repeat:
                out.do_not_repeat.append(key)
        return out
    if seed.repair.kind != "reperceive" and seed.confidence >= 0.8:
        out = normalize_reflect_diagnosis(seed.to_dict())
        out.source = "merged_seed"
        if model.detail and not out.detail:
            out.detail = model.detail
        return out
    if diagnosis_is_authoritative(model):
        out = normalize_reflect_diagnosis(model.to_dict())
        out.source = "merged_model"
        return out
    if seed.confidence > model.confidence:
        out = normalize_reflect_diagnosis(seed.to_dict())
        out.source = "merged_seed"
        return out
    out = normalize_reflect_diagnosis(model.to_dict())
    out.source = out.source or "merged_model"
    return out


def reflect_schema_addendum() -> str:
    """System-prompt fragment describing the ReflectDiagnosis JSON shape."""
    return (
        "\n\nREFLECT MODE. The executive detected a prediction error after the last "
        "actuation. You are the recovery specialist: localize the fault in the "
        "perceptor→brain→actor chain and emit one repair. Perceive is a tool for "
        "diagnosis; your product is surprise_explanation (ReflectDiagnosis), not "
        "another vague look.\n"
        "Use packet.reflect measured facts: intended_point vs motor_landed_point, "
        "expected vs actual surfaces, executor_message (watch for 'in background'), "
        "discovery_hypotheses, prior_perceptions, and the screenshot.\n"
        "Fault loci: perception | handoff | actor | world_semantics | prediction | unknown.\n"
        "Transition classes: no_effect | wrong_transition | partial_transition | "
        "occlusion | stale | matched | unknown.\n"
        "Repair kinds: retry_with_corrected_geometry | "
        "retry_same_affordance_different_motor | follow_observed_transition | "
        "re_ground_then_act | backtrack_dismiss | invoke_revert_effects | reperceive.\n"
        "Prefer confidence >= 0.85 only with clear evidence. Do NOT invent motors. "
        "When selection chrome is goal-inconsistent (e.g. '2 Selected' includes "
        "non-goal content), use invoke_revert_effects — never follow_observed_transition "
        "to toolbar Forward on a wrong selection. "
        "When the world shows a different but goal-advancing control (e.g. selection "
        "toolbar Forward after a failed picker prediction AND selection matches the "
        "goal), use follow_observed_transition — never recommended_next=reperceive "
        "solely to avoid deciding.\n"
        "Add to your JSON:\n"
        '  "surprise_explanation": {\n'
        '    "cause": "wrong_target|no_effect|wrong_surface|occlusion|stale_geometry|'
        'motor_miss|motor_path|handoff_loss|partial_effect|unknown",\n'
        '    "locus": "perception|handoff|actor|world_semantics|prediction|unknown",\n'
        '    "transition_class": "no_effect|wrong_transition|partial_transition|'
        'occlusion|stale|matched|unknown",\n'
        '    "detail": str,\n'
        '    "confidence": float,\n'
        '    "evidence": [str],\n'
        '    "recommended_next": "act|explore|reperceive|think|search",\n'
        '    "corrected_point": [x, y]|null,\n'
        '    "do_not_repeat": [str],\n'
        '    "repair": {\n'
        '      "kind": "retry_with_corrected_geometry|retry_same_affordance_different_motor|'
        'follow_observed_transition|re_ground_then_act|backtrack_dismiss|'
        'invoke_revert_effects|reperceive",\n'
        '      "capability": str,\n'
        '      "target": str,\n'
        '      "geometry": [x, y]|null,\n'
        '      "motor_constraint": str,\n'
        '      "detail": str\n'
        "    }\n"
        "  }\n"
    )


def enrich_reflect_packet(packet: Dict[str, Any]) -> Dict[str, Any]:
    """Attach runtime seed diagnosis onto an existing reflect packet."""
    if not isinstance(packet, dict) or not packet:
        return packet
    seed = seed_reflect_diagnosis_from_measured(packet)
    packet = dict(packet)
    packet["runtime_seed_diagnosis"] = seed.to_dict()
    packet["task"] = (
        "LOCALIZE the fault (perception|handoff|actor|world_semantics|prediction) "
        "and emit one repair. Measured facts and runtime_seed_diagnosis are "
        "evidence — confirm or refute against the screenshot; do not ignore a "
        "high-confidence seed without contrary pixel evidence. Primary output is "
        "surprise_explanation as ReflectDiagnosis. Do not invent a motor path."
    )
    packet["discovery_questions"] = [
        "Did the motor land where the brain intended?",
        "Did the executor use a degraded path (background AXPress, wrong gesture)?",
        "Did the expected surface appear, or a partial/wrong transition?",
        "Is there an observed control that advances the goal (follow_observed_transition)?",
        "Was geometry/label lost between perceptor inventory and the actor brief?",
    ]
    return packet
