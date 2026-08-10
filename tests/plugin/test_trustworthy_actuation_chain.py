"""Cross-cutting goldens for the trustworthy observation→actuation chain."""

from plugin.agent.capabilities.invoke_affordance import invoke_affordance
from plugin.agent.capabilities.typed_actuators import (
    looks_like_keyboard_chord,
    parse_keyboard_chord,
)
from plugin.agent.executive.intention_frame import (
    AttemptValidity,
    MethodOutcome,
    MethodStatus,
    begin_attempt,
    close_attempt,
)
from plugin.agent.failure_layers import (
    filter_capability_failure_beliefs,
    grounding_uncertain,
)
from plugin.agent.role_binding import RoleBinder
from plugin.perception.coverage_quality import compute_coverage_quality
from plugin.worldmodel.scene.focus import _surface_state_from_view


class _Goal:
    contact = "Pallavi"
    link_query = "zarooratwala"
    target_contact = "Tanmay"


def test_ax_shell_only_not_task_coverage_one():
    q = compute_coverage_quality(
        nodes=[
            {"role": "AXApplication"},
            {"role": "AXWindow"},
            {"role": "unknown"},
        ],
        has_screenshot=True,
        ocr_text_count=0,
        actionable_control_count=0,
    )
    assert q.chrome_only
    assert q.structural_coverage < 0.2
    assert q.task_coverage < 0.5
    assert q.actionable_coverage == 0.0


def test_surface_composition_list_plus_empty_placeholder():
    st = _surface_state_from_view(
        {
            "app": "WhatsApp",
            "screen": "LIST",
            "window_name": "WhatsApp for Mac",
            "visible_contacts": ["Pallavi", "Tanmay"],
            "open_conversation": "",
            "empty_placeholder": True,
        },
        phase="reach_source",
    )
    assert st.sidebar_surface == "list"
    assert st.main_surface == "empty_placeholder"
    assert st.derived_screen_alias() in {"list", "empty_placeholder"}


def test_surface_composition_search_sidebar_with_open_conversation():
    st = _surface_state_from_view(
        {
            "app": "WhatsApp",
            "screen": "SEARCH_RESULTS",
            "search_query": "zarooratwala",
            "visible_contacts": ["Pallavi"],
            "open_conversation": "Pallavi",
        },
        phase="hunt_content",
    )
    assert st.sidebar_surface == "search_results"
    assert st.main_surface == "conversation"


def test_keyboard_chord_never_named_click():
    assert looks_like_keyboard_chord("press_cmd_shift_f")
    chord = parse_keyboard_chord("press_cmd_shift_f")
    assert chord is not None
    assert "command" in chord.keys and "shift" in chord.keys

    class _RT:
        def activate(self, app):
            pass

        def click(self, app, label, *, bounds=None):
            raise AssertionError("must not click a keyboard chord")

    out = invoke_affordance("WhatsApp", "press_cmd_shift_f", _RT())
    assert out.ok is False
    assert out.realization in {"hypothesized_method", "refused_untyped_chord"}
    assert (out.evidence or {}).get("hypothesized_method") is True


def test_attempt_validity_blocks_method_exhaustion():
    att = begin_attempt(method_id="reveal_context_click", intention_id="i_1")
    close_attempt(
        att,
        execution_status="geometry_mismatch",
        method_outcome=MethodOutcome.EFFECT_ABSENT.value,
        attempt_validity=AttemptValidity.INCONCLUSIVE_GROUNDING.value,
    )
    assert not att.may_mark_method_ineffective()
    assert att.method_status == MethodStatus.UNTRIED.value


def test_failure_layers_strip_mouse_blocked_when_geometry_uncertain():
    class ES:
        attempt_validity = "inconclusive_grounding"

    kept = filter_capability_failure_beliefs(
        ["mouse_interaction_blocked", "need_select", "context_menu_opaque"],
        execution_state=ES(),
        evidence={"intended_vs_landed_distance_px": 783},
    )
    assert "mouse_interaction_blocked" not in [k.lower() for k in kept]
    assert grounding_uncertain(ES(), {"intended_vs_landed_distance_px": 783})


def test_provisional_relational_open_for_message_not_brand_row():
    binder = RoleBinder()
    # Brand conversation row: content matches, identity fails → still refused.
    ok, why, _ = binder.action_allowed(
        role="source_container",
        target="ZarooratWala – Fresh Groceries",
        candidate={
            "label": "ZarooratWala – Fresh Groceries",
            "kind": "search_result_row",
            "domain": "whatsapp",
            "text": "zarooratwala.com",
        },
        goal=_Goal(),
        allow_propose=True,
        task_relevance=0.99,
    )
    assert ok is False
    assert why == "identity_contract_unsatisfied"

    # Message/link shaped hit: content match may exploratory-open.
    ok2, why2, _ = binder.action_allowed(
        role="source_object",
        target="https://www.zarooratwala.com/fresh",
        candidate={
            "label": "https://www.zarooratwala.com/fresh",
            "text": "https://www.zarooratwala.com/fresh",
            "kind": "message_with_link",
            "domain": "whatsapp",
            "container": "",
        },
        goal=_Goal(),
        allow_propose=True,
        bindings={},
        task_relevance=0.95,
    )
    assert ok2 is True
    assert why2 == "provisional_relational_open"
