"""Capability descriptors and hierarchical retrieval over the catalog."""

from __future__ import annotations

from plugin.agent.executive.capabilities import (
    CapabilityRegistry,
    default_registry,
)


def test_registry_covers_every_realized_verb():
    from plugin.agent.capabilities.catalog import realized_verbs

    registry = CapabilityRegistry.from_catalog()
    for verb in realized_verbs():
        assert registry.get(verb) is not None, verb


def test_irreversible_commit_is_marked_and_devalued():
    registry = default_registry()
    commit = registry.get("commit_irreversible")
    assert commit is not None
    assert commit.is_irreversible is True
    # A pure reversible read of similar reliability should outrank it.
    compose = registry.get("compose_search_query")
    assert compose.value() > commit.value()


def test_preconditions_filter_retrieval():
    registry = default_registry()
    # Only a candidate_set is available: resolve_entity fits, open_entity does not.
    got = {d.verb for d in registry.retrieve(facts=["candidate_set"], limit=9)}
    assert "resolve_entity" in got
    assert "open_entity" not in got


def test_reversible_only_excludes_the_committing_move():
    registry = default_registry()
    verbs = {d.verb for d in registry.retrieve(reversible_only=True, limit=9)}
    assert "commit_irreversible" not in verbs


def test_retrieval_is_ranked_by_value():
    registry = default_registry()
    ordered = registry.retrieve(limit=9)
    values = [d.value() for d in ordered]
    assert values == sorted(values, reverse=True)


def test_explore_shortlist_is_reversible():
    registry = default_registry()
    shortlist = registry.shortlist_for(meta_action="explore", limit=9)
    assert all(not d.is_irreversible for d in shortlist)


def test_act_shortlist_may_include_commit():
    registry = default_registry()
    verbs = {d.verb for d in registry.shortlist_for(meta_action="act", facts=["gated_target"], limit=9)}
    assert "commit_irreversible" in verbs


def test_observed_outcomes_move_reliability():
    registry = CapabilityRegistry.from_catalog()
    before = registry.get("locate_content").reliability
    for _ in range(5):
        registry.observe_reliability("locate_content", success=False)
    after = registry.get("locate_content").reliability
    assert after < before


def test_ranked_capabilities_orders_by_registry_value():
    from plugin.agent.decision_consultation import (
        choosable_capabilities,
        ranked_capabilities,
    )

    ranked = ranked_capabilities()
    assert set(ranked) == set(choosable_capabilities())
    # commit_irreversible should not lead a value-ranked list.
    if "commit_irreversible" in ranked:
        assert ranked[0] != "commit_irreversible"


def test_ranked_capabilities_drops_forbidden():
    from plugin.agent.decision_consultation import ranked_capabilities

    ranked = ranked_capabilities(forbidden=["open_entity"])
    assert "open_entity" not in ranked
