"""X (Twitter) input service.

Reads the authenticated user's own posts. Only ``GET /2/users/{id}/tweets``
qualifies for X's "Owned Read" rate ($0.001 per resource, measured at $0.0008
on 2026-09-21) and only when authenticated as the owner of the developer app —
an app-only bearer token is charged the normal read rate instead.

Resources are deduplicated within a 24-hour UTC window, so re-fetching posts we
have already seen today is free. That makes it safe to prefer re-reading over
risking a gap.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import requests

from process_bluesky.services.base_input_service import BaseInputService

logger = logging.getLogger(__name__)

API_BASE = "https://api.x.com/2"
TOKEN_URL = "https://api.x.com/2/oauth2/token"
TIMEOUT_SECONDS = 30

TWEET_FIELDS = "created_at,text,referenced_tweets,entities,conversation_id"


class XAuthError(Exception):
    """Authentication failed and could not be recovered by refreshing."""


class XCreditsDepletedError(Exception):
    """The account is out of API credits (HTTP 402)."""


class XInputService(BaseInputService):
    """Fetches the authenticated user's own X posts."""

    def __init__(
        self,
        user_id: str,
        access_token: str,
        refresh_token: str,
        client_id: str,
        client_secret: str,
        token_persister: Optional[Any] = None,
    ) -> None:
        """
        Args:
            token_persister: called as ``(access_token, refresh_token)`` before
                the new tokens are used. X issues single-use refresh tokens, so
                if persistence fails we must fail loudly rather than continue
                with a token pair that exists only in memory — the old pair is
                already dead at that point.
        """
        self.user_id = user_id
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = client_id
        self.client_secret = client_secret
        self._persist_tokens = token_persister
        self.connected = False

    def connect(self) -> bool:
        response = self._get(f"{API_BASE}/users/me")
        self.connected = response is not None
        return self.connected

    def disconnect(self) -> None:
        """Nothing to tear down: every call is a plain stateless HTTPS request."""
        self.connected = False

    def refresh_access_token(self) -> None:
        """Exchange the refresh token for a new pair.

        X invalidates the old refresh token the moment this succeeds, and hands
        back a *new* one. Persist before adopting: if the write fails after we
        have already overwritten the in-memory tokens, the next process start
        reads a refresh token that X has already revoked, and authentication is
        dead until someone re-authorises by hand.
        """
        response = requests.post(
            TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
                "client_id": self.client_id,
            },
            auth=(self.client_id, self.client_secret),
            timeout=TIMEOUT_SECONDS,
        )
        if response.status_code != 200:
            raise XAuthError(
                f"token refresh failed: HTTP {response.status_code} {response.text[:200]}"
            )

        payload = response.json()
        new_access = payload["access_token"]
        new_refresh = payload.get("refresh_token", self.refresh_token)

        if self._persist_tokens is not None:
            self._persist_tokens(new_access, new_refresh)

        self.access_token = new_access
        self.refresh_token = new_refresh
        logger.info("X access token refreshed")

    def _get(self, url: str, params: Optional[dict] = None, _retried: bool = False):
        response = requests.get(
            url,
            headers={"Authorization": f"Bearer {self.access_token}"},
            params=params,
            timeout=TIMEOUT_SECONDS,
        )

        if response.status_code == 402:
            raise XCreditsDepletedError("X API credits depleted")

        if response.status_code == 401 and not _retried:
            self.refresh_access_token()
            return self._get(url, params, _retried=True)

        if response.status_code != 200:
            raise XAuthError(f"HTTP {response.status_code}: {response.text[:200]}")

        return response.json()

    def get_credit_balance(self) -> float:
        """Remaining prepaid credits, in USD.

        Surfaced so a runaway loop shows up as money draining rather than only
        as log volume.
        """
        payload = self._get(f"{API_BASE}/usage/credits")
        return float(payload["data"]["total_balance"])

    def get_latest_posts(self, since_timestamp: Optional[str] = None) -> list[dict[str, Any]]:
        """Return the user's recent posts, newest first, in the common format.

        ``since_timestamp`` is part of the BaseInputService contract but X
        filters by post id, not time. The caller filters against the watermark.
        """
        params = {
            "max_results": 50,
            "tweet.fields": TWEET_FIELDS,
            "exclude": "retweets",
        }
        payload = self._get(f"{API_BASE}/users/{self.user_id}/tweets", params=params)
        return [self._to_common(item) for item in payload.get("data", [])]

    @staticmethod
    def _to_common(tweet: dict[str, Any]) -> dict[str, Any]:
        referenced = tweet.get("referenced_tweets") or []
        replied_to = next(
            (ref["id"] for ref in referenced if ref["type"] == "replied_to"), None
        )
        quoted = next((ref["id"] for ref in referenced if ref["type"] == "quoted"), None)
        return {
            "id": tweet["id"],
            "content": tweet.get("text", ""),
            "timestamp": tweet.get("created_at", ""),
            "author": "x",
            "metadata": {
                "replied_to": replied_to,
                "quoted": quoted,
                "urls": (tweet.get("entities") or {}).get("urls", []),
                "conversation_id": tweet.get("conversation_id"),
            },
        }
