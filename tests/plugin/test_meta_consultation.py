"""LLM meta-action choice: always-on inference, sanitize contracts, assess wiring."""

from __future__ import annotations

from plugin.agent.consultation_routing import is_vision_task, resolve_reasoning_route
from plugin.agent.executive.meta_action import MetaAction, MetaContext
from plugin.agent.executive.meta_consultation import (
    meta_context_packet,
    resolve_meta_choice,
    sanitize_meta_choice,
)
from plugin.agent.executive.sufficiency import SufficiencyInputs, assess_sufficiency
from plugin.agent.runtime.state import ExecutionState


def _suff(**kwargs):
    return assess_sufficiency(SufficiencyInputs(**kwargs))


class _StubMetaChooser:
    def __init__(self, payload, *, repair_payload=None):
        self.payload = payload
        self.repair_payload = repair_payload
        self.calls = 0
        self.packets = []

    def choose(self, system: str, packet: dict):
        self.calls += 1
        self.packets.append(packet)
        self.last_packet = packet
        if packet.get("rejected_choice") and self.repair_payload is not None:
            return dict(self.repair_payload)
        return dict(self.payload)


def test_meta_choice_usecase_routes_to_decision_text_stack():
    msgs = [
        {"role": "system", "content": "Choose meta."},
        {"role": "user", "content": "Choose the next meta-action."},
    ]
    route = resolve_reasoning_route("perception", msgs, usecase="meta_choice")
    assert not is_vision_task(route.task)
    assert route.task == "decision"
    assert route.modality.value == "text"


def test_sanitize_forces_perceive_when_post_act_look_owed():
    ctx = MetaContext(
        post_action_look_owed=True,
        awaiting_verification=True,
        has_grounded_action=True,
        last_action_surprised=False,
    )
    choice = sanitize_meta_choice(
        {"meta_action": "act", "why": "commit", "confidence": 0.9},
        ctx,
    )
    assert choice is not None
    assert choice.action is MetaAction.PERCEIVE
    assert choice.scores.get("source") == "llm_contract"


def test_sanitize_does_not_override_exhausted_think():
    """Budgets are advisory — LLM THINK stands even when think_exhausted."""
    ctx = MetaContext(think_exhausted=True, ambiguous=True)
    choice = sanitize_meta_choice({"meta_action": "think", "why": "ponder"}, ctx)
    assert choice is not None
    assert choice.action is MetaAction.THINK
    assert choice.scores.get("source") == "llm"


def test_resolve_always_invokes_chooser():
    chooser = _StubMetaChooser(
        {"meta_action": "act", "why": "grounded move ready", "confidence": 0.8}
    )
    ctx = MetaContext(
        sufficiency=_suff(has_grounded_action=True),
        has_grounded_action=True,
    )
    choice = resolve_meta_choice(ctx, chooser=chooser)
    assert chooser.calls == 1
    assert choice.action is MetaAction.ACT
    assert choice.scores.get("source") == "llm"
    packet = chooser.last_packet
    assert packet["evidence"]["has_grounded_action"] is True
    assert "look_debt" in packet and "budgets" in packet


def test_resolve_never_uses_ladder_on_llm_failure():
    class _Boom:
        def choose(self, system, packet):
            raise RuntimeError("no model")

    choice = resolve_meta_choice(MetaContext(), chooser=_Boom())
    assert choice.action is MetaAction.ASK
    assert choice.scores.get("source") == "llm_failed"
    assert "ladder" not in (choice.reason or "").lower()


def test_resolve_repairs_unknown_meta_via_second_llm_call():
    chooser = _StubMetaChooser(
        {"meta_action": "not_a_real_meta", "why": "oops", "confidence": 0.5},
        repair_payload={"meta_action": "act", "why": "commit", "confidence": 0.9},
    )
    ctx = MetaContext(
        has_grounded_action=True,
        sufficiency=_suff(has_grounded_action=True),
    )
    choice = resolve_meta_choice(ctx, chooser=chooser)
    assert chooser.calls == 2
    assert choice.action is MetaAction.ACT
    assert choice.scores.get("repaired") == 1.0


def test_sanitize_does_not_force_ask_user_on_hard_block():
    """hard_block is a packet signal; LLM ACT is not rewritten to ASK_USER."""
    choice = sanitize_meta_choice(
        {"meta_action": "act", "why": "try anyway", "confidence": 0.8},
        MetaContext(hard_block=True, has_grounded_action=True),
    )
    assert choice is not None
    assert choice.action is MetaAction.ACT


def test_meta_packet_has_mined_sections():
    from plugin.agent.executive.meta_situation import (
        META_PACKET_REQUIRED_SECTIONS,
        MetaSituation,
    )

    packet = meta_context_packet(
        MetaContext(
            sufficiency=_suff(has_grounded_action=True),
            has_grounded_action=True,
            post_action_look_owed=False,
        ),
        situation=MetaSituation(
            cognitive_mode="deliberative",
            mode_triggers=["branch_exhausted"],
            static_streak=2,
            evidence_gaps=["target geometry"],
        ),
    )
    for section in META_PACKET_REQUIRED_SECTIONS:
        assert section in packet, section
    assert packet["search"]["mode_triggers"] == ["branch_exhausted"]
    assert packet["evidence"]["evidence_gaps"] == ["target geometry"]


def test_assess_uses_injected_meta_chooser():
    from plugin.agent.executive.sync import assess_executive_judgement

    chooser = _StubMetaChooser(
        {"meta_action": "explore", "why": "reveal hidden control", "confidence": 0.7}
    )
    state = ExecutionState()
    _suff_v, meta = assess_executive_judgement(
        state,
        has_grounded_action=False,
        probe_available=True,
        meta_chooser=chooser,
    )
    assert chooser.calls == 1
    assert meta.action is MetaAction.EXPLORE
    assert state.last_meta_action == "explore"


def test_assess_llm_ask_user_not_replaced_by_scorer():
    """LLM ASK_USER must win over a scorer that would ACT."""
    from plugin.agent.executive.meta_action import MetaChoice
    from plugin.agent.executive.sync import assess_executive_judgement

    monkey_scorer = lambda ctx: MetaChoice(
        MetaAction.ACT, "scorer would act", {"act": 1.0}
    )
    import plugin.agent.executive.meta_action as meta_mod

    # Patch via assess's import path: select_meta_action is imported inside assess.
    chooser = _StubMetaChooser(
        {"meta_action": "ask", "why": "no self-serve route", "confidence": 0.9}
    )
    original = meta_mod.select_meta_action
    meta_mod.select_meta_action = monkey_scorer
    try:
        _suff_v, meta = assess_executive_judgement(
            ExecutionState(), has_grounded_action=False, meta_chooser=chooser
        )
    finally:
        meta_mod.select_meta_action = original
    assert meta.action is MetaAction.ASK
    assert chooser.calls == 1


def test_controller_does_not_preseed_hard_block_from_backtrack():
    """Smell removed: backtrack exhaustion must not inject hard_block=True."""
    import ast
    from pathlib import Path

    src = Path(__file__).resolve().parents[2] / "plugin/agent/controller.py"
    tree = ast.parse(src.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "hard_block":
                    raise AssertionError(
                        "controller still assigns hard_block — pre-seed smell returned"
                    )


def test_no_hermes_meta_llm_flag_in_meta_consultation():
    from pathlib import Path

    import plugin.agent.executive.meta_consultation as mod

    assert not hasattr(mod, "meta_llm_enabled")
    text = Path(mod.__file__).read_text(encoding="utf-8")
    assert "HERMES_META_LLM" not in text
    assert "ladder_fallback" not in text
    assert "import decision_ladder" not in text
    assert "from plugin.agent.executive.hierarchy import decision_ladder" not in text


def test_meta_packet_exposes_streak_budgets_not_hard_block_seed():
    packet = meta_context_packet(
        MetaContext(
            backtrack_exhausted=True,
            has_grounded_action=False,
            hard_block=False,
        )
    )
    assert packet["budgets"]["backtrack_exhausted"] is True
    assert packet["search"]["hard_block"] is False


def test_sanitize_incomplete_reveal_forces_explore_not_act():
    choice = sanitize_meta_choice(
        {"meta_action": "act", "why": "click content again", "confidence": 0.95},
        MetaContext(
            incomplete_reveal=True,
            route_discovery_owed=True,
            retrieve_ready=True,
            address_known=True,
            has_grounded_action=True,
        ),
    )
    assert choice is not None
    assert choice.action is MetaAction.EXPLORE
    assert choice.scores.get("source") == "llm_contract"


def test_sanitize_route_discovery_blocks_research():
    choice = sanitize_meta_choice(
        {"meta_action": "search", "why": "hunt again", "confidence": 0.8},
        MetaContext(route_discovery_owed=True, expected_overlay_missing=True),
    )
    assert choice is not None
    assert choice.action is MetaAction.EXPLORE


def test_retrieve_ready_still_acts_when_route_not_owed():
    choice = sanitize_meta_choice(
        {"meta_action": "search", "why": "find", "confidence": 0.8},
        MetaContext(retrieve_ready=True, address_known=True, search_has_criteria=True),
    )
    assert choice is not None
    assert choice.action is MetaAction.ACT


def test_sanitize_referent_repair_forces_act_not_explore():
    choice = sanitize_meta_choice(
        {"meta_action": "explore", "why": "look around", "confidence": 0.9},
        MetaContext(
            referent_repair_owed=True,
            incomplete_reveal=False,
            route_discovery_owed=False,
            has_grounded_action=True,
        ),
    )
    assert choice is not None
    assert choice.action is MetaAction.ACT
    assert choice.scores.get("source") == "llm_contract"
    assert choice.scores.get("referent_repair") == 1.0


def test_select_meta_referent_repair_hard_returns_act():
    from plugin.agent.executive.meta_action import select_meta_action

    choice = select_meta_action(
        MetaContext(
            referent_repair_owed=True,
            has_grounded_action=True,
            route_discovery_owed=True,
            incomplete_reveal=True,
        )
    )
    assert choice.action is MetaAction.ACT
    assert "referent repair" in choice.reason.lower()
