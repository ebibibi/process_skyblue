"""Tests for the two-step X re-authorisation helper."""

from __future__ import annotations

import base64
import hashlib
import json
import stat
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

import pytest

from process_bluesky import x_authorize


def test_pkce_challenge_is_s256_of_verifier() -> None:
    verifier, challenge = x_authorize.pkce_pair()
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    assert challenge == expected
    assert 43 <= len(verifier) <= 128


def test_start_writes_private_pending_file_and_url(tmp_path) -> None:
    pending = tmp_path / "data/x_authorize.json"
    url = x_authorize.start("cid", "http://localhost:8765/callback", pending)
    query = parse_qs(urlparse(url).query)
    data = json.loads(pending.read_text())
    assert query["scope"] == [x_authorize.SCOPES]
    assert "tweet.write" in query["scope"][0]
    assert query["state"] == [data["state"]]
    assert stat.S_IMODE(pending.stat().st_mode) == 0o600


def test_parse_redirect_checks_state() -> None:
    assert x_authorize.parse_redirect("http://localhost/cb?state=s&code=c", "s") == "c"
    with pytest.raises(ValueError, match="state"):
        x_authorize.parse_redirect("http://localhost/cb?state=other&code=c", "s")
    with pytest.raises(ValueError, match="error"):
        x_authorize.parse_redirect("http://localhost/cb?error=access_denied&state=s", "s")


def test_finish_persists_tokens_and_removes_pending(tmp_path) -> None:
    env = tmp_path / ".env"
    env.write_text("X_ACCESS_TOKEN=old\nX_REFRESH_TOKEN=old\nOTHER=keep\n")
    pending = tmp_path / "data/x_authorize.json"
    x_authorize.start("cid", "http://localhost:8765/callback", pending)
    state = json.loads(pending.read_text())["state"]
    response = MagicMock(status_code=200)
    response.json.return_value = {"access_token": "A", "refresh_token": "R",
                                  "scope": "tweet.read tweet.write users.read offline.access"}
    with patch.object(x_authorize.requests, "post", return_value=response) as post:
        scope = x_authorize.finish("cid", "secret", f"http://localhost:8765/callback?state={state}&code=C",
                                   pending, env)
    assert "tweet.write" in scope
    assert post.call_args.kwargs["data"]["code"] == "C"
    assert "X_ACCESS_TOKEN=A" in env.read_text() and "OTHER=keep" in env.read_text()
    assert not pending.exists()
