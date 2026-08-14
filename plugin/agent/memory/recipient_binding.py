"""Pre-MethodFrontier recipient resolution via MemorySystem.

Ensures send/forward effects resolve EntityRef before substrate selection.

Architecture order (merge-critical):
  1. EntityResolver → BindingUncertainty (epistemic)
  2. If epistemic ambiguity → EvidenceAcquisitionEpisode (Brain/MetaActor)
  3. Identity consultant reinterprets structured hypotheses
  4. ActionRiskPolicy on the post-evidence binding — never overridden by gather
  5. proceed | ASK | refuse

ASK is terminal information acquisition after bounded evidence effort.
"""

from __future__ import annotations

from dataclasses import dataclass, field
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
from plugin.agent.memory.types import BindingUncertainty, MemoryQuery


@dataclass
class RecipientResolutionResult:
    status: str  # proceed | ask | refuse | skip
    surface_form: str = ""
    entity_id: str = ""
    channel_external_id: str = ""
    channel_provider: str = ""
    display_name: str = ""
    question: str = ""
    alternatives: Optional[list] = None
    reason: str = ""
    bootstrap_state: str = ""
    evidence_probes: list[str] = field(default_factory=list)
    identity_hypotheses: list = field(default_factory=list)


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
        return "send_message"
    if any("send" in e for e in desired_effects):
        return "send_message"
    return "send_message"


def _epistemically_ambiguous(proposal: Any) -> bool:
    """True when binding uncertainty needs more evidence (not policy refusal)."""
    unc = getattr(proposal, "uncertainty", None)
    if unc is None:
        return True
    reasons = set(getattr(unc, "ambiguity_reasons", None) or [])
    if "no_candidates" in reasons:
        return True
    if reasons:
        return True
    margin = float(getattr(unc, "margin", 0.0) or 0.0)
    conf = float(getattr(unc, "confidence", 0.0) or 0.0)
    if margin < 0.15 or conf < 0.45:
        # Unique exact alias may still be clear enough — leave to risk policy
        # after gather skip; treat as ambiguous for gather when multi-candidate.
        alts = list(getattr(unc, "alternatives", None) or [])
        if alts and margin < 0.15:
            return True
    return False


def _working_context_disputes_top(
    proposal: Any, working_context: Optional[dict[str, Any]]
) -> bool:
    wc = dict(working_context or {})
    l1_id = str(wc.get("recent_entity_id") or "").strip()
    l1_name = str(wc.get("recent_entity_name") or "").strip().lower()
    if not l1_id and not l1_name:
        return False
    ranked = list(getattr(proposal, "ranked", None) or [])
    top = str(getattr(proposal, "entity_id", "") or "")
    if len(ranked) < 2 or not top:
        return False
    for r in ranked[:6]:
        eid = str(getattr(r, "ref", "") or "")
        payload = dict(getattr(r, "payload", None) or {})
        cname = str(payload.get("canonical_name") or "").lower()
        hit = (l1_id and eid == l1_id) or (
            l1_name and (l1_name == cname or l1_name in cname)
        )
        if hit and eid != top:
            return True
    return False


def _uncertainty_for_entity(
    proposal: Any,
    *,
    entity_id: str,
    reason: str,
) -> BindingUncertainty:
    """Build uncertainty for ActionRiskPolicy after epistemic resolution."""
    ranked = list(getattr(proposal, "ranked", None) or [])
    top = next((r for r in ranked if str(r.ref) == entity_id), None)
    if top is None and ranked:
        top = ranked[0]
    conf = float(getattr(top, "final_score", 0.55) or 0.55) if top else 0.55
    # Established binding after consultation — clear margin for policy.
    return BindingUncertainty(
        top_candidate=entity_id,
        alternatives=[
            str(r.ref)
            for r in ranked
            if str(r.ref) != entity_id
        ][:4],
        confidence=max(conf, 0.5),
        margin=0.25,
        ambiguity_reasons=[],
        evidence_quality=0.6,
        feature_scores=dict(getattr(top, "feature_scores", None) or {})
        if top
        else {},
    )


def _commit_goal(
    goal: Any,
    *,
    surface: str,
    entity_id: str,
    channel: str,
    memory: Any,
) -> tuple[str, str]:
    grounded = ChannelGrounding(memory).resolve(entity_id, channel)
    display = str((grounded.display_name if grounded else "") or surface)
    try:
        goal.committed_entity_id = entity_id
        goal.committed_channel_id = grounded.external_id if grounded else ""
        goal.committed_display_name = display
        if display:
            if getattr(goal, "target_contact", ""):
                goal.target_contact = display
            if getattr(goal, "recipient", ""):
                goal.recipient = display
            if getattr(goal, "contact", "") and not getattr(goal, "link_query", ""):
                if str(goal.contact).strip().lower() == surface.lower():
                    goal.contact = display
    except Exception:
        pass
    return (grounded.external_id if grounded else ""), display


def resolve_recipient_before_methods(
    memory: Any,
    *,
    goal: Any,
    desired_effects: Optional[list[str]] = None,
    channel: str = "whatsapp",
    bootstrap_state: Optional[str] = None,
    working_context: Optional[dict[str, Any]] = None,
    world_probes: bool = True,
    evidence_budget: int = 4,
) -> RecipientResolutionResult:
    """Resolve person recipients: evidence first (if needed), then risk policy."""
    surface = _surface_form_from_goal(goal)
    if not surface:
        return RecipientResolutionResult(status="skip", reason="no_surface_form")

    if not isinstance(memory, LocalMemorySystem):
        return RecipientResolutionResult(
            status="skip",
            surface_form=surface,
            reason="memory_not_local",
        )

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
                "working_context": dict(working_context or {}),
            },
            limit=8,
        )
    )
    ctx = ContextAssembler().assemble(packet)
    proposal = EntityResolver().resolve(
        surface_form=surface, role="recipient", packet=ctx.packet
    )

    if not proposal.entity_id or not packet.ranked:
        return RecipientResolutionResult(
            status="ask",
            surface_form=surface,
            question=f"I couldn't find a contact matching '{surface}'. Who did you mean?",
            reason="no_candidates",
            bootstrap_state=boot,
        )

    probes: list[str] = []
    hyp_dicts: list = []
    entity_id = str(proposal.entity_id)
    epistemic_reason = "resolved"
    uncertainty = proposal.uncertainty

    needs_gather = _epistemically_ambiguous(proposal) or _working_context_disputes_top(
        proposal, working_context
    )

    if needs_gather:
        from plugin.agent.brain.evidence_acquisition import acquire_for_entity_resolution
        from plugin.agent.brain.identity_consultant import consult_after_episode

        episode = acquire_for_entity_resolution(
            memory,
            list(proposal.ranked or packet.ranked),
            surface=surface,
            channel=channel,
            working_context=working_context,
            budget=evidence_budget,
            world_probes=world_probes,
        )
        probes = episode.probe_labels()
        consultation = consult_after_episode(episode, surface=surface)
        hyp_dicts = [h.to_dict() for h in consultation.hypotheses]

        if consultation.action == "proceed" and consultation.entity_id:
            entity_id = consultation.entity_id
            epistemic_reason = consultation.reason
            uncertainty = _uncertainty_for_entity(
                proposal, entity_id=entity_id, reason=epistemic_reason
            )
        else:
            # Epistemic ASK — still run risk policy only for refuse-class effects
            # after failed discrimination; ASK is the epistemic outcome.
            alts = [
                {"entity_id": h.entity_id, "label": h.display_name}
                for h in consultation.hypotheses[:5]
            ]
            if not alts:
                for r in proposal.ranked[:5]:
                    alts.append(
                        {
                            "entity_id": r.ref,
                            "label": str(r.payload.get("canonical_name") or r.ref),
                        }
                    )
            labels = " or ".join(f"**{a['label']}**" for a in alts[:3]) or surface
            # Policy refuse must still win for very-high-risk effects even when
            # identity is unknown — check risk with remaining uncertainty.
            decision_early = ActionRiskPolicy().allows(effect, proposal.uncertainty)
            if decision_early.action == "refuse":
                return RecipientResolutionResult(
                    status="refuse",
                    surface_form=surface,
                    entity_id=proposal.entity_id,
                    reason=decision_early.reason,
                    bootstrap_state=boot,
                    evidence_probes=probes,
                    identity_hypotheses=hyp_dicts,
                )
            return RecipientResolutionResult(
                status="ask",
                surface_form=surface,
                entity_id=proposal.entity_id,
                alternatives=alts,
                question=(
                    f"I checked personal memory and available channel signals, "
                    f"but still can't tell which '{surface}' you mean. "
                    f"Do you mean {labels}?"
                ),
                reason=consultation.reason or "ambiguity_survived_evidence_budget",
                bootstrap_state=boot,
                evidence_probes=probes,
                identity_hypotheses=hyp_dicts,
            )

    # Binding epistemically established (or was clear) → ActionRiskPolicy
    decision = ActionRiskPolicy().allows(effect, uncertainty)

    if decision.action == "refuse":
        return RecipientResolutionResult(
            status="refuse",
            surface_form=surface,
            entity_id=entity_id,
            reason=decision.reason,
            bootstrap_state=boot,
            evidence_probes=probes,
            identity_hypotheses=hyp_dicts,
        )

    if decision.action == "ask":
        alts = []
        for r in (proposal.ranked or [])[:5]:
            alts.append(
                {
                    "entity_id": r.ref,
                    "label": str(r.payload.get("canonical_name") or r.ref),
                }
            )
        labels = " or ".join(f"**{a['label']}**" for a in alts[:3]) or surface
        return RecipientResolutionResult(
            status="ask",
            surface_form=surface,
            entity_id=entity_id,
            alternatives=alts,
            question=f"Which '{surface}' should I use — {labels}?",
            reason=decision.reason,
            bootstrap_state=boot,
            evidence_probes=probes,
            identity_hypotheses=hyp_dicts,
        )

    # proceed
    ext, display = _commit_goal(
        goal, surface=surface, entity_id=entity_id, channel=channel, memory=memory
    )
    if not display or display == surface:
        for r in proposal.ranked or []:
            if str(r.ref) == entity_id:
                display = str(r.payload.get("canonical_name") or display or surface)
                break
        try:
            goal.committed_display_name = display
        except Exception:
            pass
    return RecipientResolutionResult(
        status="proceed",
        surface_form=surface,
        entity_id=entity_id,
        channel_external_id=ext,
        channel_provider=channel,
        display_name=display,
        reason=epistemic_reason if needs_gather else (decision.reason or "resolved"),
        bootstrap_state=boot,
        evidence_probes=probes,
        identity_hypotheses=hyp_dicts,
    )
