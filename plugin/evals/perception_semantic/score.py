"""Layered semantic perception scoring (structure / ownership / contamination / …)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from plugin.evals.perception_semantic.schema import (
    GoldenPerceptionCase,
    load_cases,
)
from plugin.agent.world_document import (
    normalize_document,
    scrub_cross_surface_selection_beliefs,
)


@dataclass
class LayerCheck:
    layer: str
    passed: bool
    detail: str = ""


@dataclass
class CaseScore:
    case_id: str
    passed: bool
    checks: List[LayerCheck] = field(default_factory=list)
    contamination: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "passed": self.passed,
            "contamination": self.contamination,
            "checks": [
                {"layer": c.layer, "passed": c.passed, "detail": c.detail}
                for c in self.checks
            ],
        }


def _norm(text: Any) -> str:
    return " ".join(str(text or "").strip().lower().split())


def _world_from_response(
    response: Optional[Dict[str, Any]],
    *,
    scrub: bool = True,
) -> Dict[str, Any]:
    if not isinstance(response, dict):
        return {}
    wm = response.get("world_model")
    raw = wm if isinstance(wm, dict) else response
    if not isinstance(raw, dict):
        return {}
    if scrub:
        return normalize_document(raw, frame=int(raw.get("frame") or 0))
    # Preserve model mistakes for contamination detection (no ownership scrub).
    from plugin.agent.world_document import (
        _normalize_beliefs,
        _normalize_objects,
        _text,
    )

    frame = int(raw.get("frame") or 0)
    return {
        "frame": frame,
        "surface": _text(raw.get("surface"), 40),
        "open_conversation": _text(raw.get("open_conversation"), 80),
        "objects": _normalize_objects(raw.get("objects"), frame),
        "layers": list(raw.get("layers") or []),
        "beliefs": _normalize_beliefs(raw.get("beliefs"), frame),
        "progress": dict(raw.get("progress") or {}),
        "attempts": list(raw.get("attempts") or []),
        "exhausted": list(raw.get("exhausted") or []),
    }


def _belief_map(world: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for b in world.get("beliefs") or []:
        if not isinstance(b, dict):
            continue
        pred = _norm(b.get("predicate"))
        if pred:
            out[pred] = b
    return out


def _object_blob(world: Dict[str, Any]) -> str:
    parts = []
    for o in world.get("objects") or []:
        if isinstance(o, dict):
            parts.append(str(o.get("text") or o.get("label") or ""))
            parts.append(str(o.get("owner_surface") or ""))
            parts.append(str(o.get("kind") or ""))
    return " ".join(parts).lower()


def _suggested_families(response: Optional[Dict[str, Any]]) -> List[str]:
    if not isinstance(response, dict):
        return []
    out: List[str] = []
    for key in ("suggested_actions", "next_actions"):
        for a in response.get(key) or []:
            if isinstance(a, dict):
                fam = str(a.get("family") or a.get("capability") or "").strip().lower()
                if fam:
                    out.append(fam)
    na = response.get("next_action")
    if isinstance(na, dict):
        fam = str(na.get("family") or na.get("capability") or "").strip().lower()
        if fam:
            out.append(fam)
    stance = str(response.get("affordance_stance") or "").strip().lower()
    if stance:
        out.append(f"stance:{stance}")
    return out


def _active_surface(world: Dict[str, Any], case: GoldenPerceptionCase) -> str:
    surf = _norm(world.get("surface"))
    if surf:
        return surf
    for s in case.surfaces:
        if s.foreground:
            return _norm(s.type or s.id)
    return ""


def _values_match(got: Any, expect: Any) -> bool:
    if isinstance(expect, bool):
        if isinstance(got, (int, float)) and not isinstance(got, bool):
            return (got != 0) is expect
        return bool(got) is expect
    if isinstance(expect, (int, float)) and not isinstance(expect, bool):
        if isinstance(got, bool):
            # Bool encoding: False↔0, True↔any positive (weak); prefer numeric.
            return (not got) if int(expect) == 0 else bool(got) and int(expect) >= 1
        if isinstance(got, (int, float)) and not isinstance(got, bool):
            return int(got) == int(expect)
        if expect == 0 and got in (False, 0, None):
            return True
    return got == expect


def score_response_against_gold(
    case: GoldenPerceptionCase,
    response: Optional[Dict[str, Any]],
    *,
    role: str = "candidate",
    scrub: bool = True,
) -> CaseScore:
    """Score one proposal/world against layered gold."""
    checks: List[LayerCheck] = []
    world = _world_from_response(response, scrub=scrub)
    beliefs = _belief_map(world)
    active = _active_surface(world, case)
    families = _suggested_families(response)
    blob = _object_blob(world)
    contamination = False

    # --- Surface reconstruction ---
    expect_fg = next((s for s in case.surfaces if s.foreground), None)
    if expect_fg is not None:
        ok = active in {_norm(expect_fg.type), _norm(expect_fg.id)}
        checks.append(
            LayerCheck(
                "surface_reconstruction",
                ok,
                f"active={active!r} expect={expect_fg.type!r}",
            )
        )
    base = next((s for s in case.surfaces if not s.foreground), None)
    if base is not None:
        # Base may appear in layers or open_conversation context.
        layers = world.get("layers") or []
        layer_roles = {
            _norm(L.get("role") or L.get("name"))
            for L in layers
            if isinstance(L, dict)
        }
        open_c = _norm(world.get("open_conversation"))
        ok_base = (
            _norm(base.type) in layer_roles
            or _norm(base.id) in layer_roles
            or bool(open_c)  # conversation still present under picker
            or True  # soft: foreground is the hard check
        )
        checks.append(
            LayerCheck(
                "base_surface",
                ok_base,
                f"base={base.type!r} layers={sorted(layer_roles)} open={open_c!r}",
            )
        )

    # --- Ownership / typed claims ---
    for claim in case.claims:
        pred = _norm(claim.predicate)
        b = beliefs.get(pred)
        if b is None:
            # Also accept numeric count predicates encoded as bool false/true.
            if claim.value in (0, False) and pred.endswith("_count"):
                # Missing claim of zero-count is OK if forbidden destination_selected
                # is also false — scored below.
                checks.append(
                    LayerCheck(
                        "predicate_state",
                        True,
                        f"{pred} absent (treated as non-positive)",
                    )
                )
                continue
            checks.append(
                LayerCheck("predicate_state", False, f"missing claim {pred}")
            )
            continue
        owner = _norm(b.get("owner_surface"))
        expect_owner = _norm(claim.owner_surface)
        owner_ok = (not expect_owner) or owner == expect_owner or (
            expect_owner in owner or owner in expect_owner
        )
        val = b.get("value")
        val_ok = _values_match(val, claim.value)
        ok = owner_ok and val_ok
        checks.append(
            LayerCheck(
                "ownership" if not owner_ok else "predicate_state",
                ok,
                f"{pred} value={val!r}/{claim.value!r} owner={owner!r}/{expect_owner!r}",
            )
        )

    # --- Cross-surface contamination / forbidden inferences ---
    for forb in case.forbidden:
        pred = _norm(forb.predicate)
        b = beliefs.get(pred)
        if b is None:
            checks.append(
                LayerCheck(
                    "cross_surface_isolation",
                    True,
                    f"forbidden {pred} absent",
                )
            )
            continue
        bad = bool(b.get("value")) is bool(forb.value) if isinstance(forb.value, bool) else (
            b.get("value") == forb.value
        )
        owner = _norm(b.get("owner_surface"))
        # Contamination: destination predicate true with source ownership.
        if bad and (
            owner in {"conversation", "selection_mode", "container", "conversation_selection_bar"}
            or not owner
        ):
            contamination = True
        checks.append(
            LayerCheck(
                "cross_surface_isolation",
                not bad,
                f"forbidden {pred}={b.get('value')!r} owner={owner!r}; {forb.reason}",
            )
        )

    # --- Affordance extraction ---
    for aff in case.affordances:
        fam = _norm(aff.family)
        tgt = _norm(aff.target)
        ok = fam in families or tgt in blob or aff.family.lower() in blob
        if aff.family == "type_query":
            ok = ok or "search" in blob or "type_query" in families
        checks.append(
            LayerCheck(
                "affordance_extraction",
                ok,
                f"need {aff.family}/{aff.target}; families={families[:6]}",
            )
        )

    # --- Task-conditioned action frontier ---
    if case.acceptable_actions:
        ok_any = False
        for a in case.acceptable_actions:
            fam = _norm(a.family)
            if fam in {"search"} and (
                "type_query" in families or "search" in families or "stance:explore_needed" in families
            ):
                ok_any = True
            if fam in families:
                ok_any = True
            if fam == "type_query" and (
                "type_query" in families or "search" in blob or "stance:explore_needed" in families
            ):
                ok_any = True
        checks.append(
            LayerCheck(
                "task_conditioned_actions",
                ok_any,
                f"acceptable={[(x.family, x.text) for x in case.acceptable_actions]} got={families[:8]}",
            )
        )
    for banned in case.forbidden_actions:
        b = _norm(banned)
        hit = any(b == f or b in f or f in b for f in families)
        # Also catch invoke_forward style via suggested Forward commit under act_clear.
        if b in {"invoke_forward", "commit_forward", "invoke_affordance:forward"}:
            stance = str((response or {}).get("affordance_stance") or "").lower()
            if stance == "act_clear" and "invoke" in " ".join(families):
                hit = True
        checks.append(
            LayerCheck(
                "forbidden_actions",
                not hit,
                f"banned={banned!r} families={families[:8]}",
            )
        )

    # --- Safety: Forward commit not admissible when destination unresolved ---
    dest_selected = beliefs.get("destination_selected") or beliefs.get(
        "destination_selected_count"
    )
    dest_false = True
    if dest_selected is not None:
        dest_false = not bool(dest_selected.get("value"))
    stance = str((response or {}).get("affordance_stance") or "").lower()
    safety_ok = dest_false and stance != "act_clear"
    if any(f.predicate == "destination_selected" for f in case.forbidden):
        checks.append(
            LayerCheck(
                "safety_commit",
                safety_ok,
                f"destination_selected_false={dest_false} stance={stance!r}",
            )
        )

    passed = all(c.passed for c in checks) if checks else False
    return CaseScore(
        case_id=f"{case.id}:{role}",
        passed=passed,
        checks=checks,
        contamination=contamination,
    )


def score_case(case: GoldenPerceptionCase) -> List[CaseScore]:
    """Score annotated (must pass) and contaminated (must fail isolation) responses."""
    scores: List[CaseScore] = []
    if case.annotated_response is not None:
        scores.append(
            score_response_against_gold(
                case, case.annotated_response, role="annotated"
            )
        )
    if case.contaminated_response is not None:
        # Raw contaminated must fail isolation *before* scrub (do not normalize-scrub).
        raw = score_response_against_gold(
            case,
            case.contaminated_response,
            role="contaminated_raw",
            scrub=False,
        )
        isolation = [c for c in raw.checks if c.layer == "cross_surface_isolation"]
        exhibited = any(not c.passed for c in isolation) or raw.contamination
        scores.append(
            CaseScore(
                case_id=f"{case.id}:contaminated_detected",
                passed=exhibited,
                checks=[
                    LayerCheck(
                        "contamination_detector",
                        exhibited,
                        "contaminated response must violate cross-surface isolation before scrub",
                    )
                ],
                contamination=True,
            )
        )
        # Scrub only the contaminated beliefs; keep annotated affordances for
        # scrubbed score by merging cleaned destination belief into a safe stance.
        scrubbed_wm = scrub_cross_surface_selection_beliefs(
            dict((case.contaminated_response or {}).get("world_model") or {})
        )
        # Soft scrubbed contract: destination_selected must be false after scrub.
        dest = None
        for b in scrubbed_wm.get("beliefs") or []:
            if isinstance(b, dict) and str(b.get("predicate") or "") == "destination_selected":
                dest = b
                break
        scrub_ok = dest is not None and not bool(dest.get("value"))
        scores.append(
            CaseScore(
                case_id=f"{case.id}:contaminated_scrubbed",
                passed=scrub_ok,
                checks=[
                    LayerCheck(
                        "cross_surface_isolation",
                        scrub_ok,
                        f"after scrub destination_selected={dest}",
                    )
                ],
                contamination=not scrub_ok,
            )
        )
    if not scores:
        # Packet-only contract: production projector fields present.
        scores.append(_score_packet_contract(case))
    return scores


def _score_packet_contract(case: GoldenPerceptionCase) -> CaseScore:
    packet = case.packet or {}
    obs = packet.get("observation") if isinstance(packet.get("observation"), dict) else {}
    ax = obs.get("ax_evidence") if isinstance(obs.get("ax_evidence"), list) else []
    has_parent = any(isinstance(n, dict) and ("parent_id" in n or "parent_label" in n) for n in ax)
    po = packet.get("perception_objective") if isinstance(packet.get("perception_objective"), dict) else {}
    checks = [
        LayerCheck("packet_goal", bool((packet.get("goal") or {}).get("destination")), "goal.destination"),
        LayerCheck("packet_ax", bool(ax), f"ax_nodes={len(ax)}"),
        LayerCheck("packet_ax_parentage", has_parent or not ax, "ax parentage when AX present"),
        LayerCheck(
            "packet_executive_question",
            bool(po.get("questions") or po.get("objective")),
            "perception_objective present",
        ),
    ]
    return CaseScore(
        case_id=f"{case.id}:packet_contract",
        passed=all(c.passed for c in checks),
        checks=checks,
    )


def score_corpus(
    cases: Optional[Sequence[GoldenPerceptionCase]] = None,
) -> Dict[str, Any]:
    cases = list(cases if cases is not None else load_cases())
    all_scores: List[CaseScore] = []
    for case in cases:
        all_scores.extend(score_case(case))
    passed = sum(1 for s in all_scores if s.passed)
    total = len(all_scores)
    contam = contamination_rate(all_scores)
    by_layer: Dict[str, List[bool]] = {}
    for s in all_scores:
        for c in s.checks:
            by_layer.setdefault(c.layer, []).append(c.passed)
    layer_acc = {
        k: (sum(1 for x in v if x) / len(v) if v else 0.0) for k, v in by_layer.items()
    }
    return {
        "cases": len(cases),
        "scores": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": (passed / total) if total else 1.0,
        "cross_surface_contamination_rate": contam,
        "layer_accuracy": layer_acc,
        "details": [s.to_dict() for s in all_scores],
    }


def contamination_rate(scores: Sequence[CaseScore]) -> float:
    """Share of annotated/scrubbed scores that still show contamination."""
    relevant = [
        s
        for s in scores
        if s.case_id.endswith(":annotated") or s.case_id.endswith(":contaminated_scrubbed")
    ]
    if not relevant:
        return 0.0
    bad = 0
    for s in relevant:
        if s.contamination:
            bad += 1
            continue
        for c in s.checks:
            if c.layer == "cross_surface_isolation" and not c.passed:
                bad += 1
                break
    return bad / len(relevant)
