"""Surface ownership: selection claims are namespaced by owner_surface."""

from plugin.agent.world_document import (
    normalize_document,
    scrub_cross_surface_selection_beliefs,
)


def test_background_selection_cannot_satisfy_destination_selected():
    doc = normalize_document(
        {
            "surface": "forward_picker",
            "objects": [
                {
                    "text": "status chrome",
                    "kind": "status",
                    "owner_surface": "conversation",
                    "semantic_role": "source_message_selection",
                },
                {
                    "text": "Search",
                    "kind": "search_input",
                    "point": [1, 2],
                    "owner_surface": "forward_picker",
                },
            ],
            "beliefs": [
                {
                    "predicate": "destination_selected",
                    "value": True,
                    "confidence": 0.95,
                    "evidence": ["background selection indicator"],
                    "owner_surface": "conversation",
                    "semantic_role": "source_message_selection",
                }
            ],
        },
        frame=3,
    )
    belief = next(
        b for b in doc["beliefs"] if b["predicate"] == "destination_selected"
    )
    assert belief["value"] is False
    assert belief.get("rejected_evidence")


def test_picker_owned_destination_selected_survives():
    doc = scrub_cross_surface_selection_beliefs(
        {
            "surface": "forward_picker",
            "objects": [
                {
                    "text": "Tanmay",
                    "selected": True,
                    "matches_goal": True,
                    "owner_surface": "forward_picker",
                    "semantic_role": "recipient",
                }
            ],
            "beliefs": [
                {
                    "predicate": "destination_selected",
                    "value": True,
                    "confidence": 0.9,
                    "owner_surface": "forward_picker",
                    "semantic_role": "destination_selection",
                    "evidence": ["recipient row checked"],
                }
            ],
        }
    )
    belief = next(
        b for b in doc["beliefs"] if b["predicate"] == "destination_selected"
    )
    assert belief["value"] is True


def test_uncorroborated_destination_selected_scrubbed_even_with_picker_owner():
    doc = scrub_cross_surface_selection_beliefs(
        {
            "surface": "forward_picker",
            "objects": [
                {"text": "Papaji", "owner_surface": "forward_picker", "point": [1, 2]}
            ],
            "beliefs": [
                {
                    "predicate": "destination_selected",
                    "value": True,
                    "confidence": 0.8,
                    "owner_surface": "forward_picker",
                    "semantic_role": "destination_selection",
                    "evidence": ["guessed from chrome"],
                }
            ],
        }
    )
    belief = next(
        b for b in doc["beliefs"] if b["predicate"] == "destination_selected"
    )
    assert belief["value"] is False
