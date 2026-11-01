"""Publish one post to X. One invocation = one post.

X posting was removed in 2026-07 because pay-per-use pricing made routine
cross-posting too expensive. This CLI exists for a single deliberate exception:
the automated weekly Azure / Microsoft 365 update videos (site2youtube) are
announced on X as well. Callers decide *what* to post; this module only makes
sure a post is valid before money is spent on it.

It lives next to ``x_discord`` and ``x_mirror`` on purpose: X refresh tokens
are single-use, so every process that talks to X must share one token store
(``.env``) and one persister. A second copy of the tokens elsewhere would
revoke this one on its first refresh.

Usage:
    python -m process_bluesky.x_post --env-file .env --text "..."
    python -m process_bluesky.x_post --env-file .env --text-file post.txt
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import unicodedata
from pathlib import Path
from typing import Optional, Sequence

import requests
from dotenv import load_dotenv

from process_bluesky.services.x_input_service import (
    API_BASE,
    TIMEOUT_SECONDS,
    XAuthError,
    XCreditsDepletedError,
    XInputService,
)
from process_bluesky.services.x_text import post_url
from process_bluesky.x_mirror import persist_tokens

logger = logging.getLogger(__name__)

# The account is on the free plan: X rejects anything over weighted 280.
X_WEIGHTED_LIMIT = 280
URL_WEIGHT = 23
# twitter-text weight-1 ranges; every other code point weighs 2 (CJK, emoji).
LIGHT_RANGES: tuple[tuple[int, int], ...] = (
    (0x0000, 0x10FF),
    (0x2000, 0x200D),
    (0x2010, 0x201F),
    (0x2032, 0x2037),
)
# Japanese punctuation glued to a URL is not part of it (X cuts the link there).
URL_PATTERN = re.compile(r"https?://[^\s。、，．）」』】〉》！？]+")

# Refuse to post when the prepaid balance is nearly gone. A post that fails
# with 402 half-way through a campaign is harder to notice than a clear refusal.
MIN_BALANCE_USD = 0.50

EXIT_OK = 0
EXIT_INVALID = 2
EXIT_CREDITS = 3
EXIT_FAILED = 1


def weighted_length(text: str) -> int:
    """X's weighted length: URLs count 23, CJK and emoji 2, Latin 1."""
    urls = URL_PATTERN.findall(text)
    body = URL_PATTERN.sub("", text)
    weight = 0
    for char in body:
        if unicodedata.combining(char) or char == "️":
            continue
        code = ord(char)
        weight += 1 if any(lo <= code <= hi for lo, hi in LIGHT_RANGES) else 2
    return weight + URL_WEIGHT * len(urls)


def validate_text(text: str) -> str:
    """Return the cleaned text or raise ValueError before any API call."""
    cleaned = text.strip()
    if not cleaned:
        raise ValueError("post text is empty")
    length = weighted_length(cleaned)
    if length > X_WEIGHTED_LIMIT:
        raise ValueError(f"post is too long: weighted {length}/{X_WEIGHTED_LIMIT}")
    return cleaned


def create_post(service: XInputService, text: str, _retried: bool = False) -> str:
    """POST /2/tweets as the authenticated user and return the new post id."""
    response = requests.post(
        f"{API_BASE}/tweets",
        headers={"Authorization": f"Bearer {service.access_token}"},
        json={"text": text},
        timeout=TIMEOUT_SECONDS,
    )
    if response.status_code == 402:
        raise XCreditsDepletedError("X API credits depleted")
    if response.status_code == 401 and not _retried:
        service.refresh_access_token()
        return create_post(service, text, _retried=True)
    if response.status_code not in (200, 201):
        # 403 here usually means the token lacks the tweet.write scope.
        raise XAuthError(f"post failed: HTTP {response.status_code} {response.text[:300]}")
    return str(response.json()["data"]["id"])


def _read_text(args: argparse.Namespace) -> str:
    if args.text_file:
        return Path(args.text_file).read_text(encoding="utf-8")
    return args.text or ""


def _service_from_env(env_path: Path) -> XInputService:
    return XInputService(
        user_id=os.environ["X_USER_ID"],
        access_token=os.environ["X_ACCESS_TOKEN"],
        refresh_token=os.environ["X_REFRESH_TOKEN"],
        client_id=os.environ["X_CLIENT_ID"],
        client_secret=os.environ["X_CLIENT_SECRET"],
        token_persister=persist_tokens(str(env_path)),
    )


def _check_balance(service: XInputService) -> Optional[float]:
    try:
        return service.get_credit_balance()
    except XCreditsDepletedError:
        raise
    except Exception as exc:  # noqa: BLE001 - balance is a guard, not the job
        logger.warning("could not read X credit balance: %s", exc)
        return None


def run(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Publish one post to X")
    parser.add_argument("--env-file", required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--text")
    source.add_argument("--text-file")
    parser.add_argument("--dry-run", action="store_true", help="validate only, do not post")
    args = parser.parse_args(argv)

    try:
        text = validate_text(_read_text(args))
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_INVALID
    if args.dry_run:
        print(f"OK (dry-run): weighted={weighted_length(text)}/{X_WEIGHTED_LIMIT}")
        return EXIT_OK

    env_path = Path(args.env_file).expanduser().resolve()
    load_dotenv(env_path, override=True)
    service = _service_from_env(env_path)
    try:
        balance = _check_balance(service)
        if balance is not None and balance < MIN_BALANCE_USD:
            print(f"ERROR: X credit balance too low (${balance:.2f})", file=sys.stderr)
            return EXIT_CREDITS
        post_id = create_post(service, text)
    except XCreditsDepletedError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_CREDITS
    except (XAuthError, requests.RequestException, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_FAILED

    print(post_url(os.environ.get("X_SCREEN_NAME", "i"), post_id))
    after = _check_balance(service)
    if after is not None:
        print(f"X credit balance: ${after:.2f}")
    return EXIT_OK


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    sys.exit(run())


if __name__ == "__main__":
    main()
