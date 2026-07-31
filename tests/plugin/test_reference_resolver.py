"""Reference Resolver — intent confidence over name matching."""

from __future__ import annotations

from pathlib import Path

from plugin.agent.resolver.memory import ResolutionMemory
from plugin.agent.resolver.reference import ReferenceResolver
from plugin.agent.resolver.resolution import AUTO_RESOLVE, OBSERVE_BAND
from plugin.worldmodel.entities.entity import Entity
from plugin.worldmodel.model import WorldModel


def _entity(eid: int, name: str) -> Entity:
    return Entity(
        id=eid,
        entity_type="button",
        semantic_role=name,
        label=name,
        role="AXButton",
        actions=["click"],
        attributes={"description": name},
        visible=True,
    )


def _world(names: list[str]) -> WorldModel:
    wm = WorldModel()
    wm.active_app = "WhatsApp"
    ents = [_entity(i + 1, n) for i, n in enumerate(names)]
    wm.entities = {e.id: e for e in ents}
    wm.tracker._entities = dict(wm.entities)
    wm.tracker._next_id = len(ents) + 1
    return wm


def test_pallu_unique_personal_resolves_to_pallavi(tmp_path: Path):
    mem = ResolutionMemory(path=tmp_path / "mem.jsonl")
    resolver = ReferenceResolver(memory=mem)
    wm = _world(["Pallavi", "Pallavi Office", "Pallavi HR", "Pallavi Bangalore"])
    res = resolver.resolve(wm, "Pallu")
    assert res.winner_name == "Pallavi"
    assert res.policy == "auto"
    assert res.confidence >= AUTO_RESOLVE


def test_history_beats_string_match(tmp_path: Path):
    mem = ResolutionMemory(path=tmp_path / "mem.jsonl")
    for _ in range(20):
        mem.record("Pallu", "Pallavi", succeeded=True, source="test")
    resolver = ReferenceResolver(memory=mem)
    # Even with multiple personal names, history dominates
    wm = _world(["Pallavi", "Pallavi Sharma"])
    res = resolver.resolve(wm, "Pallu")
    assert res.winner_name == "Pallavi"
    assert res.confidence >= AUTO_RESOLVE
    assert any(e.signal == "history" and e.value > 0.5 for e in res.candidates[0].evidence)


def test_near_tie_is_low_confidence_not_hardcoded_margin(tmp_path: Path):
    mem = ResolutionMemory(path=tmp_path / "mem.jsonl")
    resolver = ReferenceResolver(memory=mem)
    wm = _world(["Support Team A", "Support Team B"])
    res = resolver.resolve(wm, "Support Team")
    assert res.winner is None
    assert res.policy in {"observe", "ask"}
    assert res.confidence < AUTO_RESOLVE
    assert len(res.candidates) >= 2


def test_learn_from_confirmation_shifts_confidence(tmp_path: Path):
    mem = ResolutionMemory(path=tmp_path / "mem.jsonl")
    resolver = ReferenceResolver(memory=mem)
    wm = _world(["Pallavi", "Pallavi HR"])
    before = resolver.resolve(wm, "HR Pallavi")
    mem.record("HR Pallavi", "Pallavi HR", succeeded=True, source="user_confirm", weight=5.0)
    after = resolver.resolve(wm, "HR Pallavi")
    assert after.candidates[0].name == "Pallavi HR"
    assert after.confidence >= before.confidence


def test_exact_name_still_autos(tmp_path: Path):
    mem = ResolutionMemory(path=tmp_path / "mem.jsonl")
    resolver = ReferenceResolver(memory=mem)
    wm = _world(["Pallavi", "Pallavi Office"])
    res = resolver.resolve(wm, "Pallavi")
    assert res.policy == "auto"
    assert res.winner_name == "Pallavi"
    assert res.confidence >= OBSERVE_BAND


def test_now_group_prefers_truncated_group_over_unrelated(tmp_path: Path):
    from plugin.agent.apps.whatsapp_semantics import apply_semantic_types
    from plugin.agent.reference import interpret_reference

    mem = ResolutionMemory(path=tmp_path / "mem.jsonl")
    resolver = ReferenceResolver(memory=mem)
    wm = _world(["Now…", "Norah", "plugin support", "Call"])
    apply_semantic_types(wm)
    ref = interpret_reference("now group")
    res = resolver.resolve(wm, "now group", reference=ref)
    assert res.winner_name is not None
    assert res.winner_name.startswith("Now")
    assert res.policy == "auto"


def test_now_group_full_label_wins(tmp_path: Path):
    from plugin.agent.apps.whatsapp_semantics import apply_semantic_types
    from plugin.agent.reference import interpret_reference

    mem = ResolutionMemory(path=tmp_path / "mem.jsonl")
    resolver = ReferenceResolver(memory=mem)
    wm = _world(["Now Group", "Now…", "Norah"])
    apply_semantic_types(wm)
    ref = interpret_reference("now group")
    res = resolver.resolve(wm, "now group", reference=ref)
    assert res.winner_name == "Now Group"


def test_semantic_types_tag_truncated_as_group():
    from plugin.agent.apps.whatsapp_semantics import apply_semantic_types, entity_semantic_type

    wm = _world(["Now…", "Pallavi"])
    apply_semantic_types(wm)
    now = next(e for e in wm.entities.values() if (e.label or "").startswith("Now"))
    pal = next(e for e in wm.entities.values() if e.label == "Pallavi")
    assert entity_semantic_type(now)[0] == "group"
    assert entity_semantic_type(pal)[0] == "contact"


def test_semantic_types_tag_long_call_cta_as_call_button():
    from plugin.agent.apps.whatsapp_semantics import apply_semantic_types, entity_semantic_type

    wm = _world(["Start video call with Pallavi", "Pallavi"])
    apply_semantic_types(wm)
    video = next(e for e in wm.entities.values() if "video call" in (e.label or "").lower())
    assert entity_semantic_type(video)[0] == "call_button"


def test_static_sidebar_row_participates_in_resolution():
    from plugin.agent.apps.whatsapp_semantics import apply_semantic_types

    mem = ResolutionMemory(path=Path("/tmp/mem.jsonl"))
    resolver = ReferenceResolver(memory=mem)
    wm = WorldModel()
    wm.active_app = "WhatsApp"
    wm.entities = {
        1: Entity(
            id=1,
            entity_type="static",
            semantic_role="Kulvinder Ji",
            label="Kulvinder Ji",
            role="AXStaticText",
            bounds=(60, 160, 260, 56),
            attributes={"description": "Chat row"},
            visible=True,
        ),
        2: Entity(
            id=2,
            entity_type="textfield",
            semantic_role="Search",
            label="Search",
            role="AXTextField",
            bounds=(40, 80, 200, 30),
            attributes={},
            visible=True,
        ),
        3: Entity(
            id=3,
            entity_type="textfield",
            semantic_role="Type a message",
            label="Type a message",
            role="AXTextField",
            bounds=(700, 900, 600, 40),
            attributes={},
            visible=True,
        ),
    }
    wm.tracker._entities = dict(wm.entities)
    wm.tracker._next_id = 4
    apply_semantic_types(wm)
    res = resolver.resolve(wm, "Kulvinder")
    assert res.candidates, "static sidebar row should enter candidate pool"
    assert res.candidates[0].name.lower().startswith("kulvinder")
