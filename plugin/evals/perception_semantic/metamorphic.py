"""Metamorphic variants for cross-surface selection fixtures.

Vary one causal fact at a time. Background selection count changes must NOT
flip destination_selected; checking a recipient checkbox is the single causal
positive transform.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List

from plugin.evals.perception_semantic.schema import (
    ActionSpec,
    GoldenPerceptionCase,
    case_to_dict,
)


def _set_claim(case: GoldenPerceptionCase, predicate: str, **fields: Any) -> None:
    for c in case.claims:
        if c.predicate == predicate:
            for k, v in fields.items():
                setattr(c, k, v)
            return


def _ax_relabel_selected(packet: Dict[str, Any], text: str) -> None:
    obs = packet.get("observation")
    if not isinstance(obs, dict):
        return
    for node in obs.get("ax_evidence") or []:
        if isinstance(node, dict) and str(node.get("label") or "").endswith("Selected"):
            node["label"] = text


def variant_source_count(
    base: GoldenPerceptionCase, count: int
) -> GoldenPerceptionCase:
    data = case_to_dict(base)
    data["id"] = f"{base.id}__source_{count}_selected"
    data["metamorphic_of"] = base.id
    data["metamorphic_transform"] = f"source_selected_count={count}"
    case = GoldenPerceptionCase.from_dict(data)
    _set_claim(case, "source_message_selected_count", value=count)
    _ax_relabel_selected(case.packet, f"{count} Selected")
    if case.annotated_response and isinstance(case.annotated_response.get("world_model"), dict):
        for b in case.annotated_response["world_model"].get("beliefs") or []:
            if isinstance(b, dict) and b.get("predicate") == "source_message_selected_count":
                b["value"] = int(count)
                b["evidence"] = [f"selection chrome shows {count} selected"]
        for o in case.annotated_response["world_model"].get("objects") or []:
            if isinstance(o, dict) and str(o.get("text") or "").endswith("Selected"):
                o["text"] = f"{count} Selected"
    # Critical invariant unchanged:
    _set_claim(case, "destination_selected", value=False)
    _set_claim(case, "destination_selected_count", value=0)
    return case


def variant_destination_name(
    base: GoldenPerceptionCase, name: str
) -> GoldenPerceptionCase:
    data = case_to_dict(base)
    data["id"] = f"{base.id}__dest_{name.lower()}"
    data["metamorphic_of"] = base.id
    data["metamorphic_transform"] = f"destination={name}"
    case = GoldenPerceptionCase.from_dict(data)
    if isinstance(case.packet.get("goal"), dict):
        case.packet["goal"]["destination"] = name
    po = case.packet.get("perception_objective")
    if isinstance(po, dict):
        po["objective"] = str(po.get("objective") or "").replace("Tanmay", name)
        po["questions"] = [
            str(q).replace("Tanmay", name) for q in (po.get("questions") or [])
        ]
    for a in case.acceptable_actions:
        if a.text:
            a.text = name
    for c in case.claims:
        if c.subject:
            c.subject = name
    return case


def variant_recipient_selected(
    base: GoldenPerceptionCase, name: str = "Tanmay"
) -> GoldenPerceptionCase:
    """Causal positive: recipient checkbox selected inside the picker."""
    data = case_to_dict(base)
    data["id"] = f"{base.id}__dest_selected_{name.lower()}"
    data["metamorphic_of"] = base.id
    data["metamorphic_transform"] = "recipient_checkbox_selected"
    case = GoldenPerceptionCase.from_dict(data)
    _set_claim(case, "destination_selected", value=True)
    _set_claim(case, "destination_selected_count", value=1)
    _set_claim(case, "destination_visible", value=True, subject=name)
    case.forbidden = [
        f for f in case.forbidden if f.predicate != "destination_selected"
    ]
    case.forbidden_actions = [
        a
        for a in case.forbidden_actions
        if a not in {"invoke_forward", "commit_forward"}
    ]
    case.acceptable_actions = [
        ActionSpec(
            family="invoke_affordance", surface="forward_picker", text="Forward"
        )
    ]
    if case.annotated_response and isinstance(case.annotated_response.get("world_model"), dict):
        wm = case.annotated_response["world_model"]
        wm.setdefault("objects", []).append(
            {
                "id": "dest_row",
                "kind": "contact_row",
                "text": name,
                "selected": True,
                "matches_goal": True,
                "owner_surface": "forward_picker",
                "semantic_role": "recipient",
                "point": [760, 360],
            }
        )
        for b in wm.get("beliefs") or []:
            if not isinstance(b, dict):
                continue
            if b.get("predicate") in {
                "destination_selected",
                "destination_selected_count",
            }:
                b["value"] = True
                b["owner_surface"] = "forward_picker"
                b["semantic_role"] = "destination_selection"
                b["evidence"] = ["recipient checkbox selected in forward_picker"]
                b.pop("rejected_evidence", None)
            if b.get("predicate") == "destination_visible":
                b["value"] = True
        case.annotated_response["affordance_stance"] = "act_clear"
        case.annotated_response["suggested_actions"] = [
            {
                "rank": 1,
                "family": "invoke_affordance",
                "text": "Forward",
                "confidence": 0.95,
                "why": "destination selected inside picker",
            }
        ]
    # Contaminated path not meaningful for positive causal variant.
    case.contaminated_response = None
    return case


def expand_family(base: GoldenPerceptionCase) -> List[GoldenPerceptionCase]:
    """Expand only cross-surface selection families.

    Latent-affordance / reveal / binding goldens are not selection metamorphic
    families — applying 1→2→3 Selected transforms there invents false variants.
    """
    frozen = GoldenPerceptionCase.from_dict(case_to_dict(base))
    phenoms = {str(p) for p in (frozen.phenomena or [])}
    if "cross_surface_selection" not in phenoms:
        return [frozen]
    out = [frozen]
    for n in (2, 3):
        out.append(variant_source_count(frozen, n))
    out.append(variant_destination_name(frozen, "Rahul"))
    out.append(variant_recipient_selected(frozen, "Tanmay"))
    return out
