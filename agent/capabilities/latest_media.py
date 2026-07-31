"""ResolveLatestMediaCapability — recency-aware media link resolution."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime
from calendar import month_name
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from agent.capabilities.base import (
    Capability,
    CapabilityContext,
    CapabilityResult,
    SelectedMetadataSpec,
)
from agent.url_resolution import (
    UrlResolutionIntent,
    build_canonical_search_queries,
    preferred_handle_candidates,
    url_matches_pattern,
)

logger = logging.getLogger(__name__)

SearchFn = Callable[[str, int], str]
_STOPWORDS = {"the", "a", "an", "of", "for", "to", "in", "on", "from"}
_BAD_SOCIAL_HANDLES = {"the", "may", "july", "august", "today", "yesterday", "tracker", "market"}

_LATEST_RE = re.compile(r"\b(latest|most recent|newest|recent|current|today(?:'s)?)\b", re.I)
_MEDIA_RE = re.compile(r"\b(youtube|podcast|interview|episode|video|link|tweet|tweets|post|thread|x|twitter)\b", re.I)
_ENTITY_RE = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\b")
_ABS_DATE_PATTERNS: Tuple[Tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(\d{1,2}\s+[A-Za-z]+\s+\d{4})\b"), "%d %B %Y"),
    (re.compile(r"\b([A-Za-z]{3}\s+\d{1,2},\s+\d{4})\b"), "%b %d, %Y"),
    (re.compile(r"\b([A-Za-z]+\s+\d{1,2},\s+\d{4})\b"), "%B %d, %Y"),
    (re.compile(r"\b(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})\b"), "%d %b %Y"),
)
_VIEWS_RE = re.compile(r"\b([\d.,]+(?:\s*[KMB])?)\s+views\b", re.I)
_CHANNEL_RE = re.compile(r"\bby\s+([A-Za-z0-9@][A-Za-z0-9@ .&'_-]{1,80})")
_SOCIAL_AUTHOR_RE = re.compile(r"\b(?:by|from)\s+(@?[A-Za-z0-9_]+)\b")


@dataclass
class MediaCandidate:
    title: str
    url: str
    description: str
    position: int
    query: str
    published_at: Optional[date]
    views: Optional[str]
    channel: Optional[str]
    author: Optional[str]
    caption: str
    confidence: float
    reason: str
    stage: str = "discovery"


def is_latest_media_intent(message: str) -> bool:
    text = (message or "").strip()
    if not text:
        return False
    return bool(_LATEST_RE.search(text) and _MEDIA_RE.search(text))


def _extract_entity_terms(objective: str) -> List[str]:
    lower = (objective or "").strip().lower()
    # Simple name extraction for known "of X" / trailing subject shapes.
    if " of " in lower:
        tail = lower.split(" of ", 1)[1]
    else:
        tail = lower
    tail = re.sub(
        r"\b(latest|most recent|newest|recent|current|today|podcast|youtube|link|episode|video|tweet|tweets|post|thread|x|twitter|find|share|by)\b",
        " ",
        tail,
        flags=re.I,
    )
    words = [
        w
        for w in re.findall(r"[a-z0-9]+", tail)
        if len(w) >= 2 and w not in _STOPWORDS
    ]
    deduped: List[str] = []
    seen = set()
    for word in words:
        if word not in seen:
            seen.add(word)
            deduped.append(word)
    return deduped[:4]


def _is_social_request(objective: str) -> bool:
    return bool(re.search(r"\b(tweet|tweets|post|thread|x|twitter)\b", objective or "", re.I))


def _social_handle_guesses(entity_terms: Sequence[str]) -> List[str]:
    return preferred_handle_candidates(entity_terms)[:2]


def _handle_mentions(text: str) -> List[str]:
    seen: List[str] = []
    for match in re.findall(r"@([A-Za-z0-9_]+)\b", text or ""):
        lowered = match.lower()
        if lowered not in seen:
            seen.append(lowered)
    return seen


def _caption_search_fragment(text: str, *, max_words: int = 6) -> str:
    words = [
        w
        for w in re.findall(r"[A-Za-z0-9']+", text or "")
        if len(w) >= 3 and w.lower() not in _STOPWORDS
    ]
    if not words:
        return ""
    return " ".join(words[:max_words])


def _build_queries(objective: str) -> List[Tuple[str, str]]:
    entities = _extract_entity_terms(objective)
    entity_phrase = " ".join(entities).strip() or objective.strip()
    current_year = date.today().year
    current_month = month_name[date.today().month]
    if _is_social_request(objective):
        handle_guesses = _social_handle_guesses(entities)
        discovery_queries = [
            f"{entity_phrase} latest tweet x",
            f"{entity_phrase} latest post twitter {current_year}",
            f"{entity_phrase} x posts {current_month} {current_year}",
            f"{entity_phrase} tweets last 7 days",
            f"{entity_phrase} archive x posts {current_year}",
        ]
        verification_queries = build_canonical_search_queries(
            UrlResolutionIntent(
                source="x",
                content_kind="status",
                entity_terms=tuple(entities),
                known_year=current_year,
            )
        )
        for handle in handle_guesses:
            verification_queries.extend(
                build_canonical_search_queries(
                    UrlResolutionIntent(
                        source="x",
                        content_kind="status",
                        entity_terms=tuple(entities),
                        known_handle=handle,
                        known_year=current_year,
                        known_date_text=f"{current_month} {current_year}",
                    )
                )
            )
        queries = [("discovery", q) for q in discovery_queries] + [
            ("verification", q) for q in verification_queries
        ]
    else:
        queries = [
            ("discovery", f"{entity_phrase} latest podcast youtube"),
            ("discovery", f"{entity_phrase} podcast {current_year}"),
            ("discovery", f"{entity_phrase} the ranveer show podcast {current_year}"),
            (
                "verification",
                build_canonical_search_queries(
                    UrlResolutionIntent(
                        source="youtube",
                        content_kind="video",
                        entity_terms=tuple((*entities, "podcast")),
                    )
                )[0],
            ),
        ]
    out: List[Tuple[str, str]] = []
    seen = set()
    for stage, query in queries:
        query = re.sub(r"\s+", " ", query).strip()
        if query and query not in seen:
            seen.add(query)
            out.append((stage, query))
    return out


def _build_social_resolution_queries(
    candidate: MediaCandidate,
    *,
    entity_terms: Sequence[str],
) -> List[Tuple[str, str]]:
    if candidate.published_at is None:
        return []

    expected_handles = [h.lower() for h in _social_handle_guesses(entity_terms)]
    text_handles = _handle_mentions(" ".join((candidate.title, candidate.description, candidate.caption)))

    handle = ""
    if expected_handles:
        handle = expected_handles[0]
    for expected in expected_handles:
        if expected in text_handles:
            handle = expected
            break
    if not handle:
        author = (candidate.author or "").lstrip("@").strip().lower()
        if author and author not in _BAD_SOCIAL_HANDLES:
            handle = author
    if not handle:
        return []

    month = month_name[candidate.published_at.month]
    year = candidate.published_at.year
    day = candidate.published_at.day
    phrase = _caption_search_fragment(candidate.caption or candidate.title)
    queries = build_canonical_search_queries(
        UrlResolutionIntent(
            source="x",
            content_kind="status",
            entity_terms=tuple(entity_terms),
            known_handle=handle,
            known_year=year,
            known_date_text=f"{month} {day}, {year}",
            known_phrase=phrase or None,
        )
    )
    return [("resolution", query) for query in queries]


def _parse_abs_date(text: str) -> Optional[date]:
    blob = (text or "").strip()
    for pattern, fmt in _ABS_DATE_PATTERNS:
        match = pattern.search(blob)
        if not match:
            continue
        candidate = match.group(1)
        try:
            return datetime.strptime(candidate, fmt).date()
        except ValueError:
            continue
    return None


def _extract_views(text: str) -> Optional[str]:
    match = _VIEWS_RE.search(text or "")
    if not match:
        return None
    return re.sub(r"\s+", "", match.group(1)) + " views"


def _extract_channel(title: str, description: str, url: str = "") -> Optional[str]:
    if re.search(r"(?:x\.com|twitter\.com)/", url or "", re.I):
        return None
    text = f"{title} {description}".strip()
    match = _CHANNEL_RE.search(text)
    if match:
        return match.group(1).strip(" .,-")
    return None


def _extract_author(title: str, description: str, url: str) -> Optional[str]:
    text = f"{title} {description}".strip()
    match = _SOCIAL_AUTHOR_RE.search(text)
    if match:
        author = match.group(1).strip(" .,-")
        if author.lstrip("@").lower() not in _BAD_SOCIAL_HANDLES:
            return author
    handle_match = re.search(r"(?:x\.com|twitter\.com)/([A-Za-z0-9_]+)", url or "", re.I)
    if handle_match:
        return "@" + handle_match.group(1)
    return None


def _build_caption(description: str, title: str, *, max_len: int = 220) -> str:
    text = re.sub(r"\s+", " ", (description or "").strip())
    if not text:
        text = re.sub(r"\s+", " ", (title or "").strip())
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"


def _is_social_primary_candidate(url: str) -> bool:
    return url_matches_pattern(url, "x", "status")


def _is_stale_latest_social_candidate(published_at: Optional[date], *, max_age_days: int = 90) -> bool:
    if published_at is None:
        return False
    return (date.today() - published_at).days > max_age_days


def _is_social_tracker_candidate(title: str, url: str, description: str) -> bool:
    blob = " ".join((title or "", url or "", description or "")).lower()
    tracker_markers = (
        "polymarket",
        "bitget",
        "prediction",
        "predictions",
        "live odds",
        "trading odds",
        "market context",
        "# tweets",
        "tweet range",
        "number of times",
        "posts on x during the month",
    )
    return any(marker in blob for marker in tracker_markers)


def _score_candidate(title: str, url: str, description: str, *, entity_terms: Sequence[str]) -> Tuple[float, str, Optional[date]]:
    url_l = (url or "").lower()
    title_l = (title or "").lower()
    desc_l = (description or "").lower()
    published = _parse_abs_date(description) or _parse_abs_date(title)

    score = 0.0
    reasons: List[str] = []
    expected_handles = {h.lower() for h in _social_handle_guesses(entity_terms)}
    mentioned_handles = set(_handle_mentions(f"{title} {description} {url}"))

    if url_matches_pattern(url, "youtube", "video"):
        score += 20
        reasons.append("watch page")
    if url_matches_pattern(url, "x", "status"):
        score += 24
        reasons.append("status page")
    if "podcasts.apple.com" in url_l or "podcastrepublic" in url_l or "listennotes" in url_l or "ivy.fm" in url_l:
        score += 22
        reasons.append("podcast episode page")
    if "youtube.com/playlist" in url_l or "music.youtube.com/podcast" in url_l:
        score -= 25
        reasons.append("playlist-like result")
    if "x.com/" in url_l or "twitter.com/" in url_l:
        score += 8
        reasons.append("social primary source")
    if "instagram.com" in url_l or "facebook.com" in url_l:
        score -= 8
        reasons.append("social repost")
    if _is_social_tracker_candidate(title, url, description):
        score -= 45
        reasons.append("tracker/prediction page")

    if any(term in title_l or term in desc_l for term in ("podcast", "trs", "interview", "episode", "tweet", "thread", "post")):
        score += 10
        reasons.append("media title match")
    if entity_terms and sum(1 for t in entity_terms if t in title_l or t in desc_l) >= max(1, min(2, len(entity_terms))):
        score += 12
        reasons.append("entity match")
    if expected_handles and expected_handles.intersection(mentioned_handles):
        score += 18
        reasons.append("target handle match")
    elif mentioned_handles and expected_handles and not expected_handles.intersection(mentioned_handles):
        score -= 18
        reasons.append("non-target handle mention")

    if published is not None:
        age_days = max(0, (date.today() - published).days)
        score += max(0.0, 40.0 - min(40.0, age_days / 30.0))
        reasons.append(f"published {published.isoformat()}")

    return score, ", ".join(reasons) or "ranked by query match", published


def _candidate_payload(candidate: MediaCandidate) -> Dict[str, Any]:
    return {
        "title": candidate.title,
        "url": candidate.url,
        "published_at": candidate.published_at.isoformat() if candidate.published_at else None,
        "views": candidate.views,
        "channel": candidate.channel,
        "author": candidate.author,
        "caption": candidate.caption,
        "confidence": round(candidate.confidence, 3),
        "reason": candidate.reason,
        "query": candidate.query,
        "stage": candidate.stage,
    }


def _extract_results(payload: str) -> List[Dict[str, Any]]:
    try:
        data = json.loads(payload or "{}")
    except Exception:
        return []
    return list(((data.get("data") or {}).get("web") or []))


def _rank_candidates(candidates: Sequence[MediaCandidate]) -> List[MediaCandidate]:
    deduped: Dict[str, MediaCandidate] = {}
    for candidate in candidates:
        existing = deduped.get(candidate.url)
        if existing is None or candidate.confidence > existing.confidence:
            deduped[candidate.url] = candidate

    return sorted(
        deduped.values(),
        key=lambda c: (
            not _is_social_tracker_candidate(c.title, c.url, c.description),
            c.published_at or date.min,
            c.confidence,
            c.stage == "resolution",
            c.stage == "verification",
            -c.position if c.position else 0,
        ),
        reverse=True,
    )


class ResolveLatestMediaCapability(Capability):
    name = "latest_media"
    description = (
        "Resolve a latest/newest/current media link request by issuing multiple "
        "web searches, preferring dated episode/watch pages over playlists and "
        "channel hubs, and comparing candidates by publication date."
    )
    required_tools = ["web_search"]
    selected_metadata_spec = SelectedMetadataSpec(
        required_fields=("url", "title"),
        strongly_expected_fields=("published_at",),
        optional_fields=("views", "channel", "author", "caption", "query"),
        at_least_one_of=(("channel", "author", "caption"),),
        missing_field_policy="report",
    )

    def execute(self, ctx: CapabilityContext) -> CapabilityResult:
        objective = (ctx.objective or "").strip()
        if not objective:
            return CapabilityResult(
                status="failed",
                capability=self.name,
                message="objective is required",
            )

        search_fn: Optional[SearchFn] = ctx.extras.get("search_fn")
        if search_fn is None:
            from tools.web_tools import web_search_tool

            search_fn = lambda query, limit=5: web_search_tool(query, limit=limit)

        queries = _build_queries(objective)
        entity_terms = _extract_entity_terms(objective)
        attempts: List[Dict[str, Any]] = []
        candidates: List[MediaCandidate] = []

        max_queries = 7 if _is_social_request(objective) else 4
        for stage, query in queries[:max_queries]:
            attempts.append({"action": "web_search", "query": query, "stage": stage})
            raw = search_fn(query, 5)
            for item in _extract_results(raw):
                title = str(item.get("title") or "")
                url = str(item.get("url") or "")
                description = str(item.get("description") or "")
                score, reason, published = _score_candidate(
                    title,
                    url,
                    description,
                    entity_terms=entity_terms,
                )
                candidates.append(
                    MediaCandidate(
                        title=title,
                        url=url,
                        description=description,
                        position=int(item.get("position") or 0),
                        query=query,
                        published_at=published,
                        views=_extract_views(description),
                        channel=_extract_channel(title, description, url),
                        author=_extract_author(title, description, url),
                        caption=_build_caption(description, title),
                        confidence=score,
                        reason=reason,
                        stage=stage,
                    )
                )
        ranked = _rank_candidates(candidates)

        if _is_social_request(objective):
            best_discovered_any = ranked[0] if ranked else None
            if (
                best_discovered_any is not None
                and best_discovered_any.stage == "discovery"
                and not _is_social_tracker_candidate(
                    best_discovered_any.title,
                    best_discovered_any.url,
                    best_discovered_any.description,
                )
            ):
                resolution_queries = _build_social_resolution_queries(
                    best_discovered_any,
                    entity_terms=entity_terms,
                )
                for stage, query in resolution_queries[:3]:
                    attempts.append({"action": "web_search", "query": query, "stage": stage})
                    raw = search_fn(query, 5)
                    for item in _extract_results(raw):
                        title = str(item.get("title") or "")
                        url = str(item.get("url") or "")
                        description = str(item.get("description") or "")
                        score, reason, published = _score_candidate(
                            title,
                            url,
                            description,
                            entity_terms=entity_terms,
                        )
                        if _is_social_primary_candidate(url):
                            score += 18
                            reason = (reason + ", resolution match").strip(", ")
                        candidates.append(
                            MediaCandidate(
                                title=title,
                                url=url,
                                description=description,
                                position=int(item.get("position") or 0),
                                query=query,
                                published_at=published,
                                views=_extract_views(description),
                                channel=_extract_channel(title, description, url),
                                author=_extract_author(title, description, url),
                                caption=_build_caption(description, title),
                                confidence=score,
                                reason=reason,
                                stage=stage,
                            )
                        )
                ranked = _rank_candidates(candidates)

            ranked_social = [c for c in ranked if _is_social_primary_candidate(c.url)]
            best_discovered = ranked[0] if ranked else None
            best_verified = ranked_social[0] if ranked_social else None
            if not best_verified:
                evidence = [_candidate_payload(c) for c in ranked[:5]]
                return CapabilityResult(
                    status="partial",
                    capability=self.name,
                    output={
                        "query": objective,
                        "selected": evidence[0] if evidence else None,
                        "candidates": evidence,
                    },
                    confidence=0.35 if evidence else 0.0,
                    evidence=evidence,
                    attempts=attempts,
                    message="Could not validate a direct X/Twitter status URL for this latest social-post request.",
                    unresolved_questions=[
                        "No direct X/Twitter status page was found to verify the latest post."
                    ],
                )
            if (
                best_discovered is not None
                and best_verified is not None
                and best_discovered.url != best_verified.url
                and (best_discovered.published_at or date.min) > (best_verified.published_at or date.min)
            ):
                evidence = [_candidate_payload(c) for c in ranked[:5]]
                return CapabilityResult(
                    status="partial",
                    capability=self.name,
                    output={
                        "query": objective,
                        "selected": evidence[0],
                        "candidates": evidence,
                    },
                    confidence=0.5,
                    evidence=evidence,
                    attempts=attempts,
                    message=(
                        "Found a newer social-post candidate, but it has not yet been "
                        "verified to a direct X/Twitter status URL."
                    ),
                    unresolved_questions=[
                        "Need a direct X/Twitter status page for the newest discovered candidate."
                    ],
                )
            ranked = ranked_social

        if not ranked:
            return CapabilityResult(
                status="failed",
                capability=self.name,
                message="No media candidates found.",
                attempts=attempts,
                unresolved_questions=["No search results were available to validate recency."],
            )

        top = ranked[0]
        evidence = [
            _candidate_payload(c)
            for c in ranked[:5]
        ]
        if _is_social_request(objective) and _is_stale_latest_social_candidate(top.published_at):
            output = {
                "query": objective,
                "selected": evidence[0],
                "candidates": evidence,
            }
            stale_date = top.published_at.isoformat() if top.published_at else "unknown date"
            return CapabilityResult(
                status="partial",
                capability=self.name,
                output=output,
                confidence=0.45,
                evidence=evidence,
                attempts=attempts,
                artifacts=[top.url],
                message=(
                    "Found a direct X/Twitter status URL, but its publication date "
                    f"({stale_date}) is too old to trust as the latest post."
                ),
                unresolved_questions=[
                    "Need a more recent direct X/Twitter status page to verify the latest post."
                ],
            )
        output = {
            "query": objective,
            "selected": evidence[0],
            "candidates": evidence,
        }
        message = (
            f"Selected dated media result: {top.title}"
            + (f" ({top.published_at.isoformat()})" if top.published_at else "")
        )
        return CapabilityResult(
            status="success",
            capability=self.name,
            output=output,
            confidence=min(0.99, 0.55 + min(top.confidence / 100.0, 0.4)),
            evidence=evidence,
            attempts=attempts,
            artifacts=[top.url],
            message=message,
        )

    def to_tool_payload(self, result: CapabilityResult) -> Dict[str, Any]:
        output = result.output if isinstance(result.output, dict) else {}
        return {
            "success": result.status == "success",
            "capability": self.name,
            "status": result.status,
            "query": output.get("query"),
            "selected": output.get("selected"),
            "candidates": output.get("candidates") or [],
            "artifacts": list(result.artifacts),
            "confidence": round(result.confidence, 3),
            "message": result.message,
            "evidence": list(result.evidence),
            "attempts": list(result.attempts),
            "unresolved_questions": list(result.unresolved_questions),
        }
