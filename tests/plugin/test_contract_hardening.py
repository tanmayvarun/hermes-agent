"""Architect contract-hardening: frames fail closed, ledger≠eligibility, etc."""

from plugin.agent.actor import ActorBrief, _normalize_to_screen, execute_actor
from plugin.agent.composition import compose_domain_adapters
from plugin.agent.executive.intention_frame import (
    AttemptRecord,
    AttemptValidity,
    Intention,
    IntentionFrame,
    MethodContext,
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
    FrameGraph,
    Grounding,
    GroundingUncertain,
    StaleCoordinateFrame,
    UnknownCoordinateFrame,
    assert_grounding_fresh,
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


def test_naked_geometry_fails_closed_without_legacy_marker():
    pt, _, audit = _normalize_to_screen(
        (450.0, 230.0),
        None,
        coordinate_space="",
        surface=None,
        allow_legacy_geometry=False,
    )
    assert pt is None
    assert audit.get("grounding_uncertain")
    pt2, _, audit2 = _normalize_to_screen(
        (450.0, 230.0),
        None,
        coordinate_space="",
        surface=None,
        allow_legacy_geometry=True,
    )
    assert pt2 == (450.0, 230.0)
    assert audit2.get("legacy_screen_assumption")


def test_image_without_frame_graph_no_legacy_identity():
    pt, _, audit = _normalize_to_screen(
        (450.0, 230.0),
        None,
        coordinate_space="image",
        surface=None,
        allow_legacy_geometry=False,
    )
    assert pt is None
    assert audit.get("grounding_uncertain")


def test_stale_capture_grounding_fails_closed():
    graph_b = build_frame_graph(
        image_size=(200.0, 100.0),
        window_origin_in_screen=(10.0, 20.0),
        capture_id="c_B",
    )
    pt, _, audit = _normalize_to_screen(
        (1200.0, 400.0),
        None,
        coordinate_space="image",
        surface=None,
        frame_id=graph_b.image_frame_id,
        graph=graph_b,
        grounding_capture_id="c_A",
    )
    assert pt is None
    assert audit.get("grounding_uncertain")
    assert audit.get("error_code") in {"stale_coordinate_frame", "grounding_uncertain"}


def test_assert_grounding_fresh_and_validate_for_actuation():
    g = build_frame_graph(
        image_size=(100.0, 100.0),
        window_origin_in_screen=(0.0, 0.0),
        capture_id="c42",
    )
    g.validate_for_actuation()
    assert_grounding_fresh(
        Grounding(coordinate_frame_id=g.image_frame_id, point=(1.0, 2.0), capture_id="c42"),
        g,
    )
    try:
        assert_grounding_fresh(
            Grounding(
                coordinate_frame_id=g.image_frame_id, point=(1.0, 2.0), capture_id="c43"
            ),
            g,
        )
        assert False, "expected StaleCoordinateFrame"
    except StaleCoordinateFrame:
        pass
    # Partially corrupt graph must not validate for actuation.
    bad = FrameGraph(
        frames={g.image_frame_id: g.get(g.image_frame_id)},
        image_frame_id=g.image_frame_id,
        capture_id="c42",
    )
    try:
        bad.validate_for_actuation()
        assert False, "expected incomplete graph refusal"
    except UnknownCoordinateFrame:
        pass


def test_method_frontier_reactivates_on_context_change():
    mid = "context_click"
    fr = MethodFrontier(
        known_untried=[mid],
        catalog={mid: MethodSpec(id=mid, capability="reveal_actions")},
    )
    fr.method_status[mid] = MethodStatus.INEFFECTIVE.value
    fr.ineffective_in_world_signature[mid] = MethodContext(
        surface="conversation", target_selected=False
    ).signature()
    # Without refresh, INEFFECTIVE is not eligible.
    assert mid not in fr.eligible_methods()
    # Context change reactivates to UNTRIED (coherent status+eligibility).
    reactivated = fr.refresh_method_frontier(
        MethodContext(surface="conversation", target_selected=True)
    )
    assert mid in reactivated
    assert fr.status_of(mid) == MethodStatus.UNTRIED.value
    assert mid in fr.eligible_methods()


def test_motor_landing_cannot_redefine_semantic_grounding():
    """Motor landing lives on AttemptRecord only — never mutates object Grounding."""
    semantic = Grounding(
        coordinate_frame_id="capture:c1/image",
        point=(1200.0, 400.0),
        capture_id="c1",
        provenance="perceptor",
        confidence=0.9,
    )
    before = semantic.to_dict()
    att = AttemptRecord(method_id="click", motor_point=[450.0, 230.0])
    # Simulate reflection writing motor landing onto the attempt, not the object.
    assert att.motor_point == [450.0, 230.0]
    assert semantic.to_dict() == before
    assert semantic.point == (1200.0, 400.0)

    class _Motor:
        def click(self, app, label, *, bounds=None):
            # Deliberately wrong landing vs semantic grounding (1200,400).
            return True, "click center=(450.0, 230.0)"

        def context_click(self, app, label, *, bounds=None):
            return True, "ok"

        def hover(self, app, label, *, bounds=None):
            return True, "ok"

        def type_text(self, *a, **k):
            return True, "ok"

        def press_escape(self, app):
            return True, "ok"

        def scroll(self, *a, **k):
            return True, "ok"

    brief = ActorBrief(
        gesture="click",
        app="App",
        point=(1200.0, 400.0),
        bounds=(1188.0, 388.0, 24.0, 24.0),
        label="msg",
        capability="select_content",
        geometry_audit={
            "source_point": [1200.0, 400.0],
            "global_desktop_point": [1200.0, 400.0],
            "capture_id": "c1",
            "grounding_capture_id": "c1",
        },
    )
    # Skip perception confirm by stubbing — motor landing is the subject under test.
    import plugin.agent.actor as actor_mod

    orig = actor_mod._commit_perception_confirm
    actor_mod._commit_perception_confirm = lambda *a, **k: None
    try:
        out = execute_actor(brief, motor=_Motor())
    finally:
        actor_mod._commit_perception_confirm = orig
    # Hard miss may refuse the act; either way semantic grounding must not move.
    assert out.evidence.get("motor_landed_point") == [450.0, 230.0] or (
        out.status == "geometry_mismatch"
        and out.evidence.get("motor_landed_point") == [450.0, 230.0]
    )
    assert brief.point == (1200.0, 400.0)
    assert out.brief["point"] == [1200.0, 400.0]
    assert semantic.point == (1200.0, 400.0)
    assert semantic.to_dict() == before


def test_typed_actuators_dependency_clean():
    import ast
    import inspect
    from plugin.agent.capabilities import typed_actuators as ta

    src = inspect.getsource(ta)
    assert "def looks_like_keyboard_chord" not in src
    assert "def parse_keyboard_chord" not in src
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = str(node.module or "")
            assert "legacy_action_adapter" not in mod
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "legacy_action_adapter" not in alias.name


def test_stale_capture_execute_emits_zero_motor_events():
    class _Motor:
        def __init__(self):
            self.calls = 0

        def click(self, *a, **k):
            self.calls += 1
            return True, "clicked"

    motor = _Motor()
    brief = ActorBrief(
        gesture="click",
        app="App",
        point=(10.0, 20.0),
        bounds=(0.0, 0.0, 24.0, 24.0),
        label="x",
        capability="open_entity",
        geometry_audit={"capture_id": "c_B", "grounding_capture_id": "c_A"},
    )
    import plugin.agent.actor as actor_mod

    orig = actor_mod._commit_perception_confirm
    actor_mod._commit_perception_confirm = lambda *a, **k: None
    try:
        out = execute_actor(brief, motor=motor)
    finally:
        actor_mod._commit_perception_confirm = orig
    assert not out.ok
    assert out.status == "inconclusive_grounding"
    assert motor.calls == 0
    assert out.evidence.get("motor_event_emitted") is False
