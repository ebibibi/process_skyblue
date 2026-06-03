"""
Tests for XIntentService.

The service sends each post as two Discord messages: a notice (mention, guide,
desktop intent link) followed by the post text alone, so the text message can be
copied verbatim. X mobile apps no longer open intent deep links, so copy-paste
is the mobile path; the intent link stays for desktop browsers.
"""
import pytest
from unittest.mock import patch, MagicMock
from process_bluesky.services.x_intent_service import XIntentService


def _ok_response() -> MagicMock:
    response = MagicMock()
    response.status_code = 204
    return response


def _payloads(mock_post) -> list:
    return [call.kwargs["json"] for call in mock_post.call_args_list]


class TestXIntentService:
    """Test cases for XIntentService."""

    MENTION_ID = "123456789012345678"

    def setup_method(self):
        self.service = XIntentService(
            webhook_url="https://discord.com/api/webhooks/test/token",
            mention_user_id=self.MENTION_ID,
        )

    def test_connect_returns_true(self):
        assert self.service.connect() is True

    def test_disconnect_does_nothing(self):
        self.service.disconnect()  # Should not raise

    def test_empty_content_fails(self):
        assert self.service.post_intent("")["success"] is False

    def test_whitespace_content_fails(self):
        assert self.service.post_intent("   ")["success"] is False

    @patch("process_bluesky.services.x_intent_service.requests.post")
    def test_sends_notice_then_text(self, mock_post):
        mock_post.return_value = _ok_response()

        self.service.post_intent("hello world")

        assert mock_post.call_count == 2

    @patch("process_bluesky.services.x_intent_service.requests.post")
    def test_text_message_is_verbatim(self, mock_post):
        # The post-text message must equal the content exactly: no mention,
        # guide, code fences or numbering — copying it yields only the post.
        mock_post.return_value = _ok_response()
        content = "Just the post text — コピー検証 ✨"

        self.service.post_intent(content)

        text_msg = _payloads(mock_post)[1]
        assert text_msg["content"] == content

    @patch("process_bluesky.services.x_intent_service.requests.post")
    def test_text_message_suppresses_embeds_and_mentions(self, mock_post):
        mock_post.return_value = _ok_response()

        self.service.post_intent("see https://example.com/x @someone")

        text_msg = _payloads(mock_post)[1]
        assert text_msg["flags"] == 4  # SUPPRESS_EMBEDS
        assert text_msg["allowed_mentions"] == {"parse": []}

    @patch("process_bluesky.services.x_intent_service.requests.post")
    def test_long_url_in_post_survives_verbatim(self, mock_post):
        # flags=4 only suppresses the preview card; a long URL inside the post
        # must remain byte-for-byte in the copyable text message.
        mock_post.return_value = _ok_response()
        content = (
            "新しい記事を書きました→ "
            "https://example.com/very/long/path/segment?utm_source=bsky&utm_medium=social&ref=abc123 "
            "#ブログ #開発"
        )

        self.service.post_intent(content)

        assert _payloads(mock_post)[1]["content"] == content

    @patch("process_bluesky.services.x_intent_service.requests.post")
    def test_notice_includes_mention(self, mock_post):
        mock_post.return_value = _ok_response()

        self.service.post_intent("hi")

        notice = _payloads(mock_post)[0]
        assert f"<@{self.MENTION_ID}>" in notice["content"]
        assert notice["allowed_mentions"]["users"] == [self.MENTION_ID]

    @patch("process_bluesky.services.x_intent_service.requests.post")
    def test_notice_has_desktop_intent_link(self, mock_post):
        mock_post.return_value = _ok_response()

        result = self.service.post_intent("short post")

        embed = _payloads(mock_post)[0]["embeds"][0]
        assert embed["url"].startswith("https://x.com/intent/tweet?text=")
        assert embed["url"] == result["url"]

    @patch("process_bluesky.services.x_intent_service.requests.post")
    def test_intent_url_encodes_special_chars(self, mock_post):
        mock_post.return_value = _ok_response()

        result = self.service.post_intent("a b&c")

        assert "a%20b%26c" in result["url"]

    @patch("process_bluesky.services.x_intent_service.requests.post")
    def test_no_mention_disables_all_pings(self, mock_post):
        mock_post.return_value = _ok_response()
        service = XIntentService(
            webhook_url="https://discord.com/api/webhooks/test/token"
        )

        service.post_intent("hi")

        notice = _payloads(mock_post)[0]
        assert "<@" not in notice["content"]
        assert notice["allowed_mentions"] == {"parse": []}

    @patch("process_bluesky.services.x_intent_service.requests.post")
    def test_long_intent_url_drops_embed_but_keeps_text(self, mock_post):
        # Long Japanese posts encode to a URL beyond Discord's embed URL limit:
        # the desktop link is dropped, but the copyable text is still sent.
        mock_post.return_value = _ok_response()
        content = "あ" * 800  # ~7200 chars once percent-encoded

        self.service.post_intent(content)

        notice = _payloads(mock_post)[0]
        assert "embeds" not in notice
        assert _payloads(mock_post)[1]["content"] == content

    @patch("process_bluesky.services.x_intent_service.requests.post")
    def test_very_long_text_split_verbatim_in_order(self, mock_post):
        # Content beyond a single message is split, not truncated; the chunks
        # concatenate back to the original in order, each within the limit.
        mock_post.return_value = _ok_response()
        content = "x" * 4500

        result = self.service.post_intent(content)

        assert result["success"] is True
        text_msgs = [p["content"] for p in _payloads(mock_post)[1:]]
        assert "".join(text_msgs) == content
        assert all(
            len(m) <= XIntentService.DISCORD_CONTENT_LIMIT for m in text_msgs
        )

    @patch("process_bluesky.services.x_intent_service.requests.post")
    def test_stops_when_notice_fails(self, mock_post):
        failure = MagicMock()
        failure.status_code = 400
        failure.text = "Bad Request"
        mock_post.return_value = failure

        result = self.service.post_intent("hi")

        assert result["success"] is False
        assert mock_post.call_count == 1  # text not sent after notice failed

    @patch("process_bluesky.services.x_intent_service.requests.post")
    def test_webhook_failure_returns_status(self, mock_post):
        failure = MagicMock()
        failure.status_code = 400
        failure.text = "Bad Request"
        mock_post.return_value = failure

        result = self.service.post_intent("hi")

        assert result["success"] is False
        assert "400" in result["error"]

    @patch("process_bluesky.services.x_intent_service.requests.post")
    def test_network_error_returns_message(self, mock_post):
        import requests

        mock_post.side_effect = requests.RequestException("Connection refused")

        result = self.service.post_intent("hi")

        assert result["success"] is False
        assert "Connection refused" in result["error"]
