"""Stop the same link from appearing in two consecutive BlueSky posts.

The echo guard in ``loop_guard`` compares *words*, so it only catches a post
that was relayed by hand. It cannot catch the case measured on 2026-09-21:
a scheduled video promotion and a bookmark relay described the same YouTube
video in completely different words, minutes apart. On the timeline that reads
as the same link posted twice in a row.

The rule is deliberately narrow — **only the newest post is consulted**.
Posting a link again days later is normal behaviour and must keep working;
what is being prevented is the back-to-back repeat.
"""
from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlsplit, urlunsplit

_URL = re.compile(r"https?://[^\s]+")

# Trailing characters that belong to the sentence, not to the link.
_TRAILING = ".,;:!?)]）】」』、。"

# Parameters that identify a campaign, not a document. Two URLs differing only
# in these point at the same page, and the promotion paths add them freely.
_TRACKING_PREFIXES = ("utm_",)
_TRACKING_KEYS = {"fbclid", "gclid", "igshid", "ref", "ref_src", "spm", "at_medium"}


def _is_tracking(key: str) -> bool:
    lowered = key.lower()
    return lowered in _TRACKING_KEYS or lowered.startswith(_TRACKING_PREFIXES)


def normalise_url(url: str) -> str:
    """Reduce a URL to something two paths to the same page agree on.

    youtu.be and youtube.com/watch are folded together on purpose: the
    promotion path writes the long form and hand-written posts often carry the
    short one, and they are the same video.
    """
    parts = urlsplit(url.rstrip(_TRAILING))
    host = parts.netloc.lower().split(":")[0].removeprefix("www.")
    path = parts.path.rstrip("/")
    query = [(k, v) for k, v in parse_qsl(parts.query) if not _is_tracking(k)]

    if host == "youtu.be" and path:
        video_id = path.lstrip("/")
        host, path = "youtube.com", "/watch"
        query = [("v", video_id)] + [(k, v) for k, v in query if k != "v"]
    elif host in {"youtube.com", "m.youtube.com"} and path == "/watch":
        query = [(k, v) for k, v in query if k == "v"]
        host = "youtube.com"

    query.sort()
    encoded = "&".join(f"{k}={v}" for k, v in query)
    return urlunsplit(("", host, path, encoded, ""))


def extract_links(text: str) -> set[str]:
    """Every link in ``text``, normalised."""
    return {normalise_url(match.group(0)) for match in _URL.finditer(text)}


def repeats_link(text: str, previous_text: str | None) -> bool:
    """True if posting ``text`` would put the same link in two posts in a row.

    A post with no link can never repeat one, and an empty timeline has
    nothing to repeat.
    """
    if not previous_text:
        return False
    links = extract_links(text)
    if not links:
        return False
    return bool(links & extract_links(previous_text))
