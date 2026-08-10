"""Contract: DecisionEngine.define_action_step has no promote/enumerate/selector fallthrough."""

from __future__ import annotations

from plugin.agent.decision import DecisionEngine
from plugin.agent.goal import Goal
from plugin.agent.runtime.state import ExecutionState
from plugin.worldmodel.entities.entity import Entity
from plugin.worldmodel.model import WorldModel


def test_decide_observes_without_unified_and_never_types_from_hypotheses():
    """When unified declines (hermetic default: off), decide Observes.

    It must not SearchConversation / type_query from hypothesis ranking.
    """
    wm = WorldModel()
    wm.active_app = "WhatsApp"
    ents = [
        Entity(
            id=1,
            entity_type="button",
            label="Chats",
            semantic_role="Chats",
            role="AXButton",
            actions=["click"],
            visible=True,
        ),
        Entity(
            id=2,
            entity_type="static",
            label="Search",
            semantic_role="Search",
            role="AXStaticText",
            actions=[],
            visible=True,
        ),
    ]
    wm.entities = {e.id: e for e in ents}
    wm.tracker._entities = dict(wm.entities)
    wm.tracker._next_id = 3

    decision = DecisionEngine().define_action_step(
        Goal(kind="whatsapp_voice_call", contact="Pallavi"),
        wm,
        ExecutionState(),
    )
    assert decision is not None
    assert decision.action == "Observe"
    assert decision.action_family == "observe"
    assert "unified_declined_no_legacy_fallthrough" in (decision.rationale or "")
    assert decision.action_family != "type_query"
    assert (decision.text or "") == ""
