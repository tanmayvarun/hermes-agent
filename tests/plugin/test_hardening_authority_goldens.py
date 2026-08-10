"""Mandatory authority goldens from the pre-run hardening plan."""

from plugin.agent.composition import compose_domain_adapters
from plugin.agent.procedures.forward_message import forward_role_specs
from plugin.agent.role_binding import assess_candidate_for_role
from plugin.agent.source_query_binding import evaluate_source_object_match
from plugin.agent.apps.whatsapp import _entity_binding_eligible
from plugin.worldmodel.entities.entity import Entity
from plugin.worldmodel.model import WorldModel


class _AliceGoal:
    contact = "Alice"
    link_query = "zarooratwala"
    target_contact = "Bob"
    originator = "Alice"


def test_from_alice_single_result_from_self_does_not_resolve():
    compose_domain_adapters()
    you = {
        "label": "You: https://www.zarooratwala.com/x",
        "text": "You: https://www.zarooratwala.com/x",
        "kind": "message_with_link",
        "domain": "whatsapp",
        "container": "Alice",
    }
    a = assess_candidate_for_role(
        spec=forward_role_specs(_AliceGoal())["source_object"],
        candidate=you,
        goal=_AliceGoal(),
        bindings={"source_container": {"resolved_label": "Alice"}},
        task_relevance=0.99,
    )
    assert a.binding_eligible is False


def test_sender_unknown_does_not_infer_peer():
    gm = evaluate_source_object_match(
        text="https://www.zarooratwala.com/x",
        kind="message_with_link",
        query="zarooratwala",
        container_open="Alice",
        expected_container="Alice",
        expected_originator="Alice",
        sender="",  # no authorship evidence
    )
    assert gm.container_match
    assert gm.semantic_query_match
    assert not gm.originator_match
    assert not gm.binding_eligible
    assert any(c.name == "originator" and c.status == "missing" for c in gm.constraints)


def test_non_authoritative_scorer_cannot_bind():
    """matches_goal / high relevance must not authorize RoleBinder commit."""
    compose_domain_adapters()
    world = WorldModel()
    world.open_conversation = "Alice"
    world.entities[7] = Entity(
        id=7,
        entity_type="message",
        semantic_role="message",
        label="You: https://www.zarooratwala.com/x",
        role="AXStaticText",
        bounds=(900, 400, 200, 40),
        visible=True,
        attributes={
            "matches_goal": True,
            "description": "You: https://www.zarooratwala.com/x",
            "kind": "message_with_link",
        },
    )
    ok = _entity_binding_eligible(
        world,
        7,
        query="zarooratwala",
        expected_container="Alice",
        expected_originator="Alice",
        goal=_AliceGoal(),
    )
    assert ok is False
