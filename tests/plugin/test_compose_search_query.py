"""compose_search_query authors strings — it must not hardcode query templates."""

from __future__ import annotations

from typing import Any, Dict

from plugin.agent.capabilities.compose_search_query import (
    SearchQueryBrief,
    author_query_for_goal,
    compose_search_query,
    goal_evidence_tokens,
    is_bare_entity_query,
    query_looks_corrupted,
    ui_shows_no_search_results,
)
from plugin.agent.capabilities.dispatch import can_dispatch, dispatch
from plugin.agent.capabilities.base import CapabilityRequest
from plugin.agent.capabilities.catalog import realized_verbs
from plugin.agent.features import StateFeatures
from plugin.agent.goal import Goal
from plugin.agent.unified_cognition import proposal_to_action, UnifiedProposal
from plugin.worldmodel.model import WorldModel


class _FakeAuthor:
    """Returns a judgment that is *not* ``contact + link_query`` concatenation."""

    def __init__(self, chosen: str) -> None:
        self.chosen = chosen
        self.packets: list[Dict[str, Any]] = []

    def author(self, system: str, user_packet: Dict[str, Any]) -> Dict[str, Any]:
        self.packets.append(user_packet)
        assert "evidence_tokens" in user_packet
        # Capability must not tell the author to use a fixed template.
        assert "contact +" not in system.lower()
        assert "link_query" not in system.lower() or "template" not in system.lower()
        return {
            "queries": [{"q": self.chosen, "why": "disambiguate from evidence"}],
            "chosen": self.chosen,
        }


def _goal() -> Goal:
    return Goal(
        kind="whatsapp_forward_message",
        contact="Pallavi",
        target_contact="Tanmay",
        link_query="zarooratwala",
    )


def test_compose_is_realized_in_catalog():
    assert "compose_search_query" in realized_verbs()
    assert can_dispatch("compose_search_query")


def test_goal_evidence_tokens_are_a_bag_not_a_joined_query():
    tokens = goal_evidence_tokens(_goal())
    assert "Pallavi" in tokens
    assert "zarooratwala" in tokens
    # Bag is goal evidence only — do not inject invented intent labels.
    assert "link" not in {t.lower() for t in tokens}
    # No single pre-joined template string is required to be present.
    assert "Pallavi zarooratwala" not in tokens


def test_compose_uses_author_judgment_not_contact_link_join():
    author = _FakeAuthor(chosen="zarooratwala Pallavi groceries")
    outcome = compose_search_query(
        SearchQueryBrief(goal_tokens=goal_evidence_tokens(_goal()), goal_kind="whatsapp_forward_message"),
        author=author,
    )
    assert outcome.ok
    assert outcome.evidence["chosen"] == "zarooratwala Pallavi groceries"
    # Production must not have forced the classic join.
    assert outcome.evidence["chosen"] != "Pallavi zarooratwala"
    assert author.packets[0]["evidence_tokens"]


def test_dispatch_compose_passes_goal_evidence():
    author = _FakeAuthor(chosen="pallavi invoice groceries")
    outcome = dispatch(
        CapabilityRequest(
            name="compose_search_query",
            app="WhatsApp",
            extras={"goal": _goal(), "author": author, "world_document": {"surface": "chat_list"}},
        ),
        overlay=object(),
    )
    assert outcome.ok
    assert outcome.evidence["chosen"] == "pallavi invoice groceries"


def test_bare_entity_query_detection():
    g = _goal()
    assert is_bare_entity_query("Pallavi", g)
    assert is_bare_entity_query("Tanmay", g)
    assert not is_bare_entity_query("Pallavi zarooratwala", g)
    assert not is_bare_entity_query("zarooratwala", g)


def test_starved_open_entity_on_visible_row_stays_open_entity():
    """A visible chat row carries a click point; AX starvation does not turn the
    model's open_entity into a composed search. Click what you see."""
    world = WorldModel(active_app="WhatsApp")
    features = StateFeatures(extras={"app_content_node_count": 0})
    proposal = UnifiedProposal(
        observed_state={"surface": "chat_list"},
        next_action={
            "family": "open_entity",
            "text": "Pallavi",
            "target_point": [120, 200],
            "confidence": 0.95,
        },
        confidence=0.95,
    )
    action, reason = proposal_to_action(proposal, _goal(), world, features)
    assert reason == "admissible"
    assert action is not None
    assert action.action_family == "open_entity"
    assert action.grounding_reason == "unified_multimodal"


def test_author_query_for_goal_helper():
    author = _FakeAuthor(chosen="custom authored")
    assert author_query_for_goal(_goal(), author=author) == "custom authored"


def test_llm_query_author_uses_decision_not_perception(monkeypatch):
    """032207 regression: authorship must not call the vision perception pin."""
    from types import SimpleNamespace

    from plugin.agent.capabilities.compose_search_query import LlmQueryAuthor

    seen: dict[str, object] = {}

    def fake_consult(task, messages, **kwargs):
        seen["task"] = task
        seen["usecase"] = kwargs.get("usecase")
        return SimpleNamespace(
            parsed={"chosen": "zarooratwala Pallavi", "queries": [{"q": "zarooratwala Pallavi"}]},
            raw_response='{"chosen":"zarooratwala Pallavi"}',
        )

    monkeypatch.setattr(
        "plugin.agent.reasoning_consultation.consult_reasoning",
        fake_consult,
    )

    payload = LlmQueryAuthor(timeout_s=5).author(
        "system",
        {"evidence_tokens": ["Pallavi", "zarooratwala"]},
    )
    assert seen["task"] == "decision"
    assert seen["usecase"] == "compose_search_query"
    assert payload.get("chosen") == "zarooratwala Pallavi"


def test_compose_refuses_dead_prior_and_falls_back():
    """After no_results, authorship must not re-emit the same string."""
    author = _FakeAuthor(chosen="Pallavi zarooratwala WhatsApp")
    brief = SearchQueryBrief(
        goal_tokens=goal_evidence_tokens(_goal()),
        goal_kind="whatsapp_forward_message",
        prior_queries=[
            {"q": "Pallavi zarooratwala WhatsApp", "outcome": "no_results"},
        ],
        world_document={"search_empty": True},
    )
    outcome = compose_search_query(brief, author=author)
    assert outcome.ok
    chosen = outcome.evidence["chosen"].lower()
    assert chosen != "pallavi zarooratwala whatsapp"
    assert "whatsapp" not in chosen.split()
    assert chosen  # iterative fallback over unused evidence


def test_strip_host_app_from_authored_query():
    author = _FakeAuthor(chosen="zarooratwala WhatsApp")
    outcome = compose_search_query(
        SearchQueryBrief(goal_tokens=goal_evidence_tokens(_goal())),
        author=author,
    )
    assert outcome.ok
    assert outcome.evidence["chosen"].lower() == "zarooratwala"


def test_model_choice_of_compose_search_query_passes_through():
    """When the brain elects to author a fresh query, the runtime carries that
    choice — it no longer rewrites it into locate/open based on search state.
    GroundedUiTarget geometry for the Search field is part of the contract."""
    world = WorldModel(active_app="WhatsApp")
    features = StateFeatures(
        conversation_open=True,
        extras={
            "search_empty": True,
            "search_query": "Pallavi zarooratwala WhatsApp",
            "app_content_node_count": 0,
        },
    )
    proposal = UnifiedProposal(
        observed_state={"surface": "conversation", "open_conversation": "Pallavi"},
        next_action={
            "family": "compose_search_query",
            "text": "zarooratwala",
            "target_label": "Search",
            "target_id": "search_field",
            "target_point": [150.0, 90.0],
            "confidence": 0.9,
        },
        confidence=0.9,
    )
    action, reason = proposal_to_action(proposal, _goal(), world, features)
    assert reason == "admissible"
    assert action is not None
    assert action.action_family == "compose_search_query"
    assert action.target_point is not None
    assert action.grounding_reason == "unified_multimodal"


def test_compose_search_query_without_geometry_is_inadmissible():
    world = WorldModel(active_app="WhatsApp")
    proposal = UnifiedProposal(
        observed_state={"surface": "chat_list"},
        next_action={"family": "compose_search_query", "text": "zarooratwala"},
        confidence=0.9,
    )
    action, reason = proposal_to_action(proposal, _goal(), world, StateFeatures())
    assert action is None
    assert "without_geometry" in reason


def test_compose_search_rejects_contact_entity_as_type_target():
    """Live 095344: Pallavi contact id must not become the type target."""
    from plugin.worldmodel.entities.entity import Entity

    world = WorldModel(active_app="WhatsApp")
    world.entities[900000] = Entity(
        id=900000,
        entity_type="button",
        semantic_role="Pallavi",
        label="Pallavi",
        role="AXButton",
        actions=["click"],
        bounds=(2000.0, 340.0, 250.0, 40.0),
        attributes={},
        visible=True,
    )
    proposal = UnifiedProposal(
        observed_state={"surface": "conversation", "open_conversation": "Pallavi"},
        next_action={
            "family": "compose_search_query",
            "text": "zarooratwala Pallavi",
            "target_label": "Pallavi",
            "target_id": 900000,
            "target_point": [150.0, 90.0],
            "coordinate_space": "screen",
            "confidence": 0.9,
        },
        confidence=0.9,
    )
    action, reason = proposal_to_action(proposal, _goal(), world, StateFeatures())
    assert reason == "admissible"
    assert action is not None
    assert action.target_entity_id is None
    assert action.semantic_target == "Search"
    assert action.target_point == (150, 90)


def test_reveal_actions_choice_passes_through():
    """The runtime does not force a locate before reveal_actions; the model owns
    whether the message is on screen and what to do next."""
    world = WorldModel(active_app="WhatsApp")
    features = StateFeatures(
        conversation_open=True,
        extras={"app_content_node_count": 0, "query_in_timeline": False},
    )
    proposal = UnifiedProposal(
        observed_state={
            "surface": "conversation",
            "open_conversation": "Pallavi",
            "target_object_visible": True,
        },
        next_action={
            "family": "reveal_actions",
            "text": "zarooratwala message",
            "target_point": [400, 300],
            "confidence": 0.95,
        },
        confidence=0.95,
    )
    action, reason = proposal_to_action(proposal, _goal(), world, features)
    assert reason == "admissible"
    assert action is not None
    assert action.action_family == "reveal_actions"


def test_locate_content_choice_passes_through():
    """A model-chosen locate_content is executed as-is (no promotion to select)."""
    world = WorldModel(active_app="WhatsApp")
    features = StateFeatures(
        conversation_open=True,
        extras={
            "query_in_timeline": False,
            "last_locate_query": "zarooratwala",
            "last_locate_realization": "native_find",
        },
    )
    proposal = UnifiedProposal(
        observed_state={"surface": "conversation", "open_conversation": "Pallavi"},
        next_action={
            "family": "locate_content",
            "text": "zarooratwala",
            "target_label": "Find",
            "target_point": [320.0, 40.0],
            "confidence": 0.9,
        },
        confidence=0.9,
    )
    action, reason = proposal_to_action(proposal, _goal(), world, features)
    assert reason == "admissible"
    assert action is not None
    assert action.action_family == "locate_content"
    assert action.text == "zarooratwala"
    assert action.target_point is not None


def test_the_perceptor_does_not_get_to_supply_the_search_string():
    """Authoring the query belongs to the author, not to whatever saw the screen.

    The perceptor fills a ``text`` on its proposal as a side job, and while a
    non-empty value won, that guess replaced the authored query outright. What
    it guesses is the bare contact name -- the one thing this capability's own
    prompt forbids ("do not merely echo one entity name") -- so live runs typed
    'Kulvinder' and landed in a crowded result list, while the single run where
    the perceptor happened to return nothing authored 'zarooratwala link
    Kulvinder' and put the target row on screen at once.

    Asserted against the source because the branch sits inside the live
    executor, where reaching it for real needs a running app and a model.
    """
    import inspect

    from plugin.experiments import run_forward_message

    source = inspect.getsource(run_forward_message)
    start = source.index("author_query_for_goal(")
    window = source[max(0, start - 1200) : start + 400]
    assert "step.text" not in window, (
        "the compose_search_query branch must author the query, "
        "not fall back to the text the perceptor proposed"
    )


def test_live_202832_pallavipo_query_looks_corrupted():
    """Typed zarooratwala Pallavi; field drifted to zaropratwala Pallavipo."""
    tokens = goal_evidence_tokens(_goal())
    assert query_looks_corrupted("zaropratwala Pallavipo", tokens)
    assert query_looks_corrupted("a zaropratwala Pallavipol", tokens)
    assert not query_looks_corrupted("zarooratwala Pallavi", tokens)
    assert ui_shows_no_search_results("WhatsApp for Mac", "No results")
