"""Core canonical URL pattern knowledge and query helpers.

This module centralizes source/content URL shapes so capabilities can reason
about canonical content pages (for example an X status or a YouTube watch
page) instead of duplicating ad hoc URL regexes in each leaf capability.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import parse_qs, urlparse


@dataclass(frozen=True)
class CanonicalUrlPattern:
    source: str
    content_kind: str
    hostnames: Tuple[str, ...]
    path_regexes: Tuple[str, ...] = ()
    required_query_keys: Tuple[str, ...] = ()
    query_templates: Tuple[str, ...] = ()


@dataclass(frozen=True)
class UrlResolutionIntent:
    source: str
    content_kind: str
    entity_terms: Tuple[str, ...] = ()
    known_handle: Optional[str] = None
    known_date_text: Optional[str] = None
    known_year: Optional[int] = None
    known_phrase: Optional[str] = None


_PATTERNS: Tuple[CanonicalUrlPattern, ...] = (
    CanonicalUrlPattern(
        source="x",
        content_kind="status",
        hostnames=("x.com", "twitter.com"),
        path_regexes=(r"^/[A-Za-z0-9_]+/status/\d+/?$",),
        query_templates=(
            "site:x.com {entity} status",
            "site:x.com/{handle}/status {year}",
            'site:x.com/{handle}/status "{date_text}"',
            'site:x.com/{handle}/status "{phrase}"',
            'site:x.com/{handle}/status "{phrase}" "{date_text}"',
            "site:twitter.com/{handle}/status {year}",
        ),
    ),
    CanonicalUrlPattern(
        source="youtube",
        content_kind="video",
        hostnames=("youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"),
        path_regexes=(r"^/watch/?$", r"^/shorts/[A-Za-z0-9_-]+/?$"),
        required_query_keys=("v",),
        query_templates=(
            "site:youtube.com/watch {entity}",
            "site:youtu.be {entity}",
        ),
    ),
    CanonicalUrlPattern(
        source="youtube",
        content_kind="playlist",
        hostnames=("youtube.com", "www.youtube.com", "m.youtube.com"),
        path_regexes=(r"^/playlist/?$",),
        required_query_keys=("list",),
    ),
)


def list_canonical_patterns() -> Tuple[CanonicalUrlPattern, ...]:
    return _PATTERNS


def get_canonical_pattern(source: str, content_kind: str) -> Optional[CanonicalUrlPattern]:
    for pattern in _PATTERNS:
        if pattern.source == source and pattern.content_kind == content_kind:
            return pattern
    return None


def _normalized_hostname(url: str) -> str:
    host = (urlparse(url).hostname or "").lower().strip()
    if host.startswith("www."):
        host = host[4:]
    if host.startswith("m."):
        host = host[2:]
    return host


def url_matches_pattern(url: str, source: str, content_kind: str) -> bool:
    pattern = get_canonical_pattern(source, content_kind)
    if pattern is None:
        return False
    parsed = urlparse(url or "")
    host = _normalized_hostname(url)
    if host not in {h.removeprefix("www.").removeprefix("m.") for h in pattern.hostnames}:
        return False

    query = parse_qs(parsed.query or "")
    if source == "youtube" and content_kind == "video" and host == "youtu.be":
        return bool(re.match(r"^/[A-Za-z0-9_-]+/?$", parsed.path or ""))

    matched_path = any(re.match(rx, parsed.path or "") for rx in pattern.path_regexes) if pattern.path_regexes else True
    if not matched_path:
        return False

    if pattern.required_query_keys:
        # Some canonical shapes carry identifiers in the path instead of the
        # query string, for example ``https://youtu.be/<id>``. Only enforce
        # query-key requirements when the matched path is the query-driven one.
        if re.match(r"^/watch/?$", parsed.path or ""):
            return all(query.get(key) for key in pattern.required_query_keys)
    return True


def classify_canonical_url(url: str) -> Optional[Tuple[str, str]]:
    for pattern in _PATTERNS:
        if url_matches_pattern(url, pattern.source, pattern.content_kind):
            return pattern.source, pattern.content_kind
    return None


def build_canonical_search_queries(intent: UrlResolutionIntent) -> List[str]:
    pattern = get_canonical_pattern(intent.source, intent.content_kind)
    if pattern is None:
        return []

    replacements: Dict[str, str] = {
        "entity": " ".join(intent.entity_terms).strip(),
        "handle": (intent.known_handle or "").strip(),
        "date_text": (intent.known_date_text or "").strip(),
        "year": str(intent.known_year or ""),
        "phrase": (intent.known_phrase or "").strip(),
    }

    out: List[str] = []
    seen = set()
    for template in pattern.query_templates:
        if "{handle}" in template and not replacements["handle"]:
            continue
        if "{date_text}" in template and not replacements["date_text"]:
            continue
        if "{year}" in template and not replacements["year"]:
            continue
        if "{phrase}" in template and not replacements["phrase"]:
            continue
        if "{entity}" in template and not replacements["entity"]:
            continue
        query = template.format(**replacements)
        query = re.sub(r"\s+", " ", query).strip()
        if query and query not in seen:
            seen.add(query)
            out.append(query)
    return out


def preferred_handle_candidates(entity_terms: Sequence[str]) -> List[str]:
    compact = "".join(term for term in entity_terms if term)
    underscored = "_".join(term for term in entity_terms if term)
    out: List[str] = []
    for candidate in (compact, underscored):
        candidate = candidate.strip("_").lower()
        if candidate and candidate not in out:
            out.append(candidate)
    return out[:3]
