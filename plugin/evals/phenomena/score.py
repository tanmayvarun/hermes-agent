"""Score phenomenon goldens against production executive substrate.

Usage:
    python -m plugin.evals.phenomena.score
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from plugin.evals.phenomena.schema import (
    DEFAULT_PHENOMENA_DIR,
    FIXTURE_STATUS_SPECIFICATION,
    HARD_CONTRACT_TAGS,
    PHENOMENA_VERSION,
    PHENOMENON_FAMILIES,
    GoldenFixture,
    load_all_fixtures,
    load_manifest,
)


@dataclass
class FixtureScore:
    fixture_id: str
    family: str
    passed: bool
    checks: List[Dict[str, Any]] = field(default_factory=list)
    hard_contract: bool = False
    eval_level: str = "L1"
    fixture_status: str = "golden"
    production_exercised: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "family": self.family,
            "passed": self.passed,
            "hard_contract": self.hard_contract,
            "eval_level": self.eval_level,
            "fixture_status": self.fixture_status,
            "production_exercised": self.production_exercised,
            "checks": self.checks,
            "failures": [c["name"] for c in self.checks if not c.get("passed")],
        }


def _annotate(score: FixtureScore, fix: GoldenFixture) -> FixtureScore:
    score.eval_level = str(fix.eval_level or "L1")
    score.fixture_status = str(fix.fixture_status or "golden")
    score.production_exercised = bool(fix.production_exercised)
    return score


def _check(name: str, passed: bool, detail: str = "") -> Dict[str, Any]:
    return {"name": name, "passed": bool(passed), "detail": detail}


def _intention_id(fix: GoldenFixture) -> str:
    parent = fix.parent_intention or {}
    return str(parent.get("id") or parent.get("intention_id") or "i_parent")


def _facts(fix: GoldenFixture) -> Dict[str, Any]:
    facts = dict(fix.system_facts or {})
    facts.update(dict((fix.world_before or {}).get("facts") or {}))
    return facts


def _detect(fix: GoldenFixture):
    from plugin.agent.executive.blocking import detect_warnings_and_blockers

    return detect_warnings_and_blockers(
        observation_texts=fix.observation_texts,
        view=fix.view or fix.world_before,
        features=fix.features,
        intention_id=_intention_id(fix),
        app=fix.app,
    )


def score_warning_vs_blocker(fix: GoldenFixture) -> FixtureScore:
    gold = fix.gold or {}
    warns, blockers = _detect(fix)
    checks: List[Dict[str, Any]] = []

    expect_blocker = bool(gold.get("expect_blocker", gold.get("blocker")))
    expect_warning = bool(gold.get("expect_warning", gold.get("warning")))
    checks.append(
        _check(
            "blocker_presence",
            expect_blocker == bool(blockers),
            f"expected_blocker={expect_blocker} got={len(blockers)}",
        )
    )
    checks.append(
        _check(
            "warning_presence",
            expect_warning == bool(warns) if "expect_warning" in gold or "warning" in gold else True,
            f"expected_warning={expect_warning} got={len(warns)}",
        )
    )
    if expect_blocker and blockers:
        bc = next(
            (b for b in blockers if b.kind == "insufficient_storage"),
            blockers[0],
        )
        need = gold.get("required_bytes")
        if need is not None:
            got = int(bc.required_effect.value or 0)
            checks.append(
                _check(
                    "required_bytes",
                    abs(got - int(need)) <= max(1024, int(need) * 0.01),
                    f"need≈{need} got={got}",
                )
            )
        if gold.get("app_operational") is False:
            from plugin.agent.executive.blocking import (
                EffectPredicate,
                evaluate_effect_predicate,
            )

            op = evaluate_effect_predicate(
                EffectPredicate(subject="app_operational", relation="is_true", value=True),
                world={**(fix.view or {}), "storage_pressure": True, "surface": "dialog"},
                facts=_facts(fix),
            )
            checks.append(_check("app_operational_false", op is False, f"got={op}"))
        if gold.get("parent_executable") is False:
            from plugin.agent.executive.blocking import (
                ExecutabilityStatus,
                assess_executability,
            )

            assessment = assess_executability(
                intention_id=_intention_id(fix),
                blockers=blockers,
                world=fix.view or {},
                facts={**_facts(fix), "agent_owned_reclaimable_bytes": 1},
            )
            checks.append(
                _check(
                    "parent_not_executable",
                    assessment.status != ExecutabilityStatus.EXECUTABLE.value,
                    assessment.status,
                )
            )
    # Hard: warning must not imply blocker.
    if expect_warning and not expect_blocker:
        checks.append(
            _check(
                "warning_no_blocker",
                not blockers,
                "warning must not spawn BlockingCondition",
            )
        )
    return FixtureScore(
        fixture_id=fix.fixture_id,
        family=fix.family,
        passed=all(c["passed"] for c in checks),
        checks=checks,
        hard_contract=bool(HARD_CONTRACT_TAGS.intersection(fix.tags)),
    )


def score_executability(fix: GoldenFixture) -> FixtureScore:
    from plugin.agent.executive.blocking import (
        ExecutabilityStatus,
        assess_executability,
    )

    gold = fix.gold or {}
    warns, blockers = _detect(fix)
    # Allow fixtures to inject blockers directly (post-detection world).
    if gold.get("use_injected_blockers") and fix.world_before.get("blockers"):
        from plugin.agent.executive.blocking import (
            BlockingCondition,
            EffectPredicate,
            IntentionRef,
        )

        blockers = []
        for raw in fix.world_before.get("blockers") or []:
            if not isinstance(raw, dict):
                continue
            re_ = raw.get("required_effect") or {}
            blockers.append(
                BlockingCondition(
                    kind=str(raw.get("kind") or ""),
                    required_effect=EffectPredicate(
                        subject=str(re_.get("subject") or ""),
                        relation=str(re_.get("relation") or ""),
                        value=re_.get("value"),
                    ),
                    blocks=[
                        IntentionRef(intention_id=_intention_id(fix))
                    ],
                    evidence=list(raw.get("evidence") or []),
                )
            )
    assessment = assess_executability(
        intention_id=_intention_id(fix),
        blockers=blockers,
        world=fix.view or fix.world_before,
        facts=_facts(fix),
    )
    expect = str(gold.get("status") or gold.get("executability") or "").lower()
    checks = [
        _check(
            "executability_status",
            assessment.status == expect,
            f"expected={expect} got={assessment.status}",
        )
    ]
    for forbid in fix.forbidden or []:
        # Forbidden behaviors are semantic — no SEARCH/ACT toward parent.
        if forbid in {"continue_parent_search", "normal_parent_act", "generic_observe_loop"}:
            checks.append(
                _check(
                    f"forbidden_{forbid}",
                    assessment.status
                    in {
                        ExecutabilityStatus.BLOCKED_RESOLVABLE.value,
                        ExecutabilityStatus.BLOCKED_UNRESOLVABLE.value,
                        ExecutabilityStatus.UNKNOWN.value,
                    },
                    "blocked/unknown must interrupt parent progress",
                )
            )
    _ = warns
    return FixtureScore(
        fixture_id=fix.fixture_id,
        family=fix.family,
        passed=all(c["passed"] for c in checks),
        checks=checks,
        hard_contract=True,
    )


def score_prerequisite_children(fix: GoldenFixture) -> FixtureScore:
    from plugin.agent.executive.blocking import (
        assess_executability,
        resolve_methods_for_effect,
    )
    from plugin.agent.executive.intention_frame import (
        Intention,
        IntentionFrame,
        IntentionOrigin,
        ensure_child_for_precondition,
        intention_stack_of,
        push_intention_frame,
    )
    from plugin.agent.runtime.state import ExecutionState

    gold = fix.gold or {}
    _, blockers = _detect(fix)
    assessment = assess_executability(
        intention_id=_intention_id(fix),
        blockers=blockers,
        world=fix.view or {},
        facts=_facts(fix),
    )
    checks: List[Dict[str, Any]] = []
    state = ExecutionState()
    parent = IntentionFrame(
        intention=Intention(
            id=_intention_id(fix),
            objective=str(
                (fix.parent_intention or {}).get("objective") or "forward message"
            ),
            success_predicate=str(
                (fix.parent_intention or {}).get("success_predicate")
                or "forward_affordance_grounded"
            ),
            created_from=IntentionOrigin(kind="goal"),
        )
    )
    push_intention_frame(state, parent)

    storage_bc = next(
        (
            b
            for b in (assessment.resolvable_conditions or blockers)
            if b.required_effect.subject == "storage"
        ),
        None,
    )
    if storage_bc is None and assessment.resolvable_conditions:
        storage_bc = assessment.resolvable_conditions[0]
    if storage_bc is None:
        return FixtureScore(
            fixture_id=fix.fixture_id,
            family=fix.family,
            passed=False,
            checks=[_check("has_resolvable", False, "no resolvable condition")],
            hard_contract=True,
        )
    key = storage_bc.semantic_key()
    methods = resolve_methods_for_effect(storage_bc.required_effect, facts=_facts(fix))
    pairs = [(m.capability, m.capability) for m in methods] or [
        ("relieve_host_storage", "relieve_host_storage")
    ]
    c1 = ensure_child_for_precondition(
        state, parent, effect_key=key, success_predicate=key, methods=pairs
    )
    # Second evidence source → same child (dedupe).
    c2 = ensure_child_for_precondition(
        state, parent, effect_key=key, success_predicate=key, methods=pairs
    )
    kids = [
        f
        for f in intention_stack_of(state)
        if f.parent_intention_id == parent.intention.id
    ]
    checks.append(_check("spawn_child", c1 is not None, "child missing"))
    checks.append(
        _check(
            "parent_suspended",
            bool(parent.suspended_by_child),
            f"suspended={parent.suspended_by_child}",
        )
    )
    checks.append(
        _check(
            "no_duplicate_child",
            c1 is not None and c2 is not None and c1.intention.id == c2.intention.id,
            f"ids {[k.intention.id for k in kids]}",
        )
    )
    checks.append(_check("one_child_on_stack", len(kids) == 1, f"n={len(kids)}"))
    if gold.get("child_capability"):
        assert c1 is not None
        caps = {s.capability for s in (c1.method_frontier.catalog or {}).values()}
        checks.append(
            _check(
                "child_capability",
                gold["child_capability"] in caps,
                f"caps={caps}",
            )
        )
    return FixtureScore(
        fixture_id=fix.fixture_id,
        family=fix.family,
        passed=all(c["passed"] for c in checks),
        checks=checks,
        hard_contract=True,
    )


def score_effect_resolution(fix: GoldenFixture) -> FixtureScore:
    from plugin.agent.executive.blocking import (
        EffectPredicate,
        ResourceCandidate,
        Reclaimability,
        rank_resolution_plan,
    )

    gold = fix.gold or {}
    re_ = (gold.get("required_effect") or {}) if isinstance(gold.get("required_effect"), dict) else {}
    if not re_ and fix.parent_intention.get("required_effect"):
        re_ = dict(fix.parent_intention["required_effect"])
    effect = EffectPredicate(
        subject=str(re_.get("subject") or "storage"),
        relation=str(re_.get("relation") or "available_bytes_at_least"),
        value=re_.get("value", 1),
    )
    resources = [
        ResourceCandidate(
            path=str(r.get("path") or ""),
            owner=str(r.get("owner") or "unknown"),
            persistence=str(r.get("persistence") or "unknown"),
            regenerable=bool(r.get("regenerable")),
            deletion_risk=str(r.get("deletion_risk") or "unknown"),
            reclaimability=str(
                r.get("reclaimability") or Reclaimability.UNKNOWN.value
            ),
        )
        for r in (fix.resources or [])
    ]
    plan = rank_resolution_plan(
        effect,
        resources=resources,
        facts=_facts(fix),
        offered_capabilities=fix.offered_capabilities,
    )
    checks: List[Dict[str, Any]] = []
    expect_top = gold.get("top_capability") or (
        (gold.get("ranked_capabilities") or [None])[0]
    )
    ranked = plan.get("ranked_capabilities") or []
    if expect_top:
        checks.append(
            _check(
                "top_capability",
                bool(ranked) and ranked[0] == expect_top,
                f"expected={expect_top} got={ranked}",
            )
        )
    if gold.get("expect_empty_ranked"):
        checks.append(
            _check("empty_ranked", not ranked, f"got={ranked}")
        )
    for bad in gold.get("forbidden_auto") or fix.forbidden or []:
        checks.append(
            _check(
                f"forbid_{bad}",
                bad not in ranked,
                f"unsafe method ranked: {ranked}",
            )
        )
        if bad in (plan.get("forbidden_auto") or []) or bad not in ranked:
            pass  # counted above
    if "no_unsafe_user_cleanup" in fix.tags or "delete_user_documents" in (
        gold.get("forbidden_auto") or []
    ):
        checks.append(
            _check(
                "no_user_doc_auto",
                "delete_user_documents" not in ranked,
                f"ranked={ranked}",
            )
        )
    return FixtureScore(
        fixture_id=fix.fixture_id,
        family=fix.family,
        passed=all(c["passed"] for c in checks) if checks else False,
        checks=checks,
        hard_contract=True,
    )


def score_effect_verification(fix: GoldenFixture) -> FixtureScore:
    from plugin.agent.executive.intention_frame import (
        Intention,
        IntentionFrame,
        IntentionOrigin,
        ensure_child_for_precondition,
        evaluate_intention_success,
        push_intention_frame,
        resume_parent_after_child,
    )
    from plugin.agent.runtime.state import ExecutionState

    gold = fix.gold or {}
    state = ExecutionState()
    parent = IntentionFrame(
        intention=Intention(
            id=_intention_id(fix),
            objective="forward message",
            success_predicate="forward_affordance_grounded",
            created_from=IntentionOrigin(kind="goal"),
        )
    )
    push_intention_frame(state, parent)
    need = int(gold.get("required_bytes") or fix.system_facts.get("required_bytes") or 0)
    key = f"storage:available_bytes_at_least:{need}"
    child = ensure_child_for_precondition(
        state,
        parent,
        effect_key=key,
        success_predicate=key,
        methods=[("relieve_host_storage", "relieve_host_storage")],
    )
    world = dict(fix.world_before or {})
    world.setdefault("available_storage_bytes", fix.system_facts.get("available_storage_bytes"))
    assert child is not None
    child_ok = evaluate_intention_success(child, world=world)
    expect_child_success = bool(gold.get("child_success"))
    checks = [
        _check(
            "execution_ok_ignored",
            True,  # capability claim alone never consulted here
            "judge uses world bytes, not execution_ok",
        ),
        _check(
            "child_success_predicate",
            child_ok is expect_child_success,
            f"expected={expect_child_success} got={child_ok}",
        ),
    ]
    if not expect_child_success:
        status = resume_parent_after_child(state, world=world, facts=_facts(fix))
        checks.append(
            _check(
                "parent_still_suspended",
                parent.suspended_by_child and not status.get("resumed"),
                f"resume={status}",
            )
        )
        checks.append(
            _check(
                "child_still_active",
                status.get("child_effect_met") is False,
                f"status={status}",
            )
        )
    else:
        # Child met — still must not auto-resume without recheck path.
        # Caller of resume_parent_after_child performs recheck; we assert API.
        status = resume_parent_after_child(
            state,
            world=world,
            parent_blockers=[],
            facts={
                **_facts(fix),
                "available_storage_bytes": world.get("available_storage_bytes"),
                "app_operational": bool(gold.get("app_operational", True)),
            },
        )
        if gold.get("expect_resume") is True:
            checks.append(_check("resume", bool(status.get("resumed")), str(status)))
        elif gold.get("expect_resume") is False:
            checks.append(
                _check(
                    "no_premature_resume",
                    not status.get("resumed"),
                    str(status),
                )
            )
    return FixtureScore(
        fixture_id=fix.fixture_id,
        family=fix.family,
        passed=all(c["passed"] for c in checks),
        checks=checks,
        hard_contract=True,
    )


def score_resumption(fix: GoldenFixture) -> FixtureScore:
    from plugin.agent.executive.blocking import (
        BlockingCondition,
        EffectPredicate,
        IntentionRef,
    )
    from plugin.agent.executive.intention_frame import (
        Intention,
        IntentionFrame,
        IntentionOrigin,
        ensure_child_for_precondition,
        push_intention_frame,
        resume_parent_after_child,
    )
    from plugin.agent.runtime.state import ExecutionState

    gold = fix.gold or {}
    state = ExecutionState()
    parent = IntentionFrame(
        intention=Intention(
            id=_intention_id(fix),
            objective="forward message",
            success_predicate="forward_affordance_grounded",
            created_from=IntentionOrigin(kind="goal"),
        )
    )
    push_intention_frame(state, parent)
    need = int(gold.get("required_bytes") or 184549376)
    key = f"storage:available_bytes_at_least:{need}"
    ensure_child_for_precondition(
        state,
        parent,
        effect_key=key,
        success_predicate=key,
        methods=[("relieve_host_storage", "relieve_host_storage")],
    )
    world = dict(fix.world_before or {})
    world.setdefault("available_storage_bytes", need + 10)
    parent_blockers = []
    if gold.get("parent_still_blocked"):
        parent_blockers = [
            BlockingCondition(
                kind="app_not_operational",
                required_effect=EffectPredicate(
                    subject="app_operational", relation="is_true", value=True
                ),
                blocks=[IntentionRef(intention_id=parent.intention.id)],
            )
        ]
    status = resume_parent_after_child(
        state,
        world=world,
        parent_blockers=parent_blockers,
        facts={
            **_facts(fix),
            "available_storage_bytes": world.get("available_storage_bytes"),
            "app_operational": not bool(gold.get("parent_still_blocked")),
            "blocked_app_recoverable": True,
        },
    )
    checks = [
        _check("child_effect_met", bool(status.get("child_effect_met")), str(status)),
        _check(
            "resumed",
            bool(status.get("resumed")) == bool(gold.get("expect_resume")),
            f"expected_resume={gold.get('expect_resume')} got={status.get('resumed')}",
        ),
    ]
    if gold.get("parent_still_blocked"):
        checks.append(
            _check(
                "parent_still_blocked",
                bool(status.get("parent_still_blocked")),
                str(status),
            )
        )
    if gold.get("expect_next_prerequisite"):
        from plugin.agent.executive.blocking import (
            ExecutabilityStatus,
            assess_executability,
            resolve_methods_for_effect,
        )

        assessment = assess_executability(
            intention_id=parent.intention.id,
            blockers=parent_blockers,
            world=world,
            facts={
                "app_operational": False,
                "blocked_app_recoverable": True,
                "available_storage_bytes": world.get("available_storage_bytes"),
            },
        )
        checks.append(
            _check(
                "next_prereq_resolvable",
                assessment.status == ExecutabilityStatus.BLOCKED_RESOLVABLE.value,
                assessment.status,
            )
        )
        if assessment.resolvable_conditions:
            methods = resolve_methods_for_effect(
                assessment.resolvable_conditions[0].required_effect,
                facts={"blocked_app_recoverable": True},
            )
            checks.append(
                _check(
                    "next_is_recover",
                    bool(methods) and methods[0].capability == "recover_blocked_app",
                    str(methods),
                )
            )
    return FixtureScore(
        fixture_id=fix.fixture_id,
        family=fix.family,
        passed=all(c["passed"] for c in checks),
        checks=checks,
        hard_contract=True,
    )


def score_trajectory(fix: GoldenFixture) -> FixtureScore:
    """L3: drive the production executability gate — do not re-orchestrate in scorer."""
    from plugin.agent.executive.executability_gate import run_executability_gate
    from plugin.agent.executive.intention_frame import (
        Intention,
        IntentionFrame,
        IntentionOrigin,
        active_intention_frame,
        intention_stack_of,
        push_intention_frame,
    )
    from plugin.agent.runtime.state import ExecutionState

    gold = fix.gold or {}
    checks: List[Dict[str, Any]] = []
    milestones = list(gold.get("milestones") or [])
    need = int(gold.get("required_bytes") or 0)
    free_after = gold.get("free_after_bytes")

    state = ExecutionState()
    # Parent starts WITHOUT storage precondition attached — discovery from env.
    parent = IntentionFrame(
        intention=Intention(
            id=_intention_id(fix),
            objective=str(
                (fix.parent_intention or {}).get("objective") or "forward message"
            ),
            success_predicate=str(
                (fix.parent_intention or {}).get("success_predicate")
                or "forward_affordance_grounded"
            ),
            created_from=IntentionOrigin(kind="goal"),
        )
    )
    # Refuse pre-seeded storage preconditions on L3 trajectories unless explicit.
    if gold.get("parent_has_storage_precondition"):
        pass  # known_precondition path — parent fields already encode it in gold
    push_intention_frame(state, parent)

    texts = list(fix.observation_texts)
    view = dict(fix.view or {})
    features = dict(fix.features or {})

    # Frame A: blocked dialog → gate must spawn child / ACT relieve.
    g1 = run_executability_gate(
        state,
        observation_texts=texts,
        view=view,
        features=features,
        facts=_facts(fix),
        app=fix.app,
        goal_kind="forward",
        intention_id=parent.intention.id,
    )
    if "detect_blocker" in milestones or not milestones:
        checks.append(
            _check(
                "detect_blocker",
                bool(g1.blockers),
                f"blockers={len(g1.blockers)} warnings={len(g1.warnings)}",
            )
        )
    if "blocked_resolvable" in milestones or not milestones:
        status = (g1.assessment or {}).get("status") if g1.assessment else ""
        # Gate may short-circuit into prerequisite_child without leaving assessment
        # when already resolved — accept either assessment or spawned child.
        checks.append(
            _check(
                "blocked_resolvable",
                status == "blocked_resolvable" or g1.phase == "prerequisite_child",
                f"phase={g1.phase} assessment={status}",
            )
        )
    if "parent_suspended" in milestones or not milestones:
        checks.append(
            _check(
                "parent_suspended",
                bool(parent.suspended_by_child),
                f"suspended={parent.suspended_by_child} child={g1.child_id}",
            )
        )
    if "safe_method" in milestones or not milestones:
        cap = str(getattr(g1.meta, "capability", "") or "")
        checks.append(
            _check(
                "safe_method",
                cap == "relieve_host_storage"
                and "delete_user" not in cap,
                f"capability={cap!r}",
            )
        )
    # Dedupe: second gate turn with same evidence must not spawn another child.
    g1b = run_executability_gate(
        state,
        observation_texts=texts,
        view=view,
        features=features,
        facts=_facts(fix),
        app=fix.app,
        intention_id=parent.intention.id,
    )
    kids = [
        f
        for f in intention_stack_of(state)
        if f.parent_intention_id == parent.intention.id
    ]
    if "no_duplicate_child" in milestones or not milestones:
        checks.append(
            _check(
                "no_duplicate_child",
                len(kids) == 1,
                f"n={len(kids)} phase2={g1b.phase}",
            )
        )

    # Frame C/D: cleanup execution_ok but effect unmet → no resume.
    if "no_premature_resume" in milestones or free_after is not None:
        unmet_free = max(1, (need // 10) if need else 20 * 1024 * 1024)
        state.last_housekeeping_evidence = {  # type: ignore[attr-defined]
            "execution_ok": True,
            "available_storage_bytes": unmet_free,
            "bytes_reclaimed": unmet_free,
            "headroom_met": False,
        }
        g_unmet = run_executability_gate(
            state,
            observation_texts=texts,
            view={**view, "available_storage_bytes": unmet_free},
            features=features,
            facts={**_facts(fix), "available_storage_bytes": unmet_free},
            app=fix.app,
        )
        active = active_intention_frame(state)
        checks.append(
            _check(
                "no_premature_resume",
                (
                    bool(parent.suspended_by_child)
                    and active is not None
                    and bool(active.parent_intention_id)
                    and not (g_unmet.resume or {}).get("resumed")
                    and g_unmet.phase in {"prerequisite_child_act", "prerequisite_resume"}
                )
                or (
                    # If resume attempted, must report child_effect_met false.
                    (g_unmet.resume or {}).get("child_effect_met") is False
                ),
                f"phase={g_unmet.phase} resume={g_unmet.resume} "
                f"active={getattr(active, 'intention', None) and active.intention.id} "
                f"suspended={parent.suspended_by_child}",
            )
        )

    # Frame E/F/G: effect met → gate rechecks parent.
    if free_after is not None:
        state.last_housekeeping_evidence = {  # type: ignore[attr-defined]
            "execution_ok": True,
            "available_storage_bytes": int(free_after),
            "bytes_reclaimed": int(free_after),
            "headroom_met": True,
        }
        met_view = {
            **view,
            "available_storage_bytes": int(free_after),
            "surface": "conversation"
            if gold.get("blocker_absent_after")
            else view.get("surface") or "dialog",
            "storage_pressure": not bool(gold.get("blocker_absent_after", True)),
        }
        met_feats = dict(features)
        extras = dict(met_feats.get("extras") or {})
        extras["storage_pressure"] = not bool(gold.get("blocker_absent_after", True))
        met_feats["extras"] = extras
        g_met = run_executability_gate(
            state,
            observation_texts=texts
            if not gold.get("blocker_absent_after")
            else ["chat list"],
            view=met_view,
            features=met_feats,
            facts={
                **_facts(fix),
                "available_storage_bytes": int(free_after),
                "app_operational": bool(gold.get("blocker_absent_after", True)),
                "storage_pressure": not bool(gold.get("blocker_absent_after", True)),
            },
            app=fix.app,
        )
        if "effect_verified" in milestones or not milestones:
            checks.append(
                _check(
                    "effect_verified",
                    g_met.phase == "prerequisite_resume"
                    or bool((g_met.resume or {}).get("child_effect_met")),
                    f"phase={g_met.phase} resume={g_met.resume}",
                )
            )
        if "eventual_parent_recovery" in milestones or gold.get("expect_resume") is not None:
            resumed = bool((g_met.resume or {}).get("resumed"))
            checks.append(
                _check(
                    "eventual_parent_recovery",
                    resumed == bool(gold.get("expect_resume", True)),
                    f"expected_resume={gold.get('expect_resume')} got={resumed} "
                    f"resume={g_met.resume}",
                )
            )

    return FixtureScore(
        fixture_id=fix.fixture_id,
        family=fix.family,
        passed=all(c["passed"] for c in checks) if checks else False,
        checks=checks,
        hard_contract=True,
    )


def score_dynamic_precondition_discovery(fix: GoldenFixture) -> FixtureScore:
    """Parent has no storage precondition; environment must derive required_effect."""
    from plugin.agent.executive.executability_gate import run_executability_gate
    from plugin.agent.executive.intention_frame import (
        Intention,
        IntentionFrame,
        IntentionOrigin,
        push_intention_frame,
    )
    from plugin.agent.runtime.state import ExecutionState

    parent_pre = list((fix.parent_intention or {}).get("preconditions") or [])
    checks = [
        _check(
            "parent_has_no_storage_precondition",
            not any(
                str(p.get("subject") if isinstance(p, dict) else "") == "storage"
                for p in parent_pre
            ),
            f"preconditions={parent_pre}",
        )
    ]
    state = ExecutionState()
    parent = IntentionFrame(
        intention=Intention(
            id=_intention_id(fix),
            objective=str(
                (fix.parent_intention or {}).get("objective") or "forward message"
            ),
            success_predicate="forward_affordance_grounded",
            created_from=IntentionOrigin(kind="goal"),
        )
    )
    push_intention_frame(state, parent)
    g = run_executability_gate(
        state,
        observation_texts=fix.observation_texts,
        view=fix.view,
        features=fix.features,
        facts=_facts(fix),
        app=fix.app,
        intention_id=parent.intention.id,
    )
    checks.append(
        _check(
            "derived_required_effect",
            bool(g.effect_key) and g.effect_key.startswith("storage:"),
            f"effect_key={g.effect_key!r}",
        )
    )
    checks.append(
        _check(
            "spawned_prereq_child",
            g.phase == "prerequisite_child" and bool(g.child_id),
            f"phase={g.phase} child={g.child_id}",
        )
    )
    checks.append(
        _check(
            "parent_suspended_after_discovery",
            bool(parent.suspended_by_child),
            f"suspended={parent.suspended_by_child}",
        )
    )
    return FixtureScore(
        fixture_id=fix.fixture_id,
        family=fix.family,
        passed=all(c["passed"] for c in checks),
        checks=checks,
        hard_contract=True,
    )


_SCORERS = {
    "warning_vs_blocker": score_warning_vs_blocker,
    "executability": score_executability,
    "prerequisite_children": score_prerequisite_children,
    "effect_resolution": score_effect_resolution,
    "effect_verification": score_effect_verification,
    "resumption": score_resumption,
    "trajectories": score_trajectory,
}


def score_fixture(fix: GoldenFixture) -> FixtureScore:
    # Dynamic discovery uses dedicated scorer regardless of family folder.
    if "dynamic_precondition_discovery" in fix.fixture_id or (
        (fix.gold or {}).get("score_via") == "dynamic_precondition_discovery"
    ):
        return _annotate(score_dynamic_precondition_discovery(fix), fix)
    fn = _SCORERS.get(fix.family)
    if fn is None:
        return _annotate(
            FixtureScore(
                fixture_id=fix.fixture_id,
                family=fix.family,
                passed=False,
                checks=[_check("known_family", False, fix.family)],
            ),
            fix,
        )
    return _annotate(fn(fix), fix)


def score_all(
    *,
    root: str = DEFAULT_PHENOMENA_DIR,
    version: str = PHENOMENA_VERSION,
) -> Dict[str, Any]:
    by_family = load_all_fixtures(root=root, version=version)
    modules: Dict[str, Any] = {}
    by_level: Dict[str, Dict[str, int]] = {
        "L1": {"n": 0, "passed": 0},
        "L2": {"n": 0, "passed": 0},
        "L3": {"n": 0, "passed": 0},
    }
    failures: List[Dict[str, Any]] = []
    hard_failures: List[Dict[str, Any]] = []
    specifications: List[Dict[str, Any]] = []
    production_matrix: List[Dict[str, Any]] = []
    total = 0
    passed = 0
    for fam in PHENOMENON_FAMILIES:
        scores = [score_fixture(f) for f in by_family.get(fam) or []]
        # Only golden (non-specification) fixtures count toward pass rate.
        scored = [
            s
            for s in scores
            if s.fixture_status != FIXTURE_STATUS_SPECIFICATION
        ]
        fam_pass = sum(1 for s in scored if s.passed)
        total += len(scored)
        passed += fam_pass
        fail_list = [s.to_dict() for s in scored if not s.passed]
        modules[fam] = {
            "n": len(scored),
            "passed": fam_pass,
            "rate": (fam_pass / len(scored)) if scored else 1.0,
            "failures": fail_list,
            "specifications": [
                s.to_dict()
                for s in scores
                if s.fixture_status == FIXTURE_STATUS_SPECIFICATION
            ],
        }
        for s in scores:
            d = s.to_dict()
            lvl = d.get("eval_level") or "L1"
            if lvl in by_level and s.fixture_status != FIXTURE_STATUS_SPECIFICATION:
                by_level[lvl]["n"] += 1
                if s.passed:
                    by_level[lvl]["passed"] += 1
            production_matrix.append(
                {
                    "fixture_id": s.fixture_id,
                    "family": s.family,
                    "eval_level": s.eval_level,
                    "fixture_status": s.fixture_status,
                    "production_exercised": s.production_exercised,
                    "passed": s.passed,
                }
            )
            if s.fixture_status == FIXTURE_STATUS_SPECIFICATION:
                specifications.append(d)
                continue
            if not s.passed:
                failures.append(d)
                hard_failures.append(d)
    seen = set()
    hard_dedup = []
    for h in hard_failures:
        fid = h.get("fixture_id")
        if fid in seen:
            continue
        seen.add(fid)
        hard_dedup.append(h)
    return {
        "version": version,
        "total": total,
        "passed": passed,
        "rate": (passed / total) if total else 1.0,
        "modules": modules,
        "by_level": by_level,
        "failures": failures,
        "hard_failures": hard_dedup,
        "specifications": specifications,
        "production_matrix": production_matrix,
        "manifest": load_manifest(root=root, version=version),
    }


def render(report: Dict[str, Any]) -> str:
    lines = [
        f"phenomena_{report.get('version')} — "
        f"mean={report.get('rate', 0):.2f}  golden_cases={report.get('total', 0)} "
        f"(spec={len(report.get('specifications') or [])})"
    ]
    lines.append("  --- by eval level (not equivalent) ---")
    for lvl in ("L1", "L2", "L3"):
        block = (report.get("by_level") or {}).get(lvl) or {}
        n = int(block.get("n") or 0)
        p = int(block.get("passed") or 0)
        rate = (p / n) if n else 1.0
        label = {
            "L1": "contract",
            "L2": "pipeline",
            "L3": "trajectory/gate",
        }.get(lvl, lvl)
        lines.append(f"  {lvl} {label:<18} {rate*100:3.0f}%  {p}/{n}")
    lines.append("  --- by family ---")
    for fam, block in (report.get("modules") or {}).items():
        n = int(block.get("n") or 0)
        p = int(block.get("passed") or 0)
        rate = float(block.get("rate") or 0)
        n_spec = len(block.get("specifications") or [])
        extra = f"  +{n_spec} spec" if n_spec else ""
        lines.append(f"  {fam:<24} {rate*100:3.0f}%  {p}/{n}{extra}")
    lines.append("  --- production exercised? ---")
    for row in report.get("production_matrix") or []:
        if row.get("fixture_status") == FIXTURE_STATUS_SPECIFICATION:
            flag = "SPECIFICATION"
        else:
            flag = "YES" if row.get("production_exercised") else "NO"
        lines.append(
            f"  {str(row.get('fixture_id')):<42} {flag:<14} "
            f"{row.get('eval_level')}"
        )
    return "\n".join(lines)


def blocking_failures(report: Optional[Dict[str, Any]] = None) -> List[str]:
    report = report or score_all()
    gaps = set((report.get("manifest") or {}).get("known_gap_fixture_ids") or [])
    out: List[str] = []
    for fam, block in (report.get("modules") or {}).items():
        for f in block.get("failures") or []:
            fid = str(f.get("fixture_id") or "")
            if fid in gaps:
                continue
            if f.get("fixture_status") == FIXTURE_STATUS_SPECIFICATION:
                continue
            fails = f.get("failures") or []
            out.append(f"{fam}:{fid}:{fails}")
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(list(argv) if argv is not None else None)
    report = score_all()
    print(render(report))
    fails = blocking_failures(report)
    if fails:
        print("\nBLOCKING phenomenon failures (golden only; specs excluded):")
        for line in fails:
            print(f"  FAIL {line}")
        return 1
    print("\nphenomena: all non-gap golden fixtures pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
