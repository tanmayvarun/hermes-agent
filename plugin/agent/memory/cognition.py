"""EntityResolver + ActionRiskPolicy + ContextAssembler + channel grounding.

Memory supplies evidence; this module interprets and proposes — RoleBinder commits.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence

from plugin.agent.memory.types import (
    BindingUncertainty,
    EntityBindingProposal,
    MemoryEvidencePacket,
    MemoryQuery,
    RankedCandidate,
)


@dataclass
class DecisionContext:
    """Boring ContextAssembler output — not an identity decision."""

    packet: MemoryEvidencePacket
    working_notes: list[str] = field(default_factory=list)
    token_budget: int = 2000
    truncated: bool = False


class ContextAssembler:
    """Gather / dedupe / budget / format only — does not resolve identity."""

    def assemble(
        self,
        packet: MemoryEvidencePacket,
        *,
        max_ranked: int = 8,
        working_notes: Optional[Sequence[str]] = None,
    ) -> DecisionContext:
        ranked = list(packet.ranked[:max_ranked])
        truncated = len(packet.ranked) > max_ranked
        slim = MemoryEvidencePacket(
            query_purpose=packet.query_purpose,
            recall=list(packet.recall),
            ranked=ranked,
            evidence=list(packet.evidence[:max_ranked]),
            projection_states=list(packet.projection_states),
            provenance_summary=packet.provenance_summary,
            metadata=dict(packet.metadata),
        )
        return DecisionContext(
            packet=slim,
            working_notes=list(working_notes or []),
            truncated=truncated,
        )


class EntityResolver:
    """Interpretation authority over MemoryEvidencePacket."""

    def resolve(
        self,
        *,
        surface_form: str,
        role: str,
        packet: MemoryEvidencePacket,
        working_context: Optional[Mapping[str, Any]] = None,
    ) -> EntityBindingProposal:
        ranked = list(packet.ranked)
        if not ranked:
            return EntityBindingProposal(
                role=role,
                surface_form=surface_form,
                uncertainty=BindingUncertainty(
                    confidence=0.0,
                    margin=0.0,
                    ambiguity_reasons=["no_candidates"],
                    evidence_quality=0.0,
                ),
            )

        top = ranked[0]
        second = ranked[1] if len(ranked) > 1 else None
        margin = top.final_score - (second.final_score if second else 0.0)
        reasons: list[str] = []

        # Qualitative ambiguity: two strong exact-alias competitors vs one exact + weak distractor
        exact_hits = [
            r
            for r in ranked[:5]
            if r.feature_scores.get("alias_exact", 0.0) >= 1.0
        ]
        if len(exact_hits) >= 2 and margin < 0.25:
            top_rec = float(top.feature_scores.get("interaction_recency", 0.0))
            sec_rec = float(
                second.feature_scores.get("interaction_recency", 0.0) if second else 0.0
            )
            # Day-0 WhatsApp often lacks frequency. A large recency gap
            # (e.g. today vs years-stale) is sufficient personal signal —
            # do not force ASK solely because both share an exact alias.
            recency_dominant = (
                top_rec >= 0.8
                and (top_rec - sec_rec) >= 0.7
                and margin >= 0.18
            )
            if not recency_dominant:
                reasons.append("multiple_exact_name_matches")
        if second and margin < 0.08:
            reasons.append("close_numeric_margin")
        # Recency unknown for everyone is not the same as "top is stale".
        # Only flag when another candidate has observed recency and top does not.
        top_rec = float(top.feature_scores.get("interaction_recency", 0.0))
        if top_rec < 0.1 and len(ranked) > 1:
            others_have_recency = any(
                float(r.feature_scores.get("interaction_recency", 0.0)) >= 0.1
                for r in ranked[1:5]
            )
            if others_have_recency:
                reasons.append("top_candidate_stale_interactions")
        if not reasons and margin >= 0.2 and top.final_score >= 0.45:
            # clear winner
            pass
        elif not reasons and len(ranked) == 1:
            pass
        elif not reasons and margin < 0.15:
            reasons.append("insufficient_margin")

        # Unique exact alias is strong Day-0 evidence even when frequency/recency
        # are still unknown (score may be ~0.30 from alias alone).
        unique_exact = (
            len(exact_hits) == 1
            and float(top.feature_scores.get("alias_exact", 0.0)) >= 1.0
            and margin >= 0.15
        )

        evidence_quality = min(
            1.0,
            0.4 * top.feature_scores.get("alias_exact", 0.0)
            + 0.3 * top.feature_scores.get("interaction_recency", 0.0)
            + 0.3 * top.feature_scores.get("interaction_frequency", 0.0),
        )

        feat = dict(top.feature_scores)
        if unique_exact:
            feat["unique_exact_alias"] = 1.0

        uncertainty = BindingUncertainty(
            top_candidate=top.ref,
            alternatives=[r.ref for r in ranked[1:5]],
            confidence=top.final_score,
            margin=margin,
            ambiguity_reasons=reasons,
            evidence_quality=evidence_quality,
            feature_scores=feat,
        )
        return EntityBindingProposal(
            role=role,
            entity_id=top.ref,
            surface_form=surface_form,
            alternatives=[r.ref for r in ranked[1:5]],
            evidence=[r.explanation for r in ranked[:3]],
            uncertainty=uncertainty,
            ranked=ranked,
        )


@dataclass(frozen=True)
class RiskDecision:
    action: str  # proceed | ask | refuse
    reason: str = ""


class ActionRiskPolicy:
    """Effect-dependent ambiguity tolerance — not fixed global thresholds alone."""

    # Relative risk levels for common effects
    EFFECT_RISK = {
        "open_chat": "low",
        "send_message": "moderate",
        "send_confidential": "high",
        "transfer_money": "very_high",
    }

    # Minimum qualitative evidence strength per risk class (BindingAssessment).
    # These are policy thresholds — not calibrated epistemic probabilities.
    MIN_STRENGTH = {
        "low": "weak",
        "moderate": "moderate",
        "high": "strong",
        "very_high": "decisive",
    }

    def allows(self, effect: str, uncertainty: BindingUncertainty) -> RiskDecision:
        risk = self.EFFECT_RISK.get(effect, "moderate")
        reasons = set(uncertainty.ambiguity_reasons)

        if "no_candidates" in reasons:
            return RiskDecision(action="ask", reason="no_candidates")

        # Qualitative: multiple exact names is riskier than exact+weak distractor
        if "multiple_exact_name_matches" in reasons:
            if risk in ("moderate", "high", "very_high"):
                return RiskDecision(
                    action="ask", reason="multiple_exact_name_matches"
                )

        if risk == "low":
            if uncertainty.confidence >= 0.25:
                return RiskDecision(action="proceed", reason="low_risk_effect")
            return RiskDecision(action="ask", reason="low_confidence")

        if risk == "moderate":
            unique_exact = (
                float(uncertainty.feature_scores.get("unique_exact_alias", 0.0)) >= 1.0
                and "multiple_exact_name_matches" not in reasons
            )
            if (
                uncertainty.confidence >= 0.45
                and uncertainty.margin >= 0.15
                and "multiple_exact_name_matches" not in reasons
            ):
                return RiskDecision(action="proceed", reason="clear_personal_margin")
            # Day-0: unique exact display-name match is enough to send when
            # frequency/recency are still unknown (alias-only score ~0.30).
            if unique_exact and uncertainty.margin >= 0.15 and not reasons:
                return RiskDecision(action="proceed", reason="unique_exact_alias")
            if uncertainty.margin < 0.1 or reasons:
                return RiskDecision(action="ask", reason="ambiguous_recipient")
            return RiskDecision(action="ask", reason="insufficient_confidence")

        if risk == "high":
            if (
                uncertainty.confidence >= 0.7
                and uncertainty.margin >= 0.25
                and uncertainty.evidence_quality >= 0.5
                and not reasons
            ):
                return RiskDecision(action="proceed", reason="high_bar_met")
            return RiskDecision(action="ask", reason="high_risk_requires_clarity")

        # very_high
        return RiskDecision(action="refuse", reason="very_high_risk_requires_explicit_confirm")

    def allows_binding(self, effect: str, assessment: Any) -> RiskDecision:
        """Consume qualitative BindingAssessment (evidence_strength classes).

        Epistemic gather produces BindingAssessment; this applies risk policy
        without treating policy constants as calibrated confidence.
        """
        from plugin.agent.brain.information_need import STRENGTH_ORDER

        action = str(getattr(assessment, "action", "") or "")
        strength = str(getattr(assessment, "evidence_strength", "") or "weak")
        reason = str(getattr(assessment, "reason", "") or "")
        amb = list(getattr(assessment, "ambiguity_reasons", None) or [])

        if action != "proceed" or amb:
            return RiskDecision(
                action="ask",
                reason=reason or (amb[0] if amb else "ambiguous_recipient"),
            )

        risk = self.EFFECT_RISK.get(effect, "moderate")
        if risk == "very_high":
            return RiskDecision(
                action="refuse",
                reason="very_high_risk_requires_explicit_confirm",
            )

        required = self.MIN_STRENGTH.get(risk, "moderate")
        if STRENGTH_ORDER.get(strength, -1) >= STRENGTH_ORDER.get(required, 99):
            return RiskDecision(
                action="proceed",
                reason=f"strength_{strength}_meets_{required}",
            )
        return RiskDecision(
            action="ask",
            reason=f"strength_{strength}_below_{required}",
        )


@dataclass
class EnvironmentReferent:
    entity_id: str
    provider: str
    external_id: str
    display_name: str = ""
    source_identity_id: str = ""


class ChannelGrounding:
    """Map committed canonical entity → channel identity (substrate grounding)."""

    def __init__(self, store: Any) -> None:
        self.store = store

    def resolve(
        self, entity_id: str, channel: str
    ) -> Optional[EnvironmentReferent]:
        ids = self.store.channel_identities_for_entity(
            entity_id, provider=channel.lower()
        )
        if not ids:
            # try without filter
            ids = self.store.channel_identities_for_entity(entity_id)
            ids = [s for s in ids if s.provider.lower() == channel.lower()]
        if not ids:
            return None
        sid = ids[0]
        return EnvironmentReferent(
            entity_id=entity_id,
            provider=sid.provider,
            external_id=sid.external_id,
            display_name=sid.display_name,
            source_identity_id=sid.source_identity_id,
        )


def resolve_person_for_effect(
    store: Any,
    *,
    surface_form: str,
    effect: str,
    channel: str = "",
    role: str = "recipient",
) -> dict[str, Any]:
    """Convenience: retrieve → assemble → resolve → risk policy (+ optional grounding)."""
    from plugin.agent.memory.retriever import MemoryRetriever

    packet = MemoryRetriever(store).retrieve(
        MemoryQuery(
            purpose="entity_resolution",
            text=surface_form,
            current_context={"channel": channel, "user_entity_id": "user:local"},
            limit=8,
        )
    )
    ctx = ContextAssembler().assemble(packet)
    proposal = EntityResolver().resolve(
        surface_form=surface_form, role=role, packet=ctx.packet
    )
    decision = ActionRiskPolicy().allows(effect, proposal.uncertainty)
    grounded = None
    if decision.action == "proceed" and proposal.entity_id and channel:
        grounded = ChannelGrounding(store).resolve(proposal.entity_id, channel)
    return {
        "proposal": proposal,
        "decision": decision,
        "grounding": grounded,
        "packet": packet,
    }
