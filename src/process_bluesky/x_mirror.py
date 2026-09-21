"""X → BlueSky mirror. One invocation = one check cycle.

Deliberately separate from ``main.py`` (BlueSky → Discord): the two mirrors
share no cursor and no state file, so a fault in one cannot stall or corrupt
the other.

First run records a watermark and posts nothing. Backfilling months of history
into a live timeline is not a recoverable mistake.
"""
from __future__ import annotations

import logging
import os
import sys
from typing import Any

from process_bluesky.core.x_mirror_state import XMirrorState
from process_bluesky.services.bluesky_output_service import BlueskyOutputService
from process_bluesky.services.x_input_service import (
    XCreditsDepletedError,
    XInputService,
)
from process_bluesky.services.x_text import build_text

logger = logging.getLogger(__name__)

# Cap posts per run. A mapping bug or a restored backup could otherwise turn
# one cycle into a flood on a public timeline.
MAX_POSTS_PER_RUN = 15

# Warn while there is still time to act, rather than discovering it as a 402.
LOW_BALANCE_USD = 0.20


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"{name} is not set")
    return value


def persist_tokens(env_path: str):
    """Return a callable that writes refreshed tokens back to the .env file.

    X refresh tokens are single-use. The moment a refresh succeeds the old
    token is dead, so the new pair must reach disk before it is adopted — see
    XInputService.refresh_access_token.
    """

    def _persist(access_token: str, refresh_token: str) -> None:
        lines = []
        with open(env_path, encoding="utf-8") as handle:
            for line in handle.read().splitlines():
                if line.startswith("X_ACCESS_TOKEN="):
                    lines.append(f"X_ACCESS_TOKEN={access_token}")
                elif line.startswith("X_REFRESH_TOKEN="):
                    lines.append(f"X_REFRESH_TOKEN={refresh_token}")
                else:
                    lines.append(line)
        tmp = f"{env_path}.tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
        os.chmod(tmp, 0o600)
        os.replace(tmp, env_path)

    return _persist


def select_posts_to_mirror(posts: list[dict[str, Any]], state: XMirrorState) -> list[dict[str, Any]]:
    """Pick what to post, oldest first.

    Ordering is not cosmetic. A reply can only be threaded once its parent
    exists on BlueSky, and X hands posts back newest first — mirroring in the
    received order breaks every thread written since the last run.
    """
    fresh = [
        post
        for post in posts
        if state.is_newer_than_watermark(post["id"]) and not state.already_mirrored(post["id"])
    ]
    fresh.sort(key=lambda post: int(post["id"]))
    return fresh[:MAX_POSTS_PER_RUN]


def run() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
    )

    # No defaults: a wrong path silently refreshes tokens into the wrong file,
    # and a wrong screen name produces source links that 404.
    env_path = _require("X_ENV_FILE")
    screen_name = _require("X_SCREEN_NAME")

    x_service = XInputService(
        user_id=_require("X_USER_ID"),
        access_token=_require("X_ACCESS_TOKEN"),
        refresh_token=_require("X_REFRESH_TOKEN"),
        client_id=_require("X_CLIENT_ID"),
        client_secret=_require("X_CLIENT_SECRET"),
        token_persister=persist_tokens(env_path),
    )

    state = XMirrorState(os.environ.get("X_MIRROR_STATE", "data/x_mirror_state.json"))

    try:
        posts = x_service.get_latest_posts()
    except XCreditsDepletedError:
        logger.error("X API credits depleted — mirror cannot run")
        return 1

    if not posts:
        logger.info("no posts returned")
        return 0

    if not state.is_initialised:
        newest = max(posts, key=lambda post: int(post["id"]))["id"]
        state.initialise(newest)
        logger.info(
            "first run: watermark set to %s, %d existing posts left alone",
            newest,
            len(posts),
        )
        return 0

    to_mirror = select_posts_to_mirror(posts, state)
    if not to_mirror:
        logger.info("nothing new")
        return 0

    output = BlueskyOutputService(
        identifier=_require("BLUESKY_IDENTIFIER"),
        password=_require("BLUESKY_PASSWORD"),
        state=state,
    )
    if not output.connect():
        logger.error("could not connect to BlueSky")
        return 1

    posted = 0
    for post in to_mirror:
        text = build_text(post, screen_name)
        result = output.post_content(
            text,
            metadata={
                "x_id": post["id"],
                "replied_to": (post.get("metadata") or {}).get("replied_to"),
            },
        )
        if not result["success"]:
            # Stop rather than skip. Advancing past a failure would strand the
            # post permanently and break every reply that depends on it.
            logger.error("stopping after failure on %s: %s", post["id"], result["error"])
            break
        state.advance_watermark(post["id"])
        posted += 1
        logger.info("mirrored %s -> %s", post["id"], result["id"])

    logger.info("mirrored %d/%d posts", posted, len(to_mirror))

    try:
        balance = x_service.get_credit_balance()
        logger.info("X credit balance: $%.4f", balance)
        if balance < LOW_BALANCE_USD:
            logger.warning("X credit balance is low: $%.4f", balance)
    except Exception as exc:  # noqa: BLE001 - balance is diagnostic, not fatal
        logger.warning("could not read credit balance: %s", exc)

    return 0


if __name__ == "__main__":
    sys.exit(run())
