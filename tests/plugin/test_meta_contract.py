"""v1 executive meta contracts — eight core kinds + universal envelope."""

from __future__ import annotations

from plugin.agent.executive.meta_action import CORE_META_ACTION_VALUES, MetaAction
from plugin.agent.executive.meta_contract import (
    CORE_META_KINDS,
    DecisionProblem,
    MetaActionRequest,
    MetaActionResult,
    MetaResultStatus,
    ScopeRef,
    canonicalize_meta_kind,
    category_of,
    core_meta_action_values,
    decision_problem_from_meta_context,
    is_core_meta,
)
from plugin.agent.executive.meta_action import MetaContext


def test_meta_action_enum_is_exactly_eight():
    assert {a.value for a in MetaAction} == set(CORE_META_ACTION_VALUES)
    assert len(MetaAction) == 8
    assert CORE_META_KINDS == set(MetaAction)


def test_legacy_tokens_rejected():
    for token in (
        "probe",
        "verify",
        "ask_user",
        "reflect",
        "information_gathering",
        "backtrack",
    ):
        assert canonicalize_meta_kind(token) is None


def test_core_tokens_parse():
    for value in core_meta_action_values():
        assert canonicalize_meta_kind(value) is MetaAction(value)
        assert is_core_meta(value)


def test_categories():
    assert category_of(MetaAction.SEARCH).value == "epistemic"
    assert category_of(MetaAction.ACT).value == "instrumental"
    assert category_of(MetaAction.WAIT).value == "control"


def test_envelope_roundtrip():
    req = MetaActionRequest(
        kind=MetaAction.SEARCH,
        motivation="resolve referent",
        expected_result="ranked candidates",
        success_condition="chosen or exhausted",
        scope=ScopeRef(domain="application_ui", locator={"app": "WhatsApp"}),
    )
    d = req.to_dict()
    assert d["kind"] == "search"
    assert d["category"] == "epistemic"
    assert d["motivation"]
    res = MetaActionResult(status=MetaResultStatus.PARTIAL, confidence=0.4)
    assert res.to_dict()["status"] == "partial"


def test_decision_problem_in_packet_shape():
    ctx = MetaContext(referent_search_needed=True, search_has_criteria=True)
    dp = decision_problem_from_meta_context(ctx, phase="reach_source")
    assert isinstance(dp, DecisionProblem)
    out = dp.to_dict()
    assert "selection_semantics" in out
    assert "search" in out["available_meta_actions"]
