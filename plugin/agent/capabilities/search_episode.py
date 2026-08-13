"""Information search as a compound intentional operation.

``information_search`` (MetaAction.SEARCH): criteria known, location unknown —
query → retrieve/filter → rank until SearchResult.chosen (or fail). Commit
(open_entity / select_content) is outside search (ACT / RETRIEVE).

Not to be confused with trajectory ``exploration_controller`` / branch_fitness
(INFORMATION_GATHERING), which asks which *region of the action space* to try.

See docs/design/representation-capability-substrate.md.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from plugin.agent.capabilities.revert_effects import (
    _text_matches_goal,
    content_target_fits_referents,
)

_STATUS_INCOMPLETE = frozenset({"querying", "retrieving", "ranking"})
_COMMIT_CAPS = frozenset(
    {"open_entity", "open_contact", "select_content", "reveal_actions"}
)
_SEARCH_SURFACES = frozenset({"search", "search_results", "chat_list", "forward_picker"})

# Host-agnostic regions a find may still try after a partial/empty result.
DEFAULT_SEARCH_SCOPES = (
    "visible_list",
    "filter_query",
    "timeline",
    "links_tab",
    "older_history",
)

# Generic fallback when RoleBinder / goal_match did not supply a constraint name.
# Search must never invent domain-specific reasons like "originator mismatch".
DEFAULT_ROLE_CONSTRAINT_MISMATCH = "required_role_constraint_mismatch"


def role_rejection_reason_from_assessment(
    assessment: Optional[Dict[str, Any]] = None,
    *,
    fallback: str = DEFAULT_ROLE_CONSTRAINT_MISMATCH,
) -> str:
    """Preserve structured role-failure evidence; never invent a domain reason.

    Accepts ``goal_match`` / RoleAssessment-shaped dicts with ``constraints``,
    ``missing_required``, or ``contradictions``.
    """
    gm = assessment if isinstance(assessment, dict) else {}
    for cons in gm.get("constraints") or []:
        if not isinstance(cons, dict):
            continue
        status = str(cons.get("status") or "").strip().lower()
        if status not in {"mismatch", "missing", "failed", "unsatisfied"}:
            continue
        if cons.get("required") is False:
            continue
        name = str(cons.get("name") or cons.get("constraint") or "").strip()
        if not name:
            continue
        if status == "missing":
            return f"{name} missing"[:160]
        return f"{name} mismatch"[:160]
    for miss in gm.get("missing_required") or []:
        name = str(miss or "").strip()
        if name:
            # "same_originator" / "originator" → human-readable mismatch token.
            token = name.replace("same_", "").replace("_", " ")
            return f"{token} mismatch"[:160]
    for raw in gm.get("contradictions") or []:
        text = str(raw or "").strip()
        if not text:
            continue
        head = text.split(":", 1)[0].strip().replace("_", " ")
        if head:
            return head[:160]
    return str(fallback or DEFAULT_ROLE_CONSTRAINT_MISMATCH)[:160]


@dataclass
class SearchIntent:
    """Structured find intention — criteria known, location unknown."""

    sought: str = ""
    criteria: str = ""
    search_space: str = "ui_filter"
    scope: str = ""
    constraints: List[str] = field(default_factory=list)
    stopping_rule: str = "unique_fit_or_rank_choice"
    result_limit: int = 12
    sources: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: Any) -> "SearchIntent":
        if not isinstance(raw, dict):
            return cls()
        return cls(
            sought=str(raw.get("sought") or "")[:160],
            criteria=str(raw.get("criteria") or "")[:160],
            search_space=str(raw.get("search_space") or raw.get("space") or "ui_filter")[
                :64
            ],
            scope=str(raw.get("scope") or "")[:64],
            constraints=[
                str(c)[:80] for c in (raw.get("constraints") or []) if str(c).strip()
            ][:8],
            stopping_rule=str(
                raw.get("stopping_rule") or "unique_fit_or_rank_choice"
            )[:64],
            result_limit=int(raw.get("result_limit") or 12),
            sources=[
                str(s)[:64] for s in (raw.get("sources") or []) if str(s).strip()
            ][:8],
        )


@dataclass
class SearchResult:
    """Outcome of an information_search episode (not an ACT commit)."""

    candidates: List[Dict[str, Any]] = field(default_factory=list)
    chosen: Optional[Dict[str, Any]] = None
    coverage: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    exhausted: bool = False
    unexplored_scopes: List[str] = field(default_factory=list)
    fail_reason: str = ""
    status: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: Any) -> "SearchResult":
        if not isinstance(raw, dict):
            return cls()
        chosen = raw.get("chosen")
        if chosen is not None and not isinstance(chosen, dict):
            chosen = {"label": str(chosen)}
        return cls(
            candidates=[
                c for c in (raw.get("candidates") or []) if isinstance(c, dict)
            ][:24],
            chosen=chosen if isinstance(chosen, dict) else None,
            coverage=dict(raw.get("coverage") or {})
            if isinstance(raw.get("coverage"), dict)
            else {},
            confidence=float(raw.get("confidence") or 0.0),
            exhausted=bool(raw.get("exhausted")),
            unexplored_scopes=[
                str(s)[:64]
                for s in (raw.get("unexplored_scopes") or [])
                if str(s).strip()
            ][:12],
            fail_reason=str(raw.get("fail_reason") or "")[:120],
            status=str(raw.get("status") or "")[:32],
        )


def _space_to_scope(space: str) -> str:
    s = str(space or "").strip().lower()
    if s in {"ui_filter", "filter", "search", "chat_list"}:
        return "filter_query"
    if s in {"timeline", "conversation", "messages"}:
        return "timeline"
    if s in {"links", "links_tab"}:
        return "links_tab"
    if s in {"history", "older", "older_history"}:
        return "older_history"
    if s in {"visible", "visible_list", "list"}:
        return "visible_list"
    return s or "filter_query"


def _explored_scopes_of(ep: Dict[str, Any]) -> List[str]:
    raw = ep.get("explored_scopes")
    if isinstance(raw, list) and raw:
        return [str(s)[:64] for s in raw if str(s).strip()][:12]
    scope = _space_to_scope(str(ep.get("space") or "ui_filter"))
    return [scope] if scope else ["filter_query"]


def _coverage_dict(ep: Dict[str, Any]) -> Dict[str, Any]:
    explored = _explored_scopes_of(ep)
    all_scopes = list(DEFAULT_SEARCH_SCOPES)
    for s in explored:
        if s not in all_scopes:
            all_scopes.append(s)
    tried = len(explored)
    total = max(len(all_scopes), 1)
    return {
        "explored_scopes": explored,
        "scopes_tried": tried,
        "scopes_total": total,
        "fraction": round(float(tried) / float(total), 3),
        "space": str(ep.get("space") or ""),
    }


def _unexplored_scopes(ep: Dict[str, Any]) -> List[str]:
    explored = set(_explored_scopes_of(ep))
    return [s for s in DEFAULT_SEARCH_SCOPES if s not in explored]


def search_intent_from_episode(ep: Optional[Dict[str, Any]]) -> SearchIntent:
    """Map flat episode dict → SearchIntent (document contract)."""
    if not isinstance(ep, dict) or not ep:
        return SearchIntent()
    if isinstance(ep.get("intent"), dict):
        return SearchIntent.from_dict(ep["intent"])
    sought = str(ep.get("referent") or "")
    criteria = str(ep.get("query") or "")
    tokens = [
        str(t).strip() for t in (ep.get("evidence_tokens") or []) if str(t).strip()
    ]
    if not criteria and tokens:
        criteria = " ".join(tokens[:4])
    return SearchIntent(
        sought=sought,
        criteria=criteria,
        search_space=str(ep.get("space") or "ui_filter"),
        scope=_space_to_scope(str(ep.get("space") or "ui_filter")),
        constraints=tokens[:8],
        stopping_rule="unique_fit_or_rank_choice",
        result_limit=12,
        sources=[],
    )


def search_result_from_episode(
    ep: Optional[Dict[str, Any]],
    *,
    exhausted: bool = False,
) -> SearchResult:
    """Map flat episode dict → SearchResult (coverage + unexplored scopes)."""
    if not isinstance(ep, dict) or not ep:
        return SearchResult(exhausted=bool(exhausted))
    if isinstance(ep.get("result"), dict) and ep.get("result"):
        base = SearchResult.from_dict(ep["result"])
        # Keep coverage/unexplored fresh from episode progress.
        base.coverage = _coverage_dict(ep) or base.coverage
        base.unexplored_scopes = _unexplored_scopes(ep) or base.unexplored_scopes
        base.status = str(ep.get("status") or base.status)
        base.fail_reason = str(ep.get("fail_reason") or base.fail_reason)
        base.exhausted = bool(
            exhausted
            or base.exhausted
            or str(ep.get("status")) in {"failed", "exhausted"}
        )
        return base
    status = str(ep.get("status") or "")
    chosen_label = str(ep.get("chosen_label") or "").strip()
    chosen = None
    if chosen_label:
        chosen = {"label": chosen_label, "id": ep.get("chosen_id")}
    confidence = 0.0
    if status == "complete" and chosen_label:
        confidence = 0.9
    elif status == "ranking" and int(ep.get("candidate_count") or 0) > 0:
        confidence = 0.5
    elif status in {"failed", "exhausted"}:
        confidence = 0.0
    return SearchResult(
        candidates=[],
        chosen=chosen,
        coverage=_coverage_dict(ep),
        confidence=confidence,
        exhausted=bool(exhausted or status in {"failed", "exhausted"}),
        unexplored_scopes=_unexplored_scopes(ep),
        fail_reason=str(ep.get("fail_reason") or ""),
        status=status,
    )


def stamp_search_contract(ep: Dict[str, Any], *, exhausted: bool = False) -> Dict[str, Any]:
    """Attach intent/result dicts onto the episode (in place + return)."""
    if not isinstance(ep, dict):
        return {}
    explored = _explored_scopes_of(ep)
    ep["explored_scopes"] = explored
    intent = search_intent_from_episode(ep)
    result = search_result_from_episode(ep, exhausted=exhausted)
    # Carry candidate_count into coverage for meta packet consumers.
    result.coverage = {
        **(result.coverage or {}),
        "candidate_count": int(ep.get("candidate_count") or 0),
        "filtered_count": int(ep.get("filtered_count") or 0),
        "raw_count": int(ep.get("raw_count") or 0),
    }
    ep["intent"] = intent.to_dict()
    ep["result"] = result.to_dict()
    return ep


def has_search_criteria(
    *,
    episode: Optional[Dict[str, Any]] = None,
    goal: Any = None,
    referent: str = "",
    query: str = "",
) -> bool:
    """True when SEARCH is admissible (criteria known). Else prefer EXPLORE."""
    contact, link_q, dest = goal_search_criteria(goal) if goal is not None else ("", "", "")
    ep = episode if isinstance(episode, dict) else {}
    return bool(
        str(referent or "").strip()
        or str(query or "").strip()
        or contact
        or link_q
        or dest
        or str(ep.get("referent") or "").strip()
        or str(ep.get("query") or "").strip()
        or (isinstance(ep.get("intent"), dict) and str(ep["intent"].get("sought") or "").strip())
        or (isinstance(ep.get("intent"), dict) and str(ep["intent"].get("criteria") or "").strip())
    )


def _norm(text: Any) -> str:
    return " ".join(str(text or "").strip().lower().split())


def _fingerprint(candidates: Sequence[Dict[str, Any]]) -> str:
    labels = sorted(
        _norm(c.get("label") or c.get("text")) for c in candidates if isinstance(c, dict)
    )
    raw = "|".join(x for x in labels if x)[:400]
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def _is_query_echo(label: str, query: str) -> bool:
    """True when the row is mostly a self-echo of the authored search string."""
    lab = _norm(label)
    q = _norm(query)
    if not lab or not q or len(q) < 4:
        return False
    if lab == q:
        return True
    stripped = re.sub(r"^(you|me)\s*:\s*", "", lab)
    if stripped == q:
        return True
    # "Contact: You: <query> …" chat-preview echoes
    if q in lab and (
        "you:" in lab
        or lab.startswith(q)
        or re.search(rf"\byou:\s*{re.escape(q)}\b", lab)
    ):
        # URL / domain hits that merely contain the query are not echoes.
        if "http://" in lab or "https://" in lab or "www." in lab or ".com" in lab:
            return False
        return True
    qt = {t for t in re.split(r"\W+", q) if len(t) >= 4}
    lt = {t for t in re.split(r"\W+", lab) if len(t) >= 4}
    if qt and qt <= lt and len(lt) <= len(qt) + 2:
        if "http://" in lab or "https://" in lab or "www." in lab or ".com" in lab:
            return False
        return True
    return False


def search_episode_of(execution_state: Any) -> Optional[Dict[str, Any]]:
    ep = getattr(execution_state, "search_episode", None) if execution_state else None
    return dict(ep) if isinstance(ep, dict) else None


def search_incomplete(execution_state: Any) -> bool:
    ep = search_episode_of(execution_state)
    if not ep:
        return False
    return str(ep.get("status") or "") in _STATUS_INCOMPLETE


def start_search_episode(
    execution_state: Any,
    *,
    role: str = "source",
    referent: str = "",
    query: str = "",
    evidence_tokens: Optional[Sequence[str]] = None,
    expected_originator: str = "",
    expected_container: str = "",
    sought_object: str = "",
    space: str = "ui_filter",
    reason: str = "",
    status: str = "querying",
) -> Dict[str, Any]:
    if execution_state is None:
        return {}
    frame = int(getattr(execution_state, "unified_frame", 0) or 0)
    space_s = str(space or "ui_filter")
    scope = _space_to_scope(space_s)
    ep = {
        "status": str(status or "querying"),
        "role": str(role or "source"),
        "referent": str(referent or "").strip(),
        "evidence_tokens": [
            str(t).strip() for t in (evidence_tokens or []) if str(t).strip()
        ][:12],
        # Typed goal/referent roles only — never inferred from evidence_tokens.
        "expected_originator": str(expected_originator or "").strip(),
        "expected_container": str(expected_container or "").strip(),
        "sought_object": str(sought_object or "").strip(),
        "query": str(query or "").strip(),
        "candidate_count": 0,
        "candidate_fingerprint": "",
        "chosen_label": "",
        "chosen_id": None,
        "scores": [],
        "space": space_s,
        "explored_scopes": [scope],
        "started_frame": frame,
        "reason": str(reason or "")[:120],
    }
    stamp_search_contract(ep, exhausted=False)
    try:
        execution_state.search_episode = ep
    except Exception:
        pass
    return ep


def advance_search_with_candidates(
    execution_state: Any,
    candidates: Sequence[Dict[str, Any]],
    *,
    referent: str = "",
    query: str = "",
    evidence_tokens: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """After perceive: filter/rank readiness. May complete via unique fit."""
    if execution_state is None:
        return {}
    ep = search_episode_of(execution_state) or {}
    rows = [c for c in candidates if isinstance(c, dict)]
    ref = str(referent or ep.get("referent") or "").strip()
    q = str(query or ep.get("query") or "").strip()
    tokens = list(evidence_tokens or ep.get("evidence_tokens") or [])
    if ref and ref not in tokens:
        tokens = [ref] + tokens
    if q and q not in tokens:
        tokens.append(q)

    filtered = filter_search_candidates(
        rows,
        referent=ref,
        query=q,
        evidence_tokens=tokens,
        episode=ep,
        role=str(ep.get("role") or ""),
        expected_originator=str(ep.get("expected_originator") or ""),
        expected_container=str(ep.get("expected_container") or ""),
    )
    unique = unique_fitting_candidate(
        filtered, referent=ref, evidence_tokens=tokens, query=q
    )
    status = "ranking"
    chosen_label = ""
    chosen_id: Any = None
    choice_confidence = ""
    role_rejected_ids = [
        x for x in list(ep.get("role_rejected_ids") or []) if x is not None
    ][:24]
    role_rejected_labels = [
        str(x).strip()
        for x in list(ep.get("role_rejected_labels") or [])
        if str(x).strip()
    ][:24]
    just_rejected_unique = False
    if unique is not None and len(filtered) == 1:
        gm = unique.get("goal_match") if isinstance(unique.get("goal_match"), dict) else {}
        interp = unique.get("interpretation") if isinstance(unique.get("interpretation"), dict) else {}
        contras = [str(c) for c in list(interp.get("contradictions") or [])]
        # unknown ≠ negative: missing sender stays explorable. Hard reject only
        # on explicit impossibility (self vs required sender, distractor host).
        hard_role_reject = bool(gm) and not bool(gm.get("binding_eligible")) and (
            "explicit_self_vs_required_sender" in contras
            or "url_host_contradicts_query" in contras
            or any(
                "originator_mismatch" in c and "self" in c.lower() for c in contras
            )
        )
        if hard_role_reject:
            just_rejected_unique = True
            status = "ranking"
            chosen_label = str(unique.get("label") or unique.get("text") or "")
            chosen_id = unique.get("id")
            if chosen_id is not None and chosen_id not in role_rejected_ids:
                role_rejected_ids.append(chosen_id)
            if chosen_label and chosen_label not in role_rejected_labels:
                role_rejected_labels.append(chosen_label)
        else:
            # Unique hypothesis after filter ≠ RoleBinding.resolved.
            # Mark retrieval complete with provisional choice confidence so
            # downstream cannot treat uniqueness as semantic resolution.
            status = "complete"
            chosen_label = str(unique.get("label") or unique.get("text") or "")
            chosen_id = unique.get("id")
            choice_confidence = "provisional"
    elif unique is not None and len(filtered) > 1:
        # Strong unique among many after echo demotion — still rank when ambiguous.
        status = "ranking"
    elif not filtered:
        committed_q = bool(q or str(ep.get("query") or "").strip())
        if rows:
            status = "failed"
        elif committed_q:
            # Query was authored; world returned zero candidates → empty find.
            status = "failed"
        elif str(ep.get("status") or "") == "querying":
            status = "retrieving"
        else:
            status = str(ep.get("status") or "retrieving")

    explored = _explored_scopes_of(ep)
    scope = _space_to_scope(str(ep.get("space") or "ui_filter"))
    if scope and scope not in explored:
        explored = explored + [scope]
    from plugin.agent.capabilities.search_hypothesis import hypothesis_ledger_entries

    ledger = hypothesis_ledger_entries(filtered or rows)
    if ledger and status in {"complete", "ranking"} and not chosen_label:
        # Exploration pointer: top hypothesis without forcing commit.
        top = (filtered or rows)[0] if (filtered or rows) else None
        if isinstance(top, dict):
            ep_explore_label = str(top.get("label") or top.get("text") or "")
        else:
            ep_explore_label = ""
    else:
        ep_explore_label = chosen_label
    for entry in ledger:
        if chosen_label and str(entry.get("label") or "") == chosen_label:
            entry["selected_for_exploration"] = True
        elif (
            not chosen_label
            and ep_explore_label
            and str(entry.get("label") or "") == ep_explore_label
        ):
            entry["selected_for_exploration"] = True

    ep = {
        **ep,
        "status": status,
        "referent": ref or ep.get("referent") or "",
        "query": q or ep.get("query") or "",
        "evidence_tokens": tokens[:12],
        "candidate_count": len(filtered) if filtered else len(rows),
        "candidate_fingerprint": _fingerprint(filtered or rows),
        "chosen_label": chosen_label,
        "chosen_id": chosen_id,
        "choice_confidence": choice_confidence
        or (ep.get("choice_confidence") if status == "complete" else ""),
        "explore_label": ep_explore_label or chosen_label,
        "filtered_count": len(filtered),
        "raw_count": len(rows),
        "explored_scopes": explored,
        "role_rejected_ids": role_rejected_ids,
        "role_rejected_labels": role_rejected_labels,
        "hypothesis_ledger": ledger[:16],
        "retrieval_complete": bool(
            status == "complete" or ep.get("retrieval_complete")
        ),
        # Unique / ranked choice is not RoleBinder resolution.
        "role_resolved": bool(ep.get("role_resolved")) if status != "complete" else False,
    }
    if status == "complete" and choice_confidence == "provisional":
        ep["role_resolved"] = False
        ep["retrieval_complete"] = True
    if just_rejected_unique:
        gm = unique.get("goal_match") if isinstance(unique, dict) else None
        reject_reason = role_rejection_reason_from_assessment(
            gm if isinstance(gm, dict) else None
        )
        ep["retrieval_complete"] = True
        ep["role_resolved"] = False
        ep["role_unresolved_reason"] = reject_reason
        reasons = [
            str(x).strip()
            for x in list(ep.get("role_rejected_reasons") or [])
            if str(x).strip()
        ][:24]
        if reject_reason and reject_reason not in reasons:
            reasons.append(reject_reason)
        ep["role_rejected_reasons"] = reasons
        # Frontier produced a hit but no role-valid candidate — not a mechanism failure.
        ep["status"] = "exhausted"
        ep["fail_reason"] = reject_reason
        status = "exhausted"
    if status == "failed" and rows and not filtered:
        ep["fail_reason"] = "no_candidate_fits_referent"
    elif status == "failed" and not rows:
        ep["fail_reason"] = "empty_candidate_set"
    stamp_search_contract(
        ep, exhausted=status in {"failed", "exhausted"}
    )
    # Surface candidate summaries on the result for meta consumers.
    if isinstance(ep.get("result"), dict):
        ep["result"]["candidates"] = [
            {
                "label": str(c.get("label") or c.get("text") or "")[:120],
                "id": c.get("id"),
                "rank_position": (c.get("interpretation") or {}).get("rank_position"),
                "rank_reason": str(
                    (c.get("interpretation") or {}).get("rank_reason") or ""
                )[:120],
            }
            for c in (filtered or rows)[:12]
            if isinstance(c, dict)
        ]
        ep["result"]["hypothesis_ledger"] = list(ep.get("hypothesis_ledger") or [])[:16]
    try:
        execution_state.search_episode = ep
        if status == "failed":
            note_search_progress(
                execution_state,
                delta=0.0,
                empty=True,
                reason=str(ep.get("fail_reason") or "failed"),
            )
            execution_state.search_retreat_owed = True
        elif status == "complete":
            note_search_progress(
                execution_state, delta=1.0, empty=False, reason="unique_fit"
            )
            execution_state.search_retreat_owed = False
        elif status == "ranking" and filtered:
            note_search_progress(
                execution_state,
                delta=float(len(filtered)),
                empty=False,
                reason="candidates",
            )
    except Exception:
        pass
    return ep


def note_retrieval_complete(
    execution_state: Any,
    *,
    chosen_label: str = "",
    chosen_id: Any = None,
    scores: Optional[Sequence[Any]] = None,
    role_resolved: bool = False,
    role_unresolved_reason: str = "",
    candidate_count: int = 0,
) -> Dict[str, Any]:
    """Mark retrieval finished without necessarily resolving the role referent.

    ``retrieval_complete`` ≠ ``role_resolved``. A single wrong-author hit may
    finish retrieval while source_object stays unresolved.
    """
    if execution_state is None:
        return {}
    ep = search_episode_of(execution_state) or {}
    rejected_ids = [
        x for x in list(ep.get("role_rejected_ids") or []) if x is not None
    ][:24]
    rejected_labels = [
        str(x).strip()
        for x in list(ep.get("role_rejected_labels") or [])
        if str(x).strip()
    ][:24]
    rejected_reasons = [
        str(x).strip()
        for x in list(ep.get("role_rejected_reasons") or [])
        if str(x).strip()
    ][:24]
    reason = str(
        role_unresolved_reason or DEFAULT_ROLE_CONSTRAINT_MISMATCH
    ).strip()[:160]
    if not role_resolved:
        if chosen_id is not None and chosen_id not in rejected_ids:
            rejected_ids.append(chosen_id)
        lab = str(chosen_label or "").strip()
        if lab and lab not in rejected_labels:
            rejected_labels.append(lab)
        if reason and reason not in rejected_reasons:
            rejected_reasons.append(reason)
    ep = {
        **ep,
        "retrieval_complete": True,
        "role_resolved": bool(role_resolved),
        "chosen_label": str(chosen_label or "").strip(),
        "chosen_id": chosen_id,
        "chosen_candidate": chosen_id,
        "scores": list(scores or [])[:12],
        "candidate_count": int(
            candidate_count or ep.get("candidate_count") or (1 if chosen_id is not None else 0)
        ),
        "role_unresolved_reason": reason if not role_resolved else "",
        "fail_reason": "",
        "role_rejected_ids": rejected_ids,
        "role_rejected_labels": rejected_labels,
        "role_rejected_reasons": rejected_reasons,
    }
    if role_resolved:
        ep["status"] = "complete"
    else:
        # Keep episode open for role resolution; do not pretend referent bound.
        ep["status"] = str(ep.get("status") or "ranking") or "ranking"
        if ep["status"] == "complete":
            ep["status"] = "ranking"
    stamp_search_contract(ep, exhausted=False)
    try:
        execution_state.search_episode = ep
        note_search_progress(
            execution_state,
            delta=1.0 if role_resolved else 0.5,
            empty=False,
            reason="role_resolved" if role_resolved else "retrieval_complete",
        )
        if role_resolved and hasattr(execution_state, "search_retreat_owed"):
            execution_state.search_retreat_owed = False
    except Exception:
        pass
    return ep


def complete_search_choice(
    execution_state: Any,
    *,
    chosen_label: str,
    chosen_id: Any = None,
    scores: Optional[Sequence[Any]] = None,
) -> Dict[str, Any]:
    """Role-resolved search completion (retrieval + binding-eligible referent)."""
    return note_retrieval_complete(
        execution_state,
        chosen_label=chosen_label,
        chosen_id=chosen_id,
        scores=scores,
        role_resolved=True,
        candidate_count=1,
    )


def maybe_complete_source_contact_from_visible_row(
    execution_state: Any,
    *,
    document: Optional[Dict[str, Any]] = None,
    contact: str = "",
    source_chat_open: bool = False,
) -> Optional[Dict[str, Any]]:
    """Mark source-role episode complete when an actuatable contact row is grounded.

    Opening the source container is a different commitment than ranking
    message/URL rows — do not require a typed link-query episode first
    (live 145943: Pallavi chat_row visible under foreign open).
    """
    if execution_state is None or source_chat_open:
        return None
    src = str(contact or "").strip()
    if not src:
        return None
    from plugin.agent.capabilities.resolve_entity import actuatable_source_contact_row

    row = actuatable_source_contact_row(document, src)
    if not isinstance(row, dict):
        return None
    label = str(row.get("text") or row.get("label") or row.get("name") or src).strip()
    if not label:
        return None
    ep = search_episode_of(execution_state) or {}
    status = str(ep.get("status") or "")
    if status == "complete" and str(ep.get("chosen_label") or "").strip():
        # Already chose something — keep when source-role choice still matches.
        role = str(ep.get("role") or "").strip().lower()
        chosen_n = _norm(ep.get("chosen_label"))
        if role in {"", "source"} and (
            chosen_n == _norm(label)
            or chosen_n == _norm(src)
            or _norm(src) in chosen_n
            or chosen_n in _norm(label)
        ):
            return ep
    if not ep or status in {"cleared", "inactive", "", "failed"}:
        start_search_episode(
            execution_state,
            role="source",
            referent=src,
            query="",
            evidence_tokens=[src],
            space=space_for_surface(str((document or {}).get("surface") or "chat_list")),
            reason="visible_source_contact_row",
            status="ranking",
        )
    else:
        try:
            ep = dict(ep)
            ep["role"] = "source"
            ep["referent"] = src
            execution_state.search_episode = ep
        except Exception:
            pass
    return complete_search_choice(
        execution_state,
        chosen_label=label,
        chosen_id=row.get("id"),
        scores=[1.0],
    )


def fail_search_episode(
    execution_state: Any,
    *,
    reason: str = "empty_candidate_set",
) -> Dict[str, Any]:
    """Mark find-among-many failed (generic empty / no fit) — retreat before re-SEARCH."""
    if execution_state is None:
        return {}
    ep = search_episode_of(execution_state) or {}
    explored = _explored_scopes_of(ep)
    scope = _space_to_scope(str(ep.get("space") or "ui_filter"))
    if scope and scope not in explored:
        explored = explored + [scope]
    ep = {
        **ep,
        "status": "failed",
        "fail_reason": str(reason or "empty_candidate_set")[:120],
        "chosen_label": "",
        "chosen_id": None,
        "candidate_count": int(ep.get("candidate_count") or 0),
        "explored_scopes": explored,
    }
    stamp_search_contract(ep, exhausted=True)
    try:
        execution_state.search_episode = ep
        note_search_progress(
            execution_state,
            delta=0.0,
            empty=True,
            reason=str(reason or "empty_candidate_set")[:80],
        )
        execution_state.search_retreat_owed = True
    except Exception:
        pass
    return ep


def exhaust_search_episode(
    execution_state: Any,
    *,
    reason: str = DEFAULT_ROLE_CONSTRAINT_MISMATCH,
) -> Dict[str, Any]:
    """Frontier exhausted: retrieval found hits but none are role-valid.

    Distinct from ``failed`` (mechanism / empty find). Marks the *current*
    search frontier exhausted; executive may still broaden query/scope or
    change strategy. ``reason`` must come from role-authority evidence when
    available — never a hardcoded domain relation.
    """
    if execution_state is None:
        return {}
    ep = search_episode_of(execution_state) or {}
    explored = _explored_scopes_of(ep)
    scope = _space_to_scope(str(ep.get("space") or "ui_filter"))
    if scope and scope not in explored:
        explored = explored + [scope]
    reason_s = str(reason or DEFAULT_ROLE_CONSTRAINT_MISMATCH)[:160]
    reasons = [
        str(x).strip()
        for x in list(ep.get("role_rejected_reasons") or [])
        if str(x).strip()
    ][:24]
    if reason_s and reason_s not in reasons:
        reasons.append(reason_s)
    ep = {
        **ep,
        "status": "exhausted",
        "fail_reason": reason_s[:120],
        "retrieval_complete": True,
        "role_resolved": False,
        "role_unresolved_reason": reason_s,
        "role_rejected_reasons": reasons,
        "candidate_count": int(ep.get("candidate_count") or 0),
        "explored_scopes": explored,
    }
    stamp_search_contract(ep, exhausted=True)
    try:
        execution_state.search_episode = ep
        note_search_progress(
            execution_state,
            delta=0.0,
            empty=False,
            reason=reason_s[:80],
        )
        execution_state.search_retreat_owed = True
    except Exception:
        pass
    return ep


def note_search_progress(
    execution_state: Any,
    *,
    delta: float,
    empty: bool = False,
    reason: str = "",
) -> Dict[str, Any]:
    """Record whether the last find attempt improved goal-relevant evidence."""
    if execution_state is None:
        return {}
    ep = search_episode_of(execution_state) or {}
    progress = {
        "delta": float(delta),
        "empty": bool(empty),
        "reason": str(reason or "")[:80],
        "episode_status": str(ep.get("status") or ""),
        "query": str(ep.get("query") or "")[:80],
        "candidate_count": int(ep.get("candidate_count") or 0),
    }
    try:
        execution_state.last_search_progress = progress
        if empty or float(delta) <= 0.0:
            execution_state.search_retreat_owed = True
    except Exception:
        pass
    return progress


def clear_search_retreat(execution_state: Any) -> None:
    """After BACKTRACK / INFORMATION_GATHERING — SEARCH may start a fresh episode."""
    if execution_state is None:
        return
    try:
        execution_state.search_retreat_owed = False
    except Exception:
        pass


_FIND_STAGE_FAMILIES = frozenset(
    {
        "resolve_entity",
        "resolveentity",
        "compose_search_query",
        "composesearchquery",
        "type_query",
        "typequery",
        "search",
        "locate_content",
        "locatecontent",
    }
)


def _is_non_execution_find_refusal(message: str) -> bool:
    """True when the motor never reached the app (stale/foreground/off-window).

    Live 202457: Chrome stole focus → compose_search refused as
    ``perception_invalid`` / stale. That is not a failed find among candidates;
    arming ``search_retreat_owed`` traps the agent in explore→observe forever
    while the Search field is still sitting unused.
    """
    msg = str(message or "").lower()
    if not msg:
        return False
    needles = (
        "perception_invalid",
        "refused stale click",
        "stale_precondition",
        "off_task_window",
        "outside task window",
        "holds the foreground",
        "foreground, not",
    )
    return any(n in msg for n in needles)


def note_find_stage_outcome(
    execution_state: Any,
    *,
    family: str = "",
    ok: bool = False,
    message: str = "",
) -> None:
    """Controller latch: find-stage execute must update episode/retreat.

    Backup for any executor path that forgot to call fail/complete. Does not
    reopen a completed episode when a later open click fails (ACT retries).
    """
    if execution_state is None:
        return
    fam = str(family or "").strip().lower().replace("-", "_")
    compact = fam.replace("_", "")
    if fam not in _FIND_STAGE_FAMILIES and compact not in {
        "resolveentity",
        "composesearchquery",
        "typequery",
        "search",
        "locatecontent",
    }:
        return
    ep = search_episode_of(execution_state) or {}
    status = str(ep.get("status") or "")
    is_resolve = fam in {"resolve_entity", "resolveentity"} or compact == "resolveentity"
    is_locate = fam in {"locate_content", "locatecontent"} or compact == "locatecontent"
    if ok:
        if status == "complete" and ep.get("chosen_label"):
            clear_search_retreat(execution_state)
            return
        # Resolve must leave complete or failed — never stuck in ranking (213012).
        if is_resolve and status in _STATUS_INCOMPLETE:
            fail_search_episode(
                execution_state,
                reason=str(message or "resolve_ok_without_choice")[:120],
            )
        # locate ok≠effect: bookkeeping lives in note_locate_outcome; do not
        # complete/fail the entity-resolution episode on AX-blind find.
        if is_locate:
            return
        return
    # Motor never fired — do not treat as a failed find / arm retreat.
    if _is_non_execution_find_refusal(message):
        clear_search_retreat(execution_state)
        # Keep a querying episode open so SEARCH may retry after reclaim.
        if status in {"", "failed", "cleared"} or not status:
            try:
                execution_state.search_episode = {
                    **ep,
                    "status": "querying",
                    "fail_reason": "",
                    "reason": "stale_or_foreground_refusal_retry",
                }
            except Exception:
                pass
        return
    # Failed find-stage. If ranking already chose, keep complete — open miss is ACT.
    if status == "complete" and ep.get("chosen_label"):
        return
    if status == "failed" and bool(getattr(execution_state, "search_retreat_owed", False)):
        return
    # Content locate failures are method-ledger / effect-verify concerns, not
    # entity-resolution episode failure (would wrongly arm search_retreat).
    if is_locate:
        return
    fail_search_episode(
        execution_state,
        reason=str(message or f"{fam or 'find'}_failed")[:120],
    )


def clear_search_episode(execution_state: Any, *, why: str = "") -> None:
    if execution_state is None:
        return
    try:
        if why:
            execution_state.search_episode = {
                "status": "cleared",
                "reason": why[:120],
            }
        else:
            execution_state.search_episode = None
    except Exception:
        pass


def _is_role_rejected(
    row: Dict[str, Any],
    *,
    rejected_ids: Sequence[Any],
    rejected_labels: Sequence[str],
) -> bool:
    """Stable id first; else exact normalized label. No substring containment."""
    rid = row.get("id")
    if rid is not None and rid in set(rejected_ids or []):
        return True
    label = str(row.get("label") or row.get("text") or "").strip()
    if not label:
        return False
    low = _norm(label)
    for rej in rejected_labels or []:
        rj = _norm(rej)
        if rj and rj == low:
            return True
    return False


def exclude_role_rejected_candidates(
    candidates: Sequence[Dict[str, Any]],
    episode: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Drop candidates already rejected for a hard identity/role constraint."""
    ep = episode if isinstance(episode, dict) else {}
    rejected_ids = list(ep.get("role_rejected_ids") or [])
    rejected_labels = [
        str(x) for x in (ep.get("role_rejected_labels") or []) if str(x).strip()
    ]
    if not rejected_ids and not rejected_labels:
        return [dict(c) for c in candidates if isinstance(c, dict)]
    out: List[Dict[str, Any]] = []
    for row in candidates:
        if not isinstance(row, dict):
            continue
        if _is_role_rejected(
            row, rejected_ids=rejected_ids, rejected_labels=rejected_labels
        ):
            continue
        out.append(dict(row))
    return out


def filter_search_candidates(
    candidates: Sequence[Dict[str, Any]],
    *,
    referent: str = "",
    query: str = "",
    evidence_tokens: Optional[Sequence[str]] = None,
    episode: Optional[Dict[str, Any]] = None,
    expected_originator: str = "",
    expected_container: str = "",
    role: str = "",
) -> List[Dict[str, Any]]:
    """Filter + hypothesis-rank using role-conditioned interpretation.

    Replaces the old 4-feature arithmetic soft-rank. Echoes are demoted when
    better fits exist. ``unknown`` originator is not treated as negative.
    """
    from plugin.agent.capabilities.search_hypothesis import rank_search_hypotheses

    tokens = [_norm(t) for t in (evidence_tokens or []) if _norm(t)]
    ref_n = _norm(referent)
    if ref_n and ref_n not in tokens:
        tokens = [ref_n] + tokens
    rows = exclude_role_rejected_candidates(candidates, episode)
    if not rows:
        return []

    ep = episode if isinstance(episode, dict) else {}
    role_s = str(role or ep.get("role") or "content").strip().lower() or "content"
    # Typed goal/referent state only. evidence_tokens are an unordered bag —
    # never promote a token into expected_originator / expected_container.
    # originator and container stay independent — never alias one to the other.
    origin = str(
        expected_originator or ep.get("expected_originator") or ""
    ).strip()
    container = str(
        expected_container or ep.get("expected_container") or ""
    ).strip()
    query_s = str(query or ep.get("query") or referent or "").strip()
    # Typed sought-object semantics only; free-form query must not invent
    # platform object type (instagram acquisition notes ≠ Instagram URL).
    sought_object = str(ep.get("sought_object") or "").strip()

    ranked = rank_search_hypotheses(
        rows,
        query=query_s,
        expected_container=container,
        expected_originator=origin,
        sought_object=sought_object,
        role=role_s,
    )
    return ranked


def unique_fitting_candidate(
    candidates: Sequence[Dict[str, Any]],
    *,
    referent: str = "",
    evidence_tokens: Optional[Sequence[str]] = None,
    query: str = "",
) -> Optional[Dict[str, Any]]:
    tokens = [_norm(t) for t in (evidence_tokens or []) if _norm(t)]
    ref_n = _norm(referent)
    if ref_n and ref_n not in tokens:
        tokens = [ref_n] + tokens
    fits = []
    for row in candidates:
        if not isinstance(row, dict):
            continue
        label = str(row.get("label") or row.get("text") or "")
        if query and _is_query_echo(label, query):
            continue
        if content_target_fits_referents(
            target_label=label,
            object_blob=f"{label} {row.get('id') or ''}",
            goal_referents=tokens,
        ) or (tokens and _text_matches_goal(label, tokens)):
            fits.append(row)
        elif not tokens and len(list(candidates)) == 1:
            fits.append(row)
    if len(fits) == 1:
        return fits[0]
    # Single surviving candidate after filter with a referent → accept it.
    rows = [r for r in candidates if isinstance(r, dict)]
    if len(rows) == 1 and tokens and not (query and _is_query_echo(
        str(rows[0].get("label") or rows[0].get("text") or ""), query
    )):
        return rows[0]
    return None


def candidates_from_world_document(document: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    doc = document if isinstance(document, dict) else {}
    rows: List[Dict[str, Any]] = []
    for obj in doc.get("objects") or []:
        if not isinstance(obj, dict):
            continue
        text = str(obj.get("text") or obj.get("label") or obj.get("name") or "").strip()
        if not text:
            continue
        row = {
            "label": text,
            "id": obj.get("id"),
            "kind": obj.get("kind"),
            "point": obj.get("point"),
            "matches_goal": bool(obj.get("matches_goal")),
        }
        for key in ("sender", "originator", "role", "field_role"):
            if obj.get(key) not in (None, ""):
                row[key] = obj.get(key)
        gm = obj.get("goal_match")
        if isinstance(gm, dict):
            row["goal_match"] = gm
        interp = obj.get("interpretation")
        if isinstance(interp, dict):
            row["interpretation"] = interp
        rows.append(row)
    return rows


def space_for_surface(surface: str) -> str:
    surf = str(surface or "").strip().lower()
    if surf == "forward_picker":
        return "picker"
    if surf in {"search", "search_results"}:
        return "ui_filter"
    if surf in {"conversation", "chat"}:
        return "in_surface"
    if surf == "chat_list":
        return "ui_filter"
    return "unspecified"


def _episode_holder(execution_state: Any) -> Any:
    """Return an object with `.search_episode` — real state or a throwaway box."""
    if execution_state is not None:
        return execution_state

    class _Box:
        search_episode = None
        unified_frame = 0

    return _Box()


def ensure_search_episode_from_brief(
    execution_state: Any,
    brief: Any,
) -> Dict[str, Any]:
    """Arm / advance episode from DecisionBrief world + goal."""
    if brief is None:
        return {}
    holder = _episode_holder(execution_state)
    goal = brief.goal if isinstance(getattr(brief, "goal", None), dict) else {}
    doc = brief.world if isinstance(getattr(brief, "world", None), dict) else {}
    surface = str(doc.get("surface") or "").strip().lower()
    task = getattr(brief, "task_state", None)
    # Authored/typed box string only — never fall back to goal link_query, or
    # every reach_source brief arms a ranking episode before compose.
    query = str(getattr(task, "search_query", "") or "").strip() if task else ""
    dest = str(goal.get("destination") or goal.get("target_contact") or "").strip()
    link_q = str(goal.get("source_query") or goal.get("link_query") or "").strip()
    # Source/container referent — never destination/general contact by accident.
    source_container = str(
        goal.get("source_conversation")
        or goal.get("container")
        or goal.get("conversation_with")
        or goal.get("expected_container")
        or ""
    ).strip()
    if not source_container:
        # Legacy Goal.contact is usually source, but reject when it equals dest.
        legacy = str(goal.get("contact") or "").strip()
        if legacy and _norm(legacy) != _norm(dest):
            source_container = legacy
    contact = source_container

    role = "source"
    referent = contact or link_q
    if surface == "forward_picker":
        role = "destination"
        referent = dest or referent
    elif getattr(task, "source_chat_open", False) and link_q:
        role = "content"
        referent = link_q
    elif surface in {"search", "search_results"} and link_q:
        # Sidebar search authored from a link/content cue: rank against that
        # referent (contact stays in evidence tokens). Avoids opening a
        # contact-name echo of the typed query over a content-shaped hit.
        role = "content" if (not query or _norm(query) in _norm(link_q) or _norm(link_q) in _norm(query)) else "source"
        if role == "content":
            referent = link_q

    tokens = [t for t in (referent, contact, link_q, query, dest) if t]
    tokens = list(dict.fromkeys(tokens))
    # Typed semantic roles from the goal — independent relations.
    # container ← source conversation; originator ← typed sent_by / "from X".
    # Never: expected_originator = container; never: container = destination.
    typed_container = dest if role == "destination" else source_container
    # Debt: normalize originator / expected_originator / sent_by upstream to one
    # canonical Goal relation; SEARCH should eventually consume only "originator".
    typed_originator = str(
        goal.get("originator")
        or goal.get("expected_originator")
        or goal.get("sent_by")
        or ""
    ).strip()
    # Platform/object type only when the goal explicitly typed it — not query text.
    typed_sought_object = str(
        goal.get("sought_object")
        or goal.get("object_platform")
        or goal.get("sought_platform")
        or ""
    ).strip()
    cands = candidates_from_world_document(doc)
    ep = search_episode_of(holder)
    # Arm only when search has material evidence — not on chat_list previews
    # before a query (compose-first), and not on open conversation content
    # probes (reveal/select). Those use other gates.
    results_surface = surface in {"search", "search_results"}
    picker_surface = surface == "forward_picker"
    typed_query = bool(query)
    needs_search = (
        (results_surface and cands)
        or (picker_surface and len(cands) >= 2)
        or (typed_query and results_surface)
        or (typed_query and surface == "chat_list" and cands)
        or (bool(ep) and str(ep.get("status") or "") in _STATUS_INCOMPLETE)
    )
    if not ep or str(ep.get("status") or "") in {"cleared", "inactive", ""}:
        if not needs_search:
            return {}
        start_status = "ranking" if cands else ("retrieving" if typed_query else "querying")
        if picker_surface and cands:
            start_status = "ranking"
        start_search_episode(
            holder,
            role=role,
            referent=referent,
            query=query,
            evidence_tokens=tokens,
            expected_originator=typed_originator,
            expected_container=typed_container,
            sought_object=typed_sought_object,
            space=space_for_surface(surface),
            reason="ensure_from_brief",
            status=start_status,
        )
    else:
        # Refresh typed roles when goal fields are known; never invent from tokens
        # or alias originator ← container.
        try:
            ep = dict(ep)
            if typed_originator and not str(ep.get("expected_originator") or "").strip():
                ep["expected_originator"] = typed_originator
            if typed_container and not str(ep.get("expected_container") or "").strip():
                ep["expected_container"] = typed_container
            if typed_sought_object and not str(ep.get("sought_object") or "").strip():
                ep["sought_object"] = typed_sought_object
            if query and not str(ep.get("query") or "").strip():
                ep["query"] = query
            holder.search_episode = ep
        except Exception:
            pass

    ep = search_episode_of(holder) or {}
    # Do not re-rank over a finished episode (unique fit / resolve already chose).
    # While retreat is owed after a failed find, keep the dead episode — do not
    # silently re-arm ranking from leftover rows (live 212533 loop).
    if str(ep.get("status") or "") in {"complete", "failed", "exhausted"}:
        return ep
    if (
        execution_state is not None
        and bool(getattr(execution_state, "search_retreat_owed", False))
        and ep
    ):
        return ep

    search_empty = bool(getattr(task, "search_empty", False)) if task else False
    if isinstance(doc, dict):
        search_empty = search_empty or bool(doc.get("search_empty"))

    if cands:
        return advance_search_with_candidates(
            holder,
            cands,
            referent=referent,
            query=query or str((search_episode_of(holder) or {}).get("query") or ""),
            evidence_tokens=tokens,
        )

    # Committed query + zero candidates (often search_empty chrome): fail generically
    # so meta must retreat before another SEARCH — not re-compose on a dead branch.
    committed = bool(query or str(ep.get("query") or "").strip())
    if committed and str(ep.get("status") or "") in _STATUS_INCOMPLETE:
        if search_empty or surface in _SEARCH_SURFACES | {"calls", "chat_list"}:
            return fail_search_episode(holder, reason="empty_candidate_set")

    return search_episode_of(holder) or {}


def commit_allowed_for_target(
    execution_state: Any,
    *,
    capability: str,
    target: str,
) -> Tuple[bool, str]:
    """Whether open/select may run for ``target`` given search episode state."""
    cap = str(capability or "").strip().lower()
    if cap not in _COMMIT_CAPS:
        return True, ""
    ep = search_episode_of(execution_state)
    if not ep:
        return True, ""
    status = str(ep.get("status") or "")
    if status in _STATUS_INCOMPLETE:
        return False, "search_incomplete_rank_before_commit"
    if status == "complete":
        chosen = _norm(ep.get("chosen_label"))
        tgt = _norm(target)
        if chosen and tgt and chosen not in tgt and tgt not in chosen:
            # Allow open of chosen when target empty (will be filled by helper).
            if tgt:
                return (
                    False,
                    f"commit_target_mismatches_search_choice:{ep.get('chosen_label')}",
                )
    if status in {"failed", "exhausted"}:
        return False, str(ep.get("fail_reason") or "search_failed")
    return True, ""


def search_continue_capability(
    execution_state: Any,
    brief: Any,
    *,
    meta_action: str = "",
) -> Tuple[str, str, str]:
    """Return (capability, target, why) to continue or commit after search sync.

    capability empty means no rewrite.
    Under meta SEARCH, never rewrite to open/select (ACT commits after chosen).
    """
    doc = brief.world if isinstance(getattr(brief, "world", None), dict) else {}
    surface = str(doc.get("surface") or "").strip().lower()
    meta = str(meta_action or "").strip().lower()
    if not meta:
        meta = str(getattr(brief, "meta_action", "") or "").strip().lower()
    if not meta and execution_state is not None:
        meta = str(getattr(execution_state, "last_meta_action", "") or "").strip().lower()
    allowed = set(getattr(brief, "capabilities", None) or [])
    task = getattr(brief, "task_state", None)
    goal = brief.goal if isinstance(getattr(brief, "goal", None), dict) else {}
    link_q = str(
        goal.get("source_query") or goal.get("link_query") or ""
    ).strip()
    # Open conversation + unpaid content query under SEARCH → locate in-chat
    # (live 225807: SEARCH meta kept falling through to Observe).
    if (
        surface == "conversation"
        and meta == "search"
        and bool(getattr(task, "source_chat_open", False))
        and not bool(getattr(task, "content_located", False))
        and link_q
        and "locate_content" in allowed
    ):
        return (
            "locate_content",
            link_q,
            "source open; SEARCH content query unpaid — locate_content in conversation",
        )
    # Do not hijack reveal/select on an open conversation / menus.
    if surface not in {"search", "search_results", "chat_list", "forward_picker"}:
        return "", "", ""
    ep = ensure_search_episode_from_brief(execution_state, brief)
    if not ep:
        return "", "", ""
    status = str(ep.get("status") or "")
    allowed = set(getattr(brief, "capabilities", None) or [])
    if status == "exhausted":
        return (
            "",
            "",
            "search frontier exhausted — broaden or change strategy",
        )
    if status == "complete" and ep.get("chosen_label"):
        if meta == "search":
            # Ranking done — do not re-resolve or open under SEARCH; next meta ACT.
            # status=complete is retrieval/choice complete, not RoleBinder resolved.
            return "", "", "search complete; await ACT open"
        if "open_entity" in allowed:
            return (
                "open_entity",
                str(ep.get("chosen_label") or ""),
                "search complete; explore/open chosen hypothesis (not role bind)",
            )
        return "", "", ""
    if status in _STATUS_INCOMPLETE:
        doc = brief.world if isinstance(getattr(brief, "world", None), dict) else {}
        cands = candidates_from_world_document(doc)
        filtered = filter_search_candidates(
            cands,
            referent=str(ep.get("referent") or ""),
            query=str(ep.get("query") or ""),
            evidence_tokens=list(ep.get("evidence_tokens") or []),
            episode=ep,
        )
        if not filtered and (
            ep.get("role_rejected_ids") or ep.get("role_rejected_labels")
        ):
            # Hard identity rejects exhausted the frontier — do not reselect.
            holder = _episode_holder(execution_state)
            exhaust_search_episode(
                holder,
                reason=str(
                    ep.get("role_unresolved_reason")
                    or DEFAULT_ROLE_CONSTRAINT_MISMATCH
                ),
            )
            try:
                brief.search_episode = search_episode_of(holder)
            except Exception:
                pass
            return (
                "",
                "",
                "role-rejected candidates exhausted — broaden search strategy",
            )
        unique = unique_fitting_candidate(
            filtered,
            referent=str(ep.get("referent") or ""),
            evidence_tokens=list(ep.get("evidence_tokens") or []),
            query=str(ep.get("query") or ""),
        )
        if unique is not None and len(filtered) == 1:
            label = str(unique.get("label") or unique.get("text") or "")
            holder = _episode_holder(execution_state)
            # Explicit RoleBinder assessment required to reject; missing means
            # no identity constraint attached to this candidate (contact search).
            gm = unique.get("goal_match")
            if isinstance(gm, dict):
                unique_eligible = bool(gm.get("binding_eligible"))
            else:
                unique_eligible = True
            if unique_eligible:
                complete_search_choice(
                    holder, chosen_label=label, chosen_id=unique.get("id")
                )
                try:
                    brief.search_episode = search_episode_of(holder) or {
                        **ep,
                        "status": "complete",
                        "chosen_label": label,
                        "retrieval_complete": True,
                        "role_resolved": True,
                    }
                except Exception:
                    pass
                if label:
                    if meta == "search":
                        return "", "", "search unique fit; role resolved; await ACT open"
                    if "open_entity" in allowed:
                        return (
                            "open_entity",
                            label,
                            "search unique fit; commit binding-eligible candidate",
                        )
            else:
                reject_reason = role_rejection_reason_from_assessment(
                    gm if isinstance(gm, dict) else None
                )
                note_retrieval_complete(
                    holder,
                    chosen_label=label,
                    chosen_id=unique.get("id"),
                    role_resolved=False,
                    role_unresolved_reason=reject_reason,
                    candidate_count=1,
                )
                try:
                    brief.search_episode = search_episode_of(holder)
                except Exception:
                    pass
                # Hard reject recorded — do not immediately reselect same candidate.
                exhaust_search_episode(holder, reason=reject_reason)
                try:
                    brief.search_episode = search_episode_of(holder)
                except Exception:
                    pass
                return (
                    "",
                    "",
                    "retrieval complete; role-rejected unique candidate — broaden",
                )
        if filtered and "resolve_entity" in allowed:
            top = filtered[0]
            label = str(top.get("label") or top.get("text") or "")
            # Clear score margin ⇒ treat as ranked choice for actor click.
            scores = [float(r.get("_search_score") or 0) for r in filtered[:3]]
            # retrieval_complete ≠ role_resolved. Unique/high-margin candidates
            # finish retrieval; only binding_eligible commits role resolution.
            gm_top = top.get("goal_match")
            if isinstance(gm_top, dict):
                top_eligible = bool(gm_top.get("binding_eligible"))
            else:
                top_eligible = True
            retrieval_done = (
                len(filtered) == 1
                or (len(scores) >= 2 and scores[0] >= scores[1] + 2.0)
                or (len(scores) == 1 and scores[0] > 0)
            )
            holder = _episode_holder(execution_state)
            if retrieval_done and label:
                if top_eligible:
                    complete_search_choice(
                        holder,
                        chosen_label=label,
                        chosen_id=top.get("id"),
                        scores=scores,
                    )
                    try:
                        brief.search_episode = search_episode_of(holder) or {
                            **ep,
                            "status": "complete",
                            "chosen_label": label,
                            "retrieval_complete": True,
                            "role_resolved": True,
                        }
                    except Exception:
                        pass
                    if meta == "search":
                        return "", "", "search ranked; role resolved; await ACT open"
                    if "open_entity" in allowed:
                        return (
                            "open_entity",
                            label,
                            "search ranked; commit binding-eligible candidate",
                        )
                reject_reason = role_rejection_reason_from_assessment(
                    gm_top if isinstance(gm_top, dict) else None
                )
                note_retrieval_complete(
                    holder,
                    chosen_label=label,
                    chosen_id=top.get("id"),
                    scores=scores,
                    role_resolved=False,
                    role_unresolved_reason=reject_reason,
                    candidate_count=len(filtered),
                )
                try:
                    brief.search_episode = search_episode_of(holder)
                    ep = search_episode_of(holder) or ep
                except Exception:
                    pass
                # Course-correct: drop the reject and pick another candidate.
                remaining = exclude_role_rejected_candidates(filtered, ep)
                if not remaining:
                    exhaust_search_episode(holder, reason=reject_reason)
                    try:
                        brief.search_episode = search_episode_of(holder)
                    except Exception:
                        pass
                    return (
                        "",
                        "",
                        "retrieval complete; role-rejected — no remaining candidates",
                    )
                nxt = remaining[0]
                nxt_label = str(nxt.get("label") or nxt.get("text") or "")
                return (
                    "resolve_entity",
                    nxt_label or str(ep.get("referent") or ep.get("query") or ""),
                    "role reject recorded; resolve next non-rejected candidate",
                )
            return (
                "resolve_entity",
                label or str(ep.get("referent") or ep.get("query") or ""),
                "retrieval may be complete; role unresolved — resolve_entity",
            )
        if status == "querying" and "compose_search_query" in allowed:
            return (
                "compose_search_query",
                "",
                "search episode querying; compose_search_query",
            )
        return "", "", "search_incomplete"
    return "", "", ""


def goal_search_criteria(goal: Any) -> tuple[str, str, str]:
    """Contact / link query / destination from Goal, GoalState, or dict brief."""
    if goal is None:
        return "", "", ""
    if isinstance(goal, dict):
        contact = str(
            goal.get("contact")
            or goal.get("source_conversation")
            or goal.get("subject")
            or ""
        ).strip()
        link_q = str(
            goal.get("link_query") or goal.get("source_query") or goal.get("query") or ""
        ).strip()
        dest = str(
            goal.get("target_contact")
            or goal.get("destination")
            or goal.get("target")
            or ""
        ).strip()
        return contact, link_q, dest
    contact = str(
        getattr(goal, "contact", None)
        or getattr(goal, "subject", None)
        or getattr(goal, "source_conversation", None)
        or ""
    ).strip()
    link_q = str(
        getattr(goal, "link_query", None)
        or getattr(goal, "query", None)
        or getattr(goal, "source_query", None)
        or ""
    ).strip()
    dest = str(
        getattr(goal, "target_contact", None)
        or getattr(goal, "destination", None)
        or ""
    ).strip()
    return contact, link_q, dest


def meta_referent_search_signals(
    execution_state: Any,
    *,
    phase: str = "",
    source_chat_open: bool = False,
    surface: str = "",
    goal: Any = None,
    content_located: bool = False,
    document: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Signals for MetaContext / meta packet about find-among-many."""
    from plugin.agent.executive.meta_action import SEARCH_STREAK_CAP

    ep = search_episode_of(execution_state) or {}
    status = str(ep.get("status") or "")
    incomplete = status in _STATUS_INCOMPLETE
    complete = status == "complete" and bool(ep.get("chosen_label"))
    failed = status == "failed"
    contact, link_q, dest = goal_search_criteria(goal)
    surf = str(surface or "").strip().lower()
    ph = str(phase or "").strip().lower().replace("-", "_")
    # Criteria known + target not yet committed into an open source/dest.
    criteria = bool(contact or link_q or dest or ep.get("referent") or ep.get("query"))
    on_find_surface = surf in {"search", "search_results", "chat_list", "forward_picker", "calls"}
    # Pre-source / find phases — include domain OPEN_SOURCE aliases.
    pre_source = ph in {
        "",
        "reach_source",
        "open_source",
        "preclear",
        "hunt_content",
        "find_link",
    }
    post_source = ph in {
        "act_on_content",
        "choose_destination",
        "invoke_forward",
        "committed",
        "verified",
        "commit",
    }
    source_contact_open_ready = False
    source_contact_open_label = ""
    if contact and not source_chat_open and pre_source:
        doc = document
        if doc is None and execution_state is not None:
            raw = getattr(execution_state, "unified_world_document", None)
            doc = dict(raw) if isinstance(raw, dict) else {}
        completed = maybe_complete_source_contact_from_visible_row(
            execution_state,
            document=doc if isinstance(doc, dict) else None,
            contact=contact,
            source_chat_open=source_chat_open,
        )
        if completed:
            ep = completed
            status = str(ep.get("status") or "")
            incomplete = status in _STATUS_INCOMPLETE
            complete = status == "complete" and bool(ep.get("chosen_label"))
            source_contact_open_ready = True
            source_contact_open_label = str(ep.get("chosen_label") or contact)
        else:
            from plugin.agent.capabilities.resolve_entity import (
                actuatable_source_contact_row,
            )

            row = actuatable_source_contact_row(
                doc if isinstance(doc, dict) else None, contact
            )
            if isinstance(row, dict):
                source_contact_open_ready = True
                source_contact_open_label = str(
                    row.get("text") or row.get("label") or contact
                ).strip()
    need_source = (
        (pre_source or (criteria and not post_source))
        and not source_chat_open
        and bool(contact or link_q)
        and not source_contact_open_ready
    )
    # Container open ≠ content found: unpaid link/query still owes SEARCH
    # (live 214626: false/true source open + ACT on unrelated visible row).
    role = str(ep.get("role") or "").strip().lower()
    content_episode_done = bool(complete and role == "content")
    # Content SEARCH debt only after the container is open. A completed *source*
    # episode (Pallavi row chosen) must not clear it (live 214025).
    need_content = (
        bool(link_q)
        and bool(source_chat_open)
        and not failed
        and not content_located
        and not content_episode_done
    )
    need_dest = surf == "forward_picker" and bool(dest) and not complete
    needed = bool(
        incomplete
        or (criteria and on_find_surface and not complete and not source_chat_open)
        or need_source
        or need_content
        or need_dest
    )
    # Complete clears SEARCH only when it does not leave unpaid content debt.
    if complete and not need_content:
        needed = False
    # Failed empty find: goal may still need a referent, but this episode is dead —
    # meta must retreat before re-entering SEARCH (loop convergence).
    retreat_owed = bool(
        failed
        or getattr(execution_state, "search_retreat_owed", False)
        or (
            isinstance(getattr(execution_state, "last_search_progress", None), dict)
            and (
                getattr(execution_state, "last_search_progress", {}).get("empty")
                or float(
                    getattr(execution_state, "last_search_progress", {}).get("delta")
                    or 0
                )
                <= 0.0
            )
            and str(
                getattr(execution_state, "last_search_progress", {}).get("episode_status")
                or ""
            )
            == "failed"
        )
    )
    searches = int(getattr(execution_state, "consecutive_searches", 0) or 0) if execution_state else 0
    progress = getattr(execution_state, "last_search_progress", None) if execution_state else None
    exhausted = searches >= SEARCH_STREAK_CAP or failed
    # Address known (identity open) → RETRIEVE/ACT, not another SEARCH arm.
    address_known = bool(source_chat_open and contact)
    # Soft content_located alone is not retrieve_ready — need a completed
    # *content* episode (live contract) plus located evidence. Source-role
    # complete must not arm retrieve (live 214025 YouTube).
    if link_q:
        retrieve_ready = bool(
            address_known
            and content_located
            and content_episode_done
            and not incomplete
            and not failed
        )
    else:
        retrieve_ready = bool(
            address_known
            and not need_content
            and not incomplete
            and (
                complete
                or (address_known and not need_source and not need_dest)
            )
        )
    # Visible source contact row: ACT open_entity, not another compose SEARCH.
    if source_contact_open_ready and not source_chat_open and not incomplete and not failed:
        retrieve_ready = True
        needed = False
        if source_contact_open_label:
            complete = True
    if retrieve_ready and not incomplete and not failed and not need_content:
        # Do not keep SEARCH owed when the referent address is already open
        # and unpaid content debt is cleared.
        needed = False
    if ep:
        stamp_search_contract(ep, exhausted=exhausted)
        try:
            if execution_state is not None:
                execution_state.search_episode = ep
        except Exception:
            pass
    intent = search_intent_from_episode(ep)
    result = search_result_from_episode(ep, exhausted=exhausted)
    return {
        "needed": needed,
        "incomplete": incomplete,
        "complete": complete,
        "failed": failed,
        "fail_reason": str(ep.get("fail_reason") or ""),
        "retreat_owed": retreat_owed,
        "exhausted": exhausted,
        "status": status or ("inactive" if not ep else status),
        "role": str(ep.get("role") or ""),
        "referent": str(ep.get("referent") or contact or link_q or ""),
        "query": str(ep.get("query") or link_q or ""),
        "chosen_label": str(ep.get("chosen_label") or source_contact_open_label or ""),
        "candidate_count": int(ep.get("candidate_count") or 0),
        "space": str(ep.get("space") or ""),
        "contact": contact,
        "link_query": link_q,
        "content_located": bool(content_located),
        "address_known": address_known,
        "retrieve_ready": retrieve_ready,
        "source_contact_open_ready": source_contact_open_ready,
        "source_contact_open_label": source_contact_open_label,
        "has_criteria": has_search_criteria(
            episode=ep, goal=goal, referent=contact or link_q, query=link_q
        ),
        "intent": intent.to_dict(),
        "result": result.to_dict(),
        "coverage": dict(result.coverage or {}),
        "unexplored_scopes": list(result.unexplored_scopes or []),
        "progress": dict(progress) if isinstance(progress, dict) else None,
        "episode": ep or None,
    }
