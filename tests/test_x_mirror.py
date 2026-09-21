"""Tests for the X → BlueSky mirror.

Focused on the parts that fail silently in production: the cold-start
watermark, ordering (threads break without it), byte-offset facets, and
truncation.
"""
from __future__ import annotations

import json

import pytest

from process_bluesky.core.x_mirror_state import PostedRef, XMirrorState
from process_bluesky.services.x_input_service import XInputService
from process_bluesky.services.x_text import (
    build_text,
    expand_urls,
    find_links,
    truncate_with_source,
)
from process_bluesky.x_mirror import select_posts_to_mirror


def _post(post_id: str, replied_to: str | None = None, text: str = "hi") -> dict:
    return {
        "id": post_id,
        "content": text,
        "timestamp": "2026-09-21T00:00:00.000Z",
        "author": "x",
        "metadata": {"replied_to": replied_to, "quoted": None, "urls": []},
    }


# --- watermark -------------------------------------------------------------


def test_first_run_mirrors_nothing(tmp_path):
    """A cold start must not replay history into a live timeline."""
    state = XMirrorState(str(tmp_path / "s.json"))
    assert not state.is_initialised
    assert select_posts_to_mirror([_post("100"), _post("200")], state) == []


def test_only_posts_newer_than_watermark_are_mirrored(tmp_path):
    state = XMirrorState(str(tmp_path / "s.json"))
    state.initialise("200")

    selected = select_posts_to_mirror([_post("100"), _post("200"), _post("300")], state)

    assert [p["id"] for p in selected] == ["300"]


def test_watermark_never_moves_backwards(tmp_path):
    """A retry handing back an older id must not cause a re-post."""
    state = XMirrorState(str(tmp_path / "s.json"))
    state.initialise("200")
    state.advance_watermark("300")
    state.advance_watermark("250")

    assert state.watermark == "300"


def test_watermark_survives_reload(tmp_path):
    path = str(tmp_path / "s.json")
    XMirrorState(path).initialise("200")

    assert XMirrorState(path).watermark == "200"


def test_already_mirrored_posts_are_not_repeated(tmp_path):
    state = XMirrorState(str(tmp_path / "s.json"))
    state.initialise("100")
    state.record_posted("300", PostedRef("u", "c", "u", "c"))

    assert select_posts_to_mirror([_post("300"), _post("400")], state) == [_post("400")]


# --- ordering --------------------------------------------------------------


def test_posts_are_mirrored_oldest_first(tmp_path):
    """X returns newest first. Replying before the parent exists breaks threads."""
    state = XMirrorState(str(tmp_path / "s.json"))
    state.initialise("100")

    selected = select_posts_to_mirror(
        [_post("500"), _post("300", replied_to="200"), _post("400")], state
    )

    assert [p["id"] for p in selected] == ["300", "400", "500"]


def test_runaway_is_capped(tmp_path):
    state = XMirrorState(str(tmp_path / "s.json"))
    state.initialise("0")

    selected = select_posts_to_mirror([_post(str(i)) for i in range(1, 100)], state)

    assert len(selected) == 15


# --- text ------------------------------------------------------------------


def test_tco_links_are_expanded():
    text = "見て https://t.co/abc123"
    urls = [{"url": "https://t.co/abc123", "expanded_url": "https://example.com/real"}]

    assert expand_urls(text, urls) == "見て https://example.com/real"


def test_long_post_keeps_a_link_back_and_fits():
    text = "あ" * 400
    result = truncate_with_source(text, "https://x.com/ebi/status/1")

    assert len(result) <= 300
    assert result.endswith("https://x.com/ebi/status/1")


def test_short_post_is_untouched():
    assert truncate_with_source("短い", "https://x.com/ebi/status/1") == "短い"


def test_facet_offsets_are_bytes_not_characters():
    """Japanese text makes the two differ; character offsets mislocate the link."""
    text = "これは日本語 https://example.com です"
    (start, end, url) = find_links(text)[0]

    assert url == "https://example.com"
    assert text.encode("utf-8")[start:end].decode("utf-8") == url
    assert start != text.index(url)  # would pass by accident on ASCII-only text


def test_build_text_expands_and_bounds():
    post = _post("42", text="x " + "ん" * 400 + " https://t.co/s")
    post["metadata"]["urls"] = [
        {"url": "https://t.co/s", "expanded_url": "https://example.com/long"}
    ]

    result = build_text(post, "ebi")

    assert len(result) <= 300


# --- token refresh ---------------------------------------------------------


def test_refresh_persists_before_adopting_new_tokens(monkeypatch, tmp_path):
    """X refresh tokens are single-use.

    If persistence fails after the in-memory tokens are replaced, the next
    start reads a revoked token and authentication is dead for good. The write
    must happen first, and its failure must propagate.
    """

    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"access_token": "new_at", "refresh_token": "new_rt"}

    monkeypatch.setattr(
        "process_bluesky.services.x_input_service.requests.post",
        lambda *a, **k: Response(),
    )

    def failing_persister(access_token, refresh_token):
        raise OSError("disk full")

    service = XInputService(
        user_id="1",
        access_token="old_at",
        refresh_token="old_rt",
        client_id="cid",
        client_secret="cs",
        token_persister=failing_persister,
    )

    with pytest.raises(OSError):
        service.refresh_access_token()

    assert service.access_token == "old_at"
    assert service.refresh_token == "old_rt"


def test_refresh_adopts_tokens_after_successful_persist(monkeypatch):
    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"access_token": "new_at", "refresh_token": "new_rt"}

    monkeypatch.setattr(
        "process_bluesky.services.x_input_service.requests.post",
        lambda *a, **k: Response(),
    )
    saved = {}

    service = XInputService(
        user_id="1",
        access_token="old_at",
        refresh_token="old_rt",
        client_id="cid",
        client_secret="cs",
        token_persister=lambda a, r: saved.update(access=a, refresh=r),
    )
    service.refresh_access_token()

    assert saved == {"access": "new_at", "refresh": "new_rt"}
    assert service.access_token == "new_at"


# --- state file ------------------------------------------------------------


def test_state_file_is_valid_json_after_write(tmp_path):
    path = tmp_path / "s.json"
    state = XMirrorState(str(path))
    state.initialise("1")
    state.record_posted("2", PostedRef("at://u", "cid1", "at://r", "cid0"))

    loaded = json.loads(path.read_text(encoding="utf-8"))

    assert loaded["watermark"] == "1"
    assert loaded["posted"]["2"]["root_uri"] == "at://r"
