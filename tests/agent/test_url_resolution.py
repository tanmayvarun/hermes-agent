from agent.url_resolution import (
    UrlResolutionIntent,
    build_canonical_search_queries,
    classify_canonical_url,
    preferred_handle_candidates,
    url_matches_pattern,
)


def test_url_matches_x_status_pattern():
    assert url_matches_pattern("https://x.com/elonmusk/status/2001234567890123456", "x", "status")
    assert url_matches_pattern("https://twitter.com/elonmusk/status/2001234567890123456", "x", "status")
    assert not url_matches_pattern("https://x.com/elonmusk", "x", "status")


def test_url_matches_youtube_video_pattern():
    assert url_matches_pattern("https://www.youtube.com/watch?v=0EOhz2ltIOc", "youtube", "video")
    assert url_matches_pattern("https://youtu.be/0EOhz2ltIOc", "youtube", "video")
    assert not url_matches_pattern("https://www.youtube.com/playlist?list=old", "youtube", "video")


def test_classify_canonical_url():
    assert classify_canonical_url("https://x.com/elonmusk/status/2001234567890123456") == ("x", "status")
    assert classify_canonical_url("https://www.youtube.com/watch?v=0EOhz2ltIOc") == ("youtube", "video")


def test_build_canonical_search_queries_for_x_status():
    queries = build_canonical_search_queries(
        UrlResolutionIntent(
            source="x",
            content_kind="status",
            entity_terms=("elon", "musk"),
            known_handle="elonmusk",
            known_year=2026,
            known_date_text="July 27, 2026",
            known_phrase="will not forget about Mars",
        )
    )
    assert 'site:x.com/elonmusk/status "July 27, 2026"' in queries
    assert 'site:x.com/elonmusk/status "will not forget about Mars"' in queries
    assert "site:twitter.com/elonmusk/status 2026" in queries


def test_preferred_handle_candidates():
    assert preferred_handle_candidates(("elon", "musk")) == ["elonmusk", "elon_musk"]
