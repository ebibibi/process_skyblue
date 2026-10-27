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
        service.return_value.get_posts_since.side_effect = lambda since_id: (
            [p for p in posts if int(p["id"]) > int(since_id)], True
        )
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


def test_run_fetches_only_posts_after_watermark(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = tmp_path / "x.env"
    env.write_text("\n".join(f"{key}=test" for key in (
        "X_SCREEN_NAME", "X_USER_ID", "X_ACCESS_TOKEN", "X_REFRESH_TOKEN",
        "X_CLIENT_ID", "X_CLIENT_SECRET",
    )), encoding="utf-8")
    bot = tmp_path / "bot.env"
    bot.write_text("DISCORD_BOT_TOKEN=test\n", encoding="utf-8")
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"watermark": "7"}), encoding="utf-8")
    args = ["--env-file", str(env), "--bot-env-file", str(bot),
            "--channel-id", "123", "--state-file", str(state)]
    with patch.object(x_discord, "XInputService") as service, patch.object(
        x_discord, "send_post"
    ) as send:
        service.return_value.get_posts_since.return_value = ([], True)
        assert x_discord.run(args) == 0
    service.return_value.get_posts_since.assert_called_once_with("7")
    service.return_value.get_latest_posts.assert_not_called()
    send.assert_not_called()
    assert json.loads(state.read_text())["watermark"] == "7"


def test_service_sends_since_id_only_when_given() -> None:
    from process_bluesky.services.x_input_service import XInputService

    service = XInputService("1", "access", "refresh", "client", "secret")
    with patch(
        "process_bluesky.services.x_input_service.requests.get"
    ) as get:
        get.return_value.status_code = 200
        get.return_value.json.return_value = {"data": []}
        assert service.get_latest_posts(since_id="42") == []
        assert get.call_args.kwargs["params"]["since_id"] == "42"
        service.get_latest_posts()
        assert "since_id" not in get.call_args.kwargs["params"]


def _service():
    from process_bluesky.services.x_input_service import XInputService

    return XInputService("1", "access", "refresh", "client", "secret")


def _page(ids, next_token=None):
    tweets = [{"id": str(i), "text": "t", "created_at": "2026-10-27T00:00:00Z"} for i in ids]
    meta = {"next_token": next_token} if next_token else {}
    return {"data": tweets, "meta": meta}


def test_get_posts_since_follows_pages_until_done() -> None:
    service = _service()
    with patch("process_bluesky.services.x_input_service.requests.get") as get:
        get.return_value.status_code = 200
        get.return_value.json.side_effect = [_page([60, 59], "n1"), _page([58])]
        posts, complete = service.get_posts_since("50")
    assert complete is True
    assert [p["id"] for p in posts] == ["60", "59", "58"]
    second = get.call_args_list[1].kwargs["params"]
    assert second["since_id"] == "50" and second["pagination_token"] == "n1"


def test_get_posts_since_reports_incomplete_at_page_cap() -> None:
    service = _service()
    with patch("process_bluesky.services.x_input_service.requests.get") as get:
        get.return_value.status_code = 200
        get.return_value.json.side_effect = [_page([60], "n1"), _page([59], "n2")]
        posts, complete = service.get_posts_since("50", max_pages=2)
    assert complete is False
    assert len(posts) == 2


def test_run_stops_when_gap_exceeds_page_cap(tmp_path: Path) -> None:
    env = tmp_path / "x.env"
    env.write_text("\n".join(f"{key}=test" for key in (
        "X_SCREEN_NAME", "X_USER_ID", "X_ACCESS_TOKEN", "X_REFRESH_TOKEN",
        "X_CLIENT_ID", "X_CLIENT_SECRET",
    )), encoding="utf-8")
    bot = tmp_path / "bot.env"
    bot.write_text("DISCORD_BOT_TOKEN=test\n", encoding="utf-8")
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"watermark": "7"}), encoding="utf-8")
    args = ["--env-file", str(env), "--bot-env-file", str(bot),
            "--channel-id", "123", "--state-file", str(state)]
    with patch.object(x_discord, "XInputService") as service, patch.object(
        x_discord, "send_post"
    ) as send:
        service.return_value.get_posts_since.return_value = ([post(9)], False)
        with pytest.raises(RuntimeError, match="page cap"):
            x_discord.run(args)
    send.assert_not_called()
    assert json.loads(state.read_text())["watermark"] == "7"
