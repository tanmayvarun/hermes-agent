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
