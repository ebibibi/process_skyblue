"""Convert an X post's text into something BlueSky can hold.

Two transformations, both of which change what the reader sees and so are kept
separate from the posting code and covered by tests:

- t.co links are expanded. Left alone they render as an opaque shortener that
  X may stop resolving, and they tell the reader nothing.
- Text longer than BlueSky's limit is truncated with a link back to the
  original, rather than silently losing the tail.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

# BlueSky counts graphemes, not codepoints. Python has no grapheme support in
# the stdlib, but graphemes <= codepoints always, so measuring codepoints is
# conservative: we may truncate slightly early, never too late.
BLUESKY_MAX_CHARS = 300

URL_PATTERN = re.compile(r"https?://[^\s]+")


def expand_urls(text: str, url_entities: Iterable[dict[str, Any]]) -> str:
    """Replace t.co links with the URL they point at.

    X's ``entities.urls`` gives ``url`` (the t.co form) and ``expanded_url``.
    For a quote post the trailing t.co points at the quoted post, so expanding
    it is what makes the quote followable on BlueSky.
    """
    result = text
    for entity in url_entities:
        short = entity.get("url")
        expanded = entity.get("expanded_url")
        if short and expanded:
            result = result.replace(short, expanded)
    return result


def post_url(screen_name: str, post_id: str) -> str:
    return f"https://x.com/{screen_name}/status/{post_id}"


def truncate_with_source(text: str, source_url: str, limit: int = BLUESKY_MAX_CHARS) -> str:
    """Trim to ``limit``, keeping a link to the full post.

    The link is reserved *before* trimming. Appending it afterwards is the
    obvious implementation and is wrong: the result overshoots the limit and
    BlueSky rejects the whole post.
    """
    if len(text) <= limit:
        return text

    suffix = f"… {source_url}"
    keep = limit - len(suffix)
    if keep <= 0:
        # Pathological: the URL alone fills the budget. The link is worth more
        # than a few characters of prefix.
        return source_url[:limit]
    return text[:keep].rstrip() + suffix


def build_text(post: dict[str, Any], screen_name: str) -> str:
    """Produce the BlueSky body for one X post."""
    metadata = post.get("metadata") or {}
    text = expand_urls(post.get("content", ""), metadata.get("urls") or [])
    return truncate_with_source(text, post_url(screen_name, post["id"]))


def find_links(text: str) -> list[tuple[int, int, str]]:
    """Locate links as (byte_start, byte_end, url).

    BlueSky facet offsets are **byte** offsets into the UTF-8 encoding, not
    character offsets. With Japanese text the two differ by a factor of three,
    so using character offsets puts the clickable span in the wrong place —
    and it still posts successfully, which is why this is easy to miss.
    """
    spans: list[tuple[int, int, str]] = []
    for match in URL_PATTERN.finditer(text):
        url = match.group(0).rstrip(".,;:)】」")
        start = len(text[: match.start()].encode("utf-8"))
        spans.append((start, start + len(url.encode("utf-8")), url))
    return spans
