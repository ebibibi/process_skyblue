"""
X Web Intent Service for Process BlueSky.

Sends each BlueSky post to Discord as two messages so it can be re-posted on X
with zero API credits:

1. A notice message: the mention, a short guide, and a desktop one-click Web
   Intent link (``x.com/intent/tweet?text=...``) in an embed. The intent link
   still opens a pre-filled composer in desktop browsers.
2. The post text on its own as a plain message. Copying that message yields the
   post text verbatim, with no surrounding markup (no mention, guide, or code
   fences). This is the reliable path on X mobile apps, where the intent deep
   link no longer opens the composer.

The post-text message is sent with embeds suppressed (``flags=4``) so URLs in
the post do not expand into link-preview cards, and with mentions disabled so
handles in the text do not ping anyone.

Keeping the copyable text in its own message (rather than a code block in the
notice) is deliberate: Discord's "copy message" on mobile returns the whole
message including any mention/guide/fences, so the text must stand alone.
"""
import requests
from urllib.parse import quote
from typing import Dict, Any, List, Optional


class XIntentService:
    """Posts X text to Discord: a desktop intent link plus a copyable text message."""

    INTENT_BASE = "https://x.com/intent/tweet"
    BLUESKY_BLUE = 0x0085FF
    # Discord rejects embed URLs longer than this.
    DISCORD_EMBED_URL_LIMIT = 2048
    # Discord rejects message bodies longer than this.
    DISCORD_CONTENT_LIMIT = 2000
    # Discord message flag: do not generate link-preview embeds for this message.
    SUPPRESS_EMBEDS = 1 << 2  # 4

    def __init__(self, webhook_url: str, mention_user_id: Optional[str] = None):
        self.webhook_url = webhook_url
        self.mention_user_id = mention_user_id

    def connect(self) -> bool:
        return True

    def post_intent(
        self, content: str, metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        if not content or not content.strip():
            return {"success": False, "error": "Empty content"}

        intent_url = f"{self.INTENT_BASE}?text={quote(content, safe='')}"

        # 1) Notice with the desktop one-click intent link.
        result = self._send(self._build_notice(intent_url))
        if not result["success"]:
            return result

        # 2) The post text, alone and copyable, split if it exceeds the limit.
        for chunk in self._split(content):
            result = self._send(self._build_text_message(chunk))
            if not result["success"]:
                return result

        return {"success": True, "id": "intent", "url": intent_url}

    def _build_notice(self, intent_url: str) -> Dict[str, Any]:
        """Notice message: mention, guide, and the desktop one-click intent link."""
        lines: List[str] = []
        if self.mention_user_id:
            lines.append(f"<@{self.mention_user_id}>")
        lines.append(
            "🐦 **Xに投稿** — 下のメッセージをコピーして貼り付け"
            "（PCは下のリンクでワンクリックも可）"
        )

        payload: Dict[str, Any] = {"content": "\n".join(lines)}

        # Desktop one-click link, only when the encoded URL fits an embed URL.
        # Long (e.g. Japanese) posts can exceed the limit; then the link is
        # dropped and the copyable text message still gets the user there.
        if len(intent_url) <= self.DISCORD_EMBED_URL_LIMIT:
            payload["embeds"] = [
                {
                    "title": "▶ PCはここをクリックしてXで投稿",
                    "url": intent_url,
                    "color": self.BLUESKY_BLUE,
                    "footer": {"text": "BlueSky → X 半自動同期"},
                }
            ]

        if self.mention_user_id:
            payload["allowed_mentions"] = {"users": [self.mention_user_id]}
        else:
            payload["allowed_mentions"] = {"parse": []}
        return payload

    def _build_text_message(self, chunk: str) -> Dict[str, Any]:
        """A message containing only the post text, ready to copy verbatim.

        Embeds are suppressed so URLs in the post do not expand into preview
        cards, and mentions are disabled so handles in the text do not ping.
        """
        return {
            "content": chunk,
            "allowed_mentions": {"parse": []},
            "flags": self.SUPPRESS_EMBEDS,
        }

    def _split(self, content: str) -> List[str]:
        """Split content into chunks that each fit one Discord message body.

        Chunks carry no added markers, so each message stays copyable verbatim;
        concatenating them in order reproduces the original text exactly.
        """
        limit = self.DISCORD_CONTENT_LIMIT
        if len(content) <= limit:
            return [content]
        return [content[i : i + limit] for i in range(0, len(content), limit)]

    def _send(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            response = requests.post(self.webhook_url, json=payload, timeout=10)
            if response.status_code == 204:
                return {"success": True}
            return {
                "success": False,
                "error": f"Discord webhook returned {response.status_code}: {response.text[:200]}",
            }
        except requests.RequestException as e:
            return {"success": False, "error": str(e)}

    def disconnect(self) -> None:
        pass
