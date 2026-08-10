"""Hardening goldens: coordinate provenance + search/role authority (live 171216)."""

from types import SimpleNamespace

from plugin.agent.actor import brief_from_brain_choice
from plugin.agent.executive.meta_action import MetaAction, MetaContext, select_meta_action
from plugin.agent.capabilities.search_episode import (
    note_retrieval_complete,
    search_episode_of,
)
from plugin.perception.display_topology import TaskSurface


def _task_surface_171216() -> TaskSurface:
    return TaskSurface(
        app="WhatsApp",
        window_bounds=(110.0, 25.0, 1581.0, 979.0),
        capture_origin=(774.0, 25.0),
        capture_scale=1.0,
        point_scale=1.4328125,
    )


def test_ocr_forward_is_stamped_screen_space_before_actor(monkeypatch):
    """Producer stamps screen; Actor round-trips without double-transform."""
    from plugin.agent import actor as actor_mod

    surf = _task_surface_171216()
    monkeypatch.setattr(actor_mod, "_task_surface_from_doc", lambda doc, app="": surf)

    doc = {
        "surface": "context_menu",
        "open_conversation": "Pallavi",
        "objects": [
            {
                "id": "fwd",
                "kind": "menu_item",
                "text": "Forward",
                "point": [1380, 217],
                "coordinate_space": "screen",
                "geometry_source": "ocr",
            }
        ],
        "task_surface": {
            "window_bounds": [110, 25, 1581, 979],
            "capture_origin": [774, 25],
            "point_scale": 1.4328125,
        },
    }
    brief = brief_from_brain_choice(
        {
            "family": "invoke_affordance",
            "target_id": "fwd",
            "target_label": "Forward",
            "target_point": [1380, 217],
            "coordinate_space": "screen",
            "geometry_source": "ocr",
        },
        doc,
        app="WhatsApp",
        capability="invoke_affordance",
    )
    assert brief.point is not None
    x, y = float(brief.point[0]), float(brief.point[1])
    assert abs(x - 1380.0) <= 2.0
    assert abs(y - 217.0) <= 2.0
    assert abs(x - 2751.28125) > 100.0


def test_untagged_actionable_geometry_fails_closed(monkeypatch):
    """Untagged actionable point → no motor (Actor never infers space)."""
    from plugin.agent import actor as actor_mod

    surf = _task_surface_171216()
    monkeypatch.setattr(actor_mod, "_task_surface_from_doc", lambda doc, app="": surf)

    doc = {
        "surface": "context_menu",
        "objects": [
            {
                "id": "fwd",
                "kind": "menu_item",
                "text": "Forward",
                "point": [1380, 217],
                # Intentionally untagged — must fail closed.
            }
        ],
        "task_surface": {
            "window_bounds": [110, 25, 1581, 979],
            "capture_origin": [774, 25],
            "point_scale": 1.4328125,
        },
    }
    brief = brief_from_brain_choice(
        {
            "family": "invoke_affordance",
            "target_id": "fwd",
            "target_label": "Forward",
            "target_point": [1380, 217],
            # No coordinate_space on brain either.
        },
        doc,
        app="WhatsApp",
        capability="invoke_affordance",
    )
    assert brief.point is None
    assert brief.bounds is None


def test_grounding_reground_only_beats_destination_search():
    ctx = MetaContext(
        post_action_look_owed=False,
        destination_search_needed=True,
        grounding_reground_only=True,
        search_exhausted=False,
        act_clear=False,
    )
    choice = select_meta_action(ctx)
    assert choice.action == MetaAction.PERCEIVE


def test_retrieval_complete_but_role_unresolved():
    es = SimpleNamespace(search_episode={}, search_retreat_owed=False)
    ep = note_retrieval_complete(
        es,
        chosen_label="You: https://example.com/x",
        chosen_id="you_msg",
        role_resolved=False,
        role_unresolved_reason="required identity constraint failed",
        candidate_count=1,
    )
    assert ep["retrieval_complete"] is True
    assert ep["role_resolved"] is False
    assert ep["status"] != "complete"
    assert ep["chosen_candidate"] == "you_msg"
    assert "identity" in ep["role_unresolved_reason"]
    stored = search_episode_of(es)
    assert stored["retrieval_complete"] is True
    assert stored["role_resolved"] is False


def test_reground_target_disappeared_escalates_explore_reveal():
    from plugin.agent.controller import (
        _clear_post_action_reperceive_if_fresh,
        _grounding_repair_satisfied,
    )

    state = SimpleNamespace(
        must_executive_reperceive=True,
        post_action_reperceive_pending=True,
        post_action_baseline_open="",
        post_action_baseline_sig="",
        grounding_reground_only=True,
        grounding_reground_target="Forward",
        unified_world_document={
            "surface": "conversation",
            "objects": [],  # menu gone
        },
        last_grounded_affordance_set=[],
        world_exploration_needed=False,
        reveal_prefer_capability="",
        last_effect_closure={},
    )
    runtime = SimpleNamespace(execution_state=state)
    assert _grounding_repair_satisfied(state) is False
    ok = _clear_post_action_reperceive_if_fresh(
        runtime, multimodal_ok=True, proposal_model="stage1"
    )
    assert ok is True
    assert state.grounding_reground_only is False
    assert state.world_exploration_needed is True
    assert state.reveal_prefer_capability == "reveal_actions"
    assert (state.last_effect_closure or {}).get("recovery") == "explore_reveal"
