from agent.capabilities import (
    ResolveLatestMediaCapability,
    ensure_builtins,
    get_capability,
    list_capabilities,
)
from agent.capabilities.latest_media import is_latest_media_intent


def test_is_latest_media_intent():
    assert is_latest_media_intent("share the youtube link to latest podcast of jaya kishori")
    assert is_latest_media_intent("latest interview video link for x")
    assert is_latest_media_intent("find the latest tweet by elon musk")
    assert not is_latest_media_intent("find the latest plugin brochure pdf in downloads")
    assert not is_latest_media_intent("refactor the task controller")


def test_latest_media_capability_picks_newer_dated_episode():
    responses = {
        "jaya kishori latest podcast youtube": {
            "success": True,
            "data": {
                "web": [
                    {
                        "title": "Jaya Kishori Ji Podcast",
                        "url": "https://www.youtube.com/playlist?list=old",
                        "description": "Last updated on Feb 1, 2026. 8 years ago.",
                        "position": 1,
                    },
                    {
                        "title": "Jaya Kishori on God's Love, Marriage, Relationships, Parenting & Life ...",
                        "url": "https://www.youtube.com/watch?v=0EOhz2ltIOc",
                        "description": "In this 520th episode of The Ranveer Show...",
                        "position": 4,
                    },
                ]
            },
        },
        "jaya kishori podcast 2026": {
            "success": True,
            "data": {
                "web": [
                    {
                        "title": "Jaya Kishori - God's Love, Marriage, Relationships, Parenting & Life | TRS",
                        "url": "https://podcasts.apple.com/in/podcast/jaya-kishori-gods-love-marriage-relationships-parenting/id1542452346?i=1000775815286",
                        "description": "This podcast is a valuable resource... 7 July 2026 at 14:57 UTC.",
                        "position": 1,
                    }
                ]
            },
        },
        "jaya kishori the ranveer show podcast 2026": {
            "success": True,
            "data": {
                "web": [
                    {
                        "title": "Jaya Kishori - God's Love, Marriage, Relationships, Parenting & Life | TRS",
                        "url": "https://podcasts.apple.com/in/podcast/jaya-kishori-gods-love-marriage-relationships-parenting/id1542452346?i=1000775815286",
                        "description": "Published 7 July 2026 at 14:57 UTC",
                        "position": 1,
                    }
                ]
            },
        },
        "site:youtube.com/watch jaya kishori podcast": {
            "success": True,
            "data": {
                "web": [
                    {
                        "title": "Karna & Krishna Beautiful Conversation In Mahabharat by Jaya Kishori",
                        "url": "https://www.youtube.com/watch?v=9_ZnDpAKRng",
                        "description": "26 Aug 2024 ... Full Video: https://youtu.be/ahob9vKpsfQ",
                        "position": 1,
                    }
                ]
            },
        },
    }

    def search_fn(query: str, limit: int = 5) -> str:
        import json

        return json.dumps(responses.get(query, {"success": True, "data": {"web": []}}))

    cap = ResolveLatestMediaCapability()
    result = cap.execute_objective(
        "share the youtube link to latest podcast of jaya kishori",
        search_fn=search_fn,
    )
    payload = cap.to_tool_payload(result)
    assert result.status == "success"
    assert payload["selected"]["url"].startswith("https://podcasts.apple.com/")
    assert payload["selected"]["published_at"] == "2026-07-07"
    assert payload["selected"]["title"].startswith("Jaya Kishori - God's Love")
    assert "valuable resource" in payload["selected"]["caption"]


def test_latest_media_capability_registry_builtins():
    ensure_builtins()
    assert "latest_media" in list_capabilities()
    assert get_capability("latest_media") is not None


def test_latest_media_extracts_views_and_channel_metadata():
    responses = {
        "jaya kishori latest podcast youtube": {
            "success": True,
            "data": {
                "web": [
                    {
                        "title": "Jaya Kishori on God's Love, Marriage, Relationships ...",
                        "url": "https://www.youtube.com/watch?v=0EOhz2ltIOc",
                        "description": "BeerBiceps 635K views 7 July 2026 at 14:57 UTC In this 520th episode of The Ranveer Show...",
                        "position": 1,
                    }
                ]
            },
        },
        "jaya kishori podcast 2026": {"success": True, "data": {"web": []}},
        "jaya kishori the ranveer show podcast 2026": {"success": True, "data": {"web": []}},
        "site:youtube.com/watch jaya kishori podcast": {"success": True, "data": {"web": []}},
    }

    def search_fn(query: str, limit: int = 5) -> str:
        import json

        return json.dumps(responses.get(query, {"success": True, "data": {"web": []}}))

    cap = ResolveLatestMediaCapability()
    payload = cap.to_tool_payload(
        cap.execute_objective(
            "share the youtube link to latest podcast of jaya kishori",
            search_fn=search_fn,
        )
    )
    assert payload["selected"]["views"] == "635K views"
    assert "The Ranveer Show" in payload["selected"]["caption"]


def test_latest_media_capability_resolves_latest_tweet_with_metadata():
    responses = {
        "elon musk latest tweet x": {
            "success": True,
            "data": {
                "web": [
                    {
                        "title": "Elon Musk on X: Launch update",
                        "url": "https://x.com/elonmusk/status/1949651234567890123",
                        "description": "Posted on Jul 27, 2026 by @elonmusk. Starship update soon. 2.4M views.",
                        "position": 1,
                    },
                    {
                        "title": "Elon Musk interview clip",
                        "url": "https://www.youtube.com/watch?v=olderclip",
                        "description": "26 Jul 2026 discussion clip",
                        "position": 2,
                    },
                ]
            },
        },
        "site:x.com elon musk status": {
            "success": True,
            "data": {
                "web": [
                    {
                        "title": "Elon Musk on X: Launch update",
                        "url": "https://x.com/elonmusk/status/1949651234567890123",
                        "description": "Jul 27, 2026 by @elonmusk. Starship update soon.",
                        "position": 1,
                    }
                ]
            },
        },
        "site:twitter.com elon musk status": {"success": True, "data": {"web": []}},
        "elon musk latest post twitter 2026": {"success": True, "data": {"web": []}},
    }

    def search_fn(query: str, limit: int = 5) -> str:
        import json

        return json.dumps(responses.get(query, {"success": True, "data": {"web": []}}))

    cap = ResolveLatestMediaCapability()
    result = cap.execute_objective(
        "find the latest tweet by elon musk",
        search_fn=search_fn,
    )
    payload = cap.to_tool_payload(result)
    assert result.status == "success"
    assert payload["selected"]["url"] == "https://x.com/elonmusk/status/1949651234567890123"
    assert payload["selected"]["published_at"] == "2026-07-27"
    assert payload["selected"]["author"] == "@elonmusk"
    assert "Starship update soon" in payload["selected"]["caption"]


def test_latest_media_social_request_requires_direct_status_url():
    responses = {
        "elon musk latest tweet x": {
            "success": True,
            "data": {
                "web": [
                    {
                        "title": "Elon Musk # tweets May 26 - June 2, 2026?",
                        "url": "https://polymarket.com/event/elon-musk-of-tweets-may-26-june-2",
                        "description": "Jul 28, 2026 market page discussing Elon Musk tweet volume.",
                        "position": 1,
                    }
                ]
            },
        },
        "site:x.com elon musk status": {"success": True, "data": {"web": []}},
        "site:twitter.com elon musk status": {"success": True, "data": {"web": []}},
        "elon musk latest post twitter 2026": {"success": True, "data": {"web": []}},
    }

    def search_fn(query: str, limit: int = 5) -> str:
        import json

        return json.dumps(responses.get(query, {"success": True, "data": {"web": []}}))

    cap = ResolveLatestMediaCapability()
    result = cap.execute_objective(
        "find the latest tweet by elon musk",
        search_fn=search_fn,
    )
    payload = cap.to_tool_payload(result)
    assert result.status == "partial"
    assert payload["selected"]["url"] == "https://polymarket.com/event/elon-musk-of-tweets-may-26-june-2"
    assert "direct X/Twitter status" in result.message
    assert any("status page" in q.lower() for q in result.unresolved_questions)


def test_latest_media_social_request_marks_stale_direct_status_as_partial():
    responses = {
        "elon musk latest tweet x": {
            "success": True,
            "data": {
                "web": [
                    {
                        "title": "Elon Musk on X: @cb_doge It’s time 😀",
                        "url": "https://x.com/elonmusk/status/1985373548840636724",
                        "description": "Nov 3, 2025 by @elonmusk. It’s time 😀 1.6M views.",
                        "position": 1,
                    }
                ]
            },
        },
        "site:x.com elon musk status": {"success": True, "data": {"web": []}},
        "elon musk latest post twitter 2026": {"success": True, "data": {"web": []}},
        "site:x.com/elonmusk/status July 2026": {"success": True, "data": {"web": []}},
        "site:x.com/elonmusk/status 2026": {"success": True, "data": {"web": []}},
    }

    def search_fn(query: str, limit: int = 5) -> str:
        import json

        return json.dumps(responses.get(query, {"success": True, "data": {"web": []}}))

    cap = ResolveLatestMediaCapability()
    result = cap.execute_objective(
        "find the latest tweet by elon musk",
        search_fn=search_fn,
    )
    assert result.status == "partial"
    assert "too old to trust as the latest post" in result.message


def test_latest_media_social_request_prefers_newer_unverified_candidate_over_older_verified_one():
    responses = {
        "elon musk latest tweet x": {
            "success": True,
            "data": {
                "web": [
                    {
                        "title": "Elon Musk on X: @cb_doge It’s time 😀",
                        "url": "https://x.com/elonmusk/status/1985373548840636724",
                        "description": "Nov 3, 2025 by @elonmusk. It’s time 😀 1.6M views.",
                        "position": 1,
                    }
                ]
            },
        },
        "elon musk latest post twitter 2026": {
            "success": True,
            "data": {
                "web": [
                    {
                        "title": "Elon Musk Archive — Jul 27, 2026",
                        "url": "https://elonmuskarchive.org/posts?year=2026",
                        "description": "Elon Musk @elonmusk · Jul 27, 2026 I will not forget about Mars",
                        "position": 1,
                    }
                ]
            },
        },
        "elon musk x posts July 2026": {"success": True, "data": {"web": []}},
        "elon musk tweets last 7 days": {"success": True, "data": {"web": []}},
        "elon musk archive x posts 2026": {"success": True, "data": {"web": []}},
        "site:x.com elon musk status": {"success": True, "data": {"web": []}},
        "site:x.com/elonmusk/status July 2026": {"success": True, "data": {"web": []}},
        "site:x.com/elonmusk/status 2026": {"success": True, "data": {"web": []}},
        "site:twitter.com/elonmusk/status 2026": {"success": True, "data": {"web": []}},
    }

    def search_fn(query: str, limit: int = 5) -> str:
        import json

        return json.dumps(responses.get(query, {"success": True, "data": {"web": []}}))

    cap = ResolveLatestMediaCapability()
    result = cap.execute_objective(
        "find the latest tweet by elon musk",
        search_fn=search_fn,
    )
    payload = cap.to_tool_payload(result)
    assert result.status == "partial"
    assert payload["selected"]["url"] == "https://elonmuskarchive.org/posts?year=2026"
    assert payload["selected"]["published_at"] == "2026-07-27"
    assert payload["selected"]["stage"] == "discovery"
    assert "newer social-post candidate" in result.message


def test_latest_media_social_request_resolves_discovery_candidate_to_direct_status():
    responses = {
        "elon musk latest tweet x": {
            "success": True,
            "data": {
                "web": [
                    {
                        "title": "Elon Musk Archive — Jul 27, 2026",
                        "url": "https://elonmuskarchive.org/posts?year=2026",
                        "description": "Elon Musk @elonmusk · Jul 27, 2026 I will not forget about Mars",
                        "position": 1,
                    }
                ]
            },
        },
        "elon musk latest post twitter 2026": {"success": True, "data": {"web": []}},
        "elon musk x posts July 2026": {"success": True, "data": {"web": []}},
        "elon musk tweets last 7 days": {"success": True, "data": {"web": []}},
        "elon musk archive x posts 2026": {"success": True, "data": {"web": []}},
        "site:x.com elon musk status": {"success": True, "data": {"web": []}},
        "site:x.com/elonmusk/status July 2026": {"success": True, "data": {"web": []}},
        "site:x.com/elonmusk/status 2026": {"success": True, "data": {"web": []}},
        'site:x.com/elonmusk/status "July 27, 2026"': {
            "success": True,
            "data": {
                "web": [
                    {
                        "title": "Elon Musk on X: I will not forget about Mars",
                        "url": "https://x.com/elonmusk/status/2001234567890123456",
                        "description": "Jul 27, 2026 by @elonmusk. I will not forget about Mars. 812K views.",
                        "position": 1,
                    }
                ]
            },
        },
        'site:x.com/elonmusk/status "will not forget about Mars"': {"success": True, "data": {"web": []}},
        'site:x.com/elonmusk/status "will not forget about Mars" "July 27, 2026"': {"success": True, "data": {"web": []}},
        "site:twitter.com/elonmusk/status 2026": {"success": True, "data": {"web": []}},
    }

    def search_fn(query: str, limit: int = 5) -> str:
        import json

        return json.dumps(responses.get(query, {"success": True, "data": {"web": []}}))

    cap = ResolveLatestMediaCapability()
    result = cap.execute_objective(
        "find the latest tweet by elon musk",
        search_fn=search_fn,
    )
    payload = cap.to_tool_payload(result)
    assert result.status == "success"
    assert payload["selected"]["url"] == "https://x.com/elonmusk/status/2001234567890123456"
    assert payload["selected"]["published_at"] == "2026-07-27"
    assert payload["selected"]["stage"] == "resolution"


def test_latest_media_social_request_demotes_tracker_pages_and_bad_handles():
    responses = {
        "elon musk latest tweet x": {
            "success": True,
            "data": {
                "web": [
                    {
                        "title": "Elon Musk # tweets in July 2026? Predictions & Live Odds | Bitget Wallet",
                        "url": "https://web3.bitget.com/predictions/event/elon-musk-of-tweets-july-2026",
                        "description": "This market will resolve according to the number of times Elon Musk (@elonmusk), posts on X during the month of July 2026.",
                        "position": 1,
                    },
                    {
                        "title": "Elon Musk on X: I will not forget about Mars",
                        "url": "https://x.com/elonmusk/status/2001234567890123456",
                        "description": "Jul 27, 2026 by @elonmusk. I will not forget about Mars. 812K views.",
                        "position": 2,
                    },
                ]
            },
        },
        "elon musk latest post twitter 2026": {"success": True, "data": {"web": []}},
        "elon musk x posts July 2026": {"success": True, "data": {"web": []}},
        "elon musk tweets last 7 days": {"success": True, "data": {"web": []}},
        "elon musk archive x posts 2026": {"success": True, "data": {"web": []}},
        "site:x.com elon musk status": {"success": True, "data": {"web": []}},
        "site:x.com/elonmusk/status July 2026": {"success": True, "data": {"web": []}},
        "site:x.com/elonmusk/status 2026": {"success": True, "data": {"web": []}},
    }

    seen_queries = []

    def search_fn(query: str, limit: int = 5) -> str:
        import json

        seen_queries.append(query)
        return json.dumps(responses.get(query, {"success": True, "data": {"web": []}}))

    cap = ResolveLatestMediaCapability()
    result = cap.execute_objective(
        "find the latest tweet by elon musk",
        search_fn=search_fn,
    )
    payload = cap.to_tool_payload(result)
    assert result.status == "success"
    assert payload["selected"]["url"] == "https://x.com/elonmusk/status/2001234567890123456"
    assert not any("/the/status" in query for query in seen_queries)


def test_latest_media_social_request_prefers_target_handle_over_commentator_handle():
    responses = {
        "elon musk latest tweet x": {
            "success": True,
            "data": {
                "web": [
                    {
                        "title": "Elon Musk posted 76 times on X today (07/26/26)",
                        "url": "https://www.youtube.com/watch?v=gvbq4GjRIsg",
                        "description": "Jul 27, 2026. From Andrew McCarthy. Elon reposted this. @elonmusk shared Blade Runner 2026.",
                        "position": 1,
                    },
                    {
                        "title": "Elon Musk on X: I will not forget about Mars",
                        "url": "https://x.com/elonmusk/status/2001234567890123456",
                        "description": "Jul 27, 2026 by @elonmusk. I will not forget about Mars. 812K views.",
                        "position": 2,
                    },
                ]
            },
        },
        "elon musk latest post twitter 2026": {"success": True, "data": {"web": []}},
        "elon musk x posts July 2026": {"success": True, "data": {"web": []}},
        "elon musk tweets last 7 days": {"success": True, "data": {"web": []}},
        "elon musk archive x posts 2026": {"success": True, "data": {"web": []}},
        "site:x.com elon musk status": {"success": True, "data": {"web": []}},
        "site:x.com/elonmusk/status July 2026": {"success": True, "data": {"web": []}},
        "site:x.com/elonmusk/status 2026": {"success": True, "data": {"web": []}},
    }

    seen_queries = []

    def search_fn(query: str, limit: int = 5) -> str:
        import json

        seen_queries.append(query)
        return json.dumps(responses.get(query, {"success": True, "data": {"web": []}}))

    cap = ResolveLatestMediaCapability()
    result = cap.execute_objective(
        "find the latest tweet by elon musk",
        search_fn=search_fn,
    )
    payload = cap.to_tool_payload(result)
    assert result.status == "success"
    assert payload["selected"]["url"] == "https://x.com/elonmusk/status/2001234567890123456"
    assert not any("/andrew/status" in query.lower() for query in seen_queries)
