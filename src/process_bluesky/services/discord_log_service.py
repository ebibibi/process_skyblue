"""
Discord Log Output Service for Process BlueSky.

Posts BlueSky content to a Discord channel via webhook.
"""
import requests
from typing import Dict, Any, Optional
from process_bluesky.services.base_output_service import BaseOutputService


class DiscordLogService(BaseOutputService):
    """Posts BlueSky content to a Discord channel via webhook."""

    BLUESKY_AVATAR_URL = "https://bsky.app/static/apple-touch-icon.png"

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def connect(self) -> bool:
        return True

    def post_content(
        self, content: str, metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        if not self.validate_content(content):
            return {"success": False, "error": "Empty content"}

        payload: Dict[str, Any] = {
            "username": "BlueSkyBot",
            "avatar_url": self.BLUESKY_AVATAR_URL,
            "content": content,
        }

        try:
            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=10,
            )

            if response.status_code == 204:
                return {"success": True, "id": None}

            return {
                "success": False,
                "error": f"Discord webhook returned {response.status_code}: {response.text[:200]}",
            }
        except requests.RequestException as e:
            return {"success": False, "error": str(e)}

    def disconnect(self) -> None:
        pass
