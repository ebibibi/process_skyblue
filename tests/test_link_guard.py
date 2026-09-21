"""Tests for the consecutive-duplicate-link guard.

The fixtures are the real pair that caused the problem on 2026-09-21: the
scheduled promotion of a video, and a bookmark relay of the same video posted
44 minutes later. Nothing but the link is shared between them.
"""
from __future__ import annotations

from process_bluesky.services.link_guard import (
    extract_links,
    normalise_url,
    repeats_link,
)

PROMOTION = (
    "ローカルLLMは今どこまで行った？DGX Sparkで5種類、クラウド最強AI 5種類で"
    "同じ将棋盤を作らせてみた。生成速度、完成度、意外な結果が🎬 "
    "https://www.youtube.com/watch?v=4xbhp_vcq4w #Azure #ClaudeCode"
)
BOOKMARK_RELAY = (
    "DGX Spark上のローカル5モデルとフロンティア5モデルに、同条件でHTML1枚の"
    "将棋盤を作らせた実測比較\n\n"
    "📎 ローカルLLM5 vs フロンティア5｜将棋盤、作れる？\n"
    "https://www.youtube.com/watch?v=4xbhp_vcq4w"
)
UNRELATED = "今日は南柏で勉強会。 https://ebisuda.connpass.com/event/401188/"


def test_same_link_in_different_words_is_caught():
    """The case the text-based echo guard cannot see."""
    assert repeats_link(BOOKMARK_RELAY, PROMOTION)


def test_different_link_is_allowed():
    assert not repeats_link(UNRELATED, PROMOTION)


def test_post_without_a_link_is_allowed():
    assert not repeats_link("今日はいい天気。", PROMOTION)


def test_empty_timeline_allows_anything():
    assert not repeats_link(PROMOTION, None)
    assert not repeats_link(PROMOTION, "")


def test_short_youtube_form_matches_long_form():
    assert repeats_link("https://youtu.be/4xbhp_vcq4w を公開しました", PROMOTION)


def test_tracking_parameters_do_not_hide_a_repeat():
    assert repeats_link(
        "https://www.youtube.com/watch?v=4xbhp_vcq4w&utm_source=bsky", PROMOTION
    )


def test_trailing_punctuation_is_not_part_of_the_link():
    assert normalise_url("https://example.com/a/b/。") == "//example.com/a/b"


def test_query_order_does_not_matter():
    assert normalise_url("https://example.com/p?b=2&a=1") == normalise_url(
        "https://example.com/p?a=1&b=2"
    )


def test_extract_links_finds_every_link():
    assert extract_links("a https://example.com b http://example.org/x") == {
        "//example.com",
        "//example.org/x",
    }
