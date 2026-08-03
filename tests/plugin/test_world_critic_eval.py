"""World-critic representation eval suite must stay green."""

from __future__ import annotations

from plugin.experiments.world_critic_eval import (
    evaluate_world_critic_scenarios,
    evaluate_world_critic_trajectories,
    score_accepted_representation,
    world_critic_scenarios,
)
from plugin.agent.world_critic import critique_world_proposal


def test_all_world_critic_scenarios_pass():
    report = evaluate_world_critic_scenarios()
    assert report["failed"] == [], report


def test_all_world_critic_trajectories_pass():
    report = evaluate_world_critic_trajectories()
    assert report["failed"] == [], report


def test_scenario_catalog_covers_forward_prompt_screens():
    names = {s.name for s in world_critic_scenarios()}
    # Spot-check each phase of Pallavi → zarooratwala → Tanmay.
    for required in (
        "s01_chat_list_to_sidebar_search",
        "s03_search_opens_pallavi_conversation",
        "s05_conversation_locate_zarooratwala",
        "s09_reveal_forward_menu",
        "s12_accept_forward_picker_after_invoke",
        "s15_reject_picker_to_sidebar_search",
        "s17_dialog_over_picker_keeps_open",
    ):
        assert required in names, required


def test_score_accepted_representation_flags_motor_scripts():
    prior = {"surface": "conversation", "open_conversation": "Pallavi"}
    proposal = {
        "surface": "conversation",
        "open_conversation": "Pallavi",
        "progress": {"phase": "", "objective": "", "notes": "use Cmd+F then keydown"},
    }
    verdict = critique_world_proposal(prior, proposal, last_action="locate_content")
    checks = score_accepted_representation(
        prior=prior,
        proposal=proposal,
        accepted=verdict.accepted_document,
        verdict=verdict,
        expect_surface="conversation",
        expect_open="Pallavi",
    )
    by_name = {c.name: c for c in checks}
    assert by_name["representation_has_no_motor_scripts"].passed is False
