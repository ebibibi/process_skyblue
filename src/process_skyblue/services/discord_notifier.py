"""
Discord Notifier for Process SkyBlue.

Sends notifications to Discord via webhook for error alerts and monitoring.
"""
import requests
from typing import Optional


class DiscordNotifier:
    """Discord webhook notifier for error alerts."""

    def __init__(self, webhook_url: str):
        """
        Initialize Discord notifier.

        Args:
            webhook_url: Discord webhook URL
        """
        self.webhook_url = webhook_url

    def send_error_notification(
        self,
        error_type: str,
        message: str,
        timestamp: str
    ) -> bool:
        """
        Send error notification to Discord.

        Args:
            error_type: Type of error (e.g., "Error", "Exception")
            message: Error message
            timestamp: ISO format timestamp

        Returns:
            True if notification was sent successfully
        """
        try:
            payload = {
                "content": "Process SkyBlue Error",
                "embeds": [{
                    "title": f"{error_type}",
                    "description": message[:2000] if len(message) > 2000 else message,
                    "color": 15158332,  # Red color
                    "timestamp": timestamp,
                    "footer": {
                        "text": "Process SkyBlue"
                    }
                }]
            }

            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=10
            )

            return response.status_code == 204

        except Exception as e:
            # Don't raise - just return False to avoid cascading failures
            print(f"Failed to send Discord notification: {str(e)}")
            return False

    def send_success_notification(
        self,
        title: str,
        message: str,
        timestamp: Optional[str] = None
    ) -> bool:
        """
        Send success notification to Discord.

        Args:
            title: Notification title
            message: Notification message
            timestamp: Optional ISO format timestamp

        Returns:
            True if notification was sent successfully
        """
        try:
            payload = {
                "embeds": [{
                    "title": title,
                    "description": message[:2000] if len(message) > 2000 else message,
                    "color": 5763719,  # Green color
                    "footer": {
                        "text": "Process SkyBlue"
                    }
                }]
            }

            if timestamp:
                payload["embeds"][0]["timestamp"] = timestamp

            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=10
            )

            return response.status_code == 204

        except Exception as e:
            print(f"Failed to send Discord notification: {str(e)}")
            return False
