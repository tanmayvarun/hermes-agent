"""Trajectory memory — persistent success/failure learning across related goals."""

from __future__ import annotations

from plugin.agent.features import StateFeatures
from plugin.agent.goal import Goal
from plugin.agent.trajectory_memory import TrajectoryMemory, TrajectoryStepRecord
from plugin.agent.transition.types import TransitionOutcome


def test_goal_family_groups_related_call_goals():
    assert Goal(kind="whatsapp_voice_call").family_key() == "whatsapp_call"
    assert Goal(kind="whatsapp_video_call").family_key() == "whatsapp_call"
    assert Goal(kind="whatsapp_forward_message").family_key() == "whatsapp_message"


def test_trajectory_memory_learns_success_and_failure(tmp_path):
    path = tmp_path / "trajectory_memory.jsonl"
    mem = TrajectoryMemory(path=path)
    goal = Goal(kind="whatsapp_voice_call", contact="Pallavi")
    feats = StateFeatures(
        app="WhatsApp",
        screen_bucket="conversation",
        conversation_open=True,
        call_available=True,
    )
    bucket = feats.bucket_key(goal.kind)
    family_bucket = feats.bucket_key(goal.family_key())
    next_bucket = feats.bucket_key("whatsapp_voice_call|call_picker")

    mem.record_run(
        goal=goal,
        success=True,
        reason="success",
        steps=[
            TrajectoryStepRecord(
                step_index=1,
                state_signature="s1",
                state_bucket=bucket,
                family_bucket=family_bucket,
                action="Click",
                action_family="start_call",
                next_state_signature="s2",
                next_state_bucket=next_bucket,
                semantic_target="Call",
                outcome=TransitionOutcome.PROGRESS.value,
                progress_delta=0.75,
            ),
            TrajectoryStepRecord(
                step_index=2,
                state_signature="s2",
                state_bucket=bucket,
                family_bucket=family_bucket,
                action="Click",
                action_family="observe",
                next_state_signature="s3",
                next_state_bucket=next_bucket,
                semantic_target="",
                outcome=TransitionOutcome.PROMISING_UNRESOLVED.value,
                progress_delta=0.10,
            ),
        ],
    )

    mem.record_run(
        goal=goal,
        success=False,
        reason="failed",
        steps=[
            TrajectoryStepRecord(
                step_index=1,
                state_signature="s1",
                state_bucket=bucket,
                family_bucket=family_bucket,
                action="Click",
                action_family="dismiss",
                next_state_signature="s4",
                next_state_bucket=bucket,
                semantic_target="Cancel",
                outcome=TransitionOutcome.NO_EFFECT.value,
                progress_delta=-0.20,
            ),
        ],
    )

    related = Goal(kind="whatsapp_video_call", contact="Pallavi")
    positive = mem.score(related, feats, "start_call", state_signature="s1")
    negative = mem.score(related, feats, "dismiss", state_signature="s1")

    assert positive > 0.0
    assert negative < 0.0
    assert path.is_file()


def test_successor_transition_bonus_prefers_consistent_next_state(tmp_path):
    path = tmp_path / "trajectory_memory.jsonl"
    mem = TrajectoryMemory(path=path)
    goal = Goal(kind="whatsapp_voice_call", contact="Pallavi")
    feats = StateFeatures(
        app="WhatsApp",
        screen_bucket="conversation",
        conversation_open=True,
        call_available=True,
    )
    bucket = feats.bucket_key(goal.kind)
    family_bucket = feats.bucket_key(goal.family_key())
    successor = feats.bucket_key("whatsapp_voice_call|call_picker")

    mem.record_run(
        goal=goal,
        success=True,
        reason="success",
        steps=[
            TrajectoryStepRecord(
                step_index=1,
                state_signature="s1",
                state_bucket=bucket,
                family_bucket=family_bucket,
                action="Click",
                action_family="start_call",
                next_state_signature="s2",
                next_state_bucket=successor,
                semantic_target="Call",
                outcome=TransitionOutcome.PROGRESS.value,
                progress_delta=0.8,
            ),
            TrajectoryStepRecord(
                step_index=2,
                state_signature="s2",
                state_bucket=successor,
                family_bucket=successor,
                action="Click",
                action_family="observe",
                next_state_signature="s3",
                next_state_bucket=successor,
                semantic_target="",
                outcome=TransitionOutcome.PROMISING_UNRESOLVED.value,
                progress_delta=0.2,
            ),
        ],
    )

    score = mem.score(Goal(kind="whatsapp_video_call", contact="Pallavi"), feats, "start_call", state_signature="s1")
    assert score > 0.0
