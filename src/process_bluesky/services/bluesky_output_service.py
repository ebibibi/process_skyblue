"""BlueSky output service — posts mirrored content, keeping threads intact.

An X reply carries only the parent's id. A BlueSky reply needs two strong refs:
the immediate parent *and* the root of the thread. The root cannot be derived
from the parent, so it is carried forward through the mapping in XMirrorState.

A reply whose parent was never mirrored (written before the mirror started, or
authored by somebody else) cannot be threaded. It is posted standalone rather
than dropped — losing the author's words is worse than losing the thread shape.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from process_bluesky.core.x_mirror_state import PostedRef, XMirrorState
from process_bluesky.services.base_output_service import BaseOutputService
from process_bluesky.services.x_text import find_links

try:
    from atproto import Client, models
except ImportError:  # pragma: no cover - exercised only where atproto is absent
    Client = None
    models = None

logger = logging.getLogger(__name__)


class BlueskyOutputService(BaseOutputService):
    """Posts to BlueSky, reconstructing reply structure where possible."""

    def __init__(self, identifier: str, password: str, state: XMirrorState) -> None:
        self.identifier = identifier
        self.password = password
        self.state = state
        self.client: Optional[Any] = None

    def connect(self) -> bool:
        if Client is None:
            logger.error("atproto is not installed")
            return False
        self.client = Client()
        self.client.login(self.identifier, self.password)
        return True

    def disconnect(self) -> None:
        """Drop the client. The atproto session needs no explicit close."""
        self.client = None

    def _build_facets(self, text: str) -> Optional[list]:
        """Make links clickable. Without facets they render as plain text."""
        spans = find_links(text)
        if not spans:
            return None
        return [
            models.AppBskyRichtextFacet.Main(
                index=models.AppBskyRichtextFacet.ByteSlice(
                    byte_start=start, byte_end=end
                ),
                features=[models.AppBskyRichtextFacet.Link(uri=url)],
            )
            for start, end, url in spans
        ]

    def resolve_reply_ref(self, replied_to_x_id: Optional[str]):
        """Build the ReplyRef for an X reply, or None if it cannot be threaded.

        Returns ``(reply_ref, parent_ref)``. ``parent_ref`` is returned so the
        caller can carry the thread root forward for the next reply in the
        chain.
        """
        if not replied_to_x_id:
            return None, None

        parent = self.state.get_posted(replied_to_x_id)
        if parent is None:
            logger.info(
                "parent %s was never mirrored; posting standalone", replied_to_x_id
            )
            return None, None

        reply_ref = models.AppBskyFeedPost.ReplyRef(
            parent=models.ComAtprotoRepoStrongRef.Main(uri=parent.uri, cid=parent.cid),
            root=models.ComAtprotoRepoStrongRef.Main(
                uri=parent.root_uri, cid=parent.root_cid
            ),
        )
        return reply_ref, parent

    def post_content(
        self, content: str, metadata: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """Post ``content``; thread it when the parent is known.

        ``metadata`` must carry ``x_id`` and may carry ``replied_to``.
        """
        metadata = metadata or {}
        x_id = metadata.get("x_id")

        try:
            reply_ref, parent = self.resolve_reply_ref(metadata.get("replied_to"))
            response = self.client.send_post(
                text=content,
                reply_to=reply_ref,
                facets=self._build_facets(content),
                langs=["ja"],
            )

            # A reply inherits the thread root; a standalone post *is* the root.
            if parent is not None:
                root_uri, root_cid = parent.root_uri, parent.root_cid
            else:
                root_uri, root_cid = response.uri, response.cid

            if x_id:
                self.state.record_posted(
                    x_id,
                    PostedRef(
                        uri=response.uri,
                        cid=response.cid,
                        root_uri=root_uri,
                        root_cid=root_cid,
                    ),
                )
            return {"success": True, "id": response.uri, "error": ""}

        except Exception as exc:  # noqa: BLE001 - reported upward, never swallowed
            logger.error("failed to post to BlueSky: %s", exc)
            return {"success": False, "id": "", "error": str(exc)}
