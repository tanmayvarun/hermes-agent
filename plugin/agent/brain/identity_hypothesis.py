"""Identity-domain evidence bags — representation only, not an orchestration brain.

Kept distinct so MetaActor can reason about *why* candidates are plausible
without collapsing into an opaque score.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

_QUALIFIER_TOKENS = re.compile(
    r"\b(phonepe|phone\s*pe|axis|hdfc|icici|work|office|official)\b",
    re.I,
)


@dataclass
class NameEvidence:
    match_kind: str  # exact | extended | qualified_partial | partial | none
    surface_form: str = ""
    canonical_name: str = ""
    aliases: list[str] = field(default_factory=list)


@dataclass
class SalienceEvidence:
    recency: float = 0.0
    frequency: float = 0.0
    frequency_known: bool = False
    # Three-way: unknown | known | error  (known implies frequency_known may be True)
    frequency_status: str = "unknown"
    recency_status: str = "unknown"  # unknown | known | error
    hot: float = 0.0
    last_interaction_at: Optional[float] = None


@dataclass
class ContextEvidence:
    working_context_hit: bool = False
    l1_preferred: bool = False
    reference_support: float = 0.0
    # Three-way: unknown | known_positive | known_negative | error
    reference_status: str = "unknown"
    active_project_hit: bool = False


@dataclass
class ChannelEvidence:
    provider: str = ""
    external_ids: list[str] = field(default_factory=list)
    display_name: str = ""


@dataclass
class IdentityHypothesis:
    entity_id: str
    display_name: str
    name: NameEvidence
    salience: SalienceEvidence = field(default_factory=SalienceEvidence)
    context: ContextEvidence = field(default_factory=ContextEvidence)
    channel: ChannelEvidence = field(default_factory=ChannelEvidence)
    gather_notes: list[str] = field(default_factory=list)
    opaque_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "display_name": self.display_name,
            "name": {
                "match_kind": self.name.match_kind,
                "surface_form": self.name.surface_form,
                "canonical_name": self.name.canonical_name,
            },
            "salience": {
                "recency": self.salience.recency,
                "frequency": self.salience.frequency,
                "frequency_known": self.salience.frequency_known,
                "frequency_status": self.salience.frequency_status,
                "recency_status": self.salience.recency_status,
                "hot": self.salience.hot,
                "last_interaction_at": self.salience.last_interaction_at,
            },
            "context": {
                "working_context_hit": self.context.working_context_hit,
                "l1_preferred": self.context.l1_preferred,
                "reference_support": self.context.reference_support,
                "reference_status": self.context.reference_status,
                "active_project_hit": self.context.active_project_hit,
            },
            "channel": {
                "provider": self.channel.provider,
                "external_ids": list(self.channel.external_ids),
            },
            "gather_notes": list(self.gather_notes),
            "opaque_score": self.opaque_score,
        }


def classify_name_match(
    surface: str, canonical: str, aliases: Optional[list[str]] = None
) -> str:
    s = (surface or "").strip().lower()
    name = (canonical or "").strip().lower()
    al = [(a or "").strip().lower() for a in (aliases or []) if a]
    if not s:
        return "none"
    if s == name or s in al:
        if s == name:
            return "exact"
        if name.startswith(s + " ") or name.endswith(" " + s) or f" {s} " in f" {name} ":
            if _QUALIFIER_TOKENS.search(name):
                return "qualified_partial"
            return "extended"
        return "exact"
    if s in name or any(s in a for a in al) or name.startswith(s):
        if _QUALIFIER_TOKENS.search(name) or any(_QUALIFIER_TOKENS.search(a) for a in al):
            return "qualified_partial"
        if name.startswith(s + " ") or any(a.startswith(s + " ") for a in al):
            return "extended"
        return "partial"
    return "none"


def hypotheses_from_ranked(
    ranked: list[Any],
    *,
    surface: str,
    memory: Any,
    channel: str = "whatsapp",
    working_context: Optional[dict[str, Any]] = None,
) -> list[IdentityHypothesis]:
    """Build structured hypotheses from retriever ranked candidates."""
    wc = dict(working_context or {})
    l1_name = str(
        wc.get("recent_entity_name") or wc.get("recent_entity") or ""
    ).strip().lower()
    l1_id = str(wc.get("recent_entity_id") or "").strip()
    projects = {
        str(p).strip().lower()
        for p in list(wc.get("recent_projects") or [])
        + list(wc.get("recent_topics") or [])
        if p
    }
    out: list[IdentityHypothesis] = []
    for r in ranked[:6]:
        eid = str(getattr(r, "ref", "") or "")
        payload = dict(getattr(r, "payload", None) or {})
        feats = dict(getattr(r, "feature_scores", None) or {})
        cname = str(payload.get("canonical_name") or "")
        aliases = list(payload.get("aliases") or [])
        match = classify_name_match(surface, cname, aliases)
        agg = None
        if hasattr(memory, "get_aggregate") and eid:
            try:
                ent = memory.get_entity(eid) if hasattr(memory, "get_entity") else None
                scope = getattr(ent, "scope", "personal") if ent else "personal"
                agg = memory.get_aggregate("user:local", eid, scope=scope)
            except Exception:
                agg = None
        freq_known = bool((getattr(agg, "metadata", None) or {}).get("frequency_known"))
        last_at = getattr(agg, "last_interaction_at", None) if agg else None
        ref_sup = 0.0
        ref_status = "unknown"
        if hasattr(memory, "recent_reference_support") and eid:
            try:
                ref_sup = float(memory.recent_reference_support(surface, eid) or 0.0)
                ref_status = "known_positive" if ref_sup >= 1.0 else "known_negative"
            except Exception:
                ref_sup = 0.0
                ref_status = "error"
        ext_ids: list[str] = []
        ch_disp = cname
        if hasattr(memory, "channel_identities_for_entity") and eid:
            try:
                for ci in memory.channel_identities_for_entity(eid, provider=channel) or []:
                    ext_ids.append(str(getattr(ci, "external_id", "") or ""))
                    if getattr(ci, "display_name", None):
                        ch_disp = str(ci.display_name)
            except Exception:
                pass
        l1_pref = bool(
            (l1_id and eid == l1_id)
            or (l1_name and l1_name == cname.lower())
            or (l1_name and l1_name in cname.lower())
        )
        proj_hit = any(p and p in cname.lower() for p in projects)
        recency_val = float(feats.get("interaction_recency", 0.0) or 0.0)
        out.append(
            IdentityHypothesis(
                entity_id=eid,
                display_name=cname,
                name=NameEvidence(
                    match_kind=match,
                    surface_form=surface,
                    canonical_name=cname,
                    aliases=aliases,
                ),
                salience=SalienceEvidence(
                    recency=recency_val,
                    frequency=float(feats.get("interaction_frequency", 0.0) or 0.0),
                    frequency_known=freq_known,
                    frequency_status="known" if freq_known else "unknown",
                    recency_status="known" if last_at is not None else "unknown",
                    hot=float(feats.get("hot_projection", 0.0) or 0.0),
                    last_interaction_at=float(last_at) if last_at else None,
                ),
                context=ContextEvidence(
                    working_context_hit=l1_pref or proj_hit,
                    l1_preferred=l1_pref,
                    reference_support=ref_sup,
                    reference_status=ref_status,
                    active_project_hit=proj_hit,
                ),
                channel=ChannelEvidence(
                    provider=channel,
                    external_ids=[x for x in ext_ids if x],
                    display_name=ch_disp,
                ),
                opaque_score=float(getattr(r, "final_score", 0.0) or 0.0),
            )
        )
    return out
