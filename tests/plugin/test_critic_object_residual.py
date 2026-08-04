"""The object inventory is held to the residual discipline, like the scalars.

The critic merges a reading as x + Δx: the carried document survives by default
and the delta must earn entry. That discipline covered surface, open_conversation
and the focused field role -- and waved ``objects`` through with the reason
"proposal provided soft content". The inventory is the part carrying the geometry
the agent clicks, so it was the one delta capable of doing real damage and the
only one nothing examined.

Between two consecutive micro-actions the visible contents cannot turn over
completely unless something caused it: the surface changed, the viewport moved, or
a filter was applied. These tests pin that rule, and pin the two directions it can
fail: waving through a fabricated screen, and refusing a real one.
"""

from __future__ import annotations

from plugin.agent.world_critic import (
    ObjectDelta,
    critique_world_proposal,
    diff_object_inventories,
    inventory_rewrite_is_explained,
)


def _rows(*names: str) -> list:
    return [{"id": f"row_{i}", "kind": "chat_row", "text": name} for i, name in enumerate(names)]


CHAT_LIST = _rows("Kulvinder Ji", "Zarooratwala Orders", "Pallavi", "Mum", "Work Group")
DIFFERENT_LIST = _rows("Alpha Co", "Beta Ltd", "Gamma Inc", "Delta LLC", "Epsilon SA")


def _decision(verdict, field: str):
    return next((d for d in verdict.decisions if d.field == field), None)


# ------------------------------------------------------------------- the diff


def test_the_diff_is_taken_on_visible_text_not_model_ids():
    """Ids are regenerated every frame, so comparing them reports a total rewrite
    on every single look."""
    before = [{"id": "a1", "text": "Kulvinder Ji"}, {"id": "a2", "text": "Pallavi"}]
    after = [{"id": "z9", "text": "Kulvinder Ji"}, {"id": "z8", "text": "Pallavi"}]
    delta = diff_object_inventories(before, after)
    assert delta.persisted == ["kulvinder ji", "pallavi"]
    assert delta.appeared == []
    assert delta.churn == 0.0


def test_the_diff_reports_what_arrived_and_left():
    delta = diff_object_inventories(_rows("A", "B", "C"), _rows("B", "C", "D"))
    assert delta.appeared == ["d"]
    assert delta.disappeared == ["a"]
    assert delta.persisted == ["b", "c"]


def test_an_empty_prior_inventory_has_no_churn():
    delta = diff_object_inventories([], _rows("A", "B"))
    assert delta.churn == 0.0
    assert delta.replacement == 1.0


# --------------------------------------------------------- what counts as drift


def test_ordinary_drift_is_explained_for_free():
    """A row or two changing is the common case and must cost nothing."""
    delta = diff_object_inventories(CHAT_LIST, _rows("Kulvinder Ji", "Zarooratwala Orders", "Pallavi", "Mum", "New Person"))
    explained, why = inventory_rewrite_is_explained(delta, surface_changed=False, last_action="observe")
    assert explained
    assert "drift" in why


def test_a_small_inventory_is_not_judged_by_ratio():
    """Two rows becoming two different rows is 100% churn and means nothing."""
    delta = diff_object_inventories(_rows("A", "B"), _rows("C", "D"))
    explained, why = inventory_rewrite_is_explained(delta, surface_changed=False, last_action="observe")
    assert explained
    assert "worth comparing" in why


def test_a_changed_surface_explains_a_new_inventory():
    delta = diff_object_inventories(CHAT_LIST, DIFFERENT_LIST)
    explained, why = inventory_rewrite_is_explained(delta, surface_changed=True, last_action="open_entity")
    assert explained
    assert "surface changed" in why


def test_scrolling_explains_a_new_inventory_on_the_same_surface():
    delta = diff_object_inventories(CHAT_LIST, DIFFERENT_LIST)
    explained, _ = inventory_rewrite_is_explained(delta, surface_changed=False, last_action="scroll_conversation")
    assert explained


def test_typing_a_query_explains_a_refiltered_list():
    delta = diff_object_inventories(CHAT_LIST, DIFFERENT_LIST)
    explained, _ = inventory_rewrite_is_explained(delta, surface_changed=False, last_action="type_query")
    assert explained


def test_a_wholesale_rewrite_after_merely_looking_is_not_explained():
    """The failure this guards: a reading that replaces the screen with a
    different screen, after an action that could not have changed it."""
    delta = diff_object_inventories(CHAT_LIST, DIFFERENT_LIST)
    explained, why = inventory_rewrite_is_explained(delta, surface_changed=False, last_action="observe")
    assert not explained
    assert "no action to explain it" in why


# ----------------------------------------------------------- through the critic


def test_the_critic_keeps_the_prior_inventory_on_an_unexplained_rewrite():
    verdict = critique_world_proposal(
        {"surface": "chat_list", "objects": CHAT_LIST},
        {"surface": "chat_list", "objects": DIFFERENT_LIST},
        last_action="observe",
    )
    decision = _decision(verdict, "objects")
    assert decision is not None and decision.verdict == "reject"
    # x survives; this Δx did not earn the right to replace it.
    assert verdict.accepted_document["objects"] == CHAT_LIST


def test_the_critic_accepts_a_rewrite_the_action_accounts_for():
    verdict = critique_world_proposal(
        {"surface": "chat_list", "objects": CHAT_LIST},
        {"surface": "chat_list", "objects": DIFFERENT_LIST},
        last_action="type_query",
    )
    decision = _decision(verdict, "objects")
    assert decision is not None and decision.verdict == "accept"
    assert verdict.accepted_document["objects"] == DIFFERENT_LIST


def test_a_first_reading_is_never_incoherent():
    """With nothing carried forward there is no residual to violate."""
    verdict = critique_world_proposal(
        {}, {"surface": "chat_list", "objects": CHAT_LIST}, last_action=""
    )
    assert verdict.accepted_document["objects"] == CHAT_LIST


# ------------------------------------------------------------- the appeal court


def test_the_judge_can_overrule_a_deterministic_refusal():
    """The rules detect an unaccounted change; only judgement can weigh it.

    A refusal the rules got wrong strands the agent on a stale picture, so the
    judge must be able to let a real change through.
    """
    asked = {}

    def _judge(*, prior, proposed, delta, surface, prior_surface, last_action):
        asked.update({"last_action": last_action, "churn": delta.churn})
        return True, "the app refreshed the list on its own"

    verdict = critique_world_proposal(
        {"surface": "chat_list", "objects": CHAT_LIST},
        {"surface": "chat_list", "objects": DIFFERENT_LIST},
        last_action="observe",
        coherence_judge=_judge,
    )
    decision = _decision(verdict, "objects")
    assert decision is not None and decision.verdict == "accept"
    assert decision.reason == "the app refreshed the list on its own"
    assert verdict.accepted_document["objects"] == DIFFERENT_LIST
    assert asked["last_action"] == "observe"
    assert asked["churn"] == 1.0


def test_the_judge_can_confirm_a_refusal_with_its_own_reason():
    def _judge(**_kwargs):
        return False, "nothing about looking at a screen replaces every row"

    verdict = critique_world_proposal(
        {"surface": "chat_list", "objects": CHAT_LIST},
        {"surface": "chat_list", "objects": DIFFERENT_LIST},
        last_action="observe",
        coherence_judge=_judge,
    )
    decision = _decision(verdict, "objects")
    assert decision is not None and decision.verdict == "reject"
    assert "replaces every row" in decision.reason


def test_the_judge_is_not_consulted_for_an_ordinary_frame():
    """Latency is the binding constraint, so the common case must not pay."""
    calls = []

    def _judge(**kwargs):
        calls.append(1)
        return True, ""

    critique_world_proposal(
        {"surface": "chat_list", "objects": CHAT_LIST},
        {"surface": "chat_list", "objects": CHAT_LIST},
        last_action="observe",
        coherence_judge=_judge,
    )
    assert not calls


def test_a_failing_judge_leaves_the_rules_in_charge():
    """A broken judge must not be the reason a reading is refused."""

    def _judge(**_kwargs):
        raise RuntimeError("provider down")

    verdict = critique_world_proposal(
        {"surface": "chat_list", "objects": CHAT_LIST},
        {"surface": "chat_list", "objects": DIFFERENT_LIST},
        last_action="observe",
        coherence_judge=_judge,
    )
    decision = _decision(verdict, "objects")
    assert decision is not None and decision.verdict == "reject"


# ------------------------------------------------- the surface table on appeal


def test_a_refused_surface_jump_can_be_allowed_on_appeal():
    """SURFACE_PARENTS is one app's topology typed by hand.

    Its refusals conflate "this cannot happen" with "nobody wrote this edge
    down", and only the first is a real incoherence. The second silently discards
    a correct reading, and cannot generalise past WhatsApp.
    """
    asked = {}

    def _surface_judge(*, prior_surface, proposed_surface, last_action, rule_reason=""):
        asked.update(
            {"from": prior_surface, "to": proposed_surface, "rule_reason": rule_reason}
        )
        return True, "a forward picker can be reached directly from a chat list here"

    verdict = critique_world_proposal(
        {"surface": "chat_list"},
        {"surface": "forward_picker"},
        last_action="observe",
        surface_judge=_surface_judge,
    )
    decision = _decision(verdict, "surface")
    assert decision is not None and decision.verdict == "accept"
    assert verdict.surface == "forward_picker"
    assert asked["from"] == "chat_list" and asked["to"] == "forward_picker"
    # The judge is told why the table refused, so it can weigh that reasoning.
    assert asked["rule_reason"]


def test_a_refused_surface_jump_stays_refused_when_the_judge_agrees():
    def _surface_judge(**_kwargs):
        return False, "nothing about looking at a list opens a forward picker"

    verdict = critique_world_proposal(
        {"surface": "chat_list"},
        {"surface": "forward_picker"},
        last_action="observe",
        surface_judge=_surface_judge,
    )
    decision = _decision(verdict, "surface")
    assert decision is not None and decision.verdict == "reject"
    assert verdict.surface == "chat_list"


def test_a_legal_transition_never_reaches_the_surface_judge():
    """The table keeps its cheap accepts; only refusals cost a call."""
    calls = []

    def _surface_judge(**_kwargs):
        calls.append(1)
        return True, ""

    critique_world_proposal(
        {"surface": "chat_list"},
        {"surface": "search"},
        last_action="type_query",
        surface_judge=_surface_judge,
    )
    assert not calls


def test_a_surface_outside_the_vocabulary_is_not_appealable():
    """Vocabulary is a contract, not a topology guess.

    A surface outside the enum has no field role, no revealed-surface semantics
    and no phase mapping downstream, so admitting one on appeal would hand those
    consumers a value they cannot interpret.
    """
    calls = []

    def _surface_judge(**_kwargs):
        calls.append(1)
        return True, "looks fine to me"

    verdict = critique_world_proposal(
        {"surface": "chat_list"},
        {"surface": "some_invented_surface"},
        last_action="observe",
        surface_judge=_surface_judge,
    )
    assert not calls
    assert verdict.surface == "chat_list"


def test_the_judge_is_off_by_default():
    """It costs a model call, so an offline test must never reach for one."""
    from plugin.agent.critic_coherence import coherence_judge_enabled, judge_for_critic

    assert coherence_judge_enabled() is False
    assert judge_for_critic() is None


def test_the_judge_is_available_when_turned_on(monkeypatch):
    from plugin.agent.critic_coherence import coherence_judge_enabled, judge_for_critic

    monkeypatch.setenv("HERMES_CRITIC_COHERENCE", "1")
    assert coherence_judge_enabled() is True
    assert callable(judge_for_critic())


def test_an_unavailable_provider_accepts_rather_than_stalls(monkeypatch):
    """The judge is an appeal against a refusal, so its own failure must not
    leave the agent worse off than before it existed."""
    from plugin.agent import critic_coherence, reasoning_consultation

    def _down(*_args, **_kwargs):
        raise RuntimeError("provider down")

    # Patched where the judge imports it from, so no call is attempted.
    monkeypatch.setattr(reasoning_consultation, "consult_reasoning", _down)
    explained, why = critic_coherence.judge_inventory_rewrite(
        prior={"objects": CHAT_LIST},
        proposed={"objects": DIFFERENT_LIST},
        delta=ObjectDelta(prior_count=5, proposed_count=5, disappeared=["a"] * 5, appeared=["b"] * 5),
        surface="chat_list",
        prior_surface="chat_list",
        last_action="observe",
        timeout_s=0.001,
    )
    assert explained is True
    assert "unjudged" in why
