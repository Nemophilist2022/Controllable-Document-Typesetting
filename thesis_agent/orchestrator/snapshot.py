"""SnapshotManager — per-step docx snapshots with LRU eviction (R6.4, R11.4, R11.5)."""

from __future__ import annotations

import os
import shutil
import tempfile
import uuid
from collections import deque


class SnapshotManager:
    """Owns a directory of docx snapshots taken before each Tool call.

    The orchestrator calls :meth:`take` *before* invoking a Tool. On
    success, the snapshot is kept (subject to LRU eviction). On Tool
    failure the orchestrator calls :meth:`rollback_last` to restore the
    document state.
    """

    def __init__(self, work_dir: str | None = None, capacity: int = 10) -> None:
        if work_dir is None:
            work_dir = tempfile.mkdtemp(prefix="thesis_agent_snap_")
        self._dir = os.path.join(work_dir, "snapshots")
        os.makedirs(self._dir, exist_ok=True)
        self._capacity = max(1, int(capacity))
        self._records: deque[dict] = deque()  # each: {token, path, step, tool_name}
        self._step = 0

    @property
    def directory(self) -> str:
        return self._dir

    # ------------------------------------------------------------------
    # take / rollback / save
    # ------------------------------------------------------------------

    def take(self, doc, *, tool_name: str = "") -> str:
        """Persist the current docx state to disk, return a token."""
        token = str(uuid.uuid4())
        fname = f"step_{self._step}_{tool_name or 'unknown'}_pre.docx"
        path = os.path.join(self._dir, fname)
        # DocumentModel.save() is the canonical write path; if anyone
        # passes a raw python-docx Document we fall back to its save().
        if hasattr(doc, "save"):
            doc.save(path)
        else:
            raise TypeError(f"snapshot target has no .save(): {type(doc).__name__}")

        self._records.append(
            {"token": token, "path": path, "step": self._step, "tool_name": tool_name}
        )
        self._step += 1
        self._evict_if_needed()
        return token

    def rollback_last(self, doc) -> bool:
        """Restore *doc* to the most recent snapshot. Returns True on success."""
        if not self._records:
            return False
        record = self._records[-1]
        path = record["path"]
        if not os.path.isfile(path):
            return False
        # The DocumentModel API supports re-loading by re-instantiating.
        if hasattr(doc, "_doc"):
            from docx import Document
            doc._doc = Document(path)
            return True
        return False

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    def _evict_if_needed(self) -> None:
        while len(self._records) > self._capacity:
            oldest = self._records.popleft()
            try:
                os.remove(oldest["path"])
            except OSError:
                pass

    def __len__(self) -> int:
        return len(self._records)
