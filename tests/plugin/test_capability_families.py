"""Tests for capability families, progressive disclosure, I/O and skill kinds."""

from dataclasses import replace

from plugin.agent.capabilities.base import CapabilitySpec, Substrate
from plugin.agent.executive.capabilities import (
    CapabilityDescriptor,
    CapabilityRegistry,
    default_registry,
)


def test_descriptors_carry_inputs_outputs_and_family():
    reg = default_registry()
    open_entity = reg.get("open_entity")
    assert open_entity is not None
    assert open_entity.family == "navigation"
    assert "surface" in open_entity.outputs
    assert open_entity.inputs  # consumes something
    assert open_entity.kind == "verb"


def test_families_group_the_catalog():
    reg = default_registry()
    families = reg.families()
    assert "search" in families
    assert "navigation" in families
    # compose_search_query and locate_content are both search-family.
    assert "compose_search_query" in families["search"]
    assert "locate_content" in families["search"]


def test_disclosure_reports_relevant_of_installed():
    reg = default_registry()
    view = reg.disclosure(meta_action="act", facts=["addressable_entity"], limit=3)
    assert view["installed_count"] == len(reg.descriptors)
    assert view["relevant_count"] <= 3
    assert view["relevant_count"] >= 1
    assert isinstance(view["families"], dict)


def test_expand_family_returns_only_that_family():
    reg = default_registry()
    nav = reg.expand_family("navigation")
    assert nav
    assert all(d.family == "navigation" for d in nav)


def test_a_skill_can_be_registered_as_a_capability():
    reg = CapabilityRegistry.from_catalog()
    skill_spec = CapabilitySpec(
        name="summarize_thread",
        substrate=Substrate.TASK_EVIDENCE,
        verb="summarize",
        description="A bounded sub-agent that reads a thread and returns a summary.",
        reversible=True,
    )
    reg.register(
        CapabilityDescriptor(
            spec=skill_spec,
            cost="medium",
            reliability=0.75,
            kind="bounded_agent",
            inputs=("open_conversation",),
            outputs=("summary",),
        )
    )
    got = reg.get("summarize_thread")
    assert got is not None
    assert got.kind == "bounded_agent"
    assert "summary" in got.outputs


def test_reliability_update_preserves_the_new_fields():
    reg = CapabilityRegistry.from_catalog()
    before = reg.get("open_entity")
    reg.observe_reliability("open_entity", success=False)
    after = reg.get("open_entity")
    assert after.reliability < before.reliability
    # I/O, family and kind survive the EMA update.
    assert after.inputs == before.inputs
    assert after.outputs == before.outputs
    assert after.kind == before.kind
