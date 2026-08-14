"""Simple compose prompts: send <body> to <Name> → gateway-ready Goal fields."""

from plugin.agent.goal import Goal


def test_send_hi_to_name_sets_message_body_not_link_query() -> None:
    g = Goal.infer_from_text("send hi to Pallavi")
    assert g.kind == "whatsapp_forward_message"
    assert g.message_body == "hi"
    assert g.target_contact == "Pallavi"
    assert g.contact == "Pallavi"
    assert g.link_query == ""


def test_find_link_prompt_still_uses_link_query_not_message_body() -> None:
    g = Goal.infer_from_text(
        "Find the ZarooratWala link sent to Pallavi and forward it to Tanmay."
    )
    assert g.kind == "whatsapp_forward_message"
    assert "zarooratwala" in (g.link_query or "").lower() or "ZarooratWala" in (
        g.link_query or ""
    )
    assert not (g.message_body or "").strip()
