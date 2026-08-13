"""Identity binding for source_query — distractor URLs must not bind."""

from plugin.agent.source_query_binding import (
    evaluate_source_object_match,
    host_contradicts_query,
    query_supported_by_text,
    scrub_matches_goal_flags,
    text_locates_source_query,
)


def test_youtube_fails_zarooratwala_identity():
    gm = evaluate_source_object_match(
        text="https://youtu.be/rHJdc-jkxys",
        kind="message_with_link",
        query="zarooratwala",
        container_open="Pallavi",
        expected_container="Pallavi",
        perception_matches_goal=True,
    )
    assert gm.container_match
    assert gm.object_type_match
    assert not gm.semantic_query_match
    assert not gm.binding_eligible
    assert "url_host_contradicts_query" in gm.contradictions


def test_zarooratwala_domain_binds():
    gm = evaluate_source_object_match(
        text="https://www.zarooratwala.com/fresh",
        kind="message_with_link",
        query="zarooratwala",
        container_open="Pallavi",
        expected_container="Pallavi",
        expected_originator="Pallavi",
        sender="Pallavi",
    )
    assert gm.binding_eligible
    assert gm.semantic_query_match
    assert gm.originator_match


def test_you_prefix_not_binding_eligible_as_from_pallavi():
    gm = evaluate_source_object_match(
        text="You: https://www.zarooratwala.com/?ref=1",
        kind="message_with_link",
        query="zarooratwala",
        container_open="Pallavi",
        expected_container="Pallavi",
        expected_originator="Pallavi",
        perception_matches_goal=True,
    )
    assert gm.container_match
    assert gm.semantic_query_match
    assert not gm.originator_match
    assert not gm.binding_eligible
    assert any(c.name == "originator" and c.status == "mismatch" for c in gm.constraints)


def test_i_sent_binds_you_prefix():
    gm = evaluate_source_object_match(
        text="You: https://www.zarooratwala.com/x",
        kind="message_with_link",
        query="zarooratwala",
        container_open="Pallavi",
        expected_container="Pallavi",
        expected_originator="self",
    )
    assert gm.binding_eligible
    assert gm.originator_match


def test_scrub_clears_false_matches_goal():
    doc = scrub_matches_goal_flags(
        {
            "open_conversation": "Pallavi",
            "objects": [
                {
                    "id": "1",
                    "kind": "message_bubble",
                    "text": "https://youtu.be/abc",
                    "matches_goal": True,
                }
            ],
        },
        query="zarooratwala",
        expected_container="Pallavi",
    )
    assert doc["objects"][0]["matches_goal"] is False
    assert doc["objects"][0]["goal_match"]["binding_eligible"] is False


def test_host_contradict_and_support_helpers():
    assert host_contradicts_query("https://youtu.be/x", "zarooratwala")
    assert not query_supported_by_text("https://youtu.be/x", "zarooratwala")
    assert text_locates_source_query("see zarooratwala.com now", "zarooratwala")
    assert not text_locates_source_query("https://youtu.be/x", "zarooratwala")


def test_self_you_identity_via_identity_resolver():
    """self/You/me must canonicalize through IdentityResolver, not SEARCH heuristics."""
    from plugin.agent.role_binding import IdentityResolver
    from plugin.agent.source_query_binding import originator_matches

    assert IdentityResolver.canonical_identity("You") == "self"
    assert IdentityResolver.canonical_identity("me") == "self"
    assert IdentityResolver.values_same_identity("self", "You")
    assert originator_matches("You", "self")
    assert originator_matches("self", "You")
    assert not originator_matches("You", "Pallavi")
