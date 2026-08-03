"""compose_search_query authors strings — it must not hardcode query templates."""

from __future__ import annotations

from typing import Any, Dict

from plugin.agent.capabilities.compose_search_query import (
    SearchQueryBrief,
    author_query_for_goal,
    compose_search_query,
    goal_evidence_tokens,
    is_bare_entity_query,
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
    author = _FakeAuthor(chosen="pallavi invoice link")
    outcome = dispatch(
        CapabilityRequest(
            name="compose_search_query",
            app="WhatsApp",
            extras={"goal": _goal(), "author": author, "world_document": {"surface": "chat_list"}},
        ),
        overlay=object(),
    )
    assert outcome.ok
    assert outcome.evidence["chosen"] == "pallavi invoice link"


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
    choice — it no longer rewrites it into locate/open based on search state."""
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
            "text": "",
            "confidence": 0.9,
        },
        confidence=0.9,
    )
    action, reason = proposal_to_action(proposal, _goal(), world, features)
    assert reason == "admissible"
    assert action is not None
    assert action.action_family == "compose_search_query"
    assert action.grounding_reason == "unified_multimodal"


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
        next_action={"family": "locate_content", "text": "zarooratwala", "confidence": 0.9},
        confidence=0.9,
    )
    action, reason = proposal_to_action(proposal, _goal(), world, features)
    assert reason == "admissible"
    assert action is not None
    assert action.action_family == "locate_content"
    assert action.text == "zarooratwala"
