"""Goal relation parse: sent_to ≠ sent_from ≠ container ≠ destination."""

from plugin.agent.goal import Goal


def test_sent_from_Alice_sets_originator_Alice():
    goal = Goal.infer_from_text(
        "find the invoice link from Alice on whatsapp and forward to Bob"
    )
    assert goal.originator.lower() == "alice"
    assert goal.contact.lower() == "alice"
    assert goal.recipient == ""
    assert goal.target_contact.lower() == "bob"


def test_sent_to_Alice_sets_recipient_not_originator():
    goal = Goal.infer_from_text(
        "find the zarooratwala link sent to Alice on whatsapp and forward to Bob"
    )
    assert goal.recipient.lower() == "alice"
    assert goal.contact.lower() == "alice"
    assert goal.originator == ""  # UNKNOWN — not aliased from recipient
    assert goal.target_contact.lower() == "bob"


def test_I_sent_to_Alice_sets_originator_self_recipient_Alice():
    goal = Goal.infer_from_text(
        "find the link I sent to Alice on whatsapp and forward to Bob"
    )
    assert goal.originator == "self"
    assert goal.recipient.lower() == "alice"
    assert goal.contact.lower() == "alice"
    assert goal.target_contact.lower() == "bob"


def test_in_Alice_chat_sets_container_originator_unknown():
    goal = Goal.infer_from_text(
        "find the invoice in Alice's chat on whatsapp and forward to Bob"
    )
    assert goal.contact.lower() == "alice"
    assert goal.originator == ""
    assert goal.recipient == ""
    assert goal.target_contact.lower() == "bob"


def test_live_zarooratwala_sent_to_prompt_does_not_require_pallavi_authorship():
    """Live 113806 prompt must not invent originator=Pallavi from sent_to."""
    goal = Goal.infer_from_text(
        "find the zarooratwala link sent to pallavi on whatsapp and forward to tanmay"
    )
    assert goal.contact.lower() == "pallavi"
    assert goal.recipient.lower() == "pallavi"
    assert goal.originator == ""
    assert goal.target_contact.lower() == "tanmay"
    assert goal.link_query == "zarooratwala"
    assert "sent to pallavi" in goal.description.lower()
    assert "from pallavi" not in goal.description.lower()
