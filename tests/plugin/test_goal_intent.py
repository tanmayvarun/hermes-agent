from plugin.agent.goal import Goal
from plugin.agent.decision_selector import build_selector_messages
from plugin.agent.features import StateFeatures
from plugin.worldmodel.model import WorldModel


def test_forward_goal_intent_hypotheses_prioritize_content_before_destination():
    goal = Goal(
        kind="whatsapp_forward_message",
        contact="Kulvinder",
        target_contact="Pallavi",
        link_query="zarooratwala",
        prompt="find the zarooratwala link sent to kulvinder on whatsapp and forward to pallavi",
    )

    hypotheses = goal.intent_hypotheses()

    assert goal.procedure_id == "whatsapp_forward_message"
    assert hypotheses[:4] == [
        "find the source content matching zarooratwala",
        "open source conversation Kulvinder",
        "inspect source conversation timeline",
        "identify the source message or link",
    ]
    assert "forward to Pallavi" in hypotheses
    assert hypotheses.index("forward to Pallavi") > hypotheses.index("identify the source message or link")


def test_zarooratwala_prompt_infers_same_forward_procedure_contract():
    goal = Goal.infer_from_text(
        "find the zarooratwala link sent to kulvinder on whatsapp and forward to pallavi"
    )

    assert goal.kind == "whatsapp_forward_message"
    assert goal.procedure_id == "whatsapp_forward_message"
    assert goal.contact.lower() == "kulvinder"
    assert goal.target_contact.lower() == "pallavi"
    assert goal.link_query == "zarooratwala"
    context = goal.execution_context_block()
    assert "find the source content matching zarooratwala" in context
    assert "Treat this structured contract as the primary task" in context


def test_selector_prompt_exposes_goal_hypotheses():
    goal = Goal(
        kind="whatsapp_forward_message",
        contact="Kulvinder",
        target_contact="Pallavi",
        link_query="india coffee house hsr layout",
        prompt="find the google maps share link of india coffee house hsr layout and share with pallavi",
    )
    features = StateFeatures(extras={"goal_hypotheses": goal.intent_hypotheses()})
    messages = build_selector_messages(
        goal,
        WorldModel(),
        features,
        candidates=[],
    )

    payload = messages[1]["content"]
    assert "goal_hypotheses" in payload
    assert "find source content matching india coffee house hsr layout" in payload
