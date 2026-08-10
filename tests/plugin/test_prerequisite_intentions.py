"""Prerequisite / BlockingCondition interruption abstraction goldens."""

from __future__ import annotations

from plugin.agent.executive.blocking import (
    BlockingCondition,
    EffectPredicate,
    ExecutabilityStatus,
    IntentionRef,
    Precondition,
    assess_executability,
    detect_warnings_and_blockers,
    evaluate_effect_predicate,
    resolve_methods_for_effect,
)
from plugin.agent.executive.intention_frame import (
    Intention,
    IntentionFrame,
    IntentionOrigin,
    IntentionStatus,
    active_intention_frame,
    ensure_child_for_precondition,
    evaluate_intention_success,
    intention_stack_of,
    push_intention_frame,
    resume_parent_after_child,
)
from plugin.agent.runtime.state import ExecutionState


def _parent_frame(intention_id: str = "i_forward") -> IntentionFrame:
    return IntentionFrame(
        intention=Intention(
            id=intention_id,
            objective="forward message",
            success_predicate="forward_affordance_grounded",
            created_from=IntentionOrigin(kind="goal"),
        )
    )


def _storage_dialog_texts() -> list:
    return [
        "Storage is too full",
        "To keep using WhatsApp, free up at least 175.81 MB of storage.",
    ]


def test_blocked_goal_storage_spawns_relieve_child():
    warns, blockers = detect_warnings_and_blockers(
        observation_texts=_storage_dialog_texts(),
        view={"screen": "dialog", "storage_pressure": True},
        features={"extras": {"storage_pressure": True, "screen_kind": "dialog"}},
        intention_id="i_forward",
        app="WhatsApp",
    )
    assert not warns
    assert any(b.kind == "insufficient_storage" for b in blockers)
    assessment = assess_executability(
        intention_id="i_forward",
        blockers=blockers,
        world={"surface": "dialog", "storage_pressure": True},
        facts={"agent_owned_reclaimable_bytes": 1, "storage_pressure": True},
    )
    assert assessment.status == ExecutabilityStatus.BLOCKED_RESOLVABLE.value
    storage_bc = next(b for b in assessment.resolvable_conditions if "storage:" in b.semantic_key())
    methods = resolve_methods_for_effect(
        storage_bc.required_effect, facts={"agent_owned_reclaimable_bytes": 1}
    )
    assert methods and methods[0].capability == "relieve_host_storage"

    state = ExecutionState()
    parent = _parent_frame()
    push_intention_frame(state, parent)
    child = ensure_child_for_precondition(
        state,
        parent,
        effect_key=storage_bc.semantic_key(),
        success_predicate=storage_bc.semantic_key(),
        methods=[(m.capability, m.capability) for m in methods],
        blocking_condition_id=storage_bc.id,
    )
    assert child is not None
    assert parent.suspended_by_child
    assert active_intention_frame(state) is child
    assert "relieve_host_storage" in child.method_frontier.catalog


def test_nonblocking_warning_does_not_interrupt():
    warns, blockers = detect_warnings_and_blockers(
        observation_texts=["Storage almost full"],
        view={"screen": "conversation"},
        features={"extras": {"screen_kind": "conversation"}},
        intention_id="i_forward",
        app="WhatsApp",
    )
    assert warns and warns[0].kind == "low_storage"
    assert not blockers
    assessment = assess_executability(
        intention_id="i_forward",
        blockers=blockers,
        world={"surface": "conversation"},
        facts={"agent_owned_reclaimable_bytes": 1},
    )
    assert assessment.status == ExecutabilityStatus.EXECUTABLE.value


def test_low_storage_warning_but_app_still_operational():
    warns, blockers = detect_warnings_and_blockers(
        observation_texts=["Running out of space on this Mac"],
        view={"screen": "conversation", "app_operational": True},
        intention_id="i_forward",
    )
    assert warns
    assert not blockers


def test_same_required_effect_from_multiple_evidence_sources_spawns_one_child():
    state = ExecutionState()
    parent = _parent_frame()
    push_intention_frame(state, parent)
    key = "storage:available_bytes_at_least:184549376"
    methods = [("relieve_host_storage", "relieve_host_storage")]
    c1 = ensure_child_for_precondition(
        state, parent, effect_key=key, success_predicate=key, methods=methods
    )
    c2 = ensure_child_for_precondition(
        state, parent, effect_key=key, success_predicate=key, methods=methods
    )
    assert c1 is not None and c2 is not None
    assert c1.intention.id == c2.intention.id
    # Two distinct blocker observation ids, same semantic key → one child.
    kids = [
        f
        for f in intention_stack_of(state)
        if f.parent_intention_id == parent.intention.id
    ]
    assert len(kids) == 1


def test_child_method_execution_success_but_effect_not_met_does_not_resume_parent():
    state = ExecutionState()
    parent = _parent_frame()
    push_intention_frame(state, parent)
    key = "storage:available_bytes_at_least:200000000"
    child = ensure_child_for_precondition(
        state,
        parent,
        effect_key=key,
        success_predicate=key,
        methods=[("relieve_host_storage", "relieve_host_storage")],
    )
    assert child is not None
    # Capability ran (execution_ok) but free space still below need.
    world = {
        "available_storage_bytes": 50_000_000,
        "execution_ok": True,
        "surface": "dialog",
    }
    assert not evaluate_intention_success(child, world=world)
    status = resume_parent_after_child(state, world=world, facts={"agent_owned_reclaimable_bytes": 1})
    assert not status.get("resumed")
    assert status.get("child_effect_met") is False
    assert active_intention_frame(state) is child
    assert parent.suspended_by_child


def test_resolved_child_does_not_resume_parent_until_parent_executability_is_rechecked():
    state = ExecutionState()
    parent = _parent_frame()
    push_intention_frame(state, parent)
    need = 184_549_376
    key = f"storage:available_bytes_at_least:{need}"
    child = ensure_child_for_precondition(
        state,
        parent,
        effect_key=key,
        success_predicate=key,
        methods=[("relieve_host_storage", "relieve_host_storage")],
    )
    assert child is not None
    # Child effect met, but parent still has app_operational blocker.
    world = {"available_storage_bytes": need + 10, "surface": "dialog", "storage_pressure": True}
    still_blocked = [
        BlockingCondition(
            kind="app_not_operational",
            required_effect=EffectPredicate(
                subject="app_operational", relation="is_true", value=True
            ),
            blocks=[IntentionRef(intention_id=parent.intention.id)],
            evidence=["dialog still up"],
        )
    ]
    status = resume_parent_after_child(
        state,
        world=world,
        parent_blockers=still_blocked,
        facts={
            "agent_owned_reclaimable_bytes": 1,
            "blocked_app_recoverable": True,
            "available_storage_bytes": need + 10,
            "app_operational": False,
            "storage_pressure": True,
        },
    )
    assert status.get("child_effect_met")
    assert status.get("parent_still_blocked")
    assert not status.get("resumed")
    assert active_intention_frame(state).intention.id == parent.intention.id
    assert not parent.suspended_by_child


def test_child_effect_met_but_parent_still_non_executable_creates_next_prerequisite():
    state = ExecutionState()
    parent = _parent_frame()
    push_intention_frame(state, parent)
    need = 184_549_376
    storage_key = f"storage:available_bytes_at_least:{need}"
    ensure_child_for_precondition(
        state,
        parent,
        effect_key=storage_key,
        success_predicate=storage_key,
        methods=[("relieve_host_storage", "relieve_host_storage")],
    )
    world = {
        "available_storage_bytes": need + 1,
        "surface": "dialog",
        "storage_pressure": True,
    }
    app_blocker = BlockingCondition(
        kind="app_not_operational",
        required_effect=EffectPredicate(
            subject="app_operational", relation="is_true", value=True
        ),
        blocks=[IntentionRef(intention_id=parent.intention.id)],
    )
    resume_parent_after_child(
        state,
        world=world,
        parent_blockers=[app_blocker],
        facts={
            "agent_owned_reclaimable_bytes": 1,
            "blocked_app_recoverable": True,
            "available_storage_bytes": need + 1,
            "app_operational": False,
        },
    )
    assessment = assess_executability(
        intention_id=parent.intention.id,
        blockers=[app_blocker],
        world=world,
        facts={
            "blocked_app_recoverable": True,
            "app_operational": False,
            "available_storage_bytes": need + 1,
        },
    )
    assert assessment.status == ExecutabilityStatus.BLOCKED_RESOLVABLE.value
    app_key = assessment.resolvable_conditions[0].semantic_key()
    assert app_key.startswith("app_operational:")
    methods = resolve_methods_for_effect(
        assessment.resolvable_conditions[0].required_effect,
        facts={"blocked_app_recoverable": True},
    )
    assert methods[0].capability == "recover_blocked_app"
    child_b = ensure_child_for_precondition(
        state,
        parent,
        effect_key=app_key,
        success_predicate=app_key,
        methods=[(m.capability, m.capability) for m in methods],
    )
    assert child_b is not None
    assert child_b.prerequisite_effect_key.startswith("app_operational:")
    assert "recover_blocked_app" in child_b.method_frontier.catalog


def test_permission_auth_dependency_stubs_resolvable():
    for subject, capability, fact in [
        ("authenticated", "authenticate", "auth_flow_available"),
        ("permission_granted", "obtain_permission", "permission_prompt_available"),
        ("dependency_present", "install_dependency", "dependency_installable"),
    ]:
        pred = EffectPredicate(subject=subject, relation="is_true", value=True)
        methods = resolve_methods_for_effect(pred, facts={fact: True})
        assert methods and methods[0].capability == capability
        assessment = assess_executability(
            intention_id="i_x",
            preconditions=[Precondition(predicate=pred)],
            blockers=[],
            world={},
            facts={fact: True, subject: False},
        )
        assert assessment.status == ExecutabilityStatus.BLOCKED_RESOLVABLE.value


def test_obsolete_parent_not_resumed_when_already_complete():
    state = ExecutionState()
    parent = _parent_frame()
    push_intention_frame(state, parent)
    key = "storage:available_bytes_at_least:1000"
    ensure_child_for_precondition(
        state,
        parent,
        effect_key=key,
        success_predicate=key,
        methods=[("relieve_host_storage", "relieve_host_storage")],
    )
    status = resume_parent_after_child(
        state,
        world={
            "available_storage_bytes": 5000,
            "surface": "forward_picker",
            "objects": [{"text": "Forward"}],
        },
        affordance_stance="act_clear",
        grounded_forward=True,
        facts={"available_storage_bytes": 5000},
    )
    assert status.get("obsolete_parent")
    assert not status.get("resumed")


def test_effect_predicate_judge_not_capability_claim():
    pred = EffectPredicate(
        subject="storage", relation="available_bytes_at_least", value=100
    )
    # Capability claiming success without world evidence must not satisfy.
    assert not evaluate_effect_predicate(
        pred, world={"desired_effect_achieved": True, "execution_ok": True}
    )
    assert evaluate_effect_predicate(
        pred, world={"available_storage_bytes": 150}
    )


def test_paired_storage_and_app_blockers_from_dialog():
    _, blockers = detect_warnings_and_blockers(
        observation_texts=_storage_dialog_texts(),
        view={"screen": "dialog"},
        features={"extras": {"storage_pressure": True, "has_dialog": True}},
        intention_id="i_forward",
    )
    kinds = {b.kind for b in blockers}
    assert "insufficient_storage" in kinds
    assert "app_not_operational" in kinds
    # First resolvable method for the goal is relieve, not recover.
    assessment = assess_executability(
        intention_id="i_forward",
        blockers=blockers,
        world={"surface": "dialog", "storage_pressure": True},
        facts={
            "agent_owned_reclaimable_bytes": 1,
            "blocked_app_recoverable": True,
            "storage_pressure": True,
        },
    )
    assert assessment.status == ExecutabilityStatus.BLOCKED_RESOLVABLE.value
    first = assessment.resolvable_conditions[0]
    assert first.required_effect.subject == "storage"
    methods = resolve_methods_for_effect(
        first.required_effect, facts={"agent_owned_reclaimable_bytes": 1}
    )
    assert methods[0].capability == "relieve_host_storage"
