"""Tell the Console's page of posts to send by hand which ones have appeared on X.

X has no affordable write API, so posts are sent by a person from a queue in the Console. The X
reader already sees every post the account makes, so it can finish the queue's bookkeeping: a post
that matches a queued text resolves that item with a link to the post.

A person often edits the text in the compose box, so an exact comparison would miss the very posts
that were worked on most. The text is compared by similarity, and much less strictly when the post
carries the same link as the queued text.
"""
from __future__ import annotations

import html
import logging
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any, Sequence
from urllib.parse import quote, unquote

import requests

from process_bluesky.services.x_text import URL_PATTERN, expand_urls, post_url

logger = logging.getLogger(__name__)

PAGE_SLUG = "x-posts"
RESOLVER = "x-post-watch"
TIMEOUT_SECONDS = 15
OPEN_ITEMS_LIMIT = 1000
# Same link: the person may have rewritten the sentence around it.
SIMILARITY_WITH_SHARED_LINK = 0.5
SIMILARITY_WITHOUT_SHARED_LINK = 0.85


def split_text(text: str) -> tuple[str, frozenset[str]]:
    """Return the text without links, normalized for comparing, and its links."""
    plain = unicodedata.normalize("NFKC", html.unescape(text))
    links = frozenset(unquote(url).rstrip("/") for url in URL_PATTERN.findall(plain))
    return " ".join(URL_PATTERN.sub(" ", plain).split()), links


def similarity(queued: str, posted: str) -> float:
    """How well a post matches a queued text, from 0 (not this post) up to 1.

    A queued text with neither words nor a shared link cannot be told from anything, so it
    never matches.
    """
    queued_text, queued_links = split_text(queued)
    posted_text, posted_links = split_text(posted)
    shared = queued_links & posted_links
    if not queued_text and not shared:
        return 0.0
    ratio = SequenceMatcher(None, queued_text, posted_text, autojunk=False).ratio()
    threshold = SIMILARITY_WITH_SHARED_LINK if shared else SIMILARITY_WITHOUT_SHARED_LINK
    return ratio if ratio >= threshold else 0.0


def posted_text(post: dict[str, Any]) -> str:
    """The post's text with t.co links expanded, as the queued text was written."""
    metadata = post.get("metadata") or {}
    return expand_urls(post.get("content", ""), metadata.get("urls") or [])


def find_matches(
    items: Sequence[dict[str, Any]], posts: Sequence[dict[str, Any]]
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Pair queued items with posts, best match first, using each of them at most once.

    A post older than the queued text cannot be that text being sent, however alike they are: the
    queue may hold a repeat of something posted before.
    """
    scored = []
    for item_index, item in enumerate(items):
        for post_index, post in enumerate(posts):
            if post.get("timestamp", "") < item.get("created_at", ""):
                continue
            score = similarity(item.get("body", ""), posted_text(post))
            if score:
                scored.append((score, item_index, post_index))
    pairs = []
    used_items: set[int] = set()
    used_posts: set[int] = set()
    for _, item_index, post_index in sorted(scored, key=lambda entry: -entry[0]):
        if item_index in used_items or post_index in used_posts:
            continue
        used_items.add(item_index)
        used_posts.add(post_index)
        pairs.append((items[item_index], posts[post_index]))
    return pairs


def report_posts(api_url: str, posts: Sequence[dict[str, Any]], screen_name: str) -> bool:
    """Resolve the queued items these posts match. False means try these posts again later.

    The page not existing yet is an answer, not a failure: nothing is queued.
    """
    page = f"{api_url.rstrip('/')}/api/pages/{PAGE_SLUG}/items"
    try:
        listed = requests.get(
            page, params={"state": "open", "limit": OPEN_ITEMS_LIMIT}, timeout=TIMEOUT_SECONDS
        )
        if listed.status_code == 404:
            return True
        listed.raise_for_status()
        for item, post in find_matches(listed.json()["items"], posts):
            resolved = requests.patch(
                f"{page}/{quote(item['key'], safe='')}",
                json={
                    "state": "done",
                    "resolved_by": RESOLVER,
                    "result_url": post_url(screen_name, post["id"]),
                },
                timeout=TIMEOUT_SECONDS,
            )
            resolved.raise_for_status()
            logger.info("X post %s resolved queued item %s", post["id"], item["key"])
    except (requests.RequestException, KeyError, ValueError) as exc:
        logger.warning("Could not update the post queue; will retry: %s", exc)
        return False
    return True
