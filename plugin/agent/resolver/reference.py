"""Reference Resolver — estimate which entity the user intended (typed + named)."""

from __future__ import annotations

from typing import List, Optional, TYPE_CHECKING

from plugin.agent.apps.whatsapp_semantics import entity_semantic_type
from plugin.agent.resolver.memory import ResolutionMemory, get_resolution_memory
from plugin.agent.resolver.resolution import (
    EvidenceItem,
    RankedCandidate,
    Resolution,
    policy_for_confidence,
)
from plugin.agent.whatsapp_view import (
    _attr,
    _is_search_mirror,
    _name_match_score,
    contact_names_from_entity,
)
from plugin.worldmodel.entities.normalize import _clean_label
from plugin.worldmodel.model import WorldModel

if TYPE_CHECKING:
    from plugin.agent.reference.types import Reference


def _is_truncated(name: str) -> bool:
    s = (_clean_label(name) or "").rstrip()
    return s.endswith("…") or s.endswith("...") or s.endswith("\u2026")


def _nickname_boost(candidate: str, needle: str, *, allow_truncated: bool = False) -> float:
    """Soft stem/prefix affinity (Pallu→Pallavi; Now→Now… when allow_truncated)."""
    c = _clean_label(candidate).lower()
    n = _clean_label(needle).lower()
    if not c or not n or len(n) < 2:
        return 0.0
    if _is_truncated(candidate) and not allow_truncated:
        return 0.0
    # Strip ellipsis for stem compare
    c_bare = c.rstrip("….")
    if allow_truncated and _is_truncated(candidate) and len(n) >= 2:
        if c_bare.startswith(n) or n.startswith(c_bare[: max(2, len(c_bare))]):
            return 0.80
        shared = 0
        for a, b in zip(n, c_bare):
            if a != b:
                break
            shared += 1
        if shared >= 2 and shared >= 0.5 * min(len(n), len(c_bare)):
            return 0.75
    if len(n.split()) > 1 and not allow_truncated:
        # multi-word needle: only exact-ish via _name_match_score
        pass
    c_tokens = [t.strip(",.<>()….") for t in c.replace(",", " ").split() if t]
    best = 0.0
    for tok in c_tokens:
        tok = tok.rstrip("….")
        if len(tok) < 3:
            continue
        score = 0.0
        if tok.startswith(n) and len(n) >= 3:
            score = 0.78 if len(c_tokens) == 1 else 0.68
        else:
            shared = 0
            for a, b in zip(n, tok):
                if a != b:
                    break
                shared += 1
            if shared >= 3 and shared >= 0.5 * min(len(n), len(tok)):
                score = 0.72 if len(c_tokens) == 1 else 0.60
        best = max(best, score)
    return best


def _goal_compat(name: str, *, prefer_contacts: bool = True, want_kind: str = "") -> float:
    """Compatibility of candidate with intended kind."""
    low = _clean_label(name).lower()
    if want_kind == "group":
        if _is_truncated(name) or "group" in low or "<>" in low:
            return 0.9
        return 0.55
    if want_kind == "community":
        return 0.9 if "community" in low or "announcement" in low else 0.4
    if not prefer_contacts:
        return 0.5
    groupish = (
        "<>" in low
        or " intro" in f" {low}"
        or low.endswith(" intro")
        or " group" in f" {low}"
        or "created this group" in low
    )
    if groupish:
        return 0.15
    tokens = [t for t in low.replace(",", " ").split() if t]
    if len(tokens) > 1:
        return 0.45
    return 0.85


class ReferenceResolver:
    """
    Structured Reference → Resolution(confidence, winner, candidates, evidence).

    Filters by semantic_type when kind is known; matches name/hypotheses.
    """

    def __init__(self, memory: Optional[ResolutionMemory] = None) -> None:
        self.memory = memory or get_resolution_memory()

    def resolve(
        self,
        world: WorldModel,
        query: str,
        *,
        goal_kind: str = "whatsapp_voice_call",
        limit: int = 8,
        reference: Optional["Reference"] = None,
    ) -> Resolution:
        from plugin.agent.reference import interpret_reference

        ref = reference or interpret_reference(query)
        q_raw = _clean_label(query) or ref.raw
        needles = []
        for n in [ref.name, *(ref.search_hypotheses or []), q_raw]:
            n = _clean_label(n)
            if n and n.lower() not in {x.lower() for x in needles}:
                needles.append(n)
        if not needles:
            return Resolution(query=query, confidence=0.0, policy="ask")

        self.memory.ensure_loaded()
        want_kind = (ref.kind or "unknown").lower()
        use_type_filter = want_kind in {"group", "community", "contact"} and ref.confidence >= 0.6
        allow_trunc = want_kind == "group"

        ranked: List[RankedCandidate] = []
        seen = set()
        typed_pool: List[RankedCandidate] = []
        all_pool: List[RankedCandidate] = []
        from plugin.agent.apps.whatsapp_targets import in_sidebar_band
        entities = list(world.entities.values())

        for e in entities:
            if not e.visible:
                continue
            etype = (e.entity_type or "").lower()
            sidebar_like = in_sidebar_band(
                e,
                entities,
                scene_graph=getattr(world, "last_scene_graph", None) or {},
            )
            # On an AX-blind app (WhatsApp) every entity is a vision-materialised
            # "static" OCR read, and in_sidebar_band deliberately returns False for
            # them — so the AX-era gate below (static only when sidebar-like) drops
            # the *entire* candidate pool, forcing resolution into the crude
            # shortest-label fallback that grabs the search-box query echo instead
            # of the chat row. The perceptor's reads are the only entities we have
            # on such an app, so admit them and let name-match scoring decide.
            attrs = getattr(e, "attributes", None)
            is_vision = (
                isinstance(attrs, dict)
                and str(attrs.get("source") or "").strip().lower() == "vision"
            )
            if etype not in {"button", "link", "cell", "unknown"} and not (
                etype == "static" and (sidebar_like or is_vision)
            ):
                continue
            if _is_search_mirror(e):
                continue
            sem_type, sem_conf = entity_semantic_type(e)
            names = contact_names_from_entity(e)
            if not names:
                desc = _attr(e, "description", "AXDescription")
                lab = _clean_label(e.label or "")
                names = [x for x in (desc, lab) if x]
            # Allow truncated labels into name list when resolving groups
            if allow_trunc:
                lab = _clean_label(e.label or "")
                if lab and _is_truncated(lab) and lab.lower() not in {x.lower() for x in names}:
                    names = list(names) + [lab]
            for name in names:
                key = _clean_label(name).lower()
                if not key or key in seen:
                    continue
                seen.add(key)
                cand = self._score_candidate(
                    name,
                    needles,
                    entity=e,
                    goal_kind=goal_kind,
                    want_kind=want_kind,
                    allow_truncated=allow_trunc,
                    query_raw=q_raw,
                    sem_type=sem_type,
                    sem_conf=sem_conf,
                )
                if cand.confidence < 0.12 and cand.name_similarity < 0.30:
                    continue
                all_pool.append(cand)
                if (not use_type_filter) or (
                    sem_type == want_kind and sem_conf >= 0.55
                ) or (
                    # truncated group rows often typed as group
                    allow_trunc and sem_type == "group" and _is_truncated(name)
                ):
                    typed_pool.append(cand)

        ranked = typed_pool if typed_pool else all_pool
        # If type filter emptied, use all with a penalty already applied in scoring when mismatch
        if use_type_filter and not typed_pool:
            ranked = all_pool

        ranked.sort(key=lambda c: (-c.confidence, -c.name_similarity, len(c.name)))
        top = ranked[:limit]

        if not top:
            return Resolution(
                query=q_raw,
                confidence=0.0,
                policy="ask",
                evidence=[EvidenceItem("empty", 0.0, "no candidate entities")],
            )

        best = top[0]
        strong = [
            c
            for c in top
            if c.name_similarity >= 0.60 and c.goal_compat >= 0.70
        ]
        if len(strong) == 1 and strong[0].name == best.name:
            best.confidence = max(best.confidence, 0.91)
            best.evidence.append(
                EvidenceItem("unique_intent", 0.91, "sole personal-name match for query")
            )

        # Group + strong stem on truncated label → auto
        if (
            want_kind == "group"
            and _is_truncated(best.name)
            and best.name_similarity >= 0.70
            and best.confidence >= 0.70
        ):
            best.confidence = max(best.confidence, 0.91)
            best.evidence.append(
                EvidenceItem("group_stem", best.name_similarity, "group kind + truncated stem")
            )

        if len(top) > 1 and best.confidence < 0.90:
            gap = best.confidence - top[1].confidence
            if gap < 0.08:
                best.confidence = min(best.confidence, 0.55 + gap)
                best.evidence.append(
                    EvidenceItem("competition", gap, f"close second: {top[1].name}")
                )

        if best.history >= 0.75:
            best.confidence = max(
                best.confidence,
                min(0.95, 0.12 * best.name_similarity + 0.85 * best.history),
            )

        policy = policy_for_confidence(best.confidence)
        if policy == "auto":
            winner, winner_name = best.entity, best.name
        elif policy == "observe":
            winner, winner_name = None, best.name
        else:
            winner, winner_name = None, None

        return Resolution(
            query=q_raw,
            winner=winner,
            winner_name=winner_name,
            confidence=best.confidence,
            candidates=top,
            evidence=list(best.evidence)
            + [
                EvidenceItem("reference_kind", ref.confidence, f"kind={ref.kind} name={ref.name!r}"),
            ],
            policy=policy,
        )

    def _score_candidate(
        self,
        name: str,
        needles: List[str],
        *,
        entity,
        goal_kind: str,
        want_kind: str,
        allow_truncated: bool,
        query_raw: str,
        sem_type: str,
        sem_conf: float,
    ) -> RankedCandidate:
        name_sim = 0.0
        nick = 0.0
        best_needle = needles[0] if needles else ""
        for needle in needles:
            s = _name_match_score(name, needle)
            n = _nickname_boost(name, needle, allow_truncated=allow_truncated)
            combined = max(s, n)
            if combined > name_sim:
                name_sim = combined
                nick = n
                best_needle = needle

        hist, hist_d = self.memory.history_score(query_raw, name)
        # Also try history under canonical name
        if best_needle != query_raw:
            h2, d2 = self.memory.history_score(best_needle, name)
            if h2 > hist:
                hist, hist_d = h2, d2
        freq, freq_d = self.memory.frequency_score(name)
        rec, rec_d = self.memory.recency_score(name)
        goal = _goal_compat(
            name,
            prefer_contacts=want_kind in {"", "contact", "unknown"},
            want_kind=want_kind,
        )
        goal_d = f"want_kind={want_kind} sem={sem_type}@{sem_conf:.2f}"

        # Type match boost / mismatch penalty
        type_factor = 1.0
        if want_kind in {"group", "community", "contact"}:
            if sem_type == want_kind and sem_conf >= 0.55:
                type_factor = 1.08
            elif sem_type in {"chrome", "search_box", "call_button"}:
                type_factor = 0.35
            elif sem_type != "unknown" and sem_type != want_kind:
                type_factor = 0.55

        base = name_sim
        if hist > 0.15 or (freq > 0.05 and hist > 0.05) or (rec > 0.05 and hist > 0.05):
            mem_w = min(0.75, 0.25 + 0.55 * hist)
            mem = max(hist, 0.5 * freq + 0.5 * rec)
            base = (1.0 - mem_w) * name_sim + mem_w * mem
        conf = base * (0.92 + 0.08 * goal) * type_factor
        if name_sim >= 0.95:
            conf = max(conf, 0.92 * type_factor)
        elif name_sim >= 0.88 and goal >= 0.7:
            conf = max(conf, 0.90 * min(1.0, type_factor))
        conf = max(0.0, min(1.0, conf))
        evidence = [
            EvidenceItem("name_similarity", name_sim, f"match {best_needle!r}≈{name!r}"),
            EvidenceItem("history", hist, hist_d),
            EvidenceItem("frequency", freq, freq_d),
            EvidenceItem("recency", rec, rec_d),
            EvidenceItem("goal_compat", goal, goal_d),
            EvidenceItem("semantic_type", sem_conf, f"{sem_type}"),
        ]
        if nick > 0:
            evidence.append(EvidenceItem("nickname_affinity", nick, "stem/prefix affinity"))

        return RankedCandidate(
            name=name,
            entity_id=None if entity is None else entity.id,
            confidence=conf,
            name_similarity=name_sim,
            history=hist,
            frequency=freq,
            recency=rec,
            goal_compat=goal,
            evidence=evidence,
            entity=entity,
        )


_DEFAULT_RESOLVER: Optional[ReferenceResolver] = None


def get_reference_resolver() -> ReferenceResolver:
    global _DEFAULT_RESOLVER
    if _DEFAULT_RESOLVER is None:
        _DEFAULT_RESOLVER = ReferenceResolver()
    return _DEFAULT_RESOLVER
