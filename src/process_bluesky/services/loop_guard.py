"""Stop the mirror from echoing BlueSky's own posts back to BlueSky.

The author still relays some BlueSky posts to X by hand (post on BlueSky,
click a generated intent link). Those relayed posts are authored on X and look
exactly like anything else the mirror should pick up — so without a guard they
come straight back, producing a duplicate.

Matching has to work on the *opening words only*. Measured against real posts
on 2026-09-21, the two sides do not agree on anything else:

    BlueSky: 私は…けどな。\n\n📎 「1合」という単位にとらわれない…\nhttps://…
    X:       私は…けどな。 / “「1合」という単位にとらわれない…” https://t.co/…

Same post, different decoration, different link form. Only the prefix survives.

Time is deliberately **not** part of the test. The obvious rule — "BlueSky
came first" — is wrong: in the measured samples the X copy was timestamped
*three minutes earlier* than the BlueSky original.
"""
from __future__ import annotations

import re

# How many normalised characters must agree before two posts are called the
# same. Long enough that ordinary short posts do not collide by accident,
# short enough to survive one side truncating the other.
PREFIX_CHARS = 40

# Below this length a prefix comparison says nothing useful, so short posts are
# never treated as echoes. Mirroring a duplicate is recoverable; silently
# dropping something the author wrote is not.
MIN_COMPARABLE_CHARS = 20

_URL = re.compile(r"https?://\S+")
_WHITESPACE = re.compile(r"\s+")
# Decoration each side adds on its own: BlueSky's 📎 marker, X's ` / “…” `
# quoting of the link title, and the ellipsis left by truncation.
_DECORATION = re.compile(r"[📎…‥・\"“”/｜|]+")


def normalise(text: str) -> str:
    """Reduce a post to the part both platforms preserve."""
    without_urls = _URL.sub("", text)
    without_decoration = _DECORATION.sub("", without_urls)
    return _WHITESPACE.sub("", without_decoration)


def is_echo(x_text: str, bluesky_texts: list[str]) -> bool:
    """True if ``x_text`` looks like a hand-relayed copy of a BlueSky post."""
    candidate = normalise(x_text)
    if len(candidate) < MIN_COMPARABLE_CHARS:
        return False

    for text in bluesky_texts:
        known = normalise(text)
        if len(known) < MIN_COMPARABLE_CHARS:
            continue
        window = min(PREFIX_CHARS, len(candidate), len(known))
        if candidate[:window] == known[:window]:
            return True
    return False


def fetch_recent_bluesky_texts(handle: str, limit: int = 100) -> list[str]:
    """Recent post texts from a BlueSky account, via the public API.

    Unauthenticated on purpose: this is a read of public data, and keeping it
    off the posting session means a guard failure can never take the posting
    credentials down with it.

    Reposts are excluded — their text belongs to somebody else, and matching
    against it would suppress the author's own words.
    """
    import json
    import urllib.parse
    import urllib.request

    url = (
        "https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed"
        f"?actor={urllib.parse.quote(handle)}&limit={limit}"
    )
    with urllib.request.urlopen(url, timeout=20) as response:
        payload = json.load(response)

    return [
        item["post"]["record"].get("text", "")
        for item in payload.get("feed", [])
        if not item.get("reason")
    ]
