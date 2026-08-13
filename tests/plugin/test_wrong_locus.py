"""General wrong-locus method forbid (field | container | patient)."""

from __future__ import annotations

from plugin.agent.actor import ActorBrief, validate_brief
from plugin.agent.capabilities.action_area import validate_actuation_grounding
from plugin.agent.capabilities.locate_content import (
    MACOS_FIND,
    LocateRequest,
    NativeFind,
)
from plugin.agent.capabilities.locus_contract import (
    LocusKind,
    wrong_locus_forbidden,
)
from plugin.agent.decision_consultation import build_decision_brief, sanitize_decision
from plugin.agent.executive.affordance_commitment import (
    arm_grounding_recovery,
    ensure_commitment_from_menu_observation,
    forbids_wrong_locus,
)
from plugin.agent.features import StateFeatures
from plugin.agent.goal import Goal
from plugin.agent.runtime.state import ExecutionState
from tests.plugin.test_locate_content import FakeSurface


def _goal() -> Goal:
    return Goal(
        kind="whatsapp_forward_message",
        contact="Pallavi",
        target_contact="Tanmay",
        link_query="zarooratwala",
    )


def test_wrong_field_locus_forbids_type_when_composer_focused():
    """Desired effect content_locate; composer focused ⇒ type/locate refuse."""
    brief = build_decision_brief(
        _goal(),
        world_document={
            "surface": "conversation",
            "open_conversation": "Pallavi",
            "focused_field_role": "composer",
            "objects": [],
        },
        features=StateFeatures(conversation_open=True, extras={}),
    )
    rejected = sanitize_decision(
        {"capability": "locate_content", "target": "zarooratwala"},
        brief,
    )
    assert not rejected.ok
    assert "wrong_locus" in rejected.why or "composer" in rejected.why.lower()

    for cap in ("locate_content", "type_query", "compose_search_query"):
        bad, why, req = wrong_locus_forbidden(
            cap,
            brief=brief,
            field_role="composer",
        )
        assert bad, (cap, why)
        assert "composer" in why
        assert req is not None and req.kind is LocusKind.FIELD


def test_native_find_does_not_type_when_only_composer_focused():
    surface = FakeSurface(["composer draft"], find_opens=False)
    surface.text_input_focused = lambda: True  # type: ignore[method-assign]
    surface.filter_field_ready = lambda: False  # type: ignore[method-assign]

    outcome = NativeFind(MACOS_FIND).locate(
        LocateRequest(query="zarooratwala", app="SomeChatApp"),
        surface,
    )
    assert not outcome.ok
    assert surface.typed == []
    assert MACOS_FIND.open_find in surface.keys


def test_wrong_container_locus_forbids_compose_into_foreign_open():
    brief = build_decision_brief(
        _goal(),
        world_document={
            "surface": "conversation",
            "open_conversation": "[CoE - IoT & AI] BLR Startups",
            "objects": [
                {"kind": "search_field", "text": "Search", "point": [120.0, 80.0]},
            ],
        },
        features=StateFeatures(conversation_open=True, extras={}),
    )
    rejected = sanitize_decision(
        {"capability": "compose_search_query", "target": ""},
        brief,
    )
    assert not rejected.ok
    assert "wrong_locus:container" in rejected.why or "foreign" in rejected.why.lower()


def test_wrong_patient_locus_still_forbids_substitute():
    state = ExecutionState()
    state.last_surface = "context_menu"
    state.unified_world_document = {
        "surface": "context_menu",
        "objects": [{"text": "Forward", "kind": "menu_item", "enabled": True}],
    }
    c = ensure_commitment_from_menu_observation(
        state,
        label="Forward",
        patient_ref="zarooratwala.com",
        desired_effect="forward_picker",
    )
    assert c is not None
    arm_grounding_recovery(state, c, reason="label_only")
    assert forbids_wrong_locus(state, family="invoke_affordance")


def test_empty_kind_high_cost_filter_fails_closed():
    ok, why = validate_actuation_grounding(
        capability="type_query",
        field_role="",
        label="",
        target_kind="",
    )
    assert not ok
    assert "empty_kind" in why

    brief = ActorBrief(
        gesture="type",
        capability="locate_content",
        field_role="none",
        label="",
        text="zarooratwala",
        point=(400.0, 400.0),
        target_kind="",
    )
    vok, vwhy = validate_brief(brief)
    assert not vok
    assert "empty_kind" in vwhy or "wrong_locus" in vwhy
