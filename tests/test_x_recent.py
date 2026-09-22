"""Tests for the read-only recent X posts export."""

from __future__ import annotations

from datetime import datetime, timezone

from process_bluesky.x_recent import filter_recent_posts, prepare_posts, render_markdown


def _post(post_id: str, timestamp: str, text: str = "hello") -> dict:
    return {
        "id": post_id,
        "content": text,
        "timestamp": timestamp,
        "author": "x",
        "metadata": {"urls": []},
    }


def test_filter_recent_posts_applies_age_and_limit_newest_first() -> None:
    now = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)
    posts = [
        _post("1", "2026-08-01T00:00:00.000Z"),
        _post("2", "2026-09-20T00:00:00.000Z"),
        _post("3", "2026-09-22T00:00:00.000Z"),
    ]

    result = filter_recent_posts(posts, days=14, limit=1, now=now)

    assert [post["id"] for post in result] == ["3"]


def test_prepare_posts_expands_links_and_adds_source_url() -> None:
    post = _post("123", "2026-09-22T00:00:00.000Z", "read https://t.co/a")
    post["metadata"]["urls"] = [
        {"url": "https://t.co/a", "expanded_url": "https://example.com/article"}
    ]

    result = prepare_posts([post], screen_name="ebi")

    assert result == [
        {
            "id": "123",
            "created_at": "2026-09-22T00:00:00.000Z",
            "text": "read https://example.com/article",
            "url": "https://x.com/ebi/status/123",
            "replied_to": None,
            "conversation_id": None,
        }
    ]


def test_render_markdown_is_human_and_agent_readable() -> None:
    posts = [
        {
            "id": "123",
            "created_at": "2026-09-22T00:00:00.000Z",
            "text": "first line\nsecond line",
            "url": "https://x.com/ebi/status/123",
            "replied_to": None,
            "conversation_id": "123",
        }
    ]

    output = render_markdown(posts)

    assert "## 2026-09-22T00:00:00.000Z" in output
    assert "first line\nsecond line" in output
    assert "https://x.com/ebi/status/123" in output
