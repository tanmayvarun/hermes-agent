"""Structured multi-source retrieval: UNION recall → ranking (separate types)."""

from __future__ import annotations

import time
from typing import Any, Mapping, Optional, Union

from plugin.agent.memory.types import (
    MemoryEvidence,
    MemoryEvidencePacket,
    MemoryQuery,
    ProjectionState,
    RankedCandidate,
    RecallCandidate,
    RetrievalPlan,
)


def _as_query(
    query: Union[str, MemoryQuery, Mapping[str, Any]],
    *,
    context: Optional[Mapping[str, Any]],
    limit: int,
) -> MemoryQuery:
    if isinstance(query, MemoryQuery):
        q = query
        if limit and q.limit == 8:
            q.limit = limit
        if context:
            q.current_context = {**q.current_context, **dict(context)}
        return q
    if isinstance(query, Mapping):
        return MemoryQuery(
            purpose=str(query.get("purpose") or "factual_recall"),
            text=str(query.get("text") or ""),
            entities=list(query.get("entities") or []),
            current_context={**(query.get("current_context") or {}), **(context or {})},
            limit=int(query.get("limit") or limit),
            recall_budget=int(query.get("recall_budget") or 50),
        )
    return MemoryQuery(
        purpose="entity_resolution" if context and context.get("purpose") == "entity_resolution" else "factual_recall",
        text=str(query or ""),
        current_context=dict(context or {}),
        limit=limit,
    )


def plan_for(query: MemoryQuery) -> RetrievalPlan:
    """Deterministic RetrievalPlanner (Slice 3)."""
    entity_ish = query.purpose == "entity_resolution" or bool(query.text)
    return RetrievalPlan(
        exact_entity_lookup=entity_ish,
        alias_lookup=entity_ish,
        fts_lookup=bool(query.text),
        relationship_lookup=True,
        recency_lookup=True,
        hot_projection_lookup=True,
        vector_lookup=False,
        per_source_budget=max(5, query.recall_budget // 4),
        total_latency_budget_ms=query.latency_budget_ms,
    )


class MemoryRetriever:
    def __init__(self, store: Any) -> None:
        self.store = store

    def retrieve(
        self,
        query: Union[str, MemoryQuery, Mapping[str, Any]],
        *,
        context: Optional[Mapping[str, Any]] = None,
        limit: int = 8,
    ) -> MemoryEvidencePacket:
        q = _as_query(query, context=context, limit=limit)
        plan = plan_for(q)
        recall = self._recall(q, plan)
        ranked = self._rank(q, recall)
        ranked = ranked[: q.limit]
        evidence = [
            MemoryEvidence(
                memory_id=r.ref,
                kind=r.ref_kind,
                content=r.payload,
                provenance=",".join(r.recall_sources),
                confidence=r.final_score,
                subject=str(r.payload.get("canonical_name") or r.payload.get("display_name") or ""),
                metadata={
                    "feature_scores": r.feature_scores,
                    "explanation": r.explanation,
                    "recall_sources": r.recall_sources,
                },
            )
            for r in ranked
        ]
        proj_states: list[ProjectionState] = []
        recent_state = self.store.get_projection_state("RecentEntities")
        if recent_state:
            proj_states.append(recent_state)
        return MemoryEvidencePacket(
            query_purpose=q.purpose,
            recall=recall,
            ranked=ranked,
            evidence=evidence,
            projection_states=proj_states,
            provenance_summary=f"recall={len(recall)} ranked={len(ranked)}",
            metadata={"plan": plan.__dict__, "text": q.text},
        )

    def _recall(self, q: MemoryQuery, plan: RetrievalPlan) -> list[RecallCandidate]:
        by_ref: dict[str, RecallCandidate] = {}

        def admit(ref: str, kind: str, source: str, **meta: Any) -> None:
            cur = by_ref.get(ref)
            if cur is None:
                by_ref[ref] = RecallCandidate(
                    ref=ref,
                    ref_kind=kind,
                    recall_sources=[source],
                    metadata=dict(meta),
                )
            else:
                if source not in cur.recall_sources:
                    cur.recall_sources.append(source)
                cur.metadata.update(meta)

        text = (q.text or "").strip()
        user_id = str(q.current_context.get("user_entity_id") or "user:local")

        if plan.hot_projection_lookup:
            state = self.store.get_projection_state("RecentEntities")
            if state and state.is_fresh:
                for row in self.store.list_recent_entities(limit=plan.per_source_budget):
                    name = (row.get("display_name") or "").lower()
                    if not text or text.lower() in name or name in text.lower():
                        admit(
                            row["entity_id"],
                            "entity",
                            "hot_recent_entities",
                            display_name=row.get("display_name"),
                            salience=row.get("salience"),
                            last_interaction_at=row.get("last_interaction_at"),
                        )
            elif state and not state.is_fresh:
                # Stale projection must not masquerade as fresh truth — skip arm.
                pass

        if plan.exact_entity_lookup or plan.alias_lookup:
            if text:
                for ent in self.store.find_entities_by_name(text):
                    exact = ent.canonical_name.strip().lower() == text.lower() or any(
                        a.strip().lower() == text.lower() for a in ent.aliases
                    )
                    source = "exact_alias" if exact else "alias_substring"
                    admit(
                        ent.entity_id,
                        "entity",
                        source,
                        canonical_name=ent.canonical_name,
                        aliases=list(ent.aliases),
                    )

        if plan.recency_lookup:
            for agg in self.store.list_aggregates_for_subject(user_id):
                ent = self.store.get_entity(agg.object_id)
                if ent is None:
                    continue
                if text:
                    names = [ent.canonical_name, *ent.aliases]
                    if not any(text.lower() in (n or "").lower() for n in names):
                        continue
                admit(
                    ent.entity_id,
                    "entity",
                    "interaction_aggregate",
                    canonical_name=ent.canonical_name,
                    count_30d=agg.count_30d,
                    last_interaction_at=agg.last_interaction_at,
                )

        if plan.fts_lookup and text:
            # Lightweight FTS stand-in over entity names (SQLite FTS later).
            for ent in self.store.find_entities_by_name(text):
                admit(
                    ent.entity_id,
                    "entity",
                    "fts_name",
                    canonical_name=ent.canonical_name,
                )

        return list(by_ref.values())

    def _rank(self, q: MemoryQuery, recall: list[RecallCandidate]) -> list[RankedCandidate]:
        user_id = str(q.current_context.get("user_entity_id") or "user:local")
        text = (q.text or "").strip().lower()
        now = time.time()
        ranked: list[RankedCandidate] = []

        for cand in recall:
            ent = self.store.get_entity(cand.ref)
            if ent is None:
                continue
            features: dict[str, float] = {}
            name = (ent.canonical_name or "").lower()
            aliases = [a.lower() for a in ent.aliases]
            if text and (text == name or text in aliases):
                features["alias_exact"] = 1.0
            elif text and (text in name or any(text in a for a in aliases)):
                features["alias_partial"] = 0.6
            else:
                features["alias_exact"] = 0.0

            agg = self.store.get_aggregate(user_id, ent.entity_id, scope=ent.scope)
            if agg:
                freq_known = bool((agg.metadata or {}).get("frequency_known"))
                if freq_known:
                    features["interaction_frequency"] = min(1.0, agg.count_30d / 50.0)
                    features["continuity"] = float(agg.continuity)
                else:
                    # Missing frequency is better than fabricated frequency.
                    features["interaction_frequency"] = 0.0
                    features["continuity"] = 0.0
                if agg.last_interaction_at:
                    days = max(0.0, (now - float(agg.last_interaction_at)) / 86400.0)
                    features["interaction_recency"] = max(0.0, 1.0 - days / 180.0)
                else:
                    features["interaction_recency"] = 0.0
            else:
                features["interaction_frequency"] = 0.0
                features["interaction_recency"] = 0.0
                features["continuity"] = 0.0

            if "hot_recent_entities" in cand.recall_sources:
                features["hot_projection"] = float(cand.metadata.get("salience") or 0.5)
            else:
                features["hot_projection"] = 0.0

            features["recent_disambiguation_support"] = float(
                self.store.recent_reference_support(text, ent.entity_id)
                if hasattr(self.store, "recent_reference_support")
                else 0.0
            )

            channel = str(q.current_context.get("channel") or "")
            if channel:
                ids = self.store.channel_identities_for_entity(
                    ent.entity_id, provider=channel.lower()
                )
                features["channel_compatible"] = 1.0 if ids else 0.0
            else:
                features["channel_compatible"] = 0.5

            final = (
                0.30 * features.get("alias_exact", 0.0)
                + 0.12 * features.get("alias_partial", 0.0)
                + 0.22 * features.get("interaction_recency", 0.0)
                + 0.13 * features.get("interaction_frequency", 0.0)
                + 0.05 * features.get("continuity", 0.0)
                + 0.05 * features.get("hot_projection", 0.0)
                + 0.13 * features.get("recent_disambiguation_support", 0.0)
            )
            if features.get("channel_compatible") == 0.0 and channel:
                final *= 0.5

            parts = [f"{k}={v:.2f}" for k, v in sorted(features.items()) if v]
            ranked.append(
                RankedCandidate(
                    ref=ent.entity_id,
                    ref_kind="entity",
                    feature_scores=features,
                    final_score=final,
                    explanation="; ".join(parts) or "no_features",
                    recall_sources=list(cand.recall_sources),
                    payload={
                        "canonical_name": ent.canonical_name,
                        "aliases": list(ent.aliases),
                        "entity_type": ent.entity_type,
                    },
                )
            )

        ranked.sort(key=lambda r: r.final_score, reverse=True)
        return ranked
