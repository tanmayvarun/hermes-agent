"""One-executive consolidation: multimodal SoT, AX settle diagnostic only."""

from __future__ import annotations

from types import SimpleNamespace

from plugin.agent.controller import (
    _META_PREEMPTS,
    _awaiting_verification,
    _clear_post_action_reperceive_if_fresh,
    _last_action_surprised,
    _note_post_action_reperceive,
    _post_action_look_unpaid,
)
from plugin.agent.executive.meta_action import MetaAction, MetaContext, select_meta_action
from plugin.agent.runtime.state import ExecutionState


def test_verify_does_not_preempt_brain():
    assert MetaAction.PERCEIVE not in _META_PREEMPTS


def test_ax_settle_regression_does_not_surprise_executive():
    state = ExecutionState()
    state.last_action = "open_entity"
    state.last_attribution = {
        "outcome": "regression",
        "effect_kind": "regression",
        "belief_authority": "ax_settle_diagnostic",
        "evidence": {
            "executor_ok": True,
            "open_before": "Q Search|",
            "open_after": "Q Search|",
        },
    }
    assert not _last_action_surprised(state)


def test_post_act_flag_requires_executive_look():
    state = ExecutionState()
    state.last_action = "open_entity"
    state.must_executive_reperceive = True
    assert _awaiting_verification(state)


def test_post_act_look_clears_even_when_open_unchanged():
    """ComposeSearchQuery keeps search chrome open — still owe only one fresh look."""
    runtime = SimpleNamespace(execution_state=ExecutionState())
    _note_post_action_reperceive(
        runtime,
        open_conversation="• Search|",
        state_sig="sig-before",
    )
    assert _awaiting_verification(runtime.execution_state)
    assert not _clear_post_action_reperceive_if_fresh(
        runtime,
        multimodal_ok=True,
        proposal_model="phash_reuse",
        open_conversation="• Search|",
        state_sig="sig-before",
    )
    assert _awaiting_verification(runtime.execution_state)
    assert _clear_post_action_reperceive_if_fresh(
        runtime,
        multimodal_ok=True,
        proposal_model="qwen3.5:4b",
        open_conversation="• Search|",
        state_sig="sig-before",
    )
    assert not _awaiting_verification(runtime.execution_state)


def test_surprise_meta_is_reflect_not_verify_skip():
    choice = select_meta_action(
        MetaContext(
            awaiting_verification=True,
            last_action_surprised=True,
            has_grounded_action=True,
        )
    )
    assert choice.action is MetaAction.PERCEIVE
    assert MetaAction.PERCEIVE not in _META_PREEMPTS


def test_new_act_resets_surprise_relook_budget():
    """Fresh motor act must not inherit a spent relook cap (live 024346 deadlock)."""
    runtime = SimpleNamespace(execution_state=ExecutionState())
    runtime.execution_state.consecutive_surprise_relooks = 99
    _note_post_action_reperceive(runtime, open_conversation="Pallavi", state_sig="sig")
    assert runtime.execution_state.consecutive_surprise_relooks == 0
    assert _awaiting_verification(runtime.execution_state)
    # With budget restored, meta schedules the owed look instead of IG.
    choice = select_meta_action(
        MetaContext(
            awaiting_verification=True,
            last_action_surprised=False,
            reperception_exhausted=False,
            branch_stale=True,
            has_grounded_action=True,
        )
    )
    assert choice.action is MetaAction.PERCEIVE


def test_post_act_debt_forces_perceive_even_when_relooks_exhausted():
    """Live 033711: exhaustion must not waive unpaid post-act re-perceive."""
    from plugin.agent.executive.hierarchy import decision_ladder

    spent_but_unpaid = MetaContext(
        awaiting_verification=True,
        post_action_look_owed=True,
        last_action_surprised=False,
        reperception_exhausted=True,
        branch_stale=True,
        has_grounded_action=True,
    )
    assert select_meta_action(spent_but_unpaid).action is MetaAction.PERCEIVE
    assert decision_ladder(spent_but_unpaid).action is MetaAction.PERCEIVE


def test_post_act_look_unpaid_is_only_the_act_reperceive_debt():
    """Surprise alone is awaiting_verification; unpaid post-act is the hard gate."""
    state = ExecutionState()
    state.last_action = "compose_search_query"
    state.last_attribution = {
        "belief_authority": "motor",
        "effect_kind": "no_transition",
        "outcome": "no_effect",
    }
    assert _awaiting_verification(state)
    assert not _post_action_look_unpaid(state)
    state.post_action_reperceive_pending = True
    assert _post_action_look_unpaid(state)


def test_no_visible_change_pays_post_act_reperceive_debt():
    """Post-act pixel-delta look is a finished re-perceive; idle phash_reuse is not."""
    runtime = SimpleNamespace(execution_state=ExecutionState())
    _note_post_action_reperceive(runtime, open_conversation="Pallavi", state_sig="sig")
    assert _post_action_look_unpaid(runtime.execution_state)
    assert not _clear_post_action_reperceive_if_fresh(
        runtime,
        multimodal_ok=True,
        proposal_model="phash_reuse",
    )
    assert _post_action_look_unpaid(runtime.execution_state)
    assert _clear_post_action_reperceive_if_fresh(
        runtime,
        multimodal_ok=True,
        proposal_model="no_visible_change",
    )
    assert not _post_action_look_unpaid(runtime.execution_state)


def test_assess_reads_post_act_flags_as_hard_look_debt():
    """Execution-state post-act flags must reach meta even if caller omits them."""
    from plugin.agent.executive.sync import assess_executive_judgement

    class _Chooser:
        def choose(self, system, packet):
            return {"meta_action": "act", "why": "skip look", "confidence": 0.9}

    state = ExecutionState()
    state.post_action_reperceive_pending = True
    state.must_executive_reperceive = True
    state.consecutive_surprise_relooks = 99  # would exhaust surprise relooks
    _suff, meta = assess_executive_judgement(
        state,
        has_grounded_action=True,
        awaiting_verification=True,
        last_action_surprised=False,
        meta_chooser=_Chooser(),
    )
    assert meta.action is MetaAction.PERCEIVE
    assert "relook owed" in (meta.reason or "") or meta.scores.get("must_reperceive") == 1.0


def test_assess_reads_streak_budgets_so_loop_need_not_rewrite_meta():
    """IG exhaustion on a stale branch: LLM may ACT; loop must not rewrite meta."""
    from plugin.agent.executive.sync import assess_executive_judgement

    class _Chooser:
        def choose(self, system, packet):
            # Chooser sees exhausted IG budget and picks act.
            assert packet["budgets"]["information_gathering_exhausted"] is True
            return {"meta_action": "act", "why": "retreat budget spent", "confidence": 0.9}

    state = ExecutionState()
    state.consecutive_information_gathering = 99
    _suff, meta = assess_executive_judgement(
        state,
        has_grounded_action=True,
        previously_suppressed=True,  # branch_stale
        meta_chooser=_Chooser(),
    )
    assert meta.action is MetaAction.ACT
    assert meta.scores.get("source") == "llm"
