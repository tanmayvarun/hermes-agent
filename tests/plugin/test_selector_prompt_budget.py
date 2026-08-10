"""The decision prompt must stay a decision prompt.

Observed live: a single ``decision_high_risk`` call carried 1.13 MB, roughly
282k tokens. About two thirds of it was one base64 JPEG repeated four times,
embedded as a JSON string that no model, vision-capable or not, can decode. It
arrived because perception records its own prompt for traceability, that record
is stored on the world model and in feature extras, and the selector prompt
included those extras wholesale.

The tests below pin the two halves of the fix: perception's stored record no
longer carries the prompt it sent, and the selector payload no longer copies
perception's working notes into a question about which of three buttons to
press.
"""

from __future__ import annotations

import json

from plugin.agent.action import Action
from plugin.agent.decision_selector import build_branch_strategy_messages, build_selector_messages
from plugin.agent.features import StateFeatures
from plugin.agent.goal import Goal
from plugin.agent.reasoning_consultation import ReasoningConsultationResult
from plugin.worldmodel.model import Entity, WorldModel

# Stands in for the base64 screenshot; distinctive enough to find anywhere it
# leaks, large enough that a leak shows up in the size assertion too.
BLOB = "SCREENSHOTBLOB" * 4000


def _world() -> WorldModel:
    world = WorldModel()
    world.active_app = "WhatsApp"
    world.entities = {
        1: Entity(
            id=1,
            entity_type="button",
            semantic_role="Search",
            label="Search",
            role="AXButton",
            actions=["click"],
            visible=True,
        ),
        2: Entity(
            id=2,
            entity_type="static",
            semantic_role="Kulvinder Ji",
            label="Kulvinder Ji",
            role="AXStaticText",
            actions=["click"],
            visible=True,
        ),
    }
    return world


def _goal() -> Goal:
    return Goal(
        kind="whatsapp_forward_message",
        contact="Kulvinder",
        target_contact="Pallavi",
        link_query="zarooratwala",
    )


def _contaminated_features() -> StateFeatures:
    """Feature extras carrying every record that used to smuggle the image in."""
    consultation = {
        "task": "screen_understanding",
        "messages": [{"role": "user", "content": [{"type": "image", "image": BLOB}]}],
        "raw_response": "{}",
    }
    return StateFeatures(
        extras={
            "perception_summary": {
                "screen_type": "conversation",
                "likely_next_family": "open_contact",
                "likely_next_target": "Kulvinder Ji",
                "consultation": consultation,
            },
            "perception_llm": {"consultation": consultation},
            "perception_result": {"objects": [{"id": "o1", "screenshot": BLOB}]},
            "perception_consultation": consultation,
            "conversation_message_relevance": {"rows": [{"text": BLOB}]},
            "conversation_context_text": [BLOB],
        }
    )


def _candidates():
    return [
        ("c1", Action(action="Click", action_family="open_contact", semantic_target="Kulvinder Ji")),
        ("c2", Action(action="Click", action_family="open_search", semantic_target="Search")),
    ]


def test_selector_prompt_never_carries_the_screenshot_it_was_derived_from():
    world = _world()
    world.last_perception_synthesis = {
        "summary": {
            "likely_next_family": "open_contact",
            "consultation": {"messages": [{"role": "user", "content": BLOB}]},
        }
    }

    messages = build_selector_messages(_goal(), world, _contaminated_features(), _candidates())
    content = messages[1]["content"]

    assert "SCREENSHOTBLOB" not in content


def test_selector_prompt_stays_within_a_decision_sized_budget():
    """A prompt an order of magnitude over this is carrying something it should not.

    Generous on purpose: the point is to catch another wholesale dump of a
    perception record, not to freeze the current field list.
    """
    messages = build_selector_messages(_goal(), _world(), _contaminated_features(), _candidates())
    content = messages[1]["content"]

    assert len(content) < 20_000, f"selector prompt grew to {len(content)} chars"


def test_selector_prompt_still_carries_what_the_choice_turns_on():
    features = _contaminated_features()
    features.extras["selected_procedure_stage"] = {"id": "locate_source", "objective": "find the link"}
    features.extras["selected_procedure_stage_missing_predicates"] = ["source_message_visible"]
    features.extras["goal_hypotheses"] = ["find source content matching zarooratwala"]

    messages = build_selector_messages(
        _goal(),
        _world(),
        features,
        _candidates(),
        frontier_summary=[{"label": "open the conversation"}],
        already_tried=[{"family": "right_click", "target": "message", "attempts": 4, "effects": ["no_change"]}],
    )
    payload = json.loads(messages[1]["content"])

    assert [c["id"] for c in payload["candidates"]] == ["c1", "c2"]
    assert payload["perception_summary"]["likely_next_target"] == "Kulvinder Ji"
    assert payload["selected_procedure_stage"]["objective"] == "find the link"
    assert payload["world_view"]["procedure_progress"]["missing_predicates"] == ["source_message_visible"]
    assert payload["goal_hypotheses"] == ["find source content matching zarooratwala"]
    assert payload["frontier_hypotheses"] == [{"label": "open the conversation"}]
    assert payload["already_tried"][0]["attempts"] == 4
    assert {e["label"] for e in payload["world_view"]["visible_entities"]} == {"Search", "Kulvinder Ji"}


def test_static_instructions_live_in_the_cacheable_system_prefix():
    """Providers cache on a byte-identical prefix, and only the system message is one.

    The user message is rebuilt from live state every call, and serialized with
    sorted keys, so static text placed there sits behind volatile keys and gets
    re-prefilled every time. These two prompts share no goal, world, features or
    candidates: any difference in the system message means state leaked into the
    half that is supposed to be invariant.
    """
    first = build_selector_messages(_goal(), _world(), _contaminated_features(), _candidates())
    empty_world = _world()
    empty_world.entities = {}
    second = build_selector_messages(
        Goal(kind="whatsapp_voice_call", contact="Pallavi"),
        empty_world,
        StateFeatures(),
        [("c9", Action(action="Click", action_family="start_call", semantic_target="Call"))],
    )

    assert first[0]["content"] == second[0]["content"]
    assert len(first[0]["content"]) > 1_000, "system prefix too small to be worth caching"


def test_no_builder_leaves_static_instructions_in_the_user_payload():
    args = (_goal(), _world(), _contaminated_features(), _candidates())
    for label, messages in (
        ("selector", build_selector_messages(*args)),
        ("branch_strategy", build_branch_strategy_messages(*args)),
    ):
        payload = json.loads(messages[1]["content"])
        leaked = {key for key in payload if key in {"instruction", "instructions"}}
        assert not leaked, f"{label} still ships {leaked} in the volatile user message"


def test_stored_consultation_record_drops_the_prompt_it_sent():
    """``to_dict`` keeps the prompt for traces; stored copies must not."""
    result = ReasoningConsultationResult(
        task="screen_understanding",
        messages=[{"role": "user", "content": [{"type": "image", "image": BLOB}]}],
    )

    assert "messages" in result.to_dict()
    assert "messages" not in result.to_dict(include_messages=False)
    assert BLOB not in json.dumps(result.to_dict(include_messages=False))
