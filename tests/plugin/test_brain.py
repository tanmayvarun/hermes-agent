"""Brain owns capability choice after critic; perception does not."""

from __future__ import annotations

from typing import Any, Dict

from plugin.agent.brain import choose_next_capability, publish_brain_choice
from plugin.agent.features import StateFeatures
from plugin.agent.goal import Goal
from plugin.agent.unified_cognition import UnifiedProposal


def _goal() -> Goal:
    return Goal(
        kind="whatsapp_forward_message",
        contact="Kulvinder",
        target_contact="Pallavi",
        link_query="zarooratwala",
    )


class _State:
    def __init__(self, document: Dict[str, Any], frontier: Dict[str, Any] | None = None) -> None:
        self.unified_world_document = document
        self.focused_field_role = str(document.get("focused_field_role") or "")
        self.last_plan_step = None
        self.search_attempt_log: list = []
        self.last_affordance_frontier = frontier or {
            "surface": document.get("surface") or "",
            "observed_actions": [
                {"family": "resolve_entity", "target_label": "Kulvinder", "target_id": "row-1"}
            ],
            "latent_actions": [],
            "probe_actions": [],
        }


class _Chooser:
    def __init__(self, payload: Dict[str, Any]) -> None:
        self.payload = payload
        self.packets: list = []

    def choose(self, system: str, packet: Dict[str, Any]) -> Dict[str, Any]:
        self.packets.append(packet)
        return self.payload


def test_brain_chooses_and_grounds_on_frontier_context():
    proposal = UnifiedProposal(
        world_model={"surface": "search"},
        observed_state={"surface": "search"},
        suggested_actions=[
            {
                "rank": 1,
                "family": "resolve_entity",
                "text": "Kulvinder",
                "target_id": "row-1",
                "why": "search result row matches source contact",
                "confidence": 0.85,
            }
        ],
        recommended_probe={"family": "hover", "target_id": "row-1", "may_reveal": ["Open"]},
        confidence=0.8,
    )
    assert proposal.next_action == {}
    features = StateFeatures(app="WhatsApp", extras={})
    state = _State(
        {
            "surface": "search",
            "objects": [{"id": "row-1", "text": "Kulvinder", "point": [12, 34]}],
        }
    )
    chooser = _Chooser(
        {"capability": "resolve_entity", "target": "Kulvinder", "why": "row", "confidence": 0.9}
    )
    trace = choose_next_capability(
        proposal, _goal(), features=features, execution_state=state, chooser=chooser
    )
    assert trace.get("applied") is True
    assert proposal.next_action["family"] == "resolve_entity"
    assert proposal.next_action["target_id"] == "row-1"
    assert proposal.next_action["target_point"] == [12, 34]
    packet = chooser.packets[0]
    assert "affordance_frontier" in packet
    assert packet["perceptor_suggestions"][0]["why"].startswith("search result")
    # Suggestions do not auto-execute: brain still chose via chooser.
    assert proposal.next_action["family"] == "resolve_entity"

    publish_brain_choice(features, proposal, trace)
    assert features.extras["brain_choice"]["family"] == "resolve_entity"
