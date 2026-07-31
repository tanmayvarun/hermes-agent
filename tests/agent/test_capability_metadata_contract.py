from agent.capabilities.base import (
    Capability,
    CapabilityContext,
    CapabilityResult,
    SelectedMetadataSpec,
)


class _SpecCapability(Capability):
    name = "spec_cap"
    selected_metadata_spec = SelectedMetadataSpec(
        required_fields=("url", "title"),
        strongly_expected_fields=("published_at",),
        at_least_one_of=(("author", "caption"),),
        missing_field_policy="downgrade",
    )

    def execute(self, ctx: CapabilityContext) -> CapabilityResult:
        return CapabilityResult(
            status="success",
            capability=self.name,
            output={
                "selected": {
                    "url": "https://example.com/item",
                }
            },
        )


def test_metadata_contract_downgrades_when_required_fields_missing():
    result = _SpecCapability().execute_objective("resolve latest thing")
    assert result.status == "partial"
    assert any(obs.get("step") == "metadata_assertions" for obs in result.observations)
    joined = " ".join(result.unresolved_questions)
    assert "required metadata" in joined
    assert "strongly expected metadata" in joined
    assert "at least one of" in joined

