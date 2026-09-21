"""State for the X → BlueSky mirror.

Kept in its own file, separate from the BlueSky → Discord state, so that a bug
in one mirror cannot corrupt the cursor of the other.

Two things are persisted:

- ``watermark``: the newest X post id seen at the moment the mirror first ran.
  Anything at or below it is history and is never mirrored. Without this a cold
  start would dump months of posts into the timeline.
- ``posted``: X post id → the BlueSky record it became. This is what lets a
  reply on X become a reply on BlueSky instead of an orphaned post.
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Keep the map bounded. A thread deeper than this is not something we need to
# reconstruct, and an unbounded file would grow forever.
MAX_POSTED_ENTRIES = 2000


@dataclass(frozen=True)
class PostedRef:
    """Where an X post ended up on BlueSky.

    ``root_*`` is carried explicitly because BlueSky replies need both the
    immediate parent and the root of the thread, and the root is not derivable
    from the parent alone.
    """

    uri: str
    cid: str
    root_uri: str
    root_cid: str

    def as_dict(self) -> dict[str, str]:
        return {
            "uri": self.uri,
            "cid": self.cid,
            "root_uri": self.root_uri,
            "root_cid": self.root_cid,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, str]) -> "PostedRef":
        return cls(
            uri=raw["uri"],
            cid=raw["cid"],
            root_uri=raw["root_uri"],
            root_cid=raw["root_cid"],
        )


class XMirrorState:
    """Persistent state for the X → BlueSky mirror."""

    def __init__(self, path: str = "data/x_mirror_state.json") -> None:
        self.path = Path(path)
        self._watermark: Optional[str] = None
        self._posted: dict[str, PostedRef] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        self._watermark = raw.get("watermark")
        self._posted = {
            key: PostedRef.from_dict(value)
            for key, value in (raw.get("posted") or {}).items()
        }

    def _save(self) -> None:
        """Write atomically.

        A half-written state file means either a lost watermark (history gets
        replayed into the timeline) or a lost mapping (threads break). Write to
        a temp file in the same directory and rename over the target.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "watermark": self._watermark,
            "posted": {key: ref.as_dict() for key, ref in self._posted.items()},
        }
        fd, tmp_name = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, self.path)
        except BaseException:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
            raise

    @property
    def watermark(self) -> Optional[str]:
        return self._watermark

    @property
    def is_initialised(self) -> bool:
        return self._watermark is not None

    def initialise(self, newest_id: str) -> None:
        """Record the starting point without mirroring anything."""
        self._watermark = newest_id
        self._save()

    def advance_watermark(self, post_id: str) -> None:
        """Move the watermark forward. Never backwards.

        X post ids are snowflakes, so numeric comparison is chronological. A
        retry that hands us an older id must not rewind the cursor and cause a
        re-post.
        """
        if self._watermark is None or int(post_id) > int(self._watermark):
            self._watermark = post_id
            self._save()

    def is_newer_than_watermark(self, post_id: str) -> bool:
        if self._watermark is None:
            return False
        return int(post_id) > int(self._watermark)

    def get_posted(self, x_id: str) -> Optional[PostedRef]:
        return self._posted.get(x_id)

    def record_posted(self, x_id: str, ref: PostedRef) -> None:
        self._posted[x_id] = ref
        if len(self._posted) > MAX_POSTED_ENTRIES:
            # Snowflake order == chronological order, so the smallest ids are
            # the oldest entries.
            for stale in sorted(self._posted, key=int)[: len(self._posted) - MAX_POSTED_ENTRIES]:
                del self._posted[stale]
        self._save()

    def already_mirrored(self, x_id: str) -> bool:
        return x_id in self._posted
