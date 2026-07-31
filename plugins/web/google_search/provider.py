"""Google Search web search provider — plugin form."""

from __future__ import annotations

import html
import logging
import re
from typing import Any, Dict, List
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from agent.web_search_provider import WebSearchProvider

logger = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)
_RESULT_RE = re.compile(
    r'<a[^>]+href="(?P<href>/url\?q=[^"]+)"[^>]*>(?P<body>.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")


def _google_search_browser_available() -> bool:
    """Return True when a browser/computer-use path is available."""
    try:
        from tools.browser_tool import _chromium_installed

        return bool(_chromium_installed())
    except Exception:
        return False


def _strip_html(text: str) -> str:
    text = html.unescape(text or "")
    text = _TAG_RE.sub(" ", text)
    return " ".join(text.split()).strip()


def _parse_google_results(page: str, limit: int) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for match in _RESULT_RE.finditer(page):
        href = html.unescape(match.group("href") or "")
        body = match.group("body") or ""
        parsed = urlparse(href)
        if parsed.path != "/url":
            continue
        params = parse_qs(parsed.query)
        target = unquote((params.get("q") or [""])[0]).strip()
        if not target or target in seen:
            continue
        if target.startswith("https://www.google.com/search"):
            continue
        title = _strip_html(body)
        if not title:
            continue
        seen.add(target)
        results.append(
            {
                "title": title,
                "url": target,
                "description": "",
                "position": len(results) + 1,
            }
        )
        if len(results) >= limit:
            break
    return results


class GoogleSearchWebSearchProvider(WebSearchProvider):
    """Google Search backend.

    Search-only: result pages are the discovery layer; page extraction
    remains delegated to the extract-capable providers.
    """

    @property
    def name(self) -> str:
        return "google-search"

    @property
    def display_name(self) -> str:
        return "Google Search"

    def is_available(self) -> bool:
        return _google_search_browser_available()

    def supports_search(self) -> bool:
        return True

    def supports_extract(self) -> bool:
        return False

    def search(self, query: str, limit: int = 5) -> Dict[str, Any]:
        try:
            from tools.interrupt import is_interrupted

            if is_interrupted():
                return {"success": False, "error": "Interrupted"}

            safe_limit = max(1, min(int(limit), 10))
            resp = httpx.get(
                "https://www.google.com/search",
                params={
                    "q": query,
                    "num": safe_limit,
                    "hl": "en",
                    "gl": "us",
                    "gbv": "1",
                    "pws": "0",
                },
                headers={
                    "User-Agent": _USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                },
                timeout=20,
                follow_redirects=True,
            )
            resp.raise_for_status()
            results = _parse_google_results(resp.text or "", safe_limit)
            if not results:
                return {
                    "success": False,
                    "error": "Google Search returned no parseable results",
                }
            return {"success": True, "data": {"web": results}}
        except httpx.HTTPStatusError as exc:
            logger.warning("Google Search HTTP error: %s", exc)
            return {
                "success": False,
                "error": f"Google Search returned HTTP {exc.response.status_code}",
            }
        except httpx.RequestError as exc:
            logger.warning("Google Search request error: %s", exc)
            return {
                "success": False,
                "error": f"Could not reach Google Search: {exc}",
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("Google Search error: %s", exc)
            return {"success": False, "error": f"Google Search failed: {exc}"}

    def get_setup_schema(self) -> Dict[str, Any]:
        return {
            "name": "Google Search",
            "badge": "free",
            "tag": "Browser/computer-use capable search path with no API key.",
            "env_vars": [],
        }
