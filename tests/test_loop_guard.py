"""Tests for the echo guard.

The fixtures are real posts captured on 2026-09-21, not invented ones. An
invented pair would have agreed on far more than the real pair does, and the
guard would have looked correct while failing in production — the two sides
only share their opening words.
"""
from __future__ import annotations

from process_bluesky.services.loop_guard import is_echo, normalise

# Same post, relayed by hand. BlueSky adds a 📎 block; X writes / "title" and
# a t.co link. Everything after the first sentence differs.
BLUESKY_RICE = (
    "私はそんなことすら気にせずに、ちょっと多めとか少なめとか自分勝手に調節して、"
    "失敗したことないけどな。\n\n"
    "📎 「1合」という単位にとらわれないご飯の炊き方｜ツジメシ\n"
    "https://note.com/example/n/abc123"
)
X_RICE = (
    "私はそんなことすら気にせずに、ちょっと多めとか少なめとか自分勝手に調節して、"
    "失敗したことないけどな。 / “「1合」という単位にとらわれないご飯の炊き方｜ツジメシ” "
    "https://t.co/Abc123"
)

BLUESKY_LLM = (
    "なるほど参考になる。LLMでもかなり高速にJavと同じようなことができるぞと。\n\n"
    "📎 TypeSafeのJevを正しく驚く、それってLLMでできませんか？\n"
    "https://zenn.dev/example"
)
X_LLM = (
    "なるほど参考になる。LLMでもかなり高速にJavと同じようなことができるぞと。 "
    "https://t.co/GSZIw9Skht"
)

# Written on X directly. Must reach BlueSky.
X_ORIGINAL = (
    "XのAPIが安くなっていたので、人間のポストはXにして、それをプログラムで読み取り、"
    "必要に応じてBlueSkyに自動連係するようにした。さて。うまく動くかな？"
)


def test_real_relayed_post_is_detected_despite_different_decoration():
    assert is_echo(X_RICE, [BLUESKY_RICE])


def test_second_real_relayed_post_is_detected():
    assert is_echo(X_LLM, [BLUESKY_LLM])


def test_post_written_on_x_is_not_suppressed():
    """The whole point of the mirror. A false positive here loses the author's words."""
    assert not is_echo(X_ORIGINAL, [BLUESKY_RICE, BLUESKY_LLM])


def test_detection_does_not_depend_on_which_side_is_older():
    """Measured: the X copy was timestamped 3 minutes *before* the BlueSky original.

    A guard keyed on "BlueSky came first" would have let that one loop.
    """
    assert is_echo(X_RICE, [BLUESKY_RICE])
    assert is_echo(BLUESKY_RICE, [X_RICE])


def test_short_posts_are_never_treated_as_echoes():
    """Below the comparison window a prefix match means nothing."""
    assert not is_echo("了解", ["了解しました。これは別の投稿です。"])


def test_unrelated_posts_do_not_match():
    assert not is_echo(
        "今日は練馬で演奏する予定だったけど台風で中止になった。残念。",
        [BLUESKY_RICE, BLUESKY_LLM],
    )


def test_empty_feed_suppresses_nothing():
    assert not is_echo(X_RICE, [])


def test_normalise_strips_urls_and_decoration():
    assert "📎" not in normalise(BLUESKY_RICE)
    assert "http" not in normalise(BLUESKY_RICE)
    assert "https" not in normalise(X_RICE)


def test_normalised_prefixes_of_a_real_pair_agree():
    """The property the guard relies on, asserted directly."""
    assert normalise(X_RICE)[:40] == normalise(BLUESKY_RICE)[:40]
