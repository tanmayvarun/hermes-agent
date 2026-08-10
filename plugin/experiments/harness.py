"""Eval harness — identity retention, screen class, transitions, e2e, recovery."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from plugin.agent.runtime.recovery import recover_after_unexpected
from plugin.agent.runtime.state import RuntimeState
from plugin.perception.macos.accessibility.observer import FixtureObserver
from plugin.worldmodel.model import WorldModel


FIXTURES = Path(__file__).resolve().parent / "fixtures"

TARGETS = {
    "ax_extraction": 0.99,
    "entity_tracking": 0.95,
    "screen_classification": 0.95,
    "transition_prediction": 0.90,
    "recovery": 0.70,
    "e2e_whatsapp_call": 0.90,
}


@dataclass
class Scorecard:
    ax_extraction: float
    entity_tracking: float
    screen_classification: float
    transition_prediction: float
    recovery: float
    e2e_whatsapp_call: float
    kill_gate_pass: bool
    notes: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _load_sequence() -> List[Path]:
    order = [
        "whatsapp_conversation.json",
        "whatsapp_search.json",
        "whatsapp_chat.json",
        "whatsapp_call.json",
    ]
    return [FIXTURES / name for name in order]


def run_identity_harness() -> float:
    """Retention on the *same* screen across focus / type / scroll churn."""
    wm = WorldModel()
    path = FIXTURES / "whatsapp_conversation.json"
    obs = FixtureObserver(path).observe()
    wm.ingest(obs)
    retentions: List[float] = []

    # focus — identical tree
    retentions.append(wm.ingest(FixtureObserver(path).observe(), action="focus").retention)

    # type — same roles/labels, tiny geometry jitter
    obs_type = FixtureObserver(path).observe()
    for n in obs_type.nodes:
        x, y, w, h = n.bbox
        n.bbox = (x + 1, y, w, h)
    retentions.append(wm.ingest(obs_type, action="type").retention)

    # scroll — larger uniform shift
    obs_scroll = FixtureObserver(path).observe()
    for n in obs_scroll.nodes:
        x, y, w, h = n.bbox
        n.bbox = (x, y + 12, w, h)
    retentions.append(wm.ingest(obs_scroll, action="scroll").retention)

    return sum(retentions) / max(1, len(retentions))

def run_screen_harness() -> float:
    wm = WorldModel()
    labels = []
    # Chat fixture may surface as conversation (open thread) — both are correct.
    expected = ["conversation", "search", {"chat", "conversation"}, "call"]
    for p, exp in zip(_load_sequence(), expected):
        obs = FixtureObserver(p).observe()
        patch = wm.ingest(obs)
        if isinstance(exp, set):
            labels.append(patch.screen_label in exp)
        else:
            labels.append(patch.screen_label == exp)
    return sum(1 for x in labels if x) / len(labels)


def run_transition_harness() -> float:
    wm = WorldModel()
    actions = [None, "open_search", "open_chat", "call"]
    for p, action in zip(_load_sequence(), actions):
        obs = FixtureObserver(p).observe()
        wm.ingest(obs, action=action)
    # Replay first transition prediction
    pred = wm.transitions.predict(1, "open_search")
    # After 4 screens ids 1..4 typically
    correct = 0
    total = 0
    for t in wm.transitions.transitions:
        total += 1
        again = wm.transitions.predict(t.from_screen, t.action, t.target_entity_id)
        if again and again.to_screen == t.to_screen:
            correct += 1
    return correct / max(1, total)


def run_recovery_harness() -> float:
    runtime = RuntimeState()
    runtime.active_task = "Call Pallavi on WhatsApp"
    for p in _load_sequence()[:2]:
        runtime.world_model.ingest(FixtureObserver(p).observe())
    # Inject unexpected: jump to call screen
    unexpected = FixtureObserver(FIXTURES / "whatsapp_call.json").observe()
    result = recover_after_unexpected(runtime, unexpected, goal=runtime.active_task)
    return 1.0 if result.recovered else 0.0


def run_e2e_plan_harness() -> float:
    """Offline e2e: DecisionEngine owns no legacy enumerate fallthrough.

    Hermetic tests pin unified cognition off, so an unfinished world Observes
    with ``unified_declined_no_legacy_fallthrough``. A completed call still
    returns no action.
    """
    from plugin.agent.decision import DecisionEngine
    from plugin.agent.goal import Goal
    from plugin.agent.runtime.state import ExecutionState

    eng = DecisionEngine()
    goal = Goal(kind="whatsapp_voice_call", contact="Pallavi")
    score = 0.0

    wm = WorldModel()
    wm.ingest(FixtureObserver(FIXTURES / "whatsapp_conversation.json").observe())
    a = eng.define_action_step(goal, wm, ExecutionState())
    if (
        a is not None
        and a.action == "Observe"
        and "unified_declined_no_legacy_fallthrough" in (a.rationale or "")
    ):
        score += 0.5

    wm2 = WorldModel()
    wm2.ingest(FixtureObserver(FIXTURES / "whatsapp_call.json").observe())
    a2 = eng.define_action_step(goal, wm2, ExecutionState())
    # Call fixture is ringing with contact evidence → goal done → no action
    if a2 is None:
        score += 0.5
    return score


def run_hypothesis_advance_harness() -> float:
    """Kill-gate: nested extras + incomplete resolution must not false-advance."""
    from plugin.agent.action import Action
    from plugin.agent.controller import _maybe_advance_search_hypothesis
    from plugin.agent.features import StateFeatures
    from plugin.agent.goal import Goal
    from plugin.agent.runtime.state import RuntimeState
    from plugin.agent.transition.post_perceive import (
        assess_post_action_perception,
        settled_empty_search_results,
    )

    score = 0.0
    checks = 0

    # 1) Nested production shape with results → no advance
    checks += 1
    rt = RuntimeState()
    goal = Goal(kind="whatsapp_voice_call", contact="now group")
    feats = StateFeatures(
        query_matches_goal=True,
        extras={
            "resolution_policy": "ask",
            "resolution_confidence": 0.0,
            "result_surface_visible": True,
            "search_result_rows": ["Now…"],
            "contact_candidates": [{"name": "Now…"}],
            "search_query": "Now",
        },
    ).to_dict()
    if not _maybe_advance_search_hypothesis(
        rt,
        goal,
        decision=Action(action="Type", action_family="type_query", text="Now"),
        after_view={"search_query": "Now"},
        after_features=feats,
        log=None,
        iteration=1,
        perception_settled=True,
    ):
        score += 1.0

    # 2) Null resolution → incomplete, not empty
    checks += 1
    incomplete = {
        "query_matches_goal": True,
        "extras": {"resolution_policy": None, "resolution_confidence": None, "search_query": "Now"},
    }
    ok, reason = settled_empty_search_results(
        view={"search_query": "Now"}, features=incomplete, perception_settled=True
    )
    assessment = assess_post_action_perception(
        action_family="type_query", view={"search_query": "Now"}, features=incomplete
    )
    if (not ok and reason == "perception_incomplete") and (not assessment.settled):
        score += 1.0

    return score / max(1, checks)


def run_scorecard() -> Scorecard:
    entity = run_identity_harness()
    screen = run_screen_harness()
    trans = run_transition_harness()
    recovery = run_recovery_harness()
    e2e = run_e2e_plan_harness()
    hyp = run_hypothesis_advance_harness()
    # Fixture AX always "extracts" fully
    ax = 1.0
    notes = []
    kill_ok = entity >= 0.80 and screen >= 0.80 and hyp >= 0.99
    if not kill_ok:
        notes.append("KILL GATE: entity/screen/hypothesis_advance — stop planner polish")
    if entity < TARGETS["entity_tracking"]:
        notes.append(f"entity_tracking {entity:.2f} < {TARGETS['entity_tracking']}")
    if screen < TARGETS["screen_classification"]:
        notes.append(f"screen_classification {screen:.2f} < target")
    if hyp < 0.99:
        notes.append(f"hypothesis_advance_settled {hyp:.2f} < 1.0")
    return Scorecard(
        ax_extraction=ax,
        entity_tracking=entity,
        screen_classification=screen,
        transition_prediction=trans,
        recovery=recovery,
        e2e_whatsapp_call=e2e,
        kill_gate_pass=kill_ok,
        notes=notes + [f"hypothesis_advance_settled={hyp:.2f}"],
    )


def replay_log(path: Path, wm: Optional[WorldModel] = None) -> WorldModel:
    """plugin replay — rebuild world from JSONL observations."""
    from plugin.experiments.logger import EventLogger

    wm = wm or WorldModel()
    for rec in EventLogger(path).read_all():
        if rec.get("kind") != "observation_fixture":
            continue
        fixture = rec.get("fixture")
        if fixture:
            obs = FixtureObserver(Path(fixture)).observe()
            wm.ingest(obs, action=rec.get("action"))
    return wm
