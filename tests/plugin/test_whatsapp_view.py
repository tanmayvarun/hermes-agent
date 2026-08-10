from __future__ import annotations

from plugin.agent.whatsapp_view import (
    WhatsAppWorldView,
    conversation_message_rows_from_entities,
    conversation_timeline_clusters_from_entities,
    _header_conversation_text,
    _is_contact_name,
    _normalize_open_conversation_text,
)
from plugin.worldmodel.entities.entity import Entity
from plugin.worldmodel.model import WorldModel


def _world_with(*entities: Entity) -> WorldModel:
    wm = WorldModel()
    wm.active_app = "WhatsApp"
    wm.entities = {e.id: e for e in entities}
    wm.tracker._entities = dict(wm.entities)
    wm.tracker._next_id = max((e.id for e in entities), default=0) + 1
    return wm


def test_date_fragment_is_not_treated_as_contact_name():
    assert _is_contact_name("Fri, 24 Jul") is False
    assert _is_contact_name("24 Jul") is False
    assert _normalize_open_conversation_text("Fri, 24 Jul") == ""
    assert _normalize_open_conversation_text("24 Jul") == ""


def test_header_conversation_text_rejects_date_fragments():
    date_row = Entity(
        id=1,
        entity_type="static",
        semantic_role="Fri, 24 Jul",
        label="Fri, 24 Jul",
        role="AXStaticText",
        visible=True,
        bounds=(600, 20, 140, 24),
    )
    assert _header_conversation_text(date_row) == ""


def test_world_view_does_not_promote_date_separator_as_open_conversation():
    wm = _world_with(
        Entity(
            id=1,
            entity_type="static",
            semantic_role="Fri, 24 Jul",
            label="Fri, 24 Jul",
            role="AXStaticText",
            visible=True,
            bounds=(600, 20, 140, 24),
        ),
        Entity(
            id=2,
            entity_type="static",
            semantic_role="Chat history",
            label="Messages in chat with Kulvinder Ji",
            role="AXStaticText",
            visible=True,
            bounds=(600, 80, 380, 28),
        ),
    )

    view = WhatsAppWorldView.from_world_model_raw(wm)
    assert view.open_conversation == "Kulvinder Ji"


def test_sidebar_region_message_noise_is_not_promoted_into_conversation_messages():
    wm = _world_with(
        Entity(
            id=1,
            entity_type="static",
            semantic_role="Sent to Kulvinder Ji",
            label="Sent to Kulvinder Ji",
            role="AXStaticText",
            visible=True,
            bounds=(40, 160, 260, 56),
            attributes={"description": "Sidebar row"},
        ),
        Entity(
            id=2,
            entity_type="static",
            semantic_role="Sent to Pallavi",
            label="Sent to Pallavi",
            role="AXStaticText",
            visible=True,
            bounds=(900, 420, 340, 56),
            attributes={"description": "Timeline row"},
        ),
    )
    wm.last_scene_graph = {
        "regions": [
            {"id": "sidebar", "kind": "sidebar", "entity_ids": [1]},
            {"id": "timeline", "kind": "timeline", "entity_ids": [2]},
        ]
    }
    texts = [
        row["text"]
        for row in conversation_message_rows_from_entities(wm.entities.values(), scene_graph=wm.last_scene_graph)
    ]

    assert any("Sent to Pallavi" in text for text in texts)
    assert all("Sent to Kulvinder Ji" not in text for text in texts)


def test_chat_list_voice_preview_is_not_conversation_surface():
    """Live 092106: sidebar 'Voice message' preview made screen=CONVERSATION
    with empty open_conversation, freezing the forward task in OPEN_SOURCE.
    """
    wm = _world_with(
        Entity(
            id=1,
            entity_type="static",
            semantic_role="Chats",
            label="Chats",
            role="AXStaticText",
            visible=True,
            bounds=(40, 20, 80, 24),
        ),
        Entity(
            id=2,
            entity_type="static",
            semantic_role="Q Search",
            label="Q Search",
            role="AXStaticText",
            visible=True,
            bounds=(40, 50, 200, 28),
        ),
        Entity(
            id=3,
            entity_type="static",
            semantic_role="Pallavi",
            label="Pallavi",
            role="AXStaticText",
            visible=True,
            bounds=(40, 200, 220, 40),
        ),
        Entity(
            id=4,
            entity_type="static",
            semantic_role="I U Voice message (0:28)",
            label="I U Voice message (0:28)",
            role="AXStaticText",
            visible=True,
            bounds=(40, 240, 260, 36),
        ),
        Entity(
            id=5,
            entity_type="static",
            semantic_role="Godrej Nurture - Care & Share",
            label="Godrej Nurture - Care & Share",
            role="AXStaticText",
            visible=True,
            bounds=(40, 300, 280, 40),
        ),
    )
    view = WhatsAppWorldView.from_world_model_raw(wm)
    assert view.screen == "LIST"
    assert not view.open_conversation
    assert not view.conversation_messages


def test_conversation_timeline_clusters_capture_visible_urls_and_text():
    wm = _world_with(
        Entity(
            id=1,
            entity_type="static",
            semantic_role="Messages in chat with Kulvinder Ji",
            label="Messages in chat with Kulvinder Ji",
            role="AXStaticText",
            visible=True,
            bounds=(600, 20, 380, 28),
        ),
        Entity(
            id=2,
            entity_type="static",
            semantic_role="Zarooratwala – Fresh Groceries Delivered",
            label="Zarooratwala – Fresh Groceries Delivered",
            role="AXStaticText",
            visible=True,
            bounds=(920, 420, 360, 56),
            attributes={"description": "https://www.zarooratwala.com/?utm_source=ig"},
        ),
        Entity(
            id=3,
            entity_type="menu",
            semantic_role="Format",
            label="Format",
            role="AXMenuItem",
            visible=True,
            bounds=(40, 20, 100, 30),
        ),
    )
    clusters = conversation_timeline_clusters_from_entities(wm.entities.values(), scene_graph=wm.last_scene_graph)

    assert clusters
    assert any("zarooratwala" in (cluster.get("text") or "").lower() for cluster in clusters)
    assert any(
        "zarooratwala.com" in str(url).lower()
        for cluster in clusters
        for url in (cluster.get("urls") or [])
    )


def test_conversation_timeline_fallback_recovers_mislabelled_message_rows():
    wm = _world_with(
        Entity(
            id=1,
            entity_type="static",
            semantic_role="Forwarded message",
            label="Your message, Link, https://www.zarooratwala.com/?utm_source=ig",
            role="AXStaticText",
            visible=True,
            bounds=(920, 420, 420, 56),
            attributes={"description": "Sidebar mislabel"},
        ),
        Entity(
            id=2,
            entity_type="button",
            semantic_role="Kulvinder Ji",
            label="Kulvinder Ji",
            role="AXButton",
            visible=True,
            bounds=(40, 200, 160, 56),
        ),
    )
    wm.last_scene_graph = {
        "regions": [
            {"id": "sidebar", "kind": "sidebar", "entity_ids": [1, 2]},
        ]
    }

    rows = conversation_message_rows_from_entities(wm.entities.values(), scene_graph=wm.last_scene_graph)
    clusters = conversation_timeline_clusters_from_entities(wm.entities.values(), scene_graph=wm.last_scene_graph)

    assert any("zarooratwala.com" in (row["text"] or "").lower() for row in rows)
    assert any("zarooratwala.com" in (cluster.get("text") or "").lower() for cluster in clusters)


def test_the_search_box_reading_itself_back_is_not_an_open_chat():
    """The header band contains the search field, so its text arrives as a
    candidate chat title. On this app that text is OCR'd, and three live runs
    confirmed the source conversation off their own query -- 'Kulvinderr',
    'Kulvinder]', 'Kulvinderng' for a typed 'Kulvinder' -- which skipped the step
    that actually opens the chat and left the agent hunting a forward affordance
    on a search screen until the clock ran out.
    """
    from plugin.agent.whatsapp_view import _echoes_search_query

    for misread in ("Kulvinder", "Kulvinderr", "Kulvinder]", "Kulvinderng"):
        assert _echoes_search_query(misread, "Kulvinder"), misread
    assert _echoes_search_query("ZarooratWala", "zarooratwala")


def test_a_real_chat_title_survives_the_echo_guard():
    """'Kulvinder Ji' is the chat this task must open while 'Kulvinder' is still
    in the search box. A prefix test alone would erase the belief at the exact
    moment it first becomes true, so the guard compares word counts first.
    """
    from plugin.agent.whatsapp_view import _echoes_search_query

    assert not _echoes_search_query("Kulvinder Ji", "Kulvinder")
    assert not _echoes_search_query("Pallavi", "Kulvinder")
    # Too short to be evidence either way: do not disqualify on three letters.
    assert not _echoes_search_query("Ram", "Ram")


def test_an_icon_glyph_does_not_disguise_a_search_echo():
    """'Q Kulvinder' is the search field, not a chat named Q Kulvinder.

    The magnifier icon carries no text, so the reader emits whatever letter it
    resembles next to the typed query. That stray token adds a word, and a
    word-count comparison then reads a pure echo as a two-word contact name. A
    live run reached the forward phase believing the open conversation was
    'Q Kulvinder' one action after typing 'Kulvinder' into the field.
    """
    from plugin.agent.whatsapp_view import _echoes_search_query

    assert _echoes_search_query("Q Kulvinder", "Kulvinder")
    assert _echoes_search_query("a zaroratwala link Kulvinder", "zarooratwala link Kulvinder")
    # The placeholder itself is the field whatever has been typed.
    assert _echoes_search_query("Q Search", "Kulvinder")
    assert _echoes_search_query("Search", "anything at all")

    # The real target must still survive: it adds a genuine word, not a glyph.
    assert not _echoes_search_query("Kulvinder Ji", "Kulvinder")
    assert not _echoes_search_query("Pallavi", "Kulvinder")


def test_the_echo_guard_remembers_the_query_it_cannot_read():
    """The frame that needs the query is the frame that lost it.

    The field's text gets taken for the chat title, which is the confusion the
    guard exists to catch -- and it is also why ``search_query`` is empty on
    exactly that frame, leaving the guard nothing to compare against. Live runs
    reached the forward phase believing the open conversation was
    'Q zarooratwala Kulvinder', their own query with the magnifier glyph read
    onto the front, with search_query blank beside it.
    """
    from plugin.agent.whatsapp_view import WhatsAppWorldView
    from plugin.worldmodel.model import WorldModel

    world = WorldModel()
    world.active_app = "WhatsApp"
    world.last_search_query = "zarooratwala Kulvinder"
    world.last_perception_synthesis = {
        "summary": {
            "screen_type": "search",
            "open_conversation": "Q zarooratwala Kulvinder",
        }
    }

    view = WhatsAppWorldView.from_world_model(world)
    assert not view.open_conversation, (
        "the field reading itself back is not an open chat, "
        "even on a frame that could not read the field"
    )


def test_a_real_chat_title_survives_the_remembered_query():
    """The remembered query must not erase the chat once it finally opens."""
    from plugin.agent.whatsapp_view import WhatsAppWorldView
    from plugin.worldmodel.model import WorldModel

    world = WorldModel()
    world.active_app = "WhatsApp"
    world.last_search_query = "zarooratwala Kulvinder"
    world.last_perception_synthesis = {
        "summary": {
            "screen_type": "conversation",
            "open_conversation": "Kulvinder Ji",
            "visible_objects": [{"text": "hello"}],
        }
    }

    view = WhatsAppWorldView.from_world_model(world)
    assert view.open_conversation == "Kulvinder Ji"
