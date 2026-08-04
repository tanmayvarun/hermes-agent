"""One perceptor: the unified reading narrates itself and feeds the decision layer.

The agent ran two vision perceptors over the same pixels. Unified cognition was
the authoritative one, but the legacy ``synthesize_perception`` still ran on
every perception cycle, forming a rival account of the screen and costing a full
multimodal round trip each time. Removing it is only safe because everything the
decision layer read from it -- the family recommendation, the screen type, the
contradictions, the human-readable run-log line -- is derivable from the unified
reading. These tests hold that derivation in place, since a silent regression
here does not crash: it degrades the agent to picking Observe forever.
"""

from __future__ import annotations

import pytest

from plugin.agent.unified_cognition import (
    UnifiedProposal,
    narrate_perception,
    unified_perception_extras,
)
from plugin.agent.world_critic import critique_world_proposal


def _proposal(**overrides) -> UnifiedProposal:
    base = dict(
        world_model={
            "surface": "search",
            "open_conversation": "",
            "objects": [
                {
                    "id": "row_kul",
                    "kind": "chat_row",
                    "text": "Kulvinder Ji",
                    "point": [100, 200],
                    "matches_goal": True,
                },
                {
                    "id": "row_zar",
                    "kind": "chat_row",
                    "text": "Zarooratwala Orders",
                    "point": [100, 260],
                },
            ],
        },
        observed_state={"surface": "search", "app": "WhatsApp"},
        next_action={"family": "open_entity", "target_label": "Kulvinder Ji"},
        coverage=1.0,
        scene_summary="Sidebar search shows two results.",
        confidence=0.72,
    )
    base.update(overrides)
    return UnifiedProposal(**base)


def _overruled_verdict(proposal: UnifiedProposal):
    """A verdict that refuses the reading: a hunt inside a conversation."""
    return critique_world_proposal(
        {"surface": "conversation", "open_conversation": "Kulvinder Ji"},
        dict(proposal.world_model),
        last_action="locate_content",
    )


def _accepted_verdict(proposal: UnifiedProposal):
    return critique_world_proposal(
        {"surface": "chat_list"}, dict(proposal.world_model), last_action="type_query"
    )


# ---------------------------------------------------------------- narration


def test_narration_reports_the_reading_and_the_objects():
    proposal = _proposal()
    text = narrate_perception(proposal, _accepted_verdict(proposal), frame=4)
    assert "Perception frame 4" in text
    assert "surface=search" in text
    # The model's own prose, not a field dump.
    assert "Sidebar search shows two results." in text
    # The inventory, with the goal match called out — the object that will be
    # clicked is the one a developer most needs to see named.
    assert "Kulvinder Ji" in text
    assert "matches goal" in text


def test_narration_reports_what_the_critic_overrode():
    """The critic's refusals are the story, so they must survive into the log.

    A reading that was overruled and one that was accepted produce identical
    accepted documents. Without the critic's half, a developer reading the log
    cannot tell which happened, and the surface they see attributed to the
    perceptor may be one the perceptor never proposed.
    """
    proposal = _proposal()
    text = narrate_perception(proposal, _overruled_verdict(proposal), frame=7)
    assert "critic overrode" in text
    assert "surface reject" in text
    # The accepted surface wins the header, not the rejected proposal.
    assert "surface=conversation" in text


def test_narration_says_so_when_the_reading_passed_intact():
    proposal = _proposal()
    text = narrate_perception(proposal, _accepted_verdict(proposal), frame=1)
    assert "accepted the update intact" in text
    assert "overrode" not in text


def test_narration_reports_coverage_and_gaps_only_when_incomplete():
    proposal = _proposal(coverage=0.6, evidence_gaps=["is the target below the fold?"])
    text = narrate_perception(proposal, None, frame=1)
    assert "coverage 0.60" in text
    assert "is the target below the fold?" in text

    # A full, gapless look should not spend a line saying so.
    full = narrate_perception(_proposal(), None, frame=1)
    assert "coverage" not in full


def test_narration_accepts_the_verdict_in_either_form():
    """The verdict is an object where produced and a dict where carried.

    ``persist_world_document`` stores ``verdict.to_dict()`` on execution state,
    so the narration is called with both shapes depending on the caller. Reading
    only attributes silently produced a critic-less narration in the live path.
    """
    proposal = _proposal()
    verdict = _overruled_verdict(proposal)
    assert narrate_perception(proposal, verdict, frame=2) == narrate_perception(
        proposal, verdict.to_dict(), frame=2
    )


def test_narration_survives_a_missing_proposal():
    assert narrate_perception(None, None) == ""


# ------------------------------------------------------- decision-layer extras


def test_extras_carry_the_family_recommendation():
    """Decision promotion and candidate scoring read these keys.

    ``policy.value.perception_synthesis_bonus`` and the family promotion in
    ``DecisionEngine.decide`` both key off likely_next_family; losing it is what
    would send the agent back to Observe forever.
    """
    proposal = _proposal()
    extras = unified_perception_extras(proposal, _accepted_verdict(proposal))
    assert extras["likely_next_family"] == "open_entity"
    assert extras["likely_next_target"] == "Kulvinder Ji"
    assert extras["active_surface"] == "search"
    assert extras["screen_type"] == "search"
    assert extras["confidence"] == pytest.approx(0.72)
    assert extras["source"] == "unified_cognition"


def test_extras_report_critic_overrides_as_contradictions():
    """A refused field *is* a contradiction, and recovery logic reads them."""
    proposal = _proposal()
    extras = unified_perception_extras(proposal, _overruled_verdict(proposal))
    contradictions = " ".join(extras["contradictions"]).lower()
    assert "surface" in contradictions
    assert extras["contradictions"], "critic refusals must surface as contradictions"


def test_extras_ask_for_another_look_when_the_model_admits_a_gap():
    """Coverage and evidence gaps replace the old mechanical agreement score.

    Cross-source agreement was the runtime guessing whether it had seen enough.
    The model's own declared gap is the same signal asked of the party that
    knows, and value scoring turns it into an observe nudge.
    """
    proposal = _proposal(coverage=0.5, evidence_gaps=["is the list scrolled?"])
    assert unified_perception_extras(proposal, None)["needs_followup_observe"] is True
    assert unified_perception_extras(_proposal(), None)["needs_followup_observe"] is False


def test_extras_do_not_invent_families_to_avoid():
    """avoid_families becomes a scoring penalty, so a guess here suppresses
    legitimate moves. The unified path withdraws dead controls through the
    affordance frontier instead."""
    assert unified_perception_extras(_proposal(), None)["avoid_families"] == []


def test_extras_survive_a_missing_proposal():
    assert unified_perception_extras(None, None) == {}


# ------------------------------------------------------------- the second call


def _count_legacy_perceptor_calls(monkeypatch, *, unified: str) -> int:
    """Run one real perception cycle and count legacy vision calls."""
    from plugin.agent import perception_cycle
    from plugin.agent.goal import Goal
    from plugin.agent.runtime.state import RuntimeState

    monkeypatch.setenv("HERMES_UNIFIED_COGNITION", unified)
    calls: list[int] = []

    def _spy(*_args, **_kwargs):
        calls.append(1)
        return None

    monkeypatch.setattr(perception_cycle, "synthesize_perception", _spy)

    runtime = RuntimeState()
    runtime.world_model.active_app = "WhatsApp"
    goal = Goal(kind="whatsapp_forward", contact="Kulvinder", target_contact="Pallavi")
    perception_cycle.build_view_features(runtime, goal, worldview=0.8)
    return len(calls)


def test_perception_cycle_does_not_run_a_second_perceptor(monkeypatch):
    """With unified cognition on, the legacy vision call must not fire.

    This is the duplicate: same pixels, a second full multimodal round trip, and
    a rival set of beliefs handed to the decision layer. Measured at roughly 17
    of 42 model calls on an 11-action live run.
    """
    assert _count_legacy_perceptor_calls(monkeypatch, unified="1") == 0


def test_legacy_perceptor_still_runs_when_unified_is_off(monkeypatch):
    """Turning unified cognition off must restore the old perceptor.

    It remains the declared fallback, and the offline suite runs with
    HERMES_UNIFIED_COGNITION=0 for hermeticity, so this is also what keeps the
    rest of the tests exercising a perceptor at all.
    """
    assert _count_legacy_perceptor_calls(monkeypatch, unified="0") == 1


# ------------------------------------------------------- enumerated inputs


def _sources(monkeypatch, *, screenshot="/tmp/frame.png", content=0, nodes=3, ocr_lines=None, ocr="1"):
    from plugin.agent.features import StateFeatures
    from plugin.agent.goal import Goal
    from plugin.agent.unified_cognition import _enumerate_sources
    from plugin.worldmodel.model import WorldModel

    monkeypatch.setenv("HERMES_PERCEPTION_OCR", ocr)
    world = WorldModel()
    world.last_screenshot_path = screenshot
    world.last_ocr_lines = list(ocr_lines or [])
    features = StateFeatures(app="WhatsApp")
    features.extras = {
        "observation_node_count": nodes,
        "app_content_node_count": content,
    }
    goal = Goal(kind="whatsapp_forward", contact="Kulvinder", target_contact="Pallavi")
    return {entry["source"]: entry for entry in _enumerate_sources(world, goal, features)}


def test_every_input_is_declared_with_its_gate_state(monkeypatch):
    """The model fuses, so it must be told what it was given."""
    entries = _sources(monkeypatch)
    assert set(entries) == {"screenshot", "accessibility", "ocr"}
    assert all(entry.get("why") for entry in entries.values())


def test_screenshot_is_always_on(monkeypatch):
    assert _sources(monkeypatch)["screenshot"]["state"] == "on"
    assert _sources(monkeypatch, screenshot="")["screenshot"]["state"] == "unavailable"


def test_a_chrome_only_ax_tree_is_declared_as_such(monkeypatch):
    """Distinguishing 'no content exposed' from 'screen is empty'.

    WhatsApp publishes a window frame and nothing else. Reporting that as a
    normal accessibility reading invites the model to conclude the surface is
    blank, which is how the agent ended up perceiving an empty screen in front
    of a full chat list.
    """
    blind = _sources(monkeypatch, content=0, nodes=3)["accessibility"]
    assert blind["state"] == "chrome_only"
    assert "not evidence" in blind["why"]

    rich = _sources(monkeypatch, content=42, nodes=88)["accessibility"]
    assert rich["state"] == "on"

    absent = _sources(monkeypatch, content=0, nodes=0)["accessibility"]
    assert absent["state"] == "empty"


def test_ocr_arrives_as_text_with_screen_point_bounds(monkeypatch):
    """OCR is an input, not a second entity inventory."""
    lines = [{"text": "Kulvinder Ji", "bounds": [10, 20, 200, 30], "confidence": 0.95}]
    entry = _sources(monkeypatch, ocr_lines=lines)["ocr"]
    assert entry["state"] == "on"
    assert entry["lines"][0]["text"] == "Kulvinder Ji"
    assert entry["lines"][0]["bounds"] == [10, 20, 200, 30]


def test_ocr_being_off_is_declared_rather_than_silent(monkeypatch):
    """A silent omission and a declared absence are read differently.

    Told nothing, the model cannot distinguish 'no text on this surface' from
    'nobody read the text', and those warrant opposite responses.
    """
    entry = _sources(monkeypatch, ocr="0")["ocr"]
    assert entry["state"] == "off"
    assert "lines" not in entry
    assert "not treat missing text as absent" in entry["why"]


def test_ocr_ran_but_found_nothing_is_distinct_from_disabled(monkeypatch):
    assert _sources(monkeypatch, ocr_lines=[], ocr="1")["ocr"]["state"] == "empty"


def test_packet_carries_the_enumerated_sources(monkeypatch):
    from plugin.agent.features import StateFeatures
    from plugin.agent.goal import Goal
    from plugin.agent.unified_cognition import build_decision_packet
    from plugin.worldmodel.model import WorldModel

    monkeypatch.setenv("HERMES_PERCEPTION_OCR", "1")
    world = WorldModel()
    world.last_screenshot_path = "/tmp/frame.png"
    features = StateFeatures(app="WhatsApp")
    features.extras = {"observation_node_count": 3, "app_content_node_count": 0}
    goal = Goal(kind="whatsapp_forward", contact="Kulvinder", target_contact="Pallavi")
    packet = build_decision_packet(goal, world, features)
    declared = {entry["source"] for entry in packet["observation"]["sources"]}
    assert declared == {"screenshot", "accessibility", "ocr"}


def _world_of_rows(n: int):
    from plugin.worldmodel.entities.entity import Entity
    from plugin.worldmodel.model import WorldModel

    world = WorldModel()
    entities = {}
    for i in range(n):
        # Only every ninth row mentions anything from the goal. The rest are the
        # unnamed furniture a task still has to operate: menu items, buttons.
        label = "Kulvinder Ji" if i % 9 == 0 else f"Some control {i}"
        entity = Entity(
            id=i + 1,
            entity_type="row",
            semantic_role="row",
            label=label,
            role="AXStaticText",
            actions=["click"],
            visible=True,
        )
        entity.bounds = (10.0, 40.0 + i * 28, 380.0, 26.0)
        entities[i + 1] = entity
    world.entities = entities
    return world


def test_goal_relevance_orders_the_evidence_but_does_not_filter_it():
    """Ranking and truncating is the runtime pre-judging what the model needs.

    That judgement is the one this design moves into the model, and the entities
    it discards are the ones no task names: Forward, the composer, New chat all
    score near zero against the goal terms while being exactly what the goal
    requires. The affordance frontier meanwhile went on advertising those actions,
    so the model was told a control existed and denied the evidence for it.
    """
    from plugin.agent.goal import Goal
    from plugin.agent.unified_cognition import _ax_evidence

    goal = Goal(
        kind="whatsapp_forward",
        contact="Kulvinder",
        target_contact="Pallavi",
        link_query="zarooratwala",
    )
    evidence = _ax_evidence(_world_of_rows(60), goal)
    assert len(evidence) == 60, "no visible entity may be withheld for irrelevance"
    # Relevance still decides order, so the goal-bearing rows arrive first where
    # attention is cheapest.
    assert evidence[0]["label"] == "Kulvinder Ji"


def test_the_evidence_bound_is_a_safety_valve_not_a_filter():
    """A pathological tree is still bounded, well above any real window."""
    from plugin.agent.goal import Goal
    from plugin.agent.unified_cognition import MAX_AX_EVIDENCE, _ax_evidence

    assert MAX_AX_EVIDENCE >= 200
    goal = Goal(kind="whatsapp_forward", contact="Kulvinder")
    assert len(_ax_evidence(_world_of_rows(400), goal)) == MAX_AX_EVIDENCE


def test_world_model_holds_the_ocr_read_from_the_observation():
    """The read travels with the capture it describes.

    Re-deriving it at packet-build time would race the window being moved or
    resized between the capture and the call.
    """
    from plugin.perception.observation import Observation
    from plugin.worldmodel.model import WorldModel

    world = WorldModel()
    lines = [{"text": "Kulvinder Ji", "bounds": [10, 20, 200, 30], "confidence": 0.9}]
    world.ingest(
        Observation(
            timestamp=0.0,
            app_name="WhatsApp",
            window_name="WhatsApp",
            nodes=[],
            screenshot_path="/tmp/frame.png",
            source="screen2ax:vision",
            meta={"ocr": {"status": "applied", "lines": lines}},
        )
    )
    assert world.last_ocr_lines == lines


def test_a_frame_without_ocr_does_not_blank_the_held_read():
    """An AX-only cycle says nothing about the text on screen.

    Clearing on it would blank the read on every alternate frame, which is worse
    than a one-frame-stale read.
    """
    from plugin.perception.observation import Observation
    from plugin.worldmodel.model import WorldModel

    world = WorldModel()
    world.last_ocr_lines = [{"text": "Kulvinder Ji", "bounds": [0, 0, 1, 1], "confidence": 0.9}]
    world.ingest(
        Observation(
            timestamp=0.0,
            app_name="WhatsApp",
            window_name="WhatsApp",
            nodes=[],
            screenshot_path="/tmp/frame2.png",
            source="pyobjc_ax",
            meta={"ocr": {"status": "empty"}},
        )
    )
    assert world.last_ocr_lines, "an OCR-less frame must not clear the held read"
