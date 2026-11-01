"""Tests for the one-shot X post CLI."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from process_bluesky import x_post
from process_bluesky.services.x_input_service import XCreditsDepletedError


def _response(status: int, payload: dict | None = None) -> MagicMock:
    response = MagicMock()
    response.status_code = status
    response.json.return_value = payload or {}
    response.text = str(payload)
    return response


def test_weighted_length_counts_cjk_double_and_url_as_23() -> None:
    assert x_post.weighted_length("abc") == 3
    assert x_post.weighted_length("日本語") == 6
    assert x_post.weighted_length("見て https://www.youtube.com/watch?v=abc") == 4 + 1 + 23


def test_url_stops_at_japanese_punctuation() -> None:
    assert x_post.weighted_length("https://x.com/a。") == 23 + 2


def test_validate_rejects_over_limit_and_empty() -> None:
    with pytest.raises(ValueError, match="too long"):
        x_post.validate_text("あ" * 141)
    with pytest.raises(ValueError, match="empty"):
        x_post.validate_text("  \n")
    assert x_post.validate_text(" " + "あ" * 140 + "\n") == "あ" * 140


def test_create_post_refreshes_once_on_401() -> None:
    service = MagicMock(access_token="old")
    service.refresh_access_token.side_effect = lambda: setattr(service, "access_token", "new")
    responses = [_response(401), _response(201, {"data": {"id": "99"}})]
    with patch.object(x_post.requests, "post", side_effect=responses) as post:
        assert x_post.create_post(service, "hello") == "99"
    assert post.call_count == 2
    assert post.call_args.kwargs["headers"]["Authorization"] == "Bearer new"


def test_create_post_raises_on_402() -> None:
    service = MagicMock(access_token="t")
    with patch.object(x_post.requests, "post", return_value=_response(402)):
        with pytest.raises(XCreditsDepletedError):
            x_post.create_post(service, "hello")


def test_run_rejects_long_text_without_calling_api(capsys) -> None:
    with patch.object(x_post.requests, "post") as post:
        code = x_post.run(["--env-file", "/nonexistent", "--text", "あ" * 200])
    assert code == x_post.EXIT_INVALID
    post.assert_not_called()
    assert "too long" in capsys.readouterr().err


def test_run_refuses_when_balance_is_low(tmp_path, monkeypatch) -> None:
    env = tmp_path / ".env"
    env.write_text("X_USER_ID=1\nX_ACCESS_TOKEN=a\nX_REFRESH_TOKEN=r\nX_CLIENT_ID=c\nX_CLIENT_SECRET=s\n")
    with patch.object(x_post.XInputService, "get_credit_balance", return_value=0.1), \
            patch.object(x_post.requests, "post") as post:
        code = x_post.run(["--env-file", str(env), "--text", "hello"])
    assert code == x_post.EXIT_CREDITS
    post.assert_not_called()


def test_run_posts_and_prints_url(tmp_path, capsys) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "X_USER_ID=1\nX_ACCESS_TOKEN=a\nX_REFRESH_TOKEN=r\nX_CLIENT_ID=c\n"
        "X_CLIENT_SECRET=s\nX_SCREEN_NAME=ebi\n")
    with patch.object(x_post.XInputService, "get_credit_balance", return_value=4.0), \
            patch.object(x_post.requests, "post", return_value=_response(201, {"data": {"id": "7"}})):
        code = x_post.run(["--env-file", str(env), "--text", "hello"])
    assert code == x_post.EXIT_OK
    assert "https://x.com/ebi/status/7" in capsys.readouterr().out
