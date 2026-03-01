"""
Tests for DiscordLogService.
"""
import pytest
from unittest.mock import patch, MagicMock
from process_skyblue.services.discord_log_service import DiscordLogService


class TestDiscordLogService:
    """Test cases for DiscordLogService."""

    def setup_method(self):
        self.service = DiscordLogService(
            webhook_url="https://discordapp.com/api/webhooks/test/token"
        )

    def test_connect_always_returns_true(self):
        assert self.service.connect() is True

    def test_disconnect_does_nothing(self):
        self.service.disconnect()  # Should not raise

    def test_get_service_name(self):
        assert self.service.get_service_name() == "DiscordLogService"

    @patch("process_skyblue.services.discord_log_service.requests.post")
    def test_post_content_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_post.return_value = mock_response

        result = self.service.post_content("Hello from BlueSky!")

        assert result["success"] is True
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        payload = call_kwargs.kwargs["json"] if "json" in call_kwargs.kwargs else call_kwargs[1]["json"]
        assert payload["username"] == "BlueSkyBot"
        assert payload["content"] == "Hello from BlueSky!"

    @patch("process_skyblue.services.discord_log_service.requests.post")
    def test_post_content_failure(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        mock_post.return_value = mock_response

        result = self.service.post_content("Hello!")

        assert result["success"] is False
        assert "400" in result["error"]

    @patch("process_skyblue.services.discord_log_service.requests.post")
    def test_post_content_network_error(self, mock_post):
        import requests
        mock_post.side_effect = requests.RequestException("Connection refused")

        result = self.service.post_content("Hello!")

        assert result["success"] is False
        assert "Connection refused" in result["error"]

    def test_post_empty_content(self):
        result = self.service.post_content("")
        assert result["success"] is False

    def test_post_whitespace_content(self):
        result = self.service.post_content("   ")
        assert result["success"] is False
