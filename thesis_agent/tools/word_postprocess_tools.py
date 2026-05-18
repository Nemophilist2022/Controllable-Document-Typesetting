"""tool_word_postprocess — refresh TOC / fields via Word COM.

Gracefully degrades on platforms without Word installed; in that case
returns ``ok=True`` with a warning so the orchestrator can still treat
the run as successful but record the missing post-process step.
"""

from __future__ import annotations

import os
import sys
from typing import Any

from .base import ToolContext, ToolResult

_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "mode": {"type": "string", "enum": ["full", "fields_only", "none"], "default": "full"},
        "docx_path": {"type": "string"},
    },
    "additionalProperties": False,
}


class WordPostprocess:
    name = "tool_word_postprocess"
    description = (
        "Run Word COM post-processing (TOC update / field refresh). "
        "Requires Windows + Microsoft Word; otherwise skipped."
    )
    input_schema = _INPUT_SCHEMA
    requires: list[str] = []
    idempotent = True

    def run(self, doc, params: dict[str, Any], ctx: ToolContext) -> ToolResult:
        # Postprocess works on a saved file; no DocumentModel mutation.
        # Snapshot-take is still useful so the orchestrator has a marker.
        token = ctx.snapshot_mgr.take(doc, tool_name=self.name) if ctx.snapshot_mgr else None
        mode = params.get("mode", "full")
        if mode == "none":
            return ToolResult(
                ok=True,
                message="postprocess skipped (mode=none)",
                rollback_token=token,
            )

        if sys.platform != "win32":
            return ToolResult(
                ok=True,
                message="postprocess skipped (non-Windows platform)",
                warnings=["Word COM not available on this platform"],
                rollback_token=token,
            )

        docx_path = params.get("docx_path")
        if not docx_path or not os.path.isfile(docx_path):
            return ToolResult(
                ok=False,
                message=f"docx_path missing or not found: {docx_path!r}",
                rollback_token=token,
            )

        try:
            from word_postprocess import postprocess  # local import keeps tests fast
            postprocess(docx_path, config=ctx.config or {}, mode=mode)
            return ToolResult(
                ok=True,
                message=f"postprocess({mode}) completed",
                rollback_token=token,
            )
        except Exception as exc:
            # R7.4 partial: the run succeeded, but field refresh failed.
            # We expose this as ok=True + warning so orchestrator can map
            # to "partial" instead of "failed".
            return ToolResult(
                ok=True,
                message=f"postprocess failed (non-fatal): {exc}",
                warnings=[f"manual TOC update may be needed: {exc}"],
                rollback_token=token,
            )


TOOLS = [WordPostprocess()]
