"""GROUNDING_WRONG_LOCUS: bad point is cheap; intent + patient survive."""

from __future__ import annotations

from plugin.agent.actor import ActorBrief, brief_from_brain_choice, validate_brief
from plugin.agent.capabilities.locus_contract import (
    point_locus_forbidden_for_capability,
    semantic_region_at_point,
)
from plugin.agent.executive.affordance_commitment import (
    arm_wrong_point_grounding_recovery,
    upsert_commitment,
)
from plugin.agent.executive.intention_frame import (
    AttemptValidity,
    FailureClass,
    Intention,
    IntentionFrame,
    MethodOutcome,
    MethodSpec,
    MethodStatus,
    close_attempt,
    begin_attempt,
    mark_method_attempted,
    recommend_recovery,
    RecoveryAction,
)
from plugin.agent.runtime.state import ExecutionState
from plugin.experiments.runs.live_health import _composer_mistype_score


def _composer_scene(*, composer_y0: float = 920.0) -> dict:
    return {
        "regions": [
            {
                "kind": "timeline",
                "bounds": [400.0, 80.0, 1400.0, 900.0],  # x0y0x1y1
            },
            {
                "kind": "composer",
                "bounds": [400.0, composer_y0, 1400.0, 1100.0],
            },
        ]
    }


def test_reveal_grounding_in_input_locus_is_rejected_before_motor():
    scene = _composer_scene()
    bad, why, _ = point_locus_forbidden_for_capability(
        "reveal_actions",
        (700.0, 990.0),
        scene_graph=scene,
    )
    assert bad is True
    assert "composer_point" in why
    brief = ActorBrief(
        gesture="context_click",
        capability="reveal_actions",
        point=(700.0, 990.0),
        label="zarooratwala lasawethe se",
        target_kind="message",
        geometry_audit={"scene_graph": scene},
    )
    ok, vwhy = validate_brief(brief)
    assert ok is False
    assert "composer_point" in vwhy


def test_message_near_composer_boundary_not_rejected_by_y_alone():
    """Reject only when semantic region says input — not because Y is low."""
    scene = {
        "regions": [
            # Timeline extends into the lower screen; composer below it.
            {"kind": "timeline", "bounds": [400.0, 80.0, 1400.0, 995.0]},
            {"kind": "composer", "bounds": [400.0, 1000.0, 1400.0, 1100.0]},
        ]
    }
    # Low Y but still inside timeline (above composer). Must remain valid.
    region = semantic_region_at_point((700.0, 980.0), scene_graph=scene)
    assert region == "timeline"
    bad, why, _ = point_locus_forbidden_for_capability(
        "reveal_actions",
        (700.0, 980.0),
        scene_graph=scene,
    )
    assert bad is False
    assert why == "ok"
    # Same low band, but inside composer → reject.
    bad2, why2, _ = point_locus_forbidden_for_capability(
        "reveal_actions",
        (700.0, 1050.0),
        scene_graph=scene,
    )
    assert bad2 is True
    assert "composer_point" in why2


def test_wrong_locus_invalidates_grounding_not_semantic_method():
    state = ExecutionState()
    c = upsert_commitment(
        state,
        family="reveal_actions",
        label="zarooratwala lasawethe se",
        desired_effect="forward_picker",
        patient_ref="zarooratwala.com",
        owner_surface_expected="conversation",
    )
    out = arm_wrong_point_grounding_recovery(
        state,
        family="reveal_actions",
        label="zarooratwala lasawethe se",
        patient_ref="zarooratwala.com",
        point=(700.0, 990.0),
        why="wrong_locus:patient:composer_point:reveal_actions:composer",
    )
    assert out.get("armed") is True
    assert state.grounding_reground_only is True
    assert state.grounding_reground_patient_ref == "zarooratwala.com"
    keys = list(c.invalid_grounding_keys) if hasattr(c, "invalid_grounding_keys") else []
    # Commitment object may be reloaded — check via state list.
    from plugin.agent.executive.affordance_commitment import list_commitments

    c2 = list_commitments(state)[-1]
    assert any("700" in k and "990" in k for k in (c2.invalid_grounding_keys or []))
    closure = state.last_effect_closure or {}
    assert closure.get("preserve_semantic_method") is True
    assert "GROUNDING_WRONG_LOCUS" in (closure.get("modes") or [])


def test_wrong_locus_recovery_preserves_patient():
    state = ExecutionState()
    arm_wrong_point_grounding_recovery(
        state,
        family="reveal_actions",
        label="msg",
        patient_ref="zarooratwala.com",
        point=(700.0, 990.0),
        why="composer_point",
    )
    assert state.grounding_reground_patient_ref == "zarooratwala.com"
    assert state.wrong_locus_recovery_owed is True
    assert state.wrong_locus_forbidden == "composer"


def test_second_grounding_source_can_recover_same_reveal_intention():
    frame = IntentionFrame(
        intention=Intention(id="i1", objective="reveal", success_predicate="p")
    )
    mid = "reveal_actions:zarooratwala"
    frame.method_frontier.catalog[mid] = MethodSpec(id=mid, capability="reveal_actions")
    frame.method_frontier.known_untried = [mid]
    mark_method_attempted(frame, mid)
    att = begin_attempt(method_id=mid)
    close_attempt(
        att,
        attempt_validity=AttemptValidity.INCONCLUSIVE_GROUNDING.value,
        failure_class=FailureClass.GROUNDING.value,
        method_outcome=MethodOutcome.EFFECT_UNCERTAIN.value,
    )
    # Inconclusive grounding must not kill the semantic method.
    assert mid in frame.method_frontier.eligible_methods() or mid in (
        frame.method_frontier.known_untried or []
    ) or frame.method_frontier.method_status.get(mid) in {
        MethodStatus.UNTRIED.value,
        "",
        None,
    }
    assert (
        recommend_recovery(
            frame,
            failure_class=FailureClass.GROUNDING.value,
            method_outcome=MethodOutcome.EFFECT_UNCERTAIN.value,
        )
        == RecoveryAction.CONTINUE_INTENTION.value
    )


def test_health_watch_recoverable_wrong_locus_does_not_immediately_kill():
    # One composer-band context click + recovery armed → soft/recoverable.
    events = [
        {
            "kind": "execution",
            "message": "context click 'zarooratwala lasawethe se' center=(700.0, 990.0)",
        },
        {
            "kind": "effect_closure",
            "modes": ["GROUNDING_WRONG_LOCUS"],
            "grounding_repair": "commitment_reground",
            "preserve_semantic_method": True,
        },
    ]
    score, why, n = _composer_mistype_score(events, "")
    assert n >= 1
    assert score < 0.85
    assert "wrong_locus_repetition" in why or "recovery" in why


def test_repeated_wrong_locus_after_recovery_exhaustion_can_stall_hard():
    events = [
        {
            "kind": "execution",
            "message": "context click 'zarooratwala' center=(700.0, 990.0)",
        },
        {
            "kind": "execution",
            "message": "context click 'zarooratwala' center=(705.0, 995.0)",
        },
        {
            "kind": "execution",
            "message": "context click 'zarooratwala' center=(710.0, 1000.0)",
        },
        # No grounding_repair / recovery tokens → treated as ignored recovery.
    ]
    score, why, n = _composer_mistype_score(events, "")
    assert n >= 3
    assert score >= 0.85
    assert "composer_mistype" in why


def test_brief_from_world_stamps_regions_for_validate():
    doc = {
        "surface": "conversation",
        "scene_graph": _composer_scene(),
        "objects": [
            {
                "id": "66",
                "kind": "message",
                "text": "zarooratwala lasawethe se",
                "point": [627.0, 993.0],
            }
        ],
    }
    brief = brief_from_brain_choice(
        {
            "family": "reveal_actions",
            "gesture": "context_click",
            "target_label": "zarooratwala lasawethe se",
            "target_point": [700.0, 990.0],
            "coordinate_space": "screen",
        },
        doc,
        capability="reveal_actions",
        allow_legacy_geometry=True,
    )
    assert brief.geometry_audit.get("scene_graph")
    ok, why = validate_brief(brief)
    assert ok is False
    assert "composer_point" in why
