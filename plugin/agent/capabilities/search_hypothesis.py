"""Role-conditioned SEARCH hypothesis interpretation (explore-order).

Separates:
  relevance / compatibility / commit_readiness (advisory)

from RoleBinder authority (commit only).

Does **not** introduce a large weighted score table. Ranking is lexicographic
over structured evidence tiers so unknown ≠ negative and relation contradictions
demote without inventing domain-specific bonuses.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from plugin.agent.source_query_binding import (
    _DISTRACTOR_HOSTS,
    evaluate_source_object_match,
    extract_urls,
    host_contradicts_query,
    infer_message_originator,
    query_supported_by_text,
    url_host,
)


def _norm(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def _is_query_echo(label: str, query: str) -> bool:
    """Local echo detector aligned with search_episode._is_query_echo."""
    lab = _norm(label)
    q = _norm(query)
    if not lab or not q or len(q) < 4:
        return False
    if lab == q:
        return True
    stripped = re.sub(r"^(you|me)\s*:\s*", "", lab)
    if stripped == q:
        return True
    if q in lab and (
        "you:" in lab
        or lab.startswith(q)
        or re.search(rf"\byou:\s*{re.escape(q)}\b", lab)
    ):
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


def _url_relevance_tier(text: str, query: str) -> Tuple[int, str]:
    """3=direct object URL, 2=related entity URL, 1=non-URL content, 0=none."""
    q = _norm(query)
    blob = _norm(text)
    urls = extract_urls(text)
    if not urls:
        if q and query_supported_by_text(blob, query):
            return 1, "text_match"
        return 0, "no_query_support"
    brand = (q.split() or [""])[0]
    best = 0
    reason = "url_present"
    for url in urls:
        host = url_host(url)
        path = _norm(url)
        if host in _DISTRACTOR_HOSTS or any(
            host.endswith("." + d) for d in _DISTRACTOR_HOSTS if "." in d
        ):
            # Related account/path — not the sought direct object.
            if brand and brand in path:
                best = max(best, 2)
                reason = "related_distractor_host"
            else:
                best = max(best, 1)
                reason = "distractor_host"
            continue
        if brand and brand in host:
            best = max(best, 3)
            reason = "direct_brand_host"
        elif brand and brand in path:
            best = max(best, 2)
            reason = "query_in_url_path"
        else:
            best = max(best, 2 if query_supported_by_text(path, query) else 1)
            reason = "url_other"
    return best, reason


def interpret_search_candidate(
    candidate: Dict[str, Any],
    *,
    query: str = "",
    expected_container: str = "",
    expected_originator: str = "",
    role: str = "content",
) -> Dict[str, Any]:
    """Build structured interpretation; does not bind."""
    label = str(
        candidate.get("label") or candidate.get("text") or candidate.get("name") or ""
    ).strip()
    kind = str(candidate.get("kind") or "").strip().lower()
    sender = candidate.get("sender") or candidate.get("originator")
    gm_in = candidate.get("goal_match") if isinstance(candidate.get("goal_match"), dict) else None

    role_l = str(role or "content").strip().lower() or "content"
    contradictions: List[str] = []
    unknowns: List[str] = []
    gm = None
    echo = bool(query and _is_query_echo(label, query))
    url_tier, url_reason = _url_relevance_tier(label, query)
    origin = infer_message_originator(label, sender=sender, kind=kind)

    # Contact/source hunts: do not apply content-patient GoalMatch (that was
    # rejecting chat_rows that merely name the contact).
    if role_l == "source":
        contact = _norm(expected_container or expected_originator or "")
        lab = _norm(label)
        name_hit = bool(contact and contact in lab)
        groupish = any(
            t in lab for t in (" created this group", "added you", "group")
        )
        if groupish and name_hit:
            contradictions.append("group_shaped_for_person_role")
        relevance_tier = 3 if name_hit and not groupish else (1 if name_hit else 0)
        if candidate.get("matches_goal") and name_hit:
            relevance_tier = max(relevance_tier, 3)
        relation_tier = 2 if not origin else (3 if name_hit else 1)
        rank_key = (
            0 if echo else 1,
            relevance_tier,
            relation_tier,
            1 if name_hit and not groupish else 0,
            0,
        )
        return {
            "relevance": {
                "query_match": name_hit,
                "url_tier": 0,
                "url_reason": "source_contact_hunt",
                "object_type_fit": kind,
                "query_echo": echo,
                "matches_goal_recall": bool(candidate.get("matches_goal")),
            },
            "relation_evidence": {
                "originator": origin or "",
                "originator_match": None,
                "container": expected_container,
                "container_match": name_hit,
                "role": "source",
            },
            "contradictions": contradictions,
            "unknowns": unknowns,
            "exploration_value": {
                "can_more_evidence_be_acquired": True,
                "explorable": not echo and not groupish,
            },
            "commit_readiness": {
                "binding_eligible": bool(name_hit and not groupish),
                "advisory_only": True,
            },
            "rank_key": list(rank_key),
            "rank_reason": (
                f"source_hunt; name_hit={name_hit}; groupish={groupish}; echo={echo}"
            )[:240],
            "goal_match": gm_in,
        }

    if query:
        gm = evaluate_source_object_match(
            text=label,
            kind=kind or "message_bubble",
            query=query,
            container_open=expected_container,
            expected_container=expected_container,
            expected_originator=expected_originator or expected_container,
            sender=sender,
            perception_matches_goal=bool(candidate.get("matches_goal")),
            role=str(candidate.get("role") or ""),
        )

    if gm is not None:
        contradictions.extend(list(gm.contradictions or []))
    if expected_originator:
        want = _norm(expected_originator)
        if not origin:
            unknowns.append("sender_unknown")
        elif _norm(origin) in {"self", "you", "me"} and want not in {"self", "you", "me"}:
            contradictions.append("explicit_self_vs_required_sender")
        elif _norm(origin) != want and _norm(origin) not in {"self", "you", "me"}:
            if want and _norm(origin) and want not in _norm(origin) and _norm(origin) not in want:
                contradictions.append("originator_name_mismatch")
    elif not origin:
        unknowns.append("sender_unknown")

    if expected_container and gm is not None and not gm.container_match:
        if "container" not in " ".join(contradictions):
            contradictions.append("wrong_container")

    query_match = bool(gm.query_match) if gm is not None else bool(
        query and query_supported_by_text(label, query)
    )

    relevance = {
        "query_match": query_match,
        "url_tier": url_tier,
        "url_reason": url_reason,
        "object_type_fit": kind,
        "query_echo": echo,
        "matches_goal_recall": bool(candidate.get("matches_goal")),
    }
    relation_evidence = {
        "originator": origin or "",
        "originator_match": bool(gm.originator_match) if gm is not None else None,
        "container": expected_container,
        "container_match": bool(gm.container_match) if gm is not None else None,
        "role": str(candidate.get("role") or ""),
    }
    commit_readiness = {
        "binding_eligible": bool(gm.binding_eligible) if gm is not None else False,
        "advisory_only": True,
    }
    exploration_value = {
        "can_more_evidence_be_acquired": bool(
            "sender_unknown" in unknowns or url_tier >= 2
        ),
        "explorable": not echo,
    }

    if "explicit_self_vs_required_sender" in contradictions:
        relation_tier = 0
    elif relation_evidence.get("originator_match") is True:
        relation_tier = 3
    elif "sender_unknown" in unknowns or not origin:
        relation_tier = 2
    else:
        relation_tier = 1

    relevance_tier = 0
    if echo:
        relevance_tier = 0
    elif url_tier >= 3 and query_match:
        relevance_tier = 4
    elif url_tier == 2 and query_match:
        relevance_tier = 3
    elif query_match:
        relevance_tier = 2
    elif candidate.get("matches_goal"):
        relevance_tier = 1

    rank_key = (
        0 if echo else 1,
        relevance_tier,
        relation_tier,
        1 if commit_readiness["binding_eligible"] else 0,
        url_tier,
    )
    rank_reason = (
        f"echo={echo}; rel_tier={relevance_tier}; origin_tier={relation_tier}; "
        f"url={url_reason}; unknowns={unknowns[:2]}; contra={contradictions[:2]}"
    )

    return {
        "relevance": relevance,
        "relation_evidence": relation_evidence,
        "contradictions": contradictions,
        "unknowns": unknowns,
        "exploration_value": exploration_value,
        "commit_readiness": commit_readiness,
        "rank_key": list(rank_key),
        "rank_reason": rank_reason[:240],
        "goal_match": gm.to_dict() if gm is not None and hasattr(gm, "to_dict") else gm_in,
    }


def attach_interpretations(
    candidates: Sequence[Dict[str, Any]],
    *,
    query: str = "",
    expected_container: str = "",
    expected_originator: str = "",
    role: str = "content",
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for raw in candidates:
        if not isinstance(raw, dict):
            continue
        row = dict(raw)
        interp = interpret_search_candidate(
            row,
            query=query,
            expected_container=expected_container,
            expected_originator=expected_originator,
            role=role,
        )
        row["interpretation"] = interp
        if isinstance(interp.get("goal_match"), dict):
            row["goal_match"] = interp["goal_match"]
        out.append(row)
    return out


def rank_search_hypotheses(
    candidates: Sequence[Dict[str, Any]],
    *,
    query: str = "",
    expected_container: str = "",
    expected_originator: str = "",
    role: str = "content",
) -> List[Dict[str, Any]]:
    """Order candidates for exploration; echoes demoted when better fits exist."""
    rows = attach_interpretations(
        candidates,
        query=query,
        expected_container=expected_container,
        expected_originator=expected_originator,
        role=role,
    )
    if not rows:
        return []

    def _key(row: Dict[str, Any]) -> Tuple:
        interp = row.get("interpretation") or {}
        rk = interp.get("rank_key") or [0, 0, 0, 0, 0]
        # Negate for sort descending via positive tuple already "higher better"
        return tuple(int(x) for x in rk)

    ranked = sorted(rows, key=_key, reverse=True)
    has_non_echo = any(
        not bool((r.get("interpretation") or {}).get("relevance", {}).get("query_echo"))
        and _key(r)[1] > 0
        for r in ranked
    )
    out: List[Dict[str, Any]] = []
    for i, row in enumerate(ranked):
        interp = dict(row.get("interpretation") or {})
        interp["rank_position"] = i + 1
        echo = bool((interp.get("relevance") or {}).get("query_echo"))
        if has_non_echo and echo:
            interp["rejected_reason"] = "query_echo_while_better_fit_exists"
            row = dict(row)
            row["interpretation"] = interp
            # Drop echoes from explore set when better fits exist.
            continue
        row = dict(row)
        row["interpretation"] = interp
        row["_search_score"] = float(
            1000 * _key(row)[0]
            + 100 * _key(row)[1]
            + 10 * _key(row)[2]
            + _key(row)[3]
            + 0.1 * _key(row)[4]
        )
        out.append(row)
    return out or ranked[:8]


def hypothesis_ledger_entries(ranked: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Mandatory per-candidate SEARCH instrumentation rows."""
    entries: List[Dict[str, Any]] = []
    for row in ranked:
        if not isinstance(row, dict):
            continue
        interp = row.get("interpretation") or {}
        entries.append(
            {
                "candidate_id": row.get("id"),
                "label": str(row.get("label") or row.get("text") or "")[:120],
                "evidence_vector": {
                    "relevance": interp.get("relevance"),
                    "relation_evidence": interp.get("relation_evidence"),
                    "commit_readiness": interp.get("commit_readiness"),
                },
                "contradictions": list(interp.get("contradictions") or [])[:6],
                "unknowns": list(interp.get("unknowns") or [])[:6],
                "rank_key": list(interp.get("rank_key") or []),
                "rank_reason": str(interp.get("rank_reason") or "")[:240],
                "rank_position": interp.get("rank_position"),
                "selected_for_exploration": bool(interp.get("rank_position") == 1),
                "rejected_reason": str(interp.get("rejected_reason") or ""),
            }
        )
    return entries


def legacy_soft_rank_scores(
    candidates: Sequence[Dict[str, Any]],
    *,
    query: str = "",
    evidence_tokens: Optional[Sequence[str]] = None,
) -> List[Tuple[float, str]]:
    """Frozen comparison helper: old 4-feature arithmetic (for tests only)."""
    from plugin.agent.capabilities.revert_effects import (
        _text_matches_goal,
        content_target_fits_referents,
    )

    tokens = [_norm(t) for t in (evidence_tokens or []) if _norm(t)]
    scored: List[Tuple[float, str]] = []
    for row in candidates:
        if not isinstance(row, dict):
            continue
        label = str(row.get("label") or row.get("text") or "")
        blob = f"{label} {row.get('id') or ''}"
        score = 0.0
        if tokens:
            fits = content_target_fits_referents(
                target_label=label, object_blob=blob, goal_referents=tokens
            ) or _text_matches_goal(blob, tokens)
            if fits:
                score += 10.0
        if row.get("matches_goal"):
            score += 3.0
        low = _norm(label)
        if "http://" in low or "https://" in low or "www." in low or ".com" in low:
            score += 4.0
        if query and _is_query_echo(label, query):
            score -= 8.0
        scored.append((score, label[:80]))
    scored.sort(key=lambda x: -x[0])
    return scored
