"""Live 171216: Forward screen point must not be image→screen transformed twice."""

from types import SimpleNamespace

from plugin.agent.actor import brief_from_brain_choice
from plugin.agent.executive.meta_action import MetaAction, MetaContext, select_meta_action
from plugin.perception.display_topology import TaskSurface


def _task_surface_171216() -> TaskSurface:
    return TaskSurface(
        app="WhatsApp",
        window_bounds=(110.0, 25.0, 1581.0, 979.0),
        capture_origin=(774.0, 25.0),
        capture_scale=1.0,
        point_scale=1.4328125,
    )


def test_forward_untagged_inventory_keeps_screen_space(monkeypatch):
    """OCR Forward ~[1380,217] agreeing with brain must not become ~2751."""
    from plugin.agent import actor as actor_mod

    surf = _task_surface_171216()

    def fake_surface_from_doc(doc, app=""):
        return surf

    monkeypatch.setattr(actor_mod, "_task_surface_from_doc", fake_surface_from_doc)

    doc = {
        "surface": "context_menu",
        "open_conversation": "Pallavi",
        "objects": [
            {
                "id": "fwd",
                "kind": "menu_item",
                "text": "Forward",
                "point": [1380, 217],
                # Intentionally untagged — live packet omitted coordinate_space.
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
            "target_point": [1407, 224],
            "coordinate_space": "screen",
            "geometry_source": "ocr",
        },
        doc,
        app="WhatsApp",
        capability="invoke_affordance",
    )
    assert brief.point is not None
    x, y = float(brief.point[0]), float(brief.point[1])
    # Must remain inside task window — never capture_origin + point * scale.
    assert 110.0 <= x <= 1691.0
    assert abs(x - 2751.28125) > 100.0
    assert abs(x - 1407.0) <= 40.0 or abs(x - 1380.0) <= 40.0
    assert 180.0 <= y <= 280.0


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
    assert "reground" in choice.reason.lower() or choice.scores.get(
        "grounding_reground_only"
    )
