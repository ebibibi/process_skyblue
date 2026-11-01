"""Re-authorise the X user token (OAuth 2.0 + PKCE) in two steps.

Needed when the stored token lacks a scope, e.g. ``x_post`` gets HTTP 403
because the token was issued for owned reads only (no ``tweet.write``).

Step 1 prints a URL. Open it while signed in to X and approve. X redirects to
the callback URI registered on the app (a localhost page that does not need to
load); copy the full address from the browser bar.

Step 2 exchanges that address for tokens and writes them to ``.env``
atomically via the same persister the other X jobs use.

    python -m process_bluesky.x_authorize --env-file .env start \
        --redirect-uri http://localhost:8765/callback
    python -m process_bluesky.x_authorize --env-file .env finish --url '<pasted URL>'

The PKCE verifier and state live in ``data/x_authorize.json`` (mode 600)
between the steps and are deleted after a successful exchange.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import secrets
import sys
from pathlib import Path
from typing import Sequence
from urllib.parse import parse_qs, urlencode, urlparse

import requests
from dotenv import load_dotenv

from process_bluesky.services.x_input_service import TIMEOUT_SECONDS, TOKEN_URL
from process_bluesky.x_mirror import persist_tokens

AUTHORIZE_URL = "https://x.com/i/oauth2/authorize"
SCOPES = "tweet.read tweet.write users.read offline.access"


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)[:96]
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def build_authorize_url(client_id: str, redirect_uri: str, state: str, challenge: str) -> str:
    query = urlencode({
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": SCOPES,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })
    return f"{AUTHORIZE_URL}?{query}"


def parse_redirect(url: str, expected_state: str) -> str:
    """Return the authorisation code, refusing a mismatched state (CSRF)."""
    params = parse_qs(urlparse(url.strip()).query)
    if "error" in params:
        raise ValueError(f"X returned an error: {params['error'][0]}")
    if params.get("state", [""])[0] != expected_state:
        raise ValueError("state does not match; start again")
    code = params.get("code", [""])[0]
    if not code:
        raise ValueError("no code in the pasted URL")
    return code


def _write_pending(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(data, handle)
    os.replace(tmp, path)


def start(client_id: str, redirect_uri: str, pending: Path) -> str:
    verifier, challenge = pkce_pair()
    state = secrets.token_urlsafe(24)
    _write_pending(pending, {"verifier": verifier, "state": state, "redirect_uri": redirect_uri})
    return build_authorize_url(client_id, redirect_uri, state, challenge)


def finish(client_id: str, client_secret: str, pasted_url: str, pending: Path, env_path: Path) -> str:
    data = json.loads(pending.read_text(encoding="utf-8"))
    code = parse_redirect(pasted_url, data["state"])
    response = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": data["redirect_uri"],
            "code_verifier": data["verifier"],
            "client_id": client_id,
        },
        auth=(client_id, client_secret),
        timeout=TIMEOUT_SECONDS,
    )
    if response.status_code != 200:
        raise RuntimeError(f"token exchange failed: HTTP {response.status_code} {response.text[:300]}")
    payload = response.json()
    persist_tokens(str(env_path))(payload["access_token"], payload["refresh_token"])
    pending.unlink(missing_ok=True)
    return str(payload.get("scope", ""))


def run(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Re-authorise the X user token")
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--pending-file", default=None)
    sub = parser.add_subparsers(dest="step", required=True)
    start_p = sub.add_parser("start")
    start_p.add_argument("--redirect-uri", required=True)
    finish_p = sub.add_parser("finish")
    finish_p.add_argument("--url", required=True)
    args = parser.parse_args(argv)

    env_path = Path(args.env_file).expanduser().resolve()
    load_dotenv(env_path, override=True)
    pending = Path(args.pending_file) if args.pending_file else env_path.parent / "data/x_authorize.json"
    client_id = os.environ["X_CLIENT_ID"]
    try:
        if args.step == "start":
            print(start(client_id, args.redirect_uri, pending))
        else:
            scope = finish(client_id, os.environ["X_CLIENT_SECRET"], args.url, pending, env_path)
            print(f"OK: tokens saved. scope={scope}")
            if "tweet.write" not in scope.split():
                print("WARNING: tweet.write is still missing; set the app to Read and write", file=sys.stderr)
                return 1
    except (OSError, ValueError, KeyError, RuntimeError, requests.RequestException) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(run())
