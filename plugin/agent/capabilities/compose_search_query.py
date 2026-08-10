"""Author a search query from task evidence — judgment, not a template.

``type_query`` / ``locate_content`` *type* a string. This capability *authors*
that string from the goal bag, world document, and what prior searches showed.
It does not hardcode ``contact + link_query`` or any other fixed pattern; a
model call (or an injected author for tests) decides how to combine evidence.

    compose_search_query → type_query(chosen) → open_entity(result) …

Outcomes report candidate queries and the chosen one. They never claim a
result row is the right object — that stays with the next observation.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Sequence, runtime_checkable

from plugin.agent.capabilities.base import CapabilityOutcome, GroundedUiTarget

logger = logging.getLogger(__name__)

_COMPOSE_SYSTEM = (
    "You author search-box queries for a desktop agent. "
    "You receive an unordered bag of goal evidence tokens, a compact world "
    "document, and prior search attempts with what the UI showed. "
    "Return ONLY JSON of the form "
    '{"queries":[{"q":"...","why":"..."}],"chosen":"..."}. '
    "Compose queries that would narrow the surface toward the goal. "
    "Ground every word in evidence_tokens (or a clear shortening of one). "
    "Do not invent extra words that are not content evidence — host search "
    "often AND-matches every token, so invented words can hide real hits. "
    "Use whatever combination of evidence you judge useful — including a "
    "single token, several tokens, token order swaps, shorter subsets, or "
    "a spelling variant. "
    "When several distinct evidence tokens are available and the surface is "
    "a crowded list of similarly named rows, prefer a query that combines "
    "more than one token so results disambiguate. "
    "When a prior query has outcome no_results / empty / failed, or results "
    "look like a poor fit for the goal criteria, you MUST choose a different "
    "string — simplify, drop a token, try another token, or change order. "
    "Do not repeat a dead query. "
    "Do not include the host application name as a search token. "
    "Do not merely echo one entity name when other evidence would "
    "disambiguate. Be persistent and willing to iterate. "
    "Never invent click scripts; only the search string."
)


@runtime_checkable
class QueryAuthor(Protocol):
    """Produces candidate search strings from a prompt packet."""

    def author(self, system: str, user_packet: Dict[str, Any]) -> Dict[str, Any]:
        """Return ``{"queries":[{"q","why"}], "chosen": str}``."""


@dataclass
class SearchQueryBrief:
    """Evidence bag for query authorship plus the search-field GroundedUiTarget.

    Authorship is judgment over task evidence. Actuation still inherits the
    GroundedUiTarget contract: the Search field's point/bounds must be bound
    before the actor types the chosen string.
    """

    goal_tokens: List[str] = field(default_factory=list)
    goal_kind: str = ""
    goal_description: str = ""
    world_document: Dict[str, Any] = field(default_factory=dict)
    prior_queries: List[Dict[str, Any]] = field(default_factory=list)
    visible_result_labels: List[str] = field(default_factory=list)
    notes: str = ""
    field: Optional[GroundedUiTarget] = None


def goal_evidence_tokens(goal: Any) -> List[str]:
    """Unordered evidence tokens extracted from a Goal — never a template."""
    tokens: List[str] = []
    seen = set()

    def add(value: Any) -> None:
        text = " ".join(str(value or "").strip().split())
        if not text:
            return
        low = text.lower()
        if low in seen:
            return
        seen.add(low)
        tokens.append(text)

    for attr in ("contact", "target_contact", "link_query", "description", "prompt"):
        add(getattr(goal, attr, None))
    # Evidence only — do not invent intent labels beyond goal fields.
    # Authorship / SEARCH refine must decide composition; the bag is not a script.
    try:
        for hyp in list(getattr(goal, "intent_hypotheses", lambda: [])() or []):
            add(hyp)
    except Exception:
        pass
    return tokens


def brief_from_context(
    goal: Any,
    *,
    world_document: Optional[Dict[str, Any]] = None,
    features: Any = None,
    prior_queries: Optional[Sequence[Dict[str, Any]]] = None,
) -> SearchQueryBrief:
    extras = {}
    if features is not None and isinstance(getattr(features, "extras", None), dict):
        extras = features.extras
    labels = []
    for key in ("visible_contacts", "search_result_rows", "contact_candidates"):
        raw = extras.get(key) or []
        if isinstance(raw, list):
            for item in raw[:12]:
                if isinstance(item, dict):
                    labels.append(str(item.get("text") or item.get("name") or "")[:80])
                else:
                    labels.append(str(item)[:80])
    priors = list(prior_queries or [])
    if not priors:
        hint = str(extras.get("search_query_hint") or extras.get("search_query") or "").strip()
        if hint:
            outcome = "no_results" if extras.get("search_empty") else "already_in_field"
            priors.append({"q": hint, "outcome": outcome})
    elif extras.get("search_empty"):
        # Promote the active field query to a failed prior so authorship iterates.
        hint = str(extras.get("search_query") or extras.get("search_query_hint") or "").strip()
        if hint and not any(
            isinstance(a, dict) and str(a.get("q") or "").strip().lower() == hint.lower()
            for a in priors
        ):
            priors.append({"q": hint, "outcome": "no_results"})
    doc = world_document if isinstance(world_document, dict) else {}
    return SearchQueryBrief(
        goal_tokens=goal_evidence_tokens(goal),
        goal_kind=str(getattr(goal, "kind", "") or ""),
        goal_description=str(getattr(goal, "description", "") or ""),
        world_document={
            "surface": doc.get("surface"),
            "open_conversation": doc.get("open_conversation"),
            "progress": doc.get("progress"),
            "exhausted": doc.get("exhausted"),
            "attempts": (doc.get("attempts") or [])[-6:],
            "search_empty": bool(extras.get("search_empty") or doc.get("search_empty")),
        },
        prior_queries=priors,
        visible_result_labels=[x for x in labels if x],
        notes=str(extras.get("scene_summary") or ""),
    )


def _parse_author_payload(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        payload = raw
    else:
        text = str(raw or "").strip()
        if not text:
            return {}
        try:
            payload = json.loads(text)
        except Exception:
            match = re.search(r"\{.*\}", text, flags=re.DOTALL)
            if not match:
                return {}
            try:
                payload = json.loads(match.group(0))
            except Exception:
                return {}
    if not isinstance(payload, dict):
        return {}
    queries = []
    for item in payload.get("queries") or []:
        if isinstance(item, str) and item.strip():
            queries.append({"q": item.strip(), "why": ""})
        elif isinstance(item, dict):
            q = str(item.get("q") or item.get("query") or "").strip()
            if q:
                queries.append({"q": q, "why": str(item.get("why") or "")[:200]})
    def _usable(q: str) -> bool:
        text = " ".join((q or "").strip().split())
        if len(text) < 2:
            return False
        # Reject digit-only / punctuation-only noise from weak model outputs.
        if all(not ch.isalnum() or ch.isdigit() for ch in text) and not any(
            ch.isalpha() for ch in text
        ):
            return False
        return True

    queries = [item for item in queries if _usable(item["q"])]
    chosen = str(payload.get("chosen") or "").strip()
    if chosen and not _usable(chosen):
        chosen = ""
    if not chosen and queries:
        chosen = queries[0]["q"]
    return {"queries": queries, "chosen": chosen}


@dataclass
class LlmQueryAuthor:
    """Default realization: one short *text* LLM call (never the vision pin)."""

    # Keep well below vision SoT hangs; deterministic fallback still authors.
    timeout_s: float = 45.0

    def author(self, system: str, user_packet: Dict[str, Any]) -> Dict[str, Any]:
        from plugin.agent.perception_synthesis import _call_llm_hard_timeout
        from plugin.agent.reasoning_consultation import consult_reasoning

        messages = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": (
                    "Author the next search-box query.\n"
                    + json.dumps(user_packet, ensure_ascii=False, default=str)[:6000]
                ),
            },
        ]
        try:
            consultation = consult_reasoning(
                "decision",
                messages,
                usecase="compose_search_query",
                caller=lambda **kwargs: _call_llm_hard_timeout(self.timeout_s, **kwargs),
                call_kwargs={
                    "timeout": self.timeout_s,
                },
                temperature=0.2,
                max_tokens=256,
            )
        except Exception as exc:
            logger.warning("compose_search_query LLM failed: %s", exc)
            return {}
        parsed = getattr(consultation, "parsed", None) or {}
        if isinstance(parsed, dict) and (parsed.get("chosen") or parsed.get("queries")):
            return _parse_author_payload(parsed)
        return _parse_author_payload(getattr(consultation, "raw_response", "") or "")


def is_bare_entity_query(text: str, goal: Any) -> bool:
    """True when ``text`` is only a single known entity name from the goal."""
    q = " ".join((text or "").strip().lower().split())
    if not q:
        return True
    singles = {
        str(getattr(goal, attr, "") or "").strip().lower()
        for attr in ("contact", "target_contact")
        if str(getattr(goal, attr, "") or "").strip()
    }
    return q in singles


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            ins, delete, sub = cur[j - 1] + 1, prev[j] + 1, prev[j - 1] + (ca != cb)
            cur.append(min(ins, delete, sub))
        prev = cur
    return prev[-1]


def query_looks_corrupted(observed: str, evidence_tokens: Sequence[str]) -> bool:
    """True when the search-field string is a near-miss garble of goal evidence.

    Live 202832: typed ``zarooratwala Pallavi``, field drifted to
    ``zaropratwala Pallavipo`` / No results. Exact token match fails, but a
    word is within edit distance 2 of a goal token — treat as corrupted so
    compose clears and retries a fresh string.
    """
    raw = " ".join((observed or "").strip().split())
    if not raw:
        return False
    # Strip common Electron search mirrors ("a …", "Q …").
    low = raw.lower()
    for prefix in ("a ", "q ", "• "):
        if low.startswith(prefix):
            raw = raw[len(prefix) :].strip()
            low = raw.lower()
            break
    words = [w for w in re.split(r"[^\w]+", low) if len(w) >= 4]
    if not words:
        return False
    tokens = [
        " ".join(str(t or "").strip().lower().split())
        for t in evidence_tokens
        if str(t or "").strip() and 3 <= len(str(t).strip()) <= 48
    ]
    token_words: List[str] = []
    for t in tokens:
        token_words.extend([w for w in re.split(r"[^\w]+", t) if len(w) >= 4])
    if not token_words:
        return False
    for tw in set(token_words):
        exact = any(w == tw for w in words)
        near = any(
            w != tw and abs(len(w) - len(tw)) <= 2 and _levenshtein(w, tw) <= 2
            for w in words
        )
        if near and not exact:
            return True
    return False


def ui_shows_no_search_results(*labels: Any) -> bool:
    """Detect WhatsApp empty-hit chrome from labels / open conversation."""
    for item in labels:
        text = " ".join(str(item or "").strip().lower().split())
        if not text:
            continue
        if "no results" in text or text == "no result":
            return True
    return False


def _failed_prior_queries(priors: Sequence[Dict[str, Any]]) -> set[str]:
    failed: set[str] = set()
    for item in priors or []:
        if not isinstance(item, dict):
            continue
        outcome = str(item.get("outcome") or "").strip().lower()
        if any(
            token in outcome
            for token in ("no_results", "empty", "failed", "compose_failed", "type_failed")
        ):
            q = str(item.get("q") or "").strip().lower()
            if q:
                failed.add(q)
                stripped = _strip_host_app_tokens(q).lower()
                if stripped:
                    failed.add(stripped)
    return failed


# Host app names are not searchable content — strip them from authored strings.
_HOST_APP_TOKENS = frozenset(
    {
        "whatsapp",
        "telegram",
        "slack",
        "messages",
        "imessage",
        "discord",
        "signal",
        "mail",
        "outlook",
        "gmail",
        "finder",
        "safari",
        "chrome",
        # Dialog / chrome labels must never become search strings.
        "cancel",
        "close",
        "dismiss",
        "ok",
        "done",
        "back",
        "delete",
        "send",
        "forward",
    }
)


def _strip_host_app_tokens(query: str) -> str:
    parts = [p for p in (query or "").split() if p.lower() not in _HOST_APP_TOKENS]
    return " ".join(parts).strip()


def _iterative_fallback_query(
    tokens: Sequence[str],
    failed: set[str],
) -> str:
    """Playful last-resort authorship when the model repeats dead queries.

    Tries unused evidence tokens and short combinations — never a fixed
    contact+link template, and never a prior that already returned no results.
    """
    clean = [
        " ".join(str(t or "").split())
        for t in tokens
        if str(t or "").strip() and str(t).strip().lower() not in _HOST_APP_TOKENS
    ]
    # Prefer shorter, more distinctive tokens first (avoid long goal sentences).
    ranked = sorted(
        {t for t in clean if 2 <= len(t) <= 48},
        key=lambda t: (len(t.split()) > 3, len(t)),
    )
    candidates: List[str] = []
    for t in ranked:
        candidates.append(t)
    for i, a in enumerate(ranked):
        for b in ranked[i + 1 :]:
            candidates.append(f"{a} {b}")
            candidates.append(f"{b} {a}")
    for cand in candidates:
        low = cand.lower()
        if low not in failed and _strip_host_app_tokens(cand):
            return _strip_host_app_tokens(cand)
    return ""


def compose_search_query(
    brief: SearchQueryBrief,
    author: Optional[QueryAuthor] = None,
) -> CapabilityOutcome:
    """Author search queries from task evidence. Does not type into the UI."""
    author = author or LlmQueryAuthor()
    packet = {
        "goal_kind": brief.goal_kind,
        "goal_description": brief.goal_description,
        "evidence_tokens": brief.goal_tokens,
        "world": brief.world_document,
        "prior_queries": brief.prior_queries,
        "visible_result_labels": brief.visible_result_labels[:16],
        "notes": brief.notes,
        "search_empty": bool(
            (brief.world_document or {}).get("search_empty")
            or "no_results" in str(brief.notes or "").lower()
            or not brief.visible_result_labels
            and bool(brief.prior_queries)
        ),
        "instruction": (
            "If prior_queries include no_results, pick a *different* string. "
            "Iterate: simplify, drop a token, swap order, or try another evidence token."
        ),
    }
    try:
        payload = author.author(_COMPOSE_SYSTEM, packet) or {}
    except Exception as exc:
        logger.warning("compose_search_query author failed: %s", exc)
        payload = {}

    parsed = _parse_author_payload(payload) if not payload.get("chosen") else payload
    if not parsed.get("chosen") and not parsed.get("queries"):
        parsed = _parse_author_payload(payload)

    chosen = _strip_host_app_tokens(str(parsed.get("chosen") or "").strip())
    queries = list(parsed.get("queries") or [])
    for item in queries:
        if isinstance(item, dict) and item.get("q"):
            item["q"] = _strip_host_app_tokens(str(item["q"]))
    failed = _failed_prior_queries(brief.prior_queries)
    # Refuse to re-emit a query that already returned no results.
    if chosen.lower() in failed:
        for item in queries:
            alt = _strip_host_app_tokens(str(item.get("q") or "").strip())
            if alt and alt.lower() not in failed:
                chosen = alt
                break
        else:
            chosen = ""
    if not chosen:
        chosen = _iterative_fallback_query(brief.goal_tokens, failed)
    if not chosen:
        return CapabilityOutcome(
            ok=False,
            capability="compose_search_query",
            realization="llm_author",
            message="compose_search_query produced no fresh query",
            evidence={
                "substrate": "task_evidence",
                "evidence_tokens": brief.goal_tokens,
                "queries": queries,
                "failed_priors": sorted(failed),
            },
        )

    return CapabilityOutcome(
        ok=True,
        capability="compose_search_query",
        realization="llm_author",
        message=f"authored search query {chosen!r}",
        evidence={
            "substrate": "task_evidence",
            "chosen": chosen,
            "queries": queries,
            "evidence_tokens": brief.goal_tokens,
            "failed_priors": sorted(failed),
        },
    )


def author_query_for_goal(
    goal: Any,
    *,
    world_document: Optional[Dict[str, Any]] = None,
    features: Any = None,
    author: Optional[QueryAuthor] = None,
) -> str:
    """Convenience for remaps: return chosen query or \"\" on failure."""
    outcome = compose_search_query(
        brief_from_context(goal, world_document=world_document, features=features),
        author=author,
    )
    if not outcome.ok:
        return ""
    return str(outcome.evidence.get("chosen") or "").strip()
