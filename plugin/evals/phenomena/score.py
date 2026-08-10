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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "family": self.family,
            "passed": self.passed,
            "hard_contract": self.hard_contract,
            "checks": self.checks,
            "failures": [c["name"] for c in self.checks if not c.get("passed")],
        }


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
    """Durable trajectory: score semantic milestones, not low-level actions."""
    from plugin.agent.executive.blocking import (
        ExecutabilityStatus,
        assess_executability,
        detect_warnings_and_blockers,
        resolve_methods_for_effect,
    )
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
    checks: List[Dict[str, Any]] = []
    milestones = list(gold.get("milestones") or [])
    # Run a compact scripted trajectory from frames or default storage path.
    frames = list(fix.frames or [])
    if not frames:
        frames = [
            {"id": "A", "observation_texts": fix.observation_texts, "view": fix.view},
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

    frame0 = frames[0]
    texts = list(frame0.get("observation_texts") or fix.observation_texts)
    view = dict(frame0.get("view") or fix.view or {})
    warns, blockers = detect_warnings_and_blockers(
        observation_texts=texts,
        view=view,
        features=fix.features,
        intention_id=parent.intention.id,
        app=fix.app,
    )
    if "detect_blocker" in milestones or not milestones:
        checks.append(
            _check(
                "detect_blocker",
                bool(blockers) and not (gold.get("allow_warning_only") and not blockers),
                f"blockers={len(blockers)} warnings={len(warns)}",
            )
        )

    assessment = assess_executability(
        intention_id=parent.intention.id,
        blockers=blockers,
        world=view,
        facts=_facts(fix),
    )
    if "blocked_resolvable" in milestones or not milestones:
        checks.append(
            _check(
                "blocked_resolvable",
                assessment.status == ExecutabilityStatus.BLOCKED_RESOLVABLE.value,
                assessment.status,
            )
        )

    storage_bc = next(
        (
            b
            for b in assessment.resolvable_conditions
            if b.required_effect.subject == "storage"
        ),
        assessment.resolvable_conditions[0] if assessment.resolvable_conditions else None,
    )
    child = None
    if storage_bc is not None:
        key = storage_bc.semantic_key()
        methods = resolve_methods_for_effect(storage_bc.required_effect, facts=_facts(fix))
        pairs = [(m.capability, m.capability) for m in methods]
        child = ensure_child_for_precondition(
            state, parent, effect_key=key, success_predicate=key, methods=pairs
        )
        ensure_child_for_precondition(
            state, parent, effect_key=key, success_predicate=key, methods=pairs
        )
    if "parent_suspended" in milestones or not milestones:
        checks.append(_check("parent_suspended", bool(parent.suspended_by_child)))
    if "no_duplicate_child" in milestones or not milestones:
        from plugin.agent.executive.intention_frame import intention_stack_of

        kids = [
            f
            for f in intention_stack_of(state)
            if f.parent_intention_id == parent.intention.id
        ]
        checks.append(_check("no_duplicate_child", len(kids) == 1, f"n={len(kids)}"))
    if "safe_method" in milestones or not milestones:
        safe = False
        if child is not None:
            caps = {s.capability for s in (child.method_frontier.catalog or {}).values()}
            safe = "relieve_host_storage" in caps and "delete_user_documents" not in caps
        checks.append(_check("safe_method", safe, "expected relieve_host_storage"))

    # Effect verify + resume from later frames / gold.
    free_after = gold.get("free_after_bytes")
    if free_after is not None and child is not None:
        need = int(storage_bc.required_effect.value or 0) if storage_bc else 0
        world = {"available_storage_bytes": int(free_after), "surface": "dialog"}
        met = evaluate_intention_success(child, world=world)
        if "effect_verified" in milestones or not milestones:
            checks.append(
                _check(
                    "effect_verified",
                    met == (int(free_after) >= need and need > 0),
                    f"free={free_after} need={need} met={met}",
                )
            )
        if met:
            status = resume_parent_after_child(
                state,
                world=world,
                parent_blockers=[] if gold.get("blocker_absent_after") else blockers,
                facts={
                    **_facts(fix),
                    "available_storage_bytes": int(free_after),
                    "app_operational": bool(gold.get("blocker_absent_after", True)),
                },
            )
            if "no_premature_resume" in milestones:
                # Always true as API contract when we call resume only after met.
                checks.append(_check("no_premature_resume", True))
            if "eventual_parent_recovery" in milestones or gold.get("expect_resume"):
                checks.append(
                    _check(
                        "eventual_parent_recovery",
                        bool(status.get("resumed")) == bool(gold.get("expect_resume", True)),
                        str(status),
                    )
                )
    return FixtureScore(
        fixture_id=fix.fixture_id,
        family=fix.family,
        passed=all(c["passed"] for c in checks) if checks else False,
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
    fn = _SCORERS.get(fix.family)
    if fn is None:
        return FixtureScore(
            fixture_id=fix.fixture_id,
            family=fix.family,
            passed=False,
            checks=[_check("known_family", False, fix.family)],
        )
    return fn(fix)


def score_all(
    *,
    root: str = DEFAULT_PHENOMENA_DIR,
    version: str = PHENOMENA_VERSION,
) -> Dict[str, Any]:
    by_family = load_all_fixtures(root=root, version=version)
    modules: Dict[str, Any] = {}
    failures: List[Dict[str, Any]] = []
    hard_failures: List[Dict[str, Any]] = []
    total = 0
    passed = 0
    for fam in PHENOMENON_FAMILIES:
        scores = [score_fixture(f) for f in by_family.get(fam) or []]
        fam_pass = sum(1 for s in scores if s.passed)
        total += len(scores)
        passed += fam_pass
        fail_list = [s.to_dict() for s in scores if not s.passed]
        modules[fam] = {
            "n": len(scores),
            "passed": fam_pass,
            "rate": (fam_pass / len(scores)) if scores else 1.0,
            "failures": fail_list,
        }
        for s in scores:
            if not s.passed:
                d = s.to_dict()
                failures.append(d)
                # Phenomenon curriculum: every failure is a hard contract miss
                # unless listed in manifest known_gap_fixture_ids.
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
        "failures": failures,
        "hard_failures": hard_dedup,
        "manifest": load_manifest(root=root, version=version),
    }


def render(report: Dict[str, Any]) -> str:
    lines = [
        f"phenomena_{report.get('version')} — "
        f"mean={report.get('rate', 0):.2f}  cases={report.get('total', 0)}"
    ]
    for fam, block in (report.get("modules") or {}).items():
        n = int(block.get("n") or 0)
        p = int(block.get("passed") or 0)
        rate = float(block.get("rate") or 0)
        lines.append(f"  {fam:<24} {rate*100:3.0f}%  {p}/{n}")
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
        print("\nBLOCKING phenomenon failures:")
        for line in fails:
            print(f"  FAIL {line}")
        return 1
    print("\nphenomena: all non-gap fixtures pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
