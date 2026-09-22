"""Export recent posts owned by the authenticated X user.

This is a read-only adapter for downstream writing and video-planning tools.
It intentionally reuses :class:`XInputService` so authentication, credit errors,
and X's owned-read endpoint stay in one implementation.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Sequence

from dotenv import load_dotenv

from process_bluesky.services.x_input_service import XInputService
from process_bluesky.services.x_text import expand_urls, post_url
from process_bluesky.x_mirror import persist_tokens


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def filter_recent_posts(
    posts: Sequence[dict[str, Any]],
    days: int,
    limit: int,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Return at most ``limit`` posts within ``days``, newest first."""
    reference = now or datetime.now(timezone.utc)
    cutoff = reference - timedelta(days=days)
    recent = [
        post
        for post in posts
        if post.get("timestamp") and _parse_timestamp(post["timestamp"]) >= cutoff
    ]
    recent.sort(key=lambda post: _parse_timestamp(post["timestamp"]), reverse=True)
    return recent[:limit]


def prepare_posts(
    posts: Sequence[dict[str, Any]], screen_name: str
) -> list[dict[str, Any]]:
    """Create a stable, content-workflow-friendly representation."""
    prepared = []
    for post in posts:
        metadata = post.get("metadata") or {}
        prepared.append(
            {
                "id": post["id"],
                "created_at": post.get("timestamp", ""),
                "text": expand_urls(
                    post.get("content", ""), metadata.get("urls") or []
                ),
                "url": post_url(screen_name, post["id"]),
                "replied_to": metadata.get("replied_to"),
                "conversation_id": metadata.get("conversation_id"),
            }
        )
    return prepared


def render_markdown(posts: Sequence[dict[str, Any]]) -> str:
    """Render posts without altering their wording."""
    if not posts:
        return "# Recent X posts\n\nNo posts found.\n"

    blocks = ["# Recent X posts"]
    for post in posts:
        blocks.append(
            f"## {post['created_at']}\n\n{post['text']}\n\nSource: {post['url']}"
        )
    return "\n\n".join(blocks) + "\n"


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env-file", default=".env", help="dotenv file with X OAuth values"
    )
    parser.add_argument("--days", type=_positive_int, default=30)
    parser.add_argument("--limit", type=_positive_int, default=50)
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point."""
    args = _parser().parse_args(argv)
    env_path = Path(args.env_file).expanduser().resolve()
    load_dotenv(env_path, override=False)

    required = (
        "X_USER_ID",
        "X_ACCESS_TOKEN",
        "X_REFRESH_TOKEN",
        "X_CLIENT_ID",
        "X_CLIENT_SECRET",
        "X_SCREEN_NAME",
    )
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise SystemExit(f"missing required environment values: {', '.join(missing)}")

    service = XInputService(
        user_id=os.environ["X_USER_ID"],
        access_token=os.environ["X_ACCESS_TOKEN"],
        refresh_token=os.environ["X_REFRESH_TOKEN"],
        client_id=os.environ["X_CLIENT_ID"],
        client_secret=os.environ["X_CLIENT_SECRET"],
        token_persister=persist_tokens(str(env_path)),
    )
    recent = filter_recent_posts(
        service.get_latest_posts(), days=args.days, limit=args.limit
    )
    prepared = prepare_posts(recent, os.environ["X_SCREEN_NAME"])

    if args.format == "markdown":
        print(render_markdown(prepared), end="")
    else:
        print(json.dumps(prepared, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
