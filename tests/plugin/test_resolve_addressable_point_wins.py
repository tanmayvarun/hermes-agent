"""Decision screen points must not lose to a mismatched label→AX resolve."""

from __future__ import annotations

from types import SimpleNamespace

from plugin.agent.capabilities.open_entity import resolve_addressable


class _Overlay:
    def resolve_target(self, world, label, action):
        # Sidebar search echo of the same URL — far from the chat-pane point.
        return SimpleNamespace(
            id=1,
            label=label,
            bounds=(180.0, 230.0, 40.0, 20.0),
            visible=True,
        )


def test_decision_point_wins_over_distant_label_match():
    world = SimpleNamespace(entities={})
    entity = resolve_addressable(
        "https://www.zarooratwala.com/?",
        {"world": world, "point": [907, 156], "app": "WhatsApp"},
        _Overlay(),
        app="WhatsApp",
    )
    assert entity.bounds is not None
    # Point-sized box centered near 907,156 — not the sidebar box at x=180.
    assert entity.bounds[0] > 800


def test_agreeing_entity_bounds_are_kept():
    world = SimpleNamespace(entities={})

    class _Near:
        def resolve_target(self, world, label, action):
            return SimpleNamespace(
                id=2,
                label=label,
                bounds=(900.0, 150.0, 40.0, 20.0),
                visible=True,
            )

    entity = resolve_addressable(
        "https://example.com",
        {"world": world, "point": [910, 160], "app": "WhatsApp"},
        _Near(),
        app="WhatsApp",
    )
    assert entity.bounds == (900.0, 150.0, 40.0, 20.0)
