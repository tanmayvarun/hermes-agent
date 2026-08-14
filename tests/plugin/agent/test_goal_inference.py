from plugin.agent.goal import Goal


def test_infer_forward_message_goal_from_whatsapp_prompt():
    goal = Goal.infer_from_text(
        "find the zarooratwala link sent to kulvinder on whatsapp and forward to pallavi"
    )

    assert goal.kind == "whatsapp_forward_message"
    assert goal.app == "WhatsApp"
    assert goal.link_query == "zarooratwala"
    assert goal.contact.lower() == "kulvinder"
    assert goal.target_contact.lower() == "pallavi"


def test_infer_forward_message_without_whatsapp_channel_literal():
    """Desktop/TUI prompts often omit 'WhatsApp'; still a forward_message goal."""
    goal = Goal.infer_from_text(
        "Find the ZarooratWala link sent to Pallavi and forward it to Tanmay."
    )

    assert goal.kind == "whatsapp_forward_message"
    assert goal.app == "WhatsApp"
    assert goal.link_query.lower() == "zarooratwala"
    assert goal.contact.lower() == "pallavi"
    assert goal.recipient.lower() == "pallavi"
    assert goal.target_contact.lower() == "tanmay"
    assert goal.originator == ""


def test_execution_context_block_includes_goal_contract():
    goal = Goal(
        kind="whatsapp_forward_message",
        contact="Kulvinder",
        target_contact="Pallavi",
        link_query="zarooratwala",
        prompt="find the zarooratwala link sent to kulvinder on whatsapp and forward to pallavi",
    )

    context = goal.execution_context_block()

    assert "Structured task contract:" in context
    assert "goal_kind: whatsapp_forward_message" in context
    assert "Kulvinder" in context
    assert "Pallavi" in context
    assert "zarooratwala" in context
