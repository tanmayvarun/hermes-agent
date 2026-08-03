"""The perceptor sees a layer stack, and permanence lives in that stack.

These pin the pure layer model: an overlay never erases the base beneath it,
objects survive occlusion, the stack stays bounded, and the human-readable
rendering enumerates every layer for developer verification.
"""

from plugin.agent.scene_layers import (
    Layer,
    base_layer,
    container_layer,
    derive_flat,
    find_layer,
    flat_objects,
    layers_from_flat,
    merge_permanence,
    normalize_layers,
    render_layers,
    surface_role,
)


def _msg(text, matches=False, point=(10, 20)):
    return {"kind": "message", "text": text, "matches_goal": matches, "point": list(point)}


def test_surface_role_maps_app_vocabularies_and_is_idempotent_on_roles():
    assert surface_role("conversation") == "container"
    assert surface_role("folder") == "container"
    assert surface_role("context_menu") == "action_menu"
    assert surface_role("share_sheet") == "action_menu"
    assert surface_role("forward_picker") == "destination"
    # idempotent on already-general role names
    assert surface_role("container") == "container"
    assert surface_role("action_menu") == "action_menu"
    assert surface_role("destination") == "destination"
    assert surface_role("nonsense") == "unknown"


def test_normalize_enforces_one_active_top_layer():
    layers = normalize_layers(
        [
            {"role": "conversation", "name": "Pallavi", "state": "active", "objects": [_msg("hi")]},
            {"role": "context_menu", "state": "active", "objects": [{"kind": "menu_item", "text": "Forward"}]},
        ]
    )
    assert [l.role for l in layers] == ["container", "action_menu"]
    assert layers[0].occluded is True
    assert layers[1].occluded is False


def test_normalize_caps_depth_to_three_keeping_base_and_top():
    layers = normalize_layers(
        [
            {"role": "container", "name": "Pallavi", "objects": [_msg("hi")]},
            {"role": "list"},
            {"role": "dialog"},
            {"role": "action_menu", "objects": [{"kind": "menu_item", "text": "Forward"}]},
        ]
    )
    assert len(layers) == 3
    assert layers[0].role == "container"  # base preserved
    assert layers[-1].role == "action_menu"  # top preserved


def test_permanence_carries_the_container_under_an_overlay():
    prior = layers_from_flat("conversation", "Pallavi", [_msg("check zarooratwala.com", matches=True)])
    # Fresh reading is only the menu -- the flat model dropped the chat.
    fresh = layers_from_flat("context_menu", "", [{"kind": "menu_item", "text": "Forward"}])
    merged = merge_permanence(prior, fresh)

    base = base_layer(merged)
    assert base is not None
    assert base.role == "container"
    assert base.name == "Pallavi"
    assert base.occluded is True
    # the goal object survives occlusion
    assert any(o.get("matches_goal") for o in base.objects)
    # the menu is the active top layer
    assert merged[-1].role == "action_menu"
    assert merged[-1].occluded is False


def test_permanence_refills_objects_stripped_behind_an_overlay():
    prior = layers_from_flat("conversation", "Pallavi", [_msg("check zarooratwala.com", matches=True)])
    # Model kept the container but listed no objects on it behind the menu.
    fresh = [
        Layer(role="container", name="Pallavi", state="occluded", objects=[]),
        Layer(role="action_menu", objects=[{"kind": "menu_item", "text": "Forward"}]),
    ]
    merged = merge_permanence(prior, fresh)
    base = base_layer(merged)
    assert base.objects and any(o.get("matches_goal") for o in base.objects)


def test_dismissing_the_overlay_returns_to_the_base_without_carrying_the_menu():
    prior = [
        Layer(role="container", name="Pallavi", state="occluded", objects=[_msg("hi")]),
        Layer(role="action_menu", objects=[{"kind": "menu_item", "text": "Forward"}]),
    ]
    fresh = layers_from_flat("conversation", "Pallavi", [_msg("hi")])
    merged = merge_permanence(prior, fresh)
    assert [l.role for l in merged] == ["container"]
    assert find_layer(merged, "action_menu") is None


def test_derive_flat_reports_overlay_on_top_and_container_beneath():
    layers = [
        Layer(role="container", name="Pallavi", state="occluded", objects=[_msg("hi")]),
        Layer(role="action_menu", objects=[{"kind": "menu_item", "text": "Forward"}]),
    ]
    surface, container_name = derive_flat(layers)
    # The crux of the fix: surface is the menu, yet the chat is still named open.
    assert surface == "context_menu"
    assert container_name == "Pallavi"


def test_flat_objects_unions_the_stack_for_clickability():
    layers = [
        Layer(role="container", name="Pallavi", state="occluded", objects=[_msg("check link", matches=True, point=(1, 1))]),
        Layer(role="action_menu", objects=[{"kind": "menu_item", "text": "Forward", "point": [2, 2]}]),
    ]
    union = flat_objects(layers)
    texts = {o.get("text") for o in union}
    assert "check link" in texts and "Forward" in texts


def test_render_lists_every_layer_and_overlay():
    layers = [
        Layer(role="container", name="Pallavi", state="occluded", objects=[_msg("check zarooratwala", matches=True)]),
        Layer(role="action_menu", objects=[{"kind": "menu_item", "text": "Forward"}, {"kind": "menu_item", "text": "Reply"}]),
    ]
    text = render_layers(layers, task_context="next: reveal_actions")
    assert "2 layers" in text
    assert "container" in text and '"Pallavi"' in text and "occluded" in text
    assert "action_menu" in text and "Forward" in text
    assert "Task context: next: reveal_actions" in text


def test_container_and_find_helpers():
    layers = [Layer(role="container", name="x"), Layer(role="destination", name="picker")]
    assert container_layer(layers).name == "x"
    assert find_layer(layers, "destination").name == "picker"
    assert find_layer(layers, "action_menu") is None
