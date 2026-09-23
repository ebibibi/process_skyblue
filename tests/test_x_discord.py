"""No network or real credentials are used by these regression tests."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from process_bluesky import x_discord


def post(identifier: int, text: str = "hello") -> dict:
    return {"id": str(identifier), "content": text, "metadata": {"urls": []}}


def test_select_in_order_with_bounded_batch() -> None:
    posts = [post(i) for i in range(40, 0, -1)]
    assert [p["id"] for p in x_discord.select_posts(posts, "10")] == [
        str(i) for i in range(11, 26)
    ]
    assert x_discord.select_posts(posts, None) == []


def test_message_has_link_and_safe_size() -> None:
    message = x_discord.message_for(post(123, "@everyone " + "x" * 3000), "owner")
    assert len(message) <= 2000
    assert message.endswith("https://x.com/owner/status/123")


def test_send_disables_mentions() -> None:
    with patch("process_bluesky.x_discord.requests.post") as send:
        x_discord.send_post("fake-token", "123", "@everyone")
    assert send.call_args.kwargs["json"]["allowed_mentions"] == {"parse": []}
    send.return_value.raise_for_status.assert_called_once()


def test_run_baseline_retry_and_cursor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env = tmp_path / "x.env"
    env.write_text("\n".join(f"{key}=test" for key in (
        "X_SCREEN_NAME", "X_USER_ID", "X_ACCESS_TOKEN", "X_REFRESH_TOKEN",
        "X_CLIENT_ID", "X_CLIENT_SECRET",
    )), encoding="utf-8")
    bot = tmp_path / "bot.env"
    bot.write_text("DISCORD_BOT_TOKEN=test\n", encoding="utf-8")
    state = tmp_path / "state.json"
    args = ["--env-file", str(env), "--bot-env-file", str(bot),
            "--channel-id", "123", "--state-file", str(state)]
    posts = [post(2), post(1)]
    with patch.object(x_discord, "XInputService") as service, patch.object(
        x_discord, "send_post"
    ) as send:
        service.return_value.get_latest_posts.side_effect = lambda: posts
        assert x_discord.run(args) == 0
        assert json.loads(state.read_text())["watermark"] == "2"
        send.assert_not_called()
        posts[:] = [post(4), post(3), post(2)]
        send.side_effect = [None, RuntimeError("Discord unavailable")]
        with pytest.raises(RuntimeError, match="unavailable"):
            x_discord.run(args)
        assert json.loads(state.read_text())["watermark"] == "3"
        send.reset_mock(side_effect=True)
        assert x_discord.run(args) == 0
        assert json.loads(state.read_text())["watermark"] == "4"
        assert send.call_count == 1
