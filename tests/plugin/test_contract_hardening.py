"""Architect contract-hardening: frames fail closed, ledger≠eligibility, etc."""

from plugin.agent.composition import compose_domain_adapters
from plugin.agent.executive.intention_frame import (
    AttemptValidity,
    Intention,
    IntentionFrame,
    MethodFrontier,
    MethodSpec,
    MethodStatus,
    begin_attempt,
    close_attempt,
    mark_method_attempted,
    record_method_status,
)
from plugin.agent.identity_evidence.whatsapp import WhatsAppUIEvidenceProvider
from plugin.agent.procedures.forward_message import forward_role_specs, role_for_action_family
from plugin.agent.role_binding import observe_entity
from plugin.perception.coordinate_frame import (
    Grounding,
    GroundingUncertain,
    UnknownCoordinateFrame,
    build_frame_graph,
    ensure_screen_space,
)
from plugin.perception.coverage_quality import ActSufficiency, compute_coverage_quality


def test_capture_image_origin_distinct_from_window_origin():
    g = build_frame_graph(
        image_size=(200.0, 100.0),
        window_origin_in_screen=(50.0, 10.0),
        image_origin_in_window=(12.0, 8.0),
        capture_id="c_roi",
    )
    img = g.get(g.image_frame_id)
    assert img is not None
    assert img.image_origin_in_window == (12.0, 8.0)
    assert img.window_origin_in_screen == (50.0, 10.0)
    assert img.frame_id.startswith("capture:c_roi/")


def test_missing_frame_fails_closed():
    try:
        ensure_screen_space((1.0, 2.0), None, coordinate_space="image", fail_closed=True)
        assert False, "expected GroundingUncertain"
    except (GroundingUncertain, UnknownCoordinateFrame):
        pass


def test_grounding_from_dict_no_silent_screen():
    assert Grounding.from_dict({"point": [1, 2]}) is None
    g = Grounding.from_dict({"point": [1, 2], "coordinate_frame_id": "capture:c1/image"})
    assert g is not None
    assert g.coordinate_frame_id == "capture:c1/image"


def test_inconclusive_attempt_leaves_method_eligible():
    frame = IntentionFrame(
        intention=Intention(id="i1", objective="o", success_predicate="p")
    )
    mid = "reveal_context_click"
    frame.method_frontier = MethodFrontier(
        known_untried=[mid],
        catalog={mid: MethodSpec(id=mid, capability="reveal_actions")},
    )
    mark_method_attempted(frame, mid)
    att = begin_attempt(method_id=mid)
    close_attempt(
        att,
        attempt_validity=AttemptValidity.INCONCLUSIVE_GROUNDING.value,
    )
    record_method_status(frame, mid, MethodStatus.UNTRIED.value)
    assert mid in frame.method_frontier.attempted
    assert mid in frame.method_frontier.eligible_methods()


def test_search_result_row_not_forced_conversation():
    compose_domain_adapters()
    obs = WhatsAppUIEvidenceProvider().observe(
        {
            "kind": "search_result_row",
            "text": "Pallavi - zarooratwala link",
            "id": "r1",
        }
    )
    assert obs.entity_kind != "conversation"
    assert "message" in obs.candidate_entity_kinds or "conversation" in obs.candidate_entity_kinds
    assert obs.ui_role == "search_result_row"


def test_role_binding_has_no_whatsapp_import():
    import plugin.agent.role_binding as rb
    import inspect

    src = inspect.getsource(rb)
    assert "ensure_whatsapp" not in src
    assert "identity_evidence.whatsapp" not in src


def test_forward_role_specs_live_in_procedure():
    specs = forward_role_specs(type("G", (), {"contact": "A", "link_query": "q"})())
    assert "source_container" in specs
    assert role_for_action_family("reveal_actions") == "source_object"


def test_act_sufficiency_not_chrome_scalar():
    q = compute_coverage_quality(
        nodes=[{"role": "AXApplication"}, {"role": "AXWindow"}],
        has_screenshot=True,
        semantic_object_count=0,
    )
    assert not ActSufficiency().satisfied(q)


def test_observe_entity_uses_registered_providers_only():
    compose_domain_adapters()
    obs = observe_entity({"kind": "chat_row", "text": "Alice - hi", "id": "c1"})
    assert obs.entity_kind == "conversation"
