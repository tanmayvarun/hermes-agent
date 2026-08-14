"""Bounded identity evidence-acquisition before ASK.

Principle:
  low confidence → first spend a bounded information-gathering budget;
  ASK only if ambiguity survives.

Not a score-weight tweak. Hypotheses carry structured evidence bags;
a qualitative reinterpretation step decides proceed vs ASK.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

DEFAULT_EVIDENCE_BUDGET = 4  # max gather probes before ASK


@dataclass
class NameEvidence:
    """How the surface form relates to the candidate name — distinct from salience."""

    match_kind: str  # exact | extended | qualified_partial | partial | none
    surface_form: str = ""
    canonical_name: str = ""
    aliases: list[str] = field(default_factory=list)


@dataclass
class SalienceEvidence:
    recency: float = 0.0
    frequency: float = 0.0
    frequency_known: bool = False
    hot: float = 0.0
    last_interaction_at: Optional[float] = None


@dataclass
class ContextEvidence:
    working_context_hit: bool = False
    l1_preferred: bool = False
    reference_support: float = 0.0
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
    opaque_score: float = 0.0  # retriever score kept for telemetry only

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
                "hot": self.salience.hot,
                "last_interaction_at": self.salience.last_interaction_at,
            },
            "context": {
                "working_context_hit": self.context.working_context_hit,
                "l1_preferred": self.context.l1_preferred,
                "reference_support": self.context.reference_support,
                "active_project_hit": self.context.active_project_hit,
            },
            "channel": {
                "provider": self.channel.provider,
                "external_ids": list(self.channel.external_ids),
            },
            "gather_notes": list(self.gather_notes),
            "opaque_score": self.opaque_score,
        }


@dataclass
class IdentityResolutionOutcome:
    action: str  # proceed | ask | gather_exhausted_ask
    entity_id: str = ""
    reason: str = ""
    hypotheses: list[IdentityHypothesis] = field(default_factory=list)
    probes_used: list[str] = field(default_factory=list)
    budget: int = DEFAULT_EVIDENCE_BUDGET


_QUALIFIER_TOKENS = re.compile(
    r"\b(phonepe|phone\s*pe|axis|hdfc|icici|work|office|official)\b",
    re.I,
)


def classify_name_match(
    surface: str, canonical: str, aliases: Optional[list[str]] = None
) -> str:
    s = (surface or "").strip().lower()
    name = (canonical or "").strip().lower()
    al = [(a or "").strip().lower() for a in (aliases or []) if a]
    if not s:
        return "none"
    if s == name or s in al:
        # Exact requested surface equals name/alias.
        # If canonical is longer with extra tokens → still exact surface hit on alias,
        # but treat multi-token canonical where surface is first token as extended
        # when surface equals an alias that is the short form only... 
        # Spec: unqualified surface "Pallavi" vs canonical "Pallavi" → exact
        # vs "Pallavi Joshi" where surface is prefix → extended
        if s == name:
            return "exact"
        # surface equals an alias entry
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
        if hasattr(memory, "recent_reference_support") and eid:
            try:
                ref_sup = float(
                    memory.recent_reference_support(surface, eid) or 0.0
                )
            except Exception:
                ref_sup = 0.0
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
                    recency=float(feats.get("interaction_recency", 0.0) or 0.0),
                    frequency=float(feats.get("interaction_frequency", 0.0) or 0.0),
                    frequency_known=freq_known,
                    hot=float(feats.get("hot_projection", 0.0) or 0.0),
                    last_interaction_at=float(last_at) if last_at else None,
                ),
                context=ContextEvidence(
                    working_context_hit=l1_pref or proj_hit,
                    l1_preferred=l1_pref,
                    reference_support=ref_sup,
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


def _probe_memory_reference_history(
    memory: Any, surface: str, hypotheses: list[IdentityHypothesis]
) -> str:
    if not hasattr(memory, "recent_reference_support"):
        return "skip_no_reference_api"
    for h in hypotheses:
        try:
            h.context.reference_support = float(
                memory.recent_reference_support(surface, h.entity_id) or 0.0
            )
            h.gather_notes.append(
                f"reference_support={h.context.reference_support:.2f}"
            )
        except Exception as exc:
            h.gather_notes.append(f"reference_error:{exc}")
    return "memory_reference_history"


def _probe_memory_aggregates(
    memory: Any, hypotheses: list[IdentityHypothesis]
) -> str:
    if not hasattr(memory, "get_aggregate"):
        return "skip_no_aggregate_api"
    for h in hypotheses:
        try:
            ent = memory.get_entity(h.entity_id) if hasattr(memory, "get_entity") else None
            scope = getattr(ent, "scope", "personal") if ent else "personal"
            agg = memory.get_aggregate("user:local", h.entity_id, scope=scope)
            if agg is None:
                continue
            meta = dict(agg.metadata or {})
            h.salience.frequency_known = bool(meta.get("frequency_known"))
            if h.salience.frequency_known:
                h.salience.frequency = min(1.0, float(agg.count_30d or 0) / 50.0)
            if agg.last_interaction_at and not h.salience.last_interaction_at:
                h.salience.last_interaction_at = float(agg.last_interaction_at)
                # derive recency feature if missing
                import time

                days = max(
                    0.0, (time.time() - float(agg.last_interaction_at)) / 86400.0
                )
                h.salience.recency = max(0.0, 1.0 - days / 180.0)
            h.gather_notes.append(
                f"aggregate freq_known={h.salience.frequency_known} "
                f"recency={h.salience.recency:.2f}"
            )
        except Exception as exc:
            h.gather_notes.append(f"aggregate_error:{exc}")
    return "memory_aggregates"


def _probe_whatsapp_contact_enrichment(
    hypotheses: list[IdentityHypothesis],
    *,
    bridge_base_url: str = "http://127.0.0.1:3000",
    timeout_s: float = 2.0,
) -> str:
    """Cheap world probe: refresh last_interaction_at from bridge /contacts."""
    try:
        req = urllib.request.Request(
            f"{bridge_base_url.rstrip('/')}/contacts", method="GET"
        )
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        return f"skip_wa_contacts:{exc}"

    by_jid: dict[str, dict[str, Any]] = {}
    by_name: dict[str, dict[str, Any]] = {}
    for c in payload.get("contacts") or []:
        jid = str(c.get("external_id") or "")
        name = str(c.get("display_name") or "").strip().lower()
        if jid:
            by_jid[jid] = c
        if name:
            by_name[name] = c

    import time

    now = time.time()
    for h in hypotheses:
        hit = None
        for jid in h.channel.external_ids:
            if jid in by_jid:
                hit = by_jid[jid]
                break
        if hit is None:
            hit = by_name.get(h.display_name.strip().lower())
        if hit is None:
            continue
        last = hit.get("last_interaction_at")
        if last is None:
            h.gather_notes.append("wa_contacts:no_timestamp")
            continue
        try:
            last_f = float(last)
        except (TypeError, ValueError):
            continue
        h.salience.last_interaction_at = last_f
        days = max(0.0, (now - last_f) / 86400.0)
        h.salience.recency = max(0.0, 1.0 - days / 180.0)
        h.gather_notes.append(f"wa_contacts:recency={h.salience.recency:.3f}")
    return "whatsapp_contacts_enrichment"


def gather_identity_evidence(
    memory: Any,
    hypotheses: list[IdentityHypothesis],
    *,
    surface: str,
    budget: int = DEFAULT_EVIDENCE_BUDGET,
    working_context: Optional[dict[str, Any]] = None,
    world_probes: bool = True,
    bridge_base_url: str = "http://127.0.0.1:3000",
) -> tuple[list[IdentityHypothesis], list[str]]:
    """Run up to ``budget`` probes; mutate hypotheses in place; return probe log."""
    probes: list[str] = []
    remaining = max(0, int(budget))

    plan: list[Callable[[], str]] = [
        lambda: _probe_memory_aggregates(memory, hypotheses),
        lambda: _probe_memory_reference_history(memory, surface, hypotheses),
    ]
    if world_probes:
        plan.append(
            lambda: _probe_whatsapp_contact_enrichment(
                hypotheses, bridge_base_url=bridge_base_url
            )
        )
    # Working-context re-check (no I/O)
    def _wc() -> str:
        wc = dict(working_context or {})
        l1 = str(wc.get("recent_entity_name") or wc.get("recent_entity") or "").lower()
        lid = str(wc.get("recent_entity_id") or "")
        for h in hypotheses:
            if (lid and h.entity_id == lid) or (
                l1 and l1 in h.display_name.lower()
            ):
                h.context.l1_preferred = True
                h.context.working_context_hit = True
                h.gather_notes.append("working_context_prefer")
        return "working_context_recheck"

    plan.insert(0, _wc)

    for step in plan:
        if remaining <= 0:
            break
        label = step()
        probes.append(label)
        remaining -= 1
    return hypotheses, probes


def reinterpret_identity_hypotheses(
    hypotheses: list[IdentityHypothesis],
    *,
    surface: str,
) -> IdentityResolutionOutcome:
    """Qualitative reinterpretation over structured evidence — not opaque rescoring.

    ASK is terminal only when discriminating evidence does not establish a winner.
    """
    if not hypotheses:
        return IdentityResolutionOutcome(action="ask", reason="no_hypotheses")

    # 1) Working / L1 context preference
    l1 = [h for h in hypotheses if h.context.l1_preferred or h.context.working_context_hit]
    if len(l1) == 1:
        return IdentityResolutionOutcome(
            action="proceed",
            entity_id=l1[0].entity_id,
            reason="working_context_preference",
            hypotheses=hypotheses,
        )
    if len(l1) > 1:
        # Prefer exact among L1 hits
        exact_l1 = [h for h in l1 if h.name.match_kind == "exact"]
        if len(exact_l1) == 1:
            return IdentityResolutionOutcome(
                action="proceed",
                entity_id=exact_l1[0].entity_id,
                reason="working_context_exact",
                hypotheses=hypotheses,
            )

    # 2) Prior reference support
    refs = [h for h in hypotheses if h.context.reference_support >= 1.0]
    if len(refs) == 1 and not any(
        h.context.l1_preferred and h.entity_id != refs[0].entity_id for h in hypotheses
    ):
        return IdentityResolutionOutcome(
            action="proceed",
            entity_id=refs[0].entity_id,
            reason="prior_reference_resolution",
            hypotheses=hypotheses,
        )

    exact = [h for h in hypotheses if h.name.match_kind == "exact"]
    qualified = [h for h in hypotheses if h.name.match_kind == "qualified_partial"]

    # 3) Casual unqualified surface: exact alias has a meaningful prior when
    #    competitors are only partial/extended without context/reference favoring them.
    #    Recent partial alone does NOT automatically override exact.
    surface_tokens = (surface or "").strip().split()
    casual_unqualified = len(surface_tokens) == 1
    if casual_unqualified and len(exact) == 1:
        rival_context = [
            h
            for h in hypotheses
            if h.entity_id != exact[0].entity_id
            and (
                h.context.l1_preferred
                or h.context.working_context_hit
                or h.context.reference_support >= 1.0
                or h.context.active_project_hit
            )
        ]
        if not rival_context:
            # Exact stands; recent extended/partial without context is not enough alone.
            return IdentityResolutionOutcome(
                action="proceed",
                entity_id=exact[0].entity_id,
                reason="exact_alias_prior_without_contextual_rival",
                hypotheses=hypotheses,
            )

    # 4) Active project / qualifier alignment (e.g. PhonePe in context → qualified)
    if qualified:
        wc_proj = [
            h
            for h in qualified
            if h.context.active_project_hit or h.context.working_context_hit
        ]
        if len(wc_proj) == 1:
            return IdentityResolutionOutcome(
                action="proceed",
                entity_id=wc_proj[0].entity_id,
                reason="qualified_match_with_project_context",
                hypotheses=hypotheses,
            )

    # 5) Single candidate left after filters
    if len(hypotheses) == 1:
        return IdentityResolutionOutcome(
            action="proceed",
            entity_id=hypotheses[0].entity_id,
            reason="single_candidate",
            hypotheses=hypotheses,
        )

    # 6) Frequency-known dominance (true counts only)
    freq_known = [
        h
        for h in hypotheses
        if h.salience.frequency_known and h.salience.frequency > 0
    ]
    if len(freq_known) >= 2:
        ranked_f = sorted(freq_known, key=lambda h: h.salience.frequency, reverse=True)
        if ranked_f[0].salience.frequency >= ranked_f[1].salience.frequency + 0.35:
            return IdentityResolutionOutcome(
                action="proceed",
                entity_id=ranked_f[0].entity_id,
                reason="frequency_dominance",
                hypotheses=hypotheses,
            )

    # Still ambiguous after structured reinterpretation
    return IdentityResolutionOutcome(
        action="ask",
        reason="ambiguity_survived_evidence_budget",
        hypotheses=hypotheses,
    )


def resolve_identity_with_evidence_loop(
    memory: Any,
    ranked: list[Any],
    *,
    surface: str,
    channel: str = "whatsapp",
    working_context: Optional[dict[str, Any]] = None,
    budget: int = DEFAULT_EVIDENCE_BUDGET,
    world_probes: bool = True,
    bridge_base_url: str = "http://127.0.0.1:3000",
) -> IdentityResolutionOutcome:
    """Full loop: structure hypotheses → gather → reinterpret → proceed|ASK."""
    hyps = hypotheses_from_ranked(
        ranked,
        surface=surface,
        memory=memory,
        channel=channel,
        working_context=working_context,
    )
    hyps, probes = gather_identity_evidence(
        memory,
        hyps,
        surface=surface,
        budget=budget,
        working_context=working_context,
        world_probes=world_probes,
        bridge_base_url=bridge_base_url,
    )
    outcome = reinterpret_identity_hypotheses(hyps, surface=surface)
    outcome.probes_used = probes
    outcome.budget = budget
    if outcome.action == "ask":
        outcome.action = "gather_exhausted_ask"
        if outcome.reason == "ambiguity_survived_evidence_budget":
            pass
        else:
            outcome.reason = outcome.reason or "ambiguity_survived_evidence_budget"
    return outcome
