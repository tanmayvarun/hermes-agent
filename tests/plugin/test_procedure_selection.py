from plugin.agent.decision_selector import build_selector_messages
from plugin.agent.features import StateFeatures
from plugin.agent.goal import Goal
from plugin.agent.procedure import current_procedure_stage, select_best_procedure
from plugin.worldmodel.model import WorldModel
import json


def test_forward_goal_binds_forward_procedure_and_stage_hypotheses():
    goal = Goal(
        kind="whatsapp_forward_message",
        contact="Kulvinder",
        target_contact="Pallavi",
        link_query="zarooratwala",
        prompt="find the zarooratwala link sent to kulvinder on whatsapp and forward to pallavi",
    )

    assert goal.procedure_id == "whatsapp_forward_message"
    assert goal.procedure is not None
    hypotheses = goal.intent_hypotheses()
    assert hypotheses[:5] == [
        "find the source content matching zarooratwala",
        "open source conversation Kulvinder",
        "inspect source conversation timeline",
        "identify the source message or link",
        "forward to Pallavi",
    ]


def test_prompt_only_goal_can_retrieve_best_matching_procedure():
    goal = Goal(
        kind="unknown",
        app="WhatsApp",
        prompt="find the zarooratwala link sent to kulvinder on whatsapp and forward to pallavi",
    )

    selection = select_best_procedure(goal)
    assert selection is not None
    assert selection.definition.id == "whatsapp_forward_message"
    assert selection.score > 1.25


def test_selector_payload_includes_selected_procedure():
    goal = Goal(
        kind="whatsapp_forward_message",
        contact="Kulvinder",
        target_contact="Pallavi",
        link_query="zarooratwala",
        prompt="find the zarooratwala link sent to kulvinder on whatsapp and forward to pallavi",
    )
    features = StateFeatures(extras={"goal_hypotheses": goal.intent_hypotheses(), "selected_procedure": goal.procedure.to_dict() if goal.procedure else {}})
    payload = build_selector_messages(goal, WorldModel(), features, [])
    content = payload[1]["content"]

    assert "selected_procedure" in content
    assert "selected_procedure_stage" in content
    assert "whatsapp_forward_message" in content


def test_selector_payload_preserves_active_cognitive_subgraph():
    goal = Goal(
        kind="whatsapp_forward_message",
        contact="Kulvinder",
        target_contact="Pallavi",
        link_query="zarooratwala",
    )
    features = StateFeatures(
        extras={
            "active_cognitive_subgraph": {
                "phase": "conversation",
                "focus_region_ids": ["timeline"],
                "active_entity_ids": [10],
                "excluded_region_ids": ["sidebar"],
            }
        }
    )
    payload = build_selector_messages(goal, WorldModel(), features, [])
    content = payload[1]["content"]
    parsed = json.loads(content)

    assert "active_cognitive_subgraph" in content
    assert parsed["world_view"]["active_cognitive_subgraph"]["phase"] == "conversation"
    assert parsed["world_view"]["active_cognitive_subgraph"]["focus_region_ids"] == ["timeline"]


def test_current_procedure_stage_tracks_predicates_and_progress():
    goal = Goal(
        kind="whatsapp_forward_message",
        contact="Kulvinder",
        target_contact="Pallavi",
        link_query="zarooratwala",
    )
    features = StateFeatures(
        extras={
            "forward_task": {
                "predicates": {
                    "source_conversation_open": True,
                    "source_conversation_visible": True,
                    "source_object_visible": True,
                }
            }
        }
    )

    stage = current_procedure_stage(goal, features)
    assert stage is not None
    assert stage["stage_id"] == "identify_source_message"
    assert stage["missing_predicates"] == ["source_object_selected"]
    assert stage["satisfied_predicates"] == []
    assert stage["stage_progress"] == 0.0
    assert stage["procedure_progress"] == 0.6
