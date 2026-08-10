"""Brain target grounding must not lose to a stale matches_goal object."""

from __future__ import annotations

from plugin.agent.decision_consultation import _ground_choice_on_world


def test_forward_picker_select_grounds_to_named_contact_not_goal_message():
    doc = {
        "surface": "forward_picker",
        "objects": [
            {
                "id": "msg_link_main",
                "kind": "message_link_preview",
                "text": "ZarooratWala - Fresh Groceries Delivered...",
                "point": [1460, 210],
                "matches_goal": True,
            },
            {
                "id": "contact_tanmay_artha",
                "kind": "contact_row",
                "text": "Tanmay <> Artha",
                "point": [1100, 420],
                "matches_goal": True,
            },
        ],
    }
    grounded = _ground_choice_on_world(doc, "select_content", "Tanmay <> Artha")
    assert grounded.get("target_id") == "contact_tanmay_artha"
    assert "Tanmay" in str(grounded.get("target_label") or "")


def test_explicit_target_beats_unrelated_matches_goal():
    doc = {
        "surface": "conversation",
        "objects": [
            {
                "id": "msg",
                "kind": "message",
                "text": "other link",
                "matches_goal": True,
                "point": [10, 10],
            },
            {
                "id": "row",
                "kind": "chat_row",
                "text": "Pallavi",
                "matches_goal": False,
                "point": [20, 20],
            },
        ],
    }
    grounded = _ground_choice_on_world(doc, "open_entity", "Pallavi")
    assert grounded.get("target_id") == "row"
