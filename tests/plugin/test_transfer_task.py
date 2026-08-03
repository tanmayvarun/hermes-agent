"""The transfer task is one shape across apps.

These tests exercise ``build_transfer_state`` on unified-document readings from
four unrelated apps. The point of the refactor is that none of them need an
app-specific view or binder: the same predicates and phase ladder fall out of
the general document, so a new app is a data mapping, not new code.
"""

from plugin.agent.goal import Goal
from plugin.agent.transfer_task import build_transfer_state, surface_role


def _forward_goal(app: str, source: str, query: str, dest: str) -> Goal:
    return Goal(kind="forward", app=app, contact=source, link_query=query, target_contact=dest)


def test_surface_roles_collapse_app_vocabularies_to_general_roles():
    assert surface_role("conversation") == "container"
    assert surface_role("folder") == "container"
    assert surface_role("context_menu") == "action_menu"
    assert surface_role("share_sheet") == "action_menu"
    assert surface_role("forward_picker") == "destination"
    assert surface_role("share_targets") == "destination"
    assert surface_role("chat_list") == "list"
    assert surface_role("something_unknown") == "unknown"


def test_container_closed_means_open_source_phase():
    goal = _forward_goal("WhatsApp", "Pallavi", "zarooratwala", "Tanmay")
    state = build_transfer_state(goal, {"surface": "chat_list", "open_conversation": "", "objects": []})
    assert state.predicates.source_conversation_open is False
    assert state.derived_phase == "OPEN_SOURCE"


def test_whatsapp_conversation_with_the_link_advances_past_open_source():
    goal = _forward_goal("WhatsApp", "Pallavi", "zarooratwala", "Tanmay")
    doc = {
        "surface": "conversation",
        "open_conversation": "Pallavi",
        "objects": [
            {"kind": "message", "text": "OTP is 4821"},
            {"kind": "message", "text": "check zarooratwala.com", "matches_goal": True},
        ],
    }
    state = build_transfer_state(goal, doc)
    assert state.predicates.source_conversation_open is True
    assert state.predicates.source_object_visible is True
    assert state.derived_phase != "OPEN_SOURCE"


def test_action_menu_surface_is_the_general_forward_surface():
    goal = _forward_goal("WhatsApp", "Pallavi", "zarooratwala", "Tanmay")
    doc = {
        "surface": "context_menu",
        "open_conversation": "Pallavi",
        "objects": [{"kind": "menu_item", "text": "Forward"}],
    }
    state = build_transfer_state(goal, doc)
    assert state.predicates.forward_surface_open is True


def test_destination_picker_and_selection_reach_pick_dest():
    goal = _forward_goal("WhatsApp", "Pallavi", "zarooratwala", "Tanmay")
    doc = {
        "surface": "forward_picker",
        "open_conversation": "",
        "objects": [
            {"kind": "chat", "text": "Aparna"},
            {"kind": "chat", "text": "Tanmay", "selected": True},
        ],
    }
    state = build_transfer_state(goal, doc)
    assert state.predicates.destination_picker_visible is True
    assert state.predicates.destination_selected is True
    assert state.derived_phase == "PICK_DEST"


def test_same_binder_handles_a_slack_forward():
    goal = _forward_goal("Slack", "#eng", "incident postmortem", "Priya")
    doc = {
        "surface": "conversation",
        "open_conversation": "#eng",
        "objects": [{"kind": "message", "text": "incident postmortem doc", "matches_goal": True}],
    }
    state = build_transfer_state(goal, doc)
    assert state.predicates.source_conversation_open is True
    assert state.predicates.source_object_visible is True


def test_same_binder_handles_a_finder_move():
    goal = _forward_goal("Finder", "Downloads", "invoice_2026.pdf", "Documents")
    doc = {
        "surface": "folder",
        "open_conversation": "Downloads",
        "objects": [
            {"kind": "file", "text": "notes.txt"},
            {"kind": "file", "text": "invoice_2026.pdf", "matches_goal": True},
        ],
    }
    state = build_transfer_state(goal, doc)
    assert state.predicates.source_conversation_open is True
    assert state.predicates.source_object_visible is True


def test_same_binder_handles_a_youtube_share():
    goal = _forward_goal("YouTube", "", "bitter lesson talk", "Copy link")
    doc = {
        "surface": "page",
        "open_conversation": "watch page",  # no required source -> any container counts
        "objects": [{"kind": "video", "text": "The Bitter Lesson talk", "matches_goal": True}],
    }
    state = build_transfer_state(goal, doc)
    assert state.predicates.source_conversation_open is True
    assert state.predicates.source_object_visible is True


def test_container_and_object_stay_open_behind_the_action_menu():
    """Opening the Forward menu must not regress the phase to OPEN_SOURCE.

    The action menu's reading lists menu items, not the conversation's messages,
    and its surface role is action_menu -- so a naive recompute would declare the
    container closed and the object gone the instant the menu appears. The
    conversation is still open underneath; the belief has to persist.
    """
    goal = _forward_goal("WhatsApp", "Pallavi", "zarooratwala", "Tanmay")
    open_doc = {
        "surface": "conversation",
        "open_conversation": "Pallavi",
        "objects": [{"kind": "message", "text": "check zarooratwala.com", "matches_goal": True}],
    }
    opened = build_transfer_state(goal, open_doc)
    assert opened.predicates.source_conversation_open is True
    assert opened.predicates.source_object_visible is True

    menu_doc = {
        "surface": "context_menu",
        "open_conversation": "",
        "objects": [{"kind": "menu_item", "text": "Forward"}, {"kind": "menu_item", "text": "Reply"}],
    }
    with_menu = build_transfer_state(goal, menu_doc, prior=opened.to_dict())
    assert with_menu.predicates.forward_surface_open is True
    assert with_menu.predicates.source_conversation_open is True  # sticky under overlay
    assert with_menu.predicates.source_object_visible is True     # sticky under overlay
    assert with_menu.derived_phase != "OPEN_SOURCE"


def test_object_bound_to_entity_when_lookup_available():
    goal = _forward_goal("WhatsApp", "Pallavi", "zarooratwala", "Tanmay")
    doc = {
        "surface": "conversation",
        "open_conversation": "Pallavi",
        "objects": [{"kind": "message", "text": "check zarooratwala.com", "matches_goal": True}],
    }
    lookup = {"check zarooratwala.com": 900002}
    state = build_transfer_state(goal, doc, entity_id_for_text=lambda t: lookup.get(t))
    obj = state.binding("source_object")
    assert obj.candidate_entity_ids == [900002]
    assert obj.resolved_entity_id == 900002


def test_prior_state_carries_forward():
    goal = _forward_goal("WhatsApp", "Pallavi", "zarooratwala", "Tanmay")
    doc = {"surface": "conversation", "open_conversation": "Pallavi", "objects": []}
    first = build_transfer_state(goal, doc)
    # Re-derive from the same reading using the prior; container stays open.
    second = build_transfer_state(goal, doc, prior=first.to_dict())
    assert second.predicates.source_conversation_open is True


# --- layered-document path ---------------------------------------------------
# When perception supplies a layer stack, object permanence is in the stack, so
# the binder reads it directly with no prior-state stickiness. These pin that
# the Forward menu (an overlay layer) never regresses the phase to OPEN_SOURCE.


def test_layers_conversation_advances_past_open_source():
    goal = _forward_goal("WhatsApp", "Pallavi", "zarooratwala", "Tanmay")
    doc = {
        "surface": "conversation",
        "open_conversation": "Pallavi",
        "layers": [
            {
                "role": "container",
                "name": "Pallavi",
                "state": "active",
                "objects": [{"kind": "message", "text": "check zarooratwala.com", "matches_goal": True}],
            }
        ],
    }
    state = build_transfer_state(goal, doc)
    assert state.predicates.source_conversation_open is True
    assert state.predicates.source_object_visible is True
    assert state.derived_phase != "OPEN_SOURCE"


def test_layers_action_menu_over_conversation_keeps_container_open_without_prior():
    """The regression the user flagged: the menu overlay must not close the chat.

    Crucially this needs NO prior state -- permanence is in the stack (the
    container layer is present, occluded), so a single reading is enough.
    """
    goal = _forward_goal("WhatsApp", "Pallavi", "zarooratwala", "Tanmay")
    doc = {
        "surface": "context_menu",
        "open_conversation": "Pallavi",
        "layers": [
            {
                "role": "container",
                "name": "Pallavi",
                "state": "occluded",
                "objects": [{"kind": "message", "text": "check zarooratwala.com", "matches_goal": True}],
            },
            {
                "role": "action_menu",
                "state": "active",
                "objects": [{"kind": "menu_item", "text": "Forward"}, {"kind": "menu_item", "text": "Reply"}],
            },
        ],
    }
    state = build_transfer_state(goal, doc)  # no prior at all
    assert state.predicates.forward_surface_open is True
    assert state.predicates.source_conversation_open is True  # sticky-free permanence
    assert state.predicates.source_object_visible is True
    assert state.derived_phase != "OPEN_SOURCE"


def test_layers_destination_picker_and_selection_reach_pick_dest():
    goal = _forward_goal("WhatsApp", "Pallavi", "zarooratwala", "Tanmay")
    doc = {
        "surface": "forward_picker",
        "layers": [
            {"role": "container", "name": "Pallavi", "state": "occluded", "objects": []},
            {
                "role": "destination",
                "state": "active",
                "objects": [
                    {"kind": "chat", "text": "Aparna"},
                    {"kind": "chat", "text": "Tanmay", "selected": True},
                ],
            },
        ],
    }
    state = build_transfer_state(goal, doc)
    assert state.predicates.destination_picker_visible is True
    assert state.predicates.destination_selected is True
    assert state.derived_phase == "PICK_DEST"
