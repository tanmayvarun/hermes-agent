"""Pre-MethodFrontier recipient resolution via MemorySystem.

Ensures send/forward effects resolve EntityRef before substrate selection.
ComputerUse / gateway receive committed channel identity — not unresolved names.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from plugin.agent.memory.bootstrap import MemoryBootstrapState
from plugin.agent.memory.cognition import (
    ActionRiskPolicy,
    ChannelGrounding,
    ContextAssembler,
    EntityResolver,
)
from plugin.agent.memory.local_store import LocalMemorySystem
from plugin.agent.memory.retriever import MemoryRetriever
from plugin.agent.memory.types import MemoryQuery


@dataclass
class RecipientResolutionResult:
    status: str  # proceed | ask | skip
    surface_form: str = ""
    entity_id: str = ""
    channel_external_id: str = ""
    channel_provider: str = ""
    display_name: str = ""
    question: str = ""
    alternatives: Optional[list] = None
    reason: str = ""
    bootstrap_state: str = ""


def _surface_form_from_goal(goal: Any) -> str:
    if goal is None:
        return ""
    for attr in ("target_contact", "recipient", "contact"):
        val = str(getattr(goal, attr, "") or "").strip()
        if val:
            return val
    return ""


def _effect_for_goal(goal: Any, desired_effects: list[str]) -> str:
    kind = str(getattr(goal, "kind", "") or "").lower()
    if "forward" in kind or "forward_message" in desired_effects:
        # Sending a known body ("send hi to X") is still send_message risk.
        body = str(getattr(goal, "message_body", "") or "").strip()
        if body and not str(getattr(goal, "link_query", "") or "").strip():
            return "send_message"
        return "send_message"
    if any("send" in e for e in desired_effects):
        return "send_message"
    return "send_message"


def resolve_recipient_before_methods(
    memory: Any,
    *,
    goal: Any,
    desired_effects: Optional[list[str]] = None,
    channel: str = "whatsapp",
    bootstrap_state: Optional[str] = None,
) -> RecipientResolutionResult:
    """Run memory entity resolution for person recipients.

    Returns ``skip`` when memory is Noop / no surface form / no LocalMemorySystem.
    """
    surface = _surface_form_from_goal(goal)
    if not surface:
        return RecipientResolutionResult(status="skip", reason="no_surface_form")

    if not isinstance(memory, LocalMemorySystem):
        return RecipientResolutionResult(
            status="skip",
            surface_form=surface,
            reason="memory_not_local",
        )

    # Already committed this turn/session
    existing = str(getattr(goal, "committed_entity_id", "") or "").strip()
    if existing:
        grounded = ChannelGrounding(memory).resolve(existing, channel)
        return RecipientResolutionResult(
            status="proceed",
            surface_form=surface,
            entity_id=existing,
            channel_external_id=(
                grounded.external_id
                if grounded
                else str(getattr(goal, "committed_channel_id", "") or "")
            ),
            channel_provider=channel,
            display_name=str(getattr(goal, "committed_display_name", "") or surface),
            reason="already_committed",
            bootstrap_state=bootstrap_state or memory.get_bootstrap_state(),
        )

    boot = bootstrap_state or memory.get_bootstrap_state()
    effects = list(desired_effects or [])
    effect = _effect_for_goal(goal, effects)

    if boot in (
        MemoryBootstrapState.NOT_STARTED.value,
        MemoryBootstrapState.AUTH_REQUIRED.value,
        MemoryBootstrapState.SOURCE_UNAVAILABLE.value,
    ):
        # Don't claim identity readiness; prefer ASK / link rather than lexical guess.
        packet_preview = MemoryRetriever(memory).retrieve(
            MemoryQuery(
                purpose="entity_resolution",
                text=surface,
                current_context={"channel": channel, "user_entity_id": "user:local"},
                limit=8,
            )
        )
        if not packet_preview.ranked:
            if boot == MemoryBootstrapState.AUTH_REQUIRED.value:
                q = (
                    f"I can use your WhatsApp history to identify which '{surface}' "
                    f"you usually mean. Link WhatsApp on this device?"
                )
            elif boot == MemoryBootstrapState.SOURCE_UNAVAILABLE.value:
                q = (
                    f"WhatsApp memory isn't available yet, so I can't safely choose "
                    f"among contacts named '{surface}'. Link or retry when WhatsApp "
                    f"is connected?"
                )
            else:
                q = (
                    f"I don't have enough personal memory yet to resolve who "
                    f"'{surface}' is. Which contact should I use?"
                )
            return RecipientResolutionResult(
                status="ask",
                surface_form=surface,
                question=q,
                reason=f"bootstrap_{boot.lower() or 'not_started'}",
                bootstrap_state=boot,
            )

    packet = MemoryRetriever(memory).retrieve(
        MemoryQuery(
            purpose="entity_resolution",
            text=surface,
            current_context={
                "channel": channel,
                "user_entity_id": "user:local",
            },
            limit=8,
        )
    )
    ctx = ContextAssembler().assemble(packet)
    proposal = EntityResolver().resolve(
        surface_form=surface, role="recipient", packet=ctx.packet
    )

    # Insufficient memory after retrieve → ASK rather than lexical substrate guess
    if not proposal.entity_id or not packet.ranked:
        return RecipientResolutionResult(
            status="ask",
            surface_form=surface,
            question=f"I couldn't find a contact matching '{surface}'. Who did you mean?",
            reason="no_candidates",
            bootstrap_state=boot,
        )

    decision = ActionRiskPolicy().allows(effect, proposal.uncertainty)
    if decision.action == "ask" or decision.action == "refuse":
        alts = []
        for r in proposal.ranked[:5]:
            name = str(r.payload.get("canonical_name") or r.ref)
            alts.append({"entity_id": r.ref, "label": name})
        labels = " or ".join(f"**{a['label']}**" for a in alts[:3]) or surface
        return RecipientResolutionResult(
            status="ask",
            surface_form=surface,
            entity_id=proposal.entity_id,
            alternatives=alts,
            question=f"Do you mean {labels}?",
            reason=decision.reason or "ambiguous",
            bootstrap_state=boot,
        )

    grounded = ChannelGrounding(memory).resolve(proposal.entity_id, channel)
    display = str(
        (grounded.display_name if grounded else "")
        or proposal.ranked[0].payload.get("canonical_name")
        or surface
    )
    # Bind onto goal for substrate handoff
    try:
        goal.committed_entity_id = proposal.entity_id
        goal.committed_channel_id = grounded.external_id if grounded else ""
        goal.committed_display_name = display
        # Prefer resolved display name for search/send strings
        if display:
            if getattr(goal, "target_contact", ""):
                goal.target_contact = display
            if getattr(goal, "recipient", ""):
                goal.recipient = display
            if getattr(goal, "contact", "") and not getattr(goal, "link_query", ""):
                # Simple send: contact is the recipient
                if str(goal.contact).strip().lower() == surface.lower():
                    goal.contact = display
    except Exception:
        pass

    return RecipientResolutionResult(
        status="proceed",
        surface_form=surface,
        entity_id=proposal.entity_id,
        channel_external_id=grounded.external_id if grounded else "",
        channel_provider=channel,
        display_name=display,
        reason=decision.reason or "resolved",
        bootstrap_state=boot,
    )
