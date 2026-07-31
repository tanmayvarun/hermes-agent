"""WhatsApp-overfitted target resolution + forward phase gates."""

from __future__ import annotations

from typing import Dict, List, Optional

from plugin.agent.action import Action
from plugin.agent.apps.whatsapp import WhatsAppOverlay, _infer_forward_phase
from plugin.agent.apps.whatsapp_targets import in_sidebar_band, resolve_whatsapp_target
from plugin.agent.features import StateFeatures
from plugin.agent.goal import Goal
from plugin.agent.policy.candidates import enumerate_candidates
from plugin.agent.whatsapp_view import WhatsAppWorldView
from plugin.worldmodel.entities.entity import Entity
from plugin.worldmodel.model import WorldModel


def _entity(
    eid: int,
    *,
    etype: str = "button",
    label: str,
    bounds=(0.0, 0.0, 40.0, 40.0),
    description: str = "",
    role: str = "AXButton",
) -> Entity:
    attrs: Dict = {}
    if description:
        attrs["description"] = description
    return Entity(
        id=eid,
        entity_type=etype,
        semantic_role=label,
        label=label,
        role=role,
        bounds=bounds,
        actions=["click"],
        attributes=attrs,
        visible=True,
    )


def _seed(entities: List[Entity], app: str = "WhatsApp") -> WorldModel:
    wm = WorldModel()
    wm.active_app = app
    wm.entities = {e.id: e for e in entities}
    wm.tracker._entities = dict(wm.entities)
    wm.tracker._next_id = max(e.id for e in entities) + 1 if entities else 1
    return wm


def test_voice_does_not_resolve_to_voice_message():
    wm = _seed(
        [
            _entity(1, label="Voice message", bounds=(1600, 1000, 48, 48)),
            _entity(2, label="Voice", bounds=(900, 40, 36, 36)),
            _entity(3, label="Type a message", etype="textfield", bounds=(400, 1000, 800, 40)),
        ]
    )
    hit = resolve_whatsapp_target(wm, "Voice", action="click", action_family="start_call")
    assert hit is not None
    assert hit.label == "Voice"
    assert hit.id == 2


def test_dismiss_later_does_not_pick_end_call():
    wm = _seed(
        [
            _entity(1, label="End Call", bounds=(900, 700, 80, 40)),
            _entity(2, label="Later", bounds=(500, 400, 60, 32)),
        ]
    )
    hit = resolve_whatsapp_target(wm, "Later", action="click", action_family="dismiss")
    assert hit is not None
    assert hit.label == "Later"
    bad = resolve_whatsapp_target(
        wm, "Later", action="click", action_family="dismiss", target_entity_id=1
    )
    assert bad is not None
    assert bad.label == "Later"


def test_empty_label_contact_falls_back_to_labeled_row():
    wm = _seed(
        [
            _entity(2, label="", bounds=(78, 91, 355, 32), description=""),
            _entity(5, label="Kulvinder Ji", bounds=(40, 200, 280, 48)),
            _entity(6, label="Papaji", bounds=(40, 260, 280, 48)),
        ]
    )
    # Wrong capability id with empty label must be rejected
    hit = resolve_whatsapp_target(
        wm,
        "Kulvinder Ji",
        action="click",
        action_family="open_contact",
        target_entity_id=2,
    )
    assert hit is not None
    assert "kulvinder" in (hit.label or "").lower()
    assert hit.id == 5


def test_contact_open_does_not_pick_avatar_image_node():
    wm = _seed(
        [
            _entity(1, label="Kulvinder Ji", etype="image", bounds=(60, 60, 48, 48), description="Profile photo"),
            _entity(2, label="Kulvinder Ji", bounds=(40, 200, 280, 48)),
            _entity(3, label="Papaji", bounds=(40, 260, 280, 48)),
        ]
    )
    hit = resolve_whatsapp_target(
        wm,
        "Kulvinder Ji",
        action="click",
        action_family="open_contact",
    )
    assert hit is not None
    assert hit.id == 2
    assert hit.entity_type != "image"


def test_sidebar_band_excludes_right_pane_header_like_row():
    ents = [
        _entity(1, label="Kulvinder Ji", bounds=(40, 200, 280, 48)),
        _entity(2, label="Kulvinder Ji", bounds=(551, 65, 260, 44)),
    ]
    assert in_sidebar_band(ents[0], ents) is True
    assert in_sidebar_band(ents[1], ents) is False


def test_contact_resolution_prefers_sidebar_row_over_right_header_match():
    wm = _seed(
        [
            _entity(1, label="Kulvinder Ji", bounds=(40, 200, 280, 48)),
            _entity(2, label="Kulvinder Ji", bounds=(551, 65, 260, 44)),
            _entity(3, label="Type a message", etype="textfield", bounds=(400, 900, 600, 40)),
        ]
    )
    hit = resolve_whatsapp_target(
        wm,
        "Kulvinder Ji",
        action="click",
        action_family="open_contact",
    )
    assert hit is not None
    assert hit.id == 1


def test_leftover_end_call_sets_leftover_call():
    wm = _seed(
        [
            _entity(1, label="End Call", bounds=(900, 700, 80, 40)),
            _entity(2, label="Papaji", bounds=(40, 200, 200, 40)),
            _entity(3, label="Type a message", etype="textfield", bounds=(400, 900, 600, 40)),
        ]
    )
    view = WhatsAppWorldView.from_world_model(wm)
    assert view.call_state in {"ringing", "maybe_end_call"}
    overlay = WhatsAppOverlay()
    goal = Goal(kind="whatsapp_voice_call", contact="Now")
    feats = overlay.features(wm, goal)
    assert feats.leftover_call is True


def test_call_window_title_sets_leftover_call_without_end_button():
    wm = _seed(
        [
            _entity(1, label="Papaji", bounds=(40, 200, 200, 40)),
            _entity(2, label="Type a message", etype="textfield", bounds=(400, 900, 600, 40)),
        ]
    )
    wm.last_window_name = "Kulvinder Ji - WhatsApp video call"
    view = WhatsAppWorldView.from_world_model(wm)
    assert view.call_state == "ringing"
    assert view.screen == "CALLING"
    overlay = WhatsAppOverlay()
    goal = Goal(kind="whatsapp_forward_message", contact="Kulvinder", target_contact="Pallavi", link_query="z")
    feats = overlay.features(wm, goal)
    assert feats.leftover_call is True


def test_forward_phase_blocks_pallavi_type_before_source():
    wm = _seed(
        [
            _entity(1, label="Papaji", bounds=(40, 200, 200, 40)),
            _entity(2, label="Search", etype="textfield", bounds=(40, 40, 280, 32)),
            _entity(3, label="Kulvinder Ji", bounds=(40, 260, 200, 40)),
        ]
    )
    overlay = WhatsAppOverlay()
    goal = Goal(
        kind="whatsapp_forward_message",
        contact="Kulvinder",
        target_contact="Pallavi",
        link_query="zaroortwala",
    )
    feats = overlay.features(wm, goal)
    assert feats.extras.get("forward_phase") in {"OPEN_SOURCE", "PRECLEAR"}
    cands = enumerate_candidates(goal, wm, feats, overlay)
    dest_types = [
        a
        for a in cands
        if a.action_family == "type_query" and "pallavi" in (a.text or "").lower()
    ]
    assert dest_types == []
    select_dest = [a for a in cands if a.action_family == "select_forward_target"]
    assert select_dest == []


def test_open_contact_is_demoted_after_source_open_in_forward():
    wm = _seed(
        [
            _entity(
                1,
                label="Messages in chat with Kulvinder Ji",
                etype="static",
                bounds=(400, 20, 400, 30),
            ),
            _entity(2, label="Kulvinder Ji", bounds=(40, 200, 280, 48)),
            _entity(3, label="Type a message", etype="textfield", bounds=(400, 900, 600, 40)),
        ]
    )
    overlay = WhatsAppOverlay()
    goal = Goal(
        kind="whatsapp_forward_message",
        contact="Kulvinder",
        target_contact="Pallavi",
        link_query="zaroortwala",
    )
    feats = overlay.features(wm, goal)
    assert feats.extras.get("forward_phase") in {"FIND_LINK", "OPEN_FORWARD"}
    from plugin.agent.action import Action
    from plugin.agent.policy.value import predicted_value_delta

    bad = Action(action="Click", semantic_target="Kulvinder Ji", action_family="open_contact")
    assert predicted_value_delta(bad, feats, goal) < 0


def test_forward_phase_find_link_no_dest_type():
    wm = _seed(
        [
            _entity(
                1,
                label="Messages in chat with Kulvinder Ji",
                etype="static",
                bounds=(400, 20, 400, 30),
            ),
            _entity(2, label="Type a message", etype="textfield", bounds=(400, 900, 600, 40)),
            _entity(3, label="hello world", etype="static", bounds=(450, 400, 300, 40)),
        ]
    )
    # Force open conversation via view heuristics: set label that view parses
    wm.entities[1].label = "Messages in chat with Kulvinder Ji"
    overlay = WhatsAppOverlay()
    goal = Goal(
        kind="whatsapp_forward_message",
        contact="Kulvinder",
        target_contact="Pallavi",
        link_query="zaroortwala",
    )
    view = WhatsAppWorldView.from_world_model(wm)
    phase = _infer_forward_phase(goal, wm, view, leftover=False)
    assert phase == "FIND_LINK"
    feats = StateFeatures(
        conversation_open=True,
        extras={
            "forward_phase": phase,
            "open_conversation": view.open_conversation or "Kulvinder Ji",
        },
    )
    cands = enumerate_candidates(goal, wm, feats, overlay)
    dest_types = [
        a
        for a in cands
        if a.action_family == "type_query" and "pallavi" in (a.text or "").lower()
    ]
    assert dest_types == []


def test_open_source_emits_search_typing_when_search_surface_visible():
    wm = _seed(
        [
            _entity(1, label="Search", etype="button", bounds=(40, 80, 120, 30)),
            _entity(2, label="Kulvinder Ji", bounds=(40, 200, 200, 40)),
            _entity(3, label="Type a message", etype="textfield", bounds=(400, 900, 600, 40)),
        ]
    )
    overlay = WhatsAppOverlay()
    goal = Goal(
        kind="whatsapp_forward_message",
        contact="Kulvinder",
        target_contact="Pallavi",
        link_query="zarooratwala",
    )
    feats = overlay.features(wm, goal)
    assert feats.extras.get("forward_phase") == "OPEN_SOURCE"
    cands = enumerate_candidates(goal, wm, feats, overlay)
    assert any(a.action_family == "type_query" and (a.text or "").lower() == "kulvinder" for a in cands)
    assert any(a.action_family == "open_search" for a in cands)


def test_type_query_never_binds_to_sidebar_search_button():
    wm = _seed(
        [
            _entity(1, label="Search", etype="button", bounds=(40, 80, 120, 30)),
            _entity(2, label="Search", etype="textfield", bounds=(40, 120, 320, 30)),
            _entity(3, label="Type a message", etype="textfield", bounds=(400, 900, 600, 40)),
        ]
    )
    hit = resolve_whatsapp_target(
        wm,
        "Search",
        action="type",
        action_family="type_query",
        target_entity_id=1,
    )
    assert hit is not None
    assert hit.entity_type == "textfield"
    assert hit.id == 2


def test_forward_message_does_not_pick_composer_share():
    wm = _seed(
        [
            _entity(1, label="Kulvinder Ji", bounds=(900, 20, 180, 34), role="AXStaticText"),
            _entity(2, label="Share", bounds=(450, 1000, 72, 36), description="Attachment"),
            _entity(3, label="Type a message", etype="textfield", bounds=(400, 1000, 800, 40)),
        ]
    )
    hit = resolve_whatsapp_target(wm, "Share", action="click", action_family="forward_message")
    assert hit is None


def test_voice_message_does_not_set_voice_call_available():
    wm = _seed(
        [
            _entity(1, label="Voice message", bounds=(1600, 1000, 48, 48)),
            _entity(2, label="Type a message", etype="textfield", bounds=(400, 1000, 800, 40)),
            _entity(
                3,
                label="Messages in chat with Now",
                etype="static",
                bounds=(500, 20, 300, 28),
            ),
        ]
    )
    view = WhatsAppWorldView.from_world_model(wm)
    assert view.voice_call_available is False


def test_open_conversation_does_not_leak_timeline_reply_text():
    wm = _seed(
        [
            _entity(1, label="Replying to Kulvinder Ji. Your message, Hello", etype="static", bounds=(500, 500, 420, 40)),
            _entity(2, label="Type a message", etype="textfield", bounds=(400, 1000, 800, 40)),
            _entity(3, label="Search", etype="button", bounds=(40, 80, 120, 30)),
        ]
    )
    view = WhatsAppWorldView.from_world_model(wm)
    assert view.open_conversation in {None, ""}


def test_open_conversation_does_not_leak_numeric_message_blob():
    wm = _seed(
        [
            _entity(
                1,
                label="added + 1,6 4 6,6 4 2,8 4 9 8, 6:10 AM",
                etype="static",
                bounds=(500, 20, 420, 34),
            ),
            _entity(2, label="Type a message", etype="textfield", bounds=(400, 1000, 800, 40)),
        ]
    )
    view = WhatsAppWorldView.from_world_model(wm)
    assert view.open_conversation in {None, ""}


def test_open_conversation_ignores_unread_badge_text():
    wm = _seed(
        [
            _entity(1, label="1 unread message", etype="unknown", bounds=(80, 20, 180, 28)),
            _entity(2, label="Kulvinder Ji", etype="button", bounds=(40, 200, 260, 48)),
            _entity(3, label="Type a message", etype="textfield", bounds=(400, 1000, 800, 40)),
        ]
    )
    view = WhatsAppWorldView.from_world_model(wm)
    assert view.open_conversation in {None, ""}


def test_open_conversation_ignores_date_separator_text():
    wm = _seed(
        [
            _entity(1, label="Friday", etype="static", bounds=(500, 20, 100, 24)),
            _entity(2, label="Type a message", etype="textfield", bounds=(400, 1000, 800, 40)),
        ]
    )
    view = WhatsAppWorldView.from_world_model(wm)
    assert view.open_conversation in {None, ""}


def test_open_conversation_ignores_generic_header_chips():
    wm = _seed(
        [
            _entity(1, label="All", etype="button", bounds=(40, 40, 80, 30)),
            _entity(2, label="Chats", etype="button", bounds=(140, 40, 80, 30)),
            _entity(3, label="Type a message", etype="textfield", bounds=(400, 1000, 800, 40)),
        ]
    )
    view = WhatsAppWorldView.from_world_model(wm)
    assert view.open_conversation in {None, ""}


def test_stale_ringing_not_success_without_start_call():
    wm = _seed(
        [
            _entity(1, label="End Call", bounds=(900, 700, 80, 40)),
            _entity(2, label="Calling Now…", etype="static", bounds=(500, 100, 200, 30)),
        ]
    )
    overlay = WhatsAppOverlay()
    goal = Goal(
        kind="whatsapp_voice_call",
        contact="Now",
        require_agent_initiated_call=True,
        require_contact_in_call=True,
    )
    status = overlay.evaluate_goal(goal, wm)
    assert status.succeeded is False
    assert "start_call" in status.reason or "stale" in status.reason


def test_chat_list_not_false_calling():
    """Nav Calls tab + end-to-end banner must not be perceived as an active call."""
    wm = _seed(
        [
            _entity(1, label="Chats", bounds=(40, 40, 60, 30)),
            _entity(2, label="Calls", bounds=(120, 40, 60, 30)),
            _entity(3, label="List of chats", etype="static", bounds=(40, 100, 300, 400)),
            _entity(4, label="end-to-end encrypted", etype="static", bounds=(400, 500, 200, 20)),
            _entity(5, label="Search", etype="textfield", bounds=(40, 80, 280, 32)),
            # Ghost zero-bound End Call must not force CALLING
            _entity(6, label="End Call", bounds=(0, 0, 0, 0)),
        ]
    )
    view = WhatsAppWorldView.from_world_model(wm)
    assert view.call_state != "ringing"
    assert view.screen != "CALLING"
    from plugin.worldmodel.screens.detect import guess_screen_label

    assert guess_screen_label(list(wm.entities.values())) != "call"


def test_calling_text_in_chat_list_does_not_force_call_state():
    wm = _seed(
        [
            _entity(1, label="Chats", bounds=(40, 40, 60, 30)),
            _entity(2, label="Calls", bounds=(120, 40, 60, 30)),
            _entity(3, label="List of chats", etype="static", bounds=(40, 100, 300, 400)),
            _entity(4, label="Calling now", etype="static", bounds=(420, 180, 200, 24)),
            _entity(5, label="Search", etype="textfield", bounds=(40, 80, 280, 32)),
        ]
    )
    view = WhatsAppWorldView.from_world_model(wm)
    assert view.call_state != "ringing"
    assert view.screen != "CALLING"


def test_end_call_candidates_only_when_visible():
    wm = _seed(
        [
            _entity(1, label="Papaji", bounds=(40, 200, 200, 40)),
            _entity(2, label="Search", etype="textfield", bounds=(40, 40, 280, 32)),
        ]
    )
    overlay = WhatsAppOverlay()
    goal = Goal(kind="whatsapp_forward_message", contact="Kulvinder", target_contact="Pallavi", link_query="z")
    feats = overlay.features(wm, goal)
    # No End Call in world → no end_call family from leftover spam
    cands = enumerate_candidates(goal, wm, feats, overlay)
    end_cands = [a for a in cands if a.action_family == "end_call"]
    assert end_cands == []
