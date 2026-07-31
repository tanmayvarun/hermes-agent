from __future__ import annotations

from plugin.agent.whatsapp_view import (
    WhatsAppWorldView,
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
