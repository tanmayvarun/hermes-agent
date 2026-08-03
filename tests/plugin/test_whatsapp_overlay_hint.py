"""The forward phase machine is demoted to an overlay hint.

The controller no longer reads WhatsApp phase names or binding shapes to decide
whether the source object is still being hunted; it asks the overlay, which
returns a domain-general blocking uncertainty the executive's sufficiency
judgement consumes.
"""

from __future__ import annotations

from plugin.agent.apps.whatsapp import WhatsAppOverlay


def _ft(phase: str, status: str) -> dict:
    return {
        "derived_phase": phase,
        "bindings": {"source_object": {"status": status}},
    }


def test_unresolved_source_in_a_hunt_phase_is_a_blocking_uncertainty():
    overlay = WhatsAppOverlay()
    assert overlay.observe_blocking_uncertainties(_ft("FIND_LINK", "unresolved")) == [
        "source_object_unresolved"
    ]
    assert overlay.observe_blocking_uncertainties(_ft("OPEN_FORWARD", "ambiguous")) == [
        "source_object_unresolved"
    ]


def test_resolved_source_is_not_blocking():
    overlay = WhatsAppOverlay()
    assert overlay.observe_blocking_uncertainties(_ft("FIND_LINK", "resolved")) == []


def test_a_later_phase_is_not_source_hunting():
    overlay = WhatsAppOverlay()
    assert overlay.observe_blocking_uncertainties(_ft("PICK_DEST", "unresolved")) == []


def test_empty_or_malformed_forward_task_is_safe():
    overlay = WhatsAppOverlay()
    assert overlay.observe_blocking_uncertainties({}) == []
    assert overlay.observe_blocking_uncertainties(None) == []  # type: ignore[arg-type]


def test_generic_overlay_has_no_forward_hint():
    from plugin.agent.apps.generic import GenericOverlay

    assert not hasattr(GenericOverlay(), "observe_blocking_uncertainties")
