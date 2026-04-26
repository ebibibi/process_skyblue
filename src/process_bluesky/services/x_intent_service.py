"""
X Web Intent Service for Process BlueSky.

Instead of posting via X API, generates a Web Intent URL and notifies
Discord so the user can post with one click. Zero API credits required.
"""
import requests
from urllib.parse import quote
from typing import Dict, Any, Optional


class XIntentService:
    """Generates X Web Intent URLs and sends them to Discord."""

    INTENT_BASE = "https://x.com/intent/tweet"
    BLUESKY_BLUE = 0x0085FF

    def __init__(self, webhook_url: str, mention_user_id: Optional[str] = None):
        self.webhook_url = webhook_url
        self.mention_user_id = mention_user_id

    def connect(self) -> bool:
        return True

    DISCORD_EMBED_URL_LIMIT = 2048

    def post_intent(
        self, content: str, metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        intent_url = f"{self.INTENT_BASE}?text={quote(content, safe='')}"

        preview = content[:200] + ("…" if len(content) > 200 else "")

        if len(intent_url) <= self.DISCORD_EMBED_URL_LIMIT:
            description = f"```\n{preview}\n```\n**[▶ クリックしてXで投稿]({intent_url})**"
            embed_url = intent_url
        else:
            description = f"```\n{preview}\n```\n⚠️ テキストが長いためリンクを分離\n\n▶ クリックしてXで投稿:\n{intent_url}"
            embed_url = self.INTENT_BASE

        payload = {
            "embeds": [
                {
                    "title": "🐦 Xに投稿する",
                    "url": embed_url,
                    "description": description,
                    "color": self.BLUESKY_BLUE,
                    "footer": {"text": "BlueSky → X 半自動同期"},
                }
            ],
        }

        if self.mention_user_id:
            payload["content"] = f"<@{self.mention_user_id}>"
            payload["allowed_mentions"] = {"users": [self.mention_user_id]}

        try:
            response = requests.post(self.webhook_url, json=payload, timeout=10)
            if response.status_code == 204:
                return {"success": True, "id": "intent", "url": intent_url}
            return {
                "success": False,
                "error": f"Discord webhook returned {response.status_code}: {response.text[:200]}",
            }
        except requests.RequestException as e:
            return {"success": False, "error": str(e)}

    def disconnect(self) -> None:
        pass
