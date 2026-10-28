"""Mirror new owned X posts to one Discord channel using the existing X reader.

The first successful read sets a baseline without reposting history. Keep the
Discord cursor independent of the X → BlueSky cursor and never call X's write API.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Sequence

import requests
from dotenv import dotenv_values, load_dotenv

from process_bluesky.services.x_input_service import XInputService
from process_bluesky.services.x_text import expand_urls, post_url
from process_bluesky.x_mirror import persist_tokens

logger = logging.getLogger(__name__)
MAX_POSTS_PER_RUN = 15
MAX_MESSAGE_LENGTH = 2000
RATE_LIMIT_RETRIES = 3
MAX_RATE_LIMIT_WAIT_SECONDS = 30.0


def select_posts(posts: Sequence[dict[str, Any]], watermark: str | None) -> list[dict[str, Any]]:
    """Return the next batch in chronological order, without skipping backlog."""
    if watermark is None:
        return []
    return sorted(
        (post for post in posts if int(post["id"]) > int(watermark)),
        key=lambda post: int(post["id"]),
    )[:MAX_POSTS_PER_RUN]


def load_state(path: Path) -> dict[str, str]:
    """Return the saved cursor (and pinned channel), or an empty state."""
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def check_channel(state: dict[str, str], channel_id: str) -> None:
    """Refuse to continue a cursor into a different channel than it was built for.

    A manual run with a stale ``--channel-id`` would otherwise advance the
    shared cursor while posting elsewhere, and the scheduled job could never
    resend those posts to the right channel.
    """
    pinned = state.get("channel_id")
    if pinned is not None and pinned != channel_id:
        raise RuntimeError(
            f"State file is pinned to channel {pinned}, not {channel_id}; "
            "use the scheduled job's channel or a separate state file"
        )


def save_watermark(path: Path, post_id: str, channel_id: str) -> None:
    """Atomically persist the latest delivered post (or initial baseline)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump({"watermark": post_id, "channel_id": channel_id}, output)
            output.flush()
            os.fsync(output.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def message_for(post: dict[str, Any], screen_name: str) -> str:
    """Show the original X text and a source link, without user-controlled pings."""
    metadata = post.get("metadata") or {}
    text = expand_urls(post.get("content", ""), metadata.get("urls") or [])
    url = post_url(screen_name, post["id"])
    header = "📝 Xの投稿\n"
    suffix = f"\n{url}"
    max_text = MAX_MESSAGE_LENGTH - len(header) - len(suffix)
    if len(text) > max_text:
        text = text[: max_text - 1] + "…"
    return header + text + suffix


def _retry_after_seconds(response: requests.Response) -> float:
    try:
        seconds = float(response.json().get("retry_after", 1.0))
    except (ValueError, AttributeError):
        seconds = float(response.headers.get("Retry-After", 1.0))
    return min(max(seconds, 0.0), MAX_RATE_LIMIT_WAIT_SECONDS)


def send_post(token: str, channel_id: str, message: str) -> None:
    """Discord Bot API: only a confirmed success advances the cursor.

    Draining a backlog sends many messages in a row, so Discord may answer
    429. Wait for its ``retry_after`` and resend the same message.
    """
    for attempt in range(RATE_LIMIT_RETRIES + 1):
        response = requests.post(
            f"https://discord.com/api/v10/channels/{channel_id}/messages",
            headers={"Authorization": f"Bot {token}"},
            json={"content": message, "allowed_mentions": {"parse": []}},
            timeout=20,
        )
        if response.status_code != 429 or attempt == RATE_LIMIT_RETRIES:
            break
        wait = _retry_after_seconds(response)
        logger.warning("Discord rate limited; retrying in %.1fs", wait)
        time.sleep(wait)
    response.raise_for_status()


def run(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--bot-env-file", required=True)
    parser.add_argument("--channel-id", required=True)
    parser.add_argument("--state-file", required=True)
    args = parser.parse_args(argv)
    if not args.channel_id.isdecimal():
        parser.error("channel-id must be a Discord snowflake")

    env_path = Path(args.env_file).expanduser().resolve()
    load_dotenv(env_path, override=True)
    bot_path = Path(args.bot_env_file).expanduser().resolve()
    # Do not load every variable from the bot env file (it also contains
    # unrelated secrets). dotenv_values returns the token without exporting it.
    state_file = Path(args.state_file)
    state = load_state(state_file)
    check_channel(state, args.channel_id)
    token = dotenv_values(bot_path).get("DISCORD_BOT_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_BOT_TOKEN is missing")
    screen_name = os.environ["X_SCREEN_NAME"]
    service = XInputService(
        user_id=os.environ["X_USER_ID"],
        access_token=os.environ["X_ACCESS_TOKEN"],
        refresh_token=os.environ["X_REFRESH_TOKEN"],
        client_id=os.environ["X_CLIENT_ID"],
        client_secret=os.environ["X_CLIENT_SECRET"],
        token_persister=persist_tokens(str(env_path)),
    )
    watermark = state.get("watermark")
    if watermark is None:
        posts = service.get_latest_posts()
        if not posts:
            logger.info("No X posts returned; leaving cursor unchanged")
            return 0
        newest_id = max(posts, key=lambda post: int(post["id"]))["id"]
        save_watermark(state_file, newest_id, args.channel_id)
        logger.info("Initial baseline: %s (no historical posts forwarded)", newest_id)
        return 0

    # Page through the whole gap so a backlog longer than one page (after an
    # outage) is still forwarded in order. If the page cap runs out, some
    # posts may be missing: stop rather than silently skipping them.
    posts, complete = service.get_posts_since(watermark)
    if not complete:
        raise RuntimeError(
            "X has more posts newer than cursor than the page cap; manual gap review required"
        )
    if not posts:
        logger.info("No new X posts; leaving cursor unchanged")
        return 0

    batch = select_posts(posts, watermark)
    for post in batch:
        send_post(token, args.channel_id, message_for(post, screen_name))
        save_watermark(state_file, post["id"], args.channel_id)
        logger.info("Sent X post %s to Discord", post["id"])
    if len(batch) == MAX_POSTS_PER_RUN:
        logger.warning("Batch limit reached; remaining posts will be sent next run")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(run())
