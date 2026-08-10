"""Rebuild the production multimodal request from a frozen golden packet.

Eval must exercise the same prompt composition production uses — not a
hand-crafted ideal prompt that never ships.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from plugin.evals.perception_semantic.schema import GoldenPerceptionCase


def resolve_screenshot(case: GoldenPerceptionCase) -> str:
    if not case.screenshot:
        return ""
    shot = Path(case.screenshot)
    if shot.is_file():
        return str(shot)
    if case.record_dir:
        cand = Path(case.record_dir) / case.screenshot
        if cand.is_file():
            return str(cand)
    # Default experiments recording layout.
    for root in (
        Path("plugin/experiments/fixtures/perceptor"),
        Path(__file__).resolve().parents[3]
        / "experiments"
        / "fixtures"
        / "perceptor",
    ):
        cand = root / case.record_dir / case.screenshot if case.record_dir else root / case.screenshot
        if cand.is_file():
            return str(cand)
        cand2 = root / "cross_surface_184742" / Path(case.screenshot).name
        if cand2.is_file():
            return str(cand2)
    return ""


def project_production_messages(
    case: GoldenPerceptionCase,
    *,
    include_image: bool = True,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Return (messages, meta) using production ``_build_messages``."""
    from plugin.agent.unified_cognition import ALLOWED_ACTIONS, _build_messages

    packet = dict(case.packet or {})
    packet.setdefault("allowed_actions", list(ALLOWED_ACTIONS))
    # Ensure ownership addendum path sees a non-fast packet.
    shot = resolve_screenshot(case) if include_image else ""
    messages, size = _build_messages(packet, shot)
    system = ""
    for m in messages:
        if m.get("role") == "system":
            system = str(m.get("content") or "")
            break
    meta = {
        "image_size": list(size) if size else [],
        "screenshot": shot,
        "has_surface_ownership_addendum": "SURFACE OWNERSHIP" in system,
        "has_perception_objective": bool(packet.get("perception_objective")),
        "ax_count": len(
            (packet.get("observation") or {}).get("ax_evidence") or []
        ),
        "system_chars": len(system),
    }
    return messages, meta


def assert_production_projector(case: GoldenPerceptionCase) -> Dict[str, Any]:
    """Deterministic checks that the production projector is wired correctly."""
    messages, meta = project_production_messages(case, include_image=False)
    ok = bool(messages) and meta.get("has_surface_ownership_addendum")
    # Destination cases must carry an executive question in the packet.
    dest = str((case.packet.get("goal") or {}).get("destination") or "")
    if dest and str((case.packet.get("observation") or {}).get("active_interaction_surface") or "") in {
        "forward_picker",
        "destination_picker",
    }:
        ok = ok and bool(meta.get("has_perception_objective"))
    return {"ok": ok, "meta": meta, "message_roles": [m.get("role") for m in messages]}
