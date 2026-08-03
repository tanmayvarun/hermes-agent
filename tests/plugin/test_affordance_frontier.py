"""The frontier must state what is true, what is expected, and keep them apart."""

from plugin.agent.affordance_frontier import (
    STATUS_LATENT,
    STATUS_OBSERVED,
    STATUS_PROBE,
    TransitionMemory,
    build_affordance_frontier,
    merge_edges,
    observed_from_ax,
    structural_edges,
)


class _Overlay:
    reveal_mode = "context_click"


_AX = [
    {"id": 7, "role": "AXSearchField", "label": "Search", "bounds": [10, 20, 200, 30], "actions": ["AXPress"]},
    {"id": 8, "role": "AXButton", "label": "Voice call", "bounds": [900, 20, 40, 30], "actions": ["AXPress"]},
    {"id": 9, "role": "AXButton", "label": "Send", "bounds": [900, 700, 40, 30], "actions": ["AXPress"]},
]

_OBJECTS = [
    {"id": "m1", "kind": "message", "text": "zarooratwala.com/fresh", "point": [980, 510], "matches_goal": True},
    {"id": "r1", "kind": "row", "text": "Pallavi", "point": [200, 300]},
]


def _frontier(**kwargs):
    params = {
        "surface": "conversation",
        "goal_kind": "whatsapp_forward_message",
        "ax_evidence": _AX,
        "objects": _OBJECTS,
        "overlay": _Overlay(),
    }
    params.update(kwargs)
    return build_affordance_frontier(**params)


def test_observed_actions_carry_provenance_and_an_actuator():
    """An action the model cannot execute or trace back is not worth sending."""
    frontier = _frontier()
    observed = frontier.observed_actions

    assert observed, "AX and the object inventory both offer actionable things"
    for affordance in observed:
        assert affordance.status == STATUS_OBSERVED
        assert affordance.actuators, f"{affordance.id} has no way to be executed"
        assert affordance.evidence, f"{affordance.id} states no provenance"


def test_send_is_observed_but_marked_irreversible():
    observed, _ = observed_from_ax(_AX, goal_kind="whatsapp_forward_message")
    send = [a for a in observed if a.target_label == "Send"]

    assert send, "Send is genuinely on screen"
    assert send[0].family == "commit_irreversible"
    assert send[0].reversible is False
    assert send[0].risk > 0


def test_off_task_controls_are_excluded_with_a_reason_not_dropped():
    """Voice call exists; pretending it does not is how the old graph lied."""
    frontier = _frontier()

    labels = {a.target_label for a in frontier.observed_actions}
    assert "Voice call" not in labels
    excluded = {item["target_label"]: item["reason"] for item in frontier.excluded_actions}
    assert "Voice call" in excluded
    assert "forward" in excluded["Voice call"]


def test_message_yields_a_probe_and_the_latent_actions_it_would_reveal():
    frontier = _frontier()

    probes = frontier.probe_actions
    assert probes, "a message object must offer a way to expose its actions"
    context = [p for p in probes if p.family == "reveal_actions"]
    assert context, "the WhatsApp overlay reveals message actions by context click"
    assert context[0].status == STATUS_PROBE
    assert context[0].expected_information_gain > 0
    assert {m.label for m in context[0].may_reveal} >= {"Forward", "Reply"}

    forward = [a for a in frontier.latent_actions if a.target_label == "Forward"]
    assert forward, "Forward must appear as latent, since it is not on screen"
    assert forward[0].status == STATUS_LATENT
    assert forward[0].available_now is False
    assert forward[0].trigger_action == context[0].id


def test_latent_actions_are_never_a_family_times_object_cross_product():
    """The polluted-graph regression: no message ever offers a voice call."""
    frontier = _frontier()

    for affordance in frontier.latent_actions + frontier.probe_actions:
        assert "call" not in (affordance.target_label or "").lower()
        assert affordance.evidence, "a latent action without a basis is an invention"

    rows_only = _frontier(objects=[{"kind": "row", "text": "Pallavi", "point": [200, 300]}])
    assert rows_only.latent_actions == []
    assert rows_only.probe_actions == []


def test_overlay_priors_contribute_latents_when_the_app_declares_them():
    class Declaring(_Overlay):
        def affordance_priors(self, surface):
            assert surface == "context_menu"
            return [
                {
                    "id": "forward_menu_item",
                    "label": "Forward",
                    "family": "invoke_affordance",
                    "available_after": "reveal_actions",
                    "probability": 0.9,
                    "basis": "whatsapp message menu",
                }
            ]

    frontier = _frontier(surface="context_menu", overlay=Declaring(), objects=[])
    declared = [a for a in frontier.latent_actions if a.id == "forward_menu_item"]

    assert declared and declared[0].evidence[0].source == "overlay_prior"


def test_whatsapp_declares_the_picker_send_no_object_prior_could_know():
    from plugin.agent.apps.whatsapp import WhatsAppOverlay

    frontier = _frontier(surface="forward_picker", overlay=WhatsAppOverlay(), objects=[])
    send = [a for a in frontier.latent_actions if a.target_label == "Send"]

    assert send, "Send appears once a recipient is chosen; say so before it does"
    assert send[0].available_now is False
    assert send[0].trigger_action == "resolve_entity"
    assert send[0].reversible is False

    assert WhatsAppOverlay().affordance_priors("conversation") == []


def test_structural_edges_stay_inside_the_goal_and_the_surface_graph():
    edges = structural_edges("conversation", "whatsapp_forward_message")
    pairs = {(e.from_action, e.to_surface) for e in edges}

    assert ("reveal_actions", "context_menu") in pairs
    assert all(e.enumeration_status == "predicted" for e in edges)
    # A conversation is not a legal parent of nothing at all, but every edge
    # offered must be one the goal can use.
    assert all(e.from_action != "start_call" for e in edges)


def test_observation_replaces_prediction_for_the_same_edge():
    memory = TransitionMemory()
    memory.record("conversation", "reveal_actions", "context_menu")
    memory.record("conversation", "reveal_actions", "context_menu")
    memory.record("conversation", "reveal_actions", "conversation")

    observed = memory.edges("conversation")
    seen = {(e.from_action, e.to_surface): e for e in observed}
    assert seen[("reveal_actions", "context_menu")].probability == 0.67
    assert seen[("reveal_actions", "context_menu")].enumeration_status == "observed"

    merged = merge_edges(observed, structural_edges("conversation", "whatsapp_forward_message"))
    context_edges = [
        e for e in merged if (e.from_action, e.to_surface) == ("reveal_actions", "context_menu")
    ]
    assert len(context_edges) == 1
    assert context_edges[0].enumeration_status == "observed"


def test_packet_shape_is_the_five_declared_classes():
    packet = _frontier().to_packet()

    assert set(packet) == {
        "surface",
        "observed_actions",
        "latent_actions",
        "probe_actions",
        "known_transition_edges",
        "excluded_actions",
    }
    for entry in packet["latent_actions"]:
        assert entry["available_now"] is False
        assert entry["available_after"]


def test_unknown_goal_is_not_filtered_as_if_it_were_a_forward():
    frontier = _frontier(goal_kind="spreadsheet_edit")
    labels = {a.target_label for a in frontier.observed_actions}

    assert "Voice call" in labels
    assert frontier.excluded_actions == []
