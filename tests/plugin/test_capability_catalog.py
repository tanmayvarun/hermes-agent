"""General capability catalog: representation substrate + realized verbs."""

from __future__ import annotations

from plugin.agent.capabilities.base import CapabilityRequest, CapabilityStatus, Substrate
from plugin.agent.capabilities.catalog import (
    MOTOR_PRIMITIVES,
    all_specs,
    model_allowed_actions,
    realized_verbs,
    spec_by_name,
)
from plugin.agent.capabilities.dispatch import can_dispatch, dispatch, searchable_surface
from plugin.agent.capabilities.locate_content import MACOS_FIND
from plugin.agent.unified_cognition import ALLOWED_ACTIONS


def test_catalog_names_the_general_capabilities():
    names = {s.name for s in all_specs()}
    assert {
        "locate_content",
        "open_entity",
        "select_content",
        "reveal_actions",
        "invoke_affordance",
        "dismiss_transient",
        "revert_effects",
        "commit_irreversible",
    } <= names


def test_only_realized_capabilities_enter_the_model_vocabulary():
    allowed = model_allowed_actions()
    for verb in realized_verbs():
        assert verb in allowed
    for motor in MOTOR_PRIMITIVES:
        assert motor in allowed
    # Nothing outside the catalog sneaks in as a fake capability.
    assert "whatsapp_forward_script" not in allowed


def test_unified_allowed_actions_comes_from_the_catalog():
    assert ALLOWED_ACTIONS == model_allowed_actions()
    assert set(realized_verbs()) <= set(ALLOWED_ACTIONS)


def test_commit_irreversible_is_never_marked_reversible():
    spec = spec_by_name("commit_irreversible")
    assert spec is not None
    assert not spec.reversible
    assert spec.substrate == Substrate.GATED_TARGET
    assert spec.status == CapabilityStatus.REALIZED


def test_realized_capabilities_are_dispatchable():
    for spec in all_specs():
        if spec.status == CapabilityStatus.REALIZED:
            assert can_dispatch(spec.name), spec.name


def test_searchable_surface_projects_host_find_declaration():
    class WithFind:
        find_affordance = MACOS_FIND

    class WithoutFind:
        pass

    asserted = searchable_surface(WithFind(), app="WhatsApp", surface="conversation")
    bare = searchable_surface(WithoutFind(), app="SomeApp")

    assert asserted.find_declared
    assert asserted.scoped_to_surface
    assert not bare.find_declared


def test_locate_without_query_is_rejected_at_dispatch():
    class Overlay:
        find_affordance = MACOS_FIND

    outcome = dispatch(CapabilityRequest(name="locate_content", app="WhatsApp", arg=""), Overlay())
    assert not outcome.ok
    assert "query" in outcome.message.lower() or "text" in outcome.message.lower()


def test_every_realized_reversible_capability_is_marked_reversible():
    for spec in all_specs():
        if spec.status == CapabilityStatus.REALIZED and spec.name != "commit_irreversible":
            assert spec.reversible, spec.name
