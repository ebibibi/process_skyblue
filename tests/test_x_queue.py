"""No network is used by these tests."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from process_bluesky import x_discord, x_queue

LINK = "https://youtu.be/abc"
QUEUED = f"Hyper-Vの検証環境、AIが6回転んでコマンド1行に\n{LINK}\n#HyperV #ClaudeCode"


def item(key: str = "a", body: str = QUEUED, created_at: str = "2026-11-06T00:00:00Z") -> dict:
    return {"key": key, "body": body, "created_at": created_at}


def post(identifier: int, text: str, timestamp: str = "2026-11-06T01:00:00.000Z", urls=()) -> dict:
    return {
        "id": str(identifier),
        "content": text,
        "timestamp": timestamp,
        "metadata": {"urls": list(urls)},
    }


def short_link_post(identifier: int, text: str) -> dict:
    return post(
        identifier,
        f"{text}\nhttps://t.co/xyz",
        urls=[{"url": "https://t.co/xyz", "expanded_url": LINK}],
    )


def test_a_post_sent_as_queued_matches_through_its_short_link() -> None:
    posted = short_link_post(1, "Hyper-Vの検証環境、AIが6回転んでコマンド1行に\n#HyperV #ClaudeCode")
    assert x_queue.find_matches([item()], [posted]) == [(item(), posted)]


def test_a_post_edited_in_the_compose_box_still_matches() -> None:
    posted = short_link_post(1, "Hyper-Vの検証環境、AIに任せたら6回転んだ話\n#HyperV #ClaudeCode")
    assert len(x_queue.find_matches([item()], [posted])) == 1


def test_html_escapes_and_width_do_not_hide_a_match() -> None:
    queued = "Ｑ＆Ａ: R&D の話を動画にしました、ぜひ見てください"
    assert x_queue.similarity(queued, "Q&amp;A: R&amp;D の話を動画にしました、ぜひ見てください") == 1.0


def test_an_unrelated_post_with_no_shared_link_does_not_match() -> None:
    assert x_queue.find_matches([item()], [post(1, "今日はいい天気でした。散歩してきます")]) == []


def test_the_same_link_with_unrelated_words_does_not_match() -> None:
    assert x_queue.find_matches([item()], [post(1, f"おすすめの一本です、ぜひ {LINK}")]) == []


def test_without_a_link_the_words_must_be_nearly_the_same() -> None:
    queued = "今週のMicrosoftの変更点をまとめました。管理者は確認してください"
    assert x_queue.similarity(queued, queued.replace("確認して", "見て")) >= 0.85
    assert x_queue.similarity(queued, "今週のAWSの障害の話をまとめました。運用担当の人向けです") == 0.0


def test_a_text_with_no_words_and_no_shared_link_never_matches() -> None:
    assert x_queue.similarity("https://example.com/a", "https://example.com/b") == 0.0
    assert x_queue.similarity("", "anything") == 0.0
    assert x_queue.similarity("https://example.com/a", "https://example.com/a") == 1.0


def test_a_post_older_than_the_queued_text_is_not_that_text_being_sent() -> None:
    older = short_link_post(1, "Hyper-Vの検証環境、AIが6回転んでコマンド1行に\n#HyperV #ClaudeCode")
    assert x_queue.find_matches([item(created_at="2026-11-06T02:00:00Z")], [older]) == []


def test_each_post_resolves_one_item_and_the_best_pair_wins() -> None:
    near = item("near", body="今週のMicrosoftの変更点をまとめました。管理者は要確認です")
    exact = item("exact", body="今週のMicrosoftの変更点をまとめました。管理者は確認してください")
    posted = post(1, "今週のMicrosoftの変更点をまとめました。管理者は確認してください")
    assert x_queue.find_matches([near, exact], [posted]) == [(exact, posted)]


def _response(status: int, payload: dict | None = None) -> MagicMock:
    response = MagicMock(status_code=status)
    response.json.return_value = payload or {}
    if status >= 400:
        response.raise_for_status.side_effect = requests.HTTPError(str(status))
    return response


def test_report_resolves_the_item_with_a_link_to_the_post() -> None:
    posted = short_link_post(42, "Hyper-Vの検証環境、AIが6回転んでコマンド1行に\n#HyperV #ClaudeCode")
    with patch.object(x_queue.requests, "get", return_value=_response(200, {"items": [item("k:1")]})), patch.object(
        x_queue.requests, "patch", return_value=_response(200)
    ) as resolve:
        assert x_queue.report_posts("http://relay/", [posted], "owner") is True
    assert resolve.call_args.args[0] == "http://relay/api/pages/x-posts/items/k%3A1"
    assert resolve.call_args.kwargs["json"] == {
        "state": "done",
        "resolved_by": "x-post-watch",
        "result_url": "https://x.com/owner/status/42",
    }


def test_report_treats_a_page_that_does_not_exist_yet_as_nothing_queued() -> None:
    with patch.object(x_queue.requests, "get", return_value=_response(404)):
        assert x_queue.report_posts("http://relay", [post(1, "x")], "owner") is True


@pytest.mark.parametrize(
    "failure",
    [
        {"side_effect": requests.ConnectionError("down")},
        {"return_value": _response(500)},
        {"return_value": _response(200, {"unexpected": []})},
    ],
)
def test_report_says_to_retry_when_the_queue_cannot_be_read(failure: dict) -> None:
    with patch.object(x_queue.requests, "get", **failure):
        assert x_queue.report_posts("http://relay", [post(1, "x")], "owner") is False


def _args(tmp_path: Path) -> list[str]:
    env = tmp_path / "x.env"
    env.write_text("\n".join(f"{key}=test" for key in (
        "X_SCREEN_NAME", "X_USER_ID", "X_ACCESS_TOKEN", "X_REFRESH_TOKEN",
        "X_CLIENT_ID", "X_CLIENT_SECRET",
    )), encoding="utf-8")
    bot = tmp_path / "bot.env"
    bot.write_text("DISCORD_BOT_TOKEN=test\n", encoding="utf-8")
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"watermark": "7"}), encoding="utf-8")
    return ["--env-file", str(env), "--bot-env-file", str(bot), "--channel-id", "123",
            "--state-file", str(state), "--queue-api-url", "http://relay",
            "--queue-state-file", str(tmp_path / "queue.json")]


def test_a_queue_outage_neither_stops_the_mirror_nor_loses_posts(tmp_path: Path) -> None:
    args = _args(tmp_path)
    queue_state = tmp_path / "queue.json"
    posts = [post(9, "second"), post(8, "first")]
    with patch.object(x_discord, "XInputService") as service, patch.object(
        x_discord, "send_post"
    ) as send, patch.object(x_discord, "report_posts") as report:
        service.return_value.get_posts_since.side_effect = lambda since: (
            [p for p in posts if int(p["id"]) > int(since)], True
        )
        report.return_value = False
        assert x_discord.run(args) == 0
        assert send.call_count == 2
        assert json.loads((tmp_path / "state.json").read_text())["watermark"] == "9"
        assert json.loads(queue_state.read_text())["watermark"] == "7"

        # The mirror has moved on; the queue is read again from where it stopped.
        report.return_value = True
        assert x_discord.run(args) == 0
        service.return_value.get_posts_since.assert_called_with("7")
        assert [p["id"] for p in report.call_args.args[1]] == ["9", "8"]
        assert send.call_count == 2
        assert json.loads(queue_state.read_text())["watermark"] == "9"

        # Caught up: back to reading only what is new.
        assert x_discord.run(args) == 0
        service.return_value.get_posts_since.assert_called_with("9")
        assert report.call_count == 2


def test_the_queue_is_left_alone_without_its_arguments(tmp_path: Path) -> None:
    args = _args(tmp_path)[:-4]
    with patch.object(x_discord, "XInputService") as service, patch.object(
        x_discord, "send_post"
    ), patch.object(x_discord, "report_posts") as report:
        service.return_value.get_posts_since.return_value = ([post(8, "x")], True)
        assert x_discord.run(args) == 0
    report.assert_not_called()


def test_the_queue_arguments_go_together(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        x_discord.run(_args(tmp_path)[:-2])
