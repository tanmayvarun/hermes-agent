"""Fusion eval grades multimodal readings against gold, not self-agreement.

Action choice is the brain's job — fusion scores surface / objects / echo only.
"""

from __future__ import annotations

from plugin.evals.corpus import (
    Fixture,
    TRAIT_NO_AX_CONTENT,
    TRAIT_SHELL_ONLY,
    TRAIT_TARGET_VISIBLE,
)
from plugin.evals.fusion import (
    score_fusion_reading,
    summarize_fusion,
    fusion_ax_blind_content_recall,
)


def _fixture(
    *,
    surface: str = "search",
    traits: tuple = (TRAIT_SHELL_ONLY, TRAIT_NO_AX_CONTENT, TRAIT_TARGET_VISIBLE),
    response: dict | None = None,
    ax_content: int = 0,
) -> Fixture:
    return Fixture(
        id="open_source/frame_test",
        phase="open_source",
        packet={
            "goal": {
                "operation": "whatsapp_forward_message",
                "source_conversation": "Kulvinder",
                "source_query": "zarooratwala",
                "destination": "Pallavi",
            },
            "observation": {
                "ax_content_node_count": ax_content,
                "ax_evidence": [
                    {"id": "app", "role": "AXApplication", "label": "WhatsApp"},
                ],
            },
            "world_model": {"surface": "chat_list", "objects": []},
        },
        response=response,
        annotation={
            "surface": surface,
            "sources": {"surface": "manual"},
        },
        traits=traits,
        screenshot={"recorded": True, "name": "frame_test.png"},
    )


def test_good_fusion_on_ax_blind_search_frame_passes():
    """AX chrome-only + vision objects = fusion succeeded (no action required)."""
    fixture = _fixture(
        response={
            "world_model": {
                "surface": "search",
                "open_conversation": "",
                "objects": [
                    {
                        "id": "row",
                        "kind": "search_result",
                        "text": "Kulvinder Ji - zarooratwala.com",
                        "matches_goal": True,
                        "point": [120, 240],
                    }
                ],
            },
            "model": "good-model",
        }
    )
    score = score_fusion_reading(fixture, fixture.response)
    assert score.score == 1.0, score.failures()
    names = {c.name for c in score.checks if c.passed}
    assert "sees_content_when_ax_blind" in names
    assert "goal_object_identified" in names
    assert "surface_matches_gold" in names


def test_search_echo_as_open_conversation_fails_fusion():
    """Treating the typed query as the open chat is the live promotion bug."""
    fixture = _fixture(
        response={
            "world_model": {
                "surface": "search",
                "open_conversation": "zarooratwala Kulvinder",
                "objects": [
                    {
                        "id": "row",
                        "text": "Kulvinder Ji",
                        "matches_goal": True,
                        "point": [120, 240],
                    }
                ],
            },
        }
    )
    score = score_fusion_reading(fixture, fixture.response)
    echo = next(c for c in score.checks if c.name == "open_conversation_not_search_echo")
    assert not echo.passed


def test_ax_blind_frame_with_no_objects_fails_content_recall():
    fixture = _fixture(
        response={
            "world_model": {"surface": "search", "objects": []},
        }
    )
    metric = fusion_ax_blind_content_recall([fixture])
    assert metric.scored == 1
    assert metric.value == 0.0


def test_summarize_fusion_over_corpus_smoke():
    fixtures = [
        _fixture(
            response={
                "world_model": {
                    "surface": "search",
                    "objects": [
                        {
                            "id": "row",
                            "text": "Kulvinder Ji zarooratwala",
                            "matches_goal": True,
                            "point": [1, 2],
                        }
                    ],
                },
            }
        )
    ]
    report = summarize_fusion(fixtures)
    assert report["fixtures_scored"] == 1
    assert report["mean_fusion_score"] == 1.0
    names = {m["name"] for m in report["metrics"]}
    assert "fusion_surface_accuracy" in names
    assert "fusion_ax_blind_content_recall" in names
    assert "fusion_action_contract" not in names
