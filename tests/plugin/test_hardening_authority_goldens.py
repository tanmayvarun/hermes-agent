"""Mandatory authority goldens from the pre-run hardening plan."""

import ast
from pathlib import Path
from types import SimpleNamespace

from plugin.agent.actor import _normalize_to_screen
from plugin.agent.apps.whatsapp import _entity_binding_eligible
from plugin.agent.capabilities.search_episode import (
    search_continue_capability,
    search_episode_of,
)
from plugin.agent.composition import compose_domain_adapters
from plugin.agent.controller import _grounding_repair_satisfied
from plugin.agent.decision_consultation import DecisionBrief, TaskState
from plugin.agent.procedures.forward_message import forward_role_specs
from plugin.agent.role_binding import IdentityResolver, assess_candidate_for_role
from plugin.agent.runtime.state import ExecutionState
from plugin.agent.source_query_binding import evaluate_source_object_match
from plugin.agent.world_document import normalize_document
from plugin.perception.coordinate_frame import build_frame_graph
from plugin.worldmodel.entities.entity import Entity
from plugin.worldmodel.model import WorldModel

_AGENT_ROOT = Path(__file__).resolve().parents[2] / "plugin" / "agent"
_RESOLVED_ENTITY_WRITERS = frozenset(
    {
        "role_binding.py",
        "apps/whatsapp.py",
        "controller.py",
        "transfer_task.py",
        "task_binding.py",
    }
)


class _AliceGoal:
    contact = "Alice"
    link_query = "zarooratwala"
    target_contact = "Bob"
    originator = "Alice"


def test_from_alice_single_result_from_self_does_not_resolve():
    compose_domain_adapters()
    you = {
        "label": "You: https://www.zarooratwala.com/x",
        "text": "You: https://www.zarooratwala.com/x",
        "kind": "message_with_link",
        "domain": "whatsapp",
        "container": "Alice",
    }
    a = assess_candidate_for_role(
        spec=forward_role_specs(_AliceGoal())["source_object"],
        candidate=you,
        goal=_AliceGoal(),
        bindings={"source_container": {"resolved_label": "Alice"}},
        task_relevance=0.99,
    )
    assert a.binding_eligible is False


def test_sender_unknown_does_not_infer_peer():
    gm = evaluate_source_object_match(
        text="https://www.zarooratwala.com/x",
        kind="message_with_link",
        query="zarooratwala",
        container_open="Alice",
        expected_container="Alice",
        expected_originator="Alice",
        sender="",  # no authorship evidence
    )
    assert gm.container_match
    assert gm.semantic_query_match
    assert not gm.originator_match
    assert not gm.binding_eligible
    assert any(c.name == "originator" and c.status == "missing" for c in gm.constraints)


def test_non_authoritative_scorer_cannot_bind():
    """matches_goal / high relevance must not authorize RoleBinder commit."""
    compose_domain_adapters()
    world = WorldModel()
    world.open_conversation = "Alice"
    world.entities[7] = Entity(
        id=7,
        entity_type="message",
        semantic_role="message",
        label="You: https://www.zarooratwala.com/x",
        role="AXStaticText",
        bounds=(900, 400, 200, 40),
        visible=True,
        attributes={
            "matches_goal": True,
            "description": "You: https://www.zarooratwala.com/x",
            "kind": "message_with_link",
        },
    )
    ok = _entity_binding_eligible(
        world,
        7,
        query="zarooratwala",
        expected_container="Alice",
        expected_originator="Alice",
        goal=_AliceGoal(),
    )
    assert ok is False


def test_vlm_bounds_are_image_space():
    doc = normalize_document(
        {
            "surface": "conversation",
            "objects": [
                {
                    "text": "Forward",
                    "bounds": [100, 200, 80, 24],
                    "geometry_source": "vlm",
                },
                {
                    "text": "Reply",
                    "bounds": [100, 240, 80, 24],
                    "geometry_source": "ocr",
                },
                {
                    "text": "Copy",
                    "bounds": [100, 280, 80, 24],
                    "geometry_source": "ax_menu",
                },
            ],
        },
        frame=1,
    )
    by_text = {o["text"]: o for o in doc["objects"]}
    assert by_text["Forward"]["coordinate_space"] == "image"
    assert by_text["Reply"]["coordinate_space"] == "screen"
    assert by_text["Copy"]["coordinate_space"] == "screen"
    assert by_text["Forward"]["geometry_source"] == "vlm"


def test_stale_capture_target_does_not_satisfy_reground():
    graph = build_frame_graph(
        image_size=(1581.0, 979.0),
        window_origin_in_screen=(110.0, 25.0),
        point_scale=1.0,
        capture_scale=1.0,
        capture_id="capture_new",
    )
    state = SimpleNamespace(
        grounding_reground_target="Forward",
        unified_world_document={
            "surface": "context_menu",
            "capture_id": "capture_new",
            "frame_graph": graph.to_dict(),
            "objects": [
                {
                    "text": "Forward",
                    "point": [1380, 217],
                    "coordinate_space": "screen",
                    "capture_id": "capture_old",  # stale prior menu frame
                    "owner_surface": "context_menu",
                    "geometry_source": "ocr",
                }
            ],
        },
        last_grounded_affordance_set=[
            {
                "target_label": "Forward",
                "actuators": [{"type": "coordinate_click", "point": [1380, 217]}],
                "coordinate_space": "screen",
                "capture_id": "capture_old",
                "owner_surface": "context_menu",
            }
        ],
        task_surface={"capture_id": "capture_new", "frame_graph": graph.to_dict()},
    )
    assert _grounding_repair_satisfied(state) is False


def test_fresh_capture_target_satisfies_reground():
    graph = build_frame_graph(
        image_size=(1581.0, 979.0),
        window_origin_in_screen=(110.0, 25.0),
        point_scale=1.0,
        capture_scale=1.0,
        capture_id="capture_now",
    )
    state = SimpleNamespace(
        grounding_reground_target="Forward",
        unified_world_document={
            "surface": "context_menu",
            "capture_id": "capture_now",
            "frame_graph": graph.to_dict(),
            "objects": [
                {
                    "text": "Forward",
                    "point": [1380, 217],
                    "coordinate_space": "screen",
                    "capture_id": "capture_now",
                    "owner_surface": "context_menu",
                    "geometry_source": "ocr",
                }
            ],
        },
        last_grounded_affordance_set=[],
        task_surface={"capture_id": "capture_now", "frame_graph": graph.to_dict()},
    )
    assert _grounding_repair_satisfied(state) is True


def test_rejected_role_candidate_is_not_immediately_reselected():
    state = ExecutionState()
    you_label = "You: https://www.zarooratwala.com/x"
    brief = DecisionBrief(
        goal={
            "source_conversation": "Alice",
            "source_query": "zarooratwala",
            "originator": "Alice",
        },
        world={
            "surface": "search",
            "objects": [
                {
                    "id": "you_msg",
                    "kind": "message_with_link",
                    "text": you_label,
                    "matches_goal": True,
                    "goal_match": {
                        "binding_eligible": False,
                        "identity_match": False,
                    },
                }
            ],
        },
        task_state=TaskState(
            phase="reach_source",
            search_query="zarooratwala",
            source_chat_open=False,
        ),
        capabilities=["open_entity", "resolve_entity", "observe", "search"],
    )
    cap, tgt, why = search_continue_capability(state, brief)
    assert cap != "open_entity"
    assert "you:" not in str(tgt or "").lower()
    ep = search_episode_of(state) or {}
    assert "you_msg" in (ep.get("role_rejected_ids") or [])
    assert ep.get("role_resolved") is False or ep.get("status") == "failed"
    # Second call must not re-pick the same rejected candidate.
    brief2 = DecisionBrief(
        goal=brief.goal,
        world=brief.world,
        task_state=brief.task_state,
        capabilities=list(brief.capabilities),
        search_episode=dict(ep),
    )
    cap2, tgt2, _why2 = search_continue_capability(state, brief2)
    assert cap2 not in {"open_entity", "resolve_entity"} or (
        "you:" not in str(tgt2 or "").lower()
    )
    assert "you:" not in str(tgt2 or "").lower()


def test_vlm_image_forward_single_transform_into_task_window():
    """VLM image-local Forward + FrameGraph → exactly one transform to screen."""
    graph = build_frame_graph(
        image_size=(1581.0, 979.0),
        window_origin_in_screen=(1962.0, 39.0),
        point_scale=1.0,
        capture_scale=1.0,
        capture_id="cap_img",
    )
    pt, bd, audit = _normalize_to_screen(
        (100.0, 200.0),
        None,
        coordinate_space="image",
        surface=None,
        frame_id=graph.image_frame_id,
        graph=graph,
        grounding_capture_id="cap_img",
        allow_legacy_geometry=False,
    )
    assert pt is not None
    assert not audit.get("grounding_uncertain")
    assert abs(float(pt[0]) - 2062.0) <= 1.0
    assert abs(float(pt[1]) - 239.0) <= 1.0
    # Inside task window [1962,39] + [1581,979]
    assert 1962.0 <= float(pt[0]) <= 1962.0 + 1581.0
    assert 39.0 <= float(pt[1]) <= 39.0 + 979.0


def test_public_values_same_identity_api():
    assert IdentityResolver.values_same_identity("Alice", "alice")
    assert not IdentityResolver.values_same_identity("Alice", "Alice Extra")


def test_resolved_entity_id_writers_are_allowlisted():
    """Static gate: only known modules may assign resolved_entity_id."""
    writers = set()
    for path in _AGENT_ROOT.rglob("*.py"):
        rel = path.relative_to(_AGENT_ROOT).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                name = None
                if isinstance(target, ast.Attribute) and target.attr == "resolved_entity_id":
                    name = "resolved_entity_id"
                elif (
                    isinstance(target, ast.Subscript)
                    and isinstance(target.slice, ast.Constant)
                    and target.slice.value == "resolved_entity_id"
                ):
                    name = "resolved_entity_id"
                if name:
                    writers.add(rel)
                    break
    unexpected = sorted(writers - _RESOLVED_ENTITY_WRITERS)
    missing_expected = sorted(_RESOLVED_ENTITY_WRITERS & writers)  # noqa: F841
    assert not unexpected, f"new resolved_entity_id writers: {unexpected}"
    assert writers & _RESOLVED_ENTITY_WRITERS, "allowlist matched no writers"
