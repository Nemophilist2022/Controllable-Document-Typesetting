"""tool_insert_toc — wrap ``thesis_formatter.toc.insert_toc``.

Depends on heading styles being present, so declares
``requires=["tool_assign_heading_styles"]`` (R3.4 contract).
"""

from __future__ import annotations

from typing import Any

from thesis_formatter.toc import ensure_toc_styles, insert_toc

from .base import ToolContext, ToolResult

_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        # Future: depth override / regenerate flag. None for MVP.
    },
    "additionalProperties": False,
}


class InsertToc:
    name = "tool_insert_toc"
    description = (
        "Insert or refresh the table of contents. Requires heading "
        "styles to already be assigned."
    )
    input_schema = _INPUT_SCHEMA
    requires: list[str] = ["tool_assign_heading_styles"]
    idempotent = True

    def run(self, doc, params: dict[str, Any], ctx: ToolContext) -> ToolResult:
        token = ctx.snapshot_mgr.take(doc, tool_name=self.name) if ctx.snapshot_mgr else None
        try:
            cfg = ctx.config or {}
            with doc.write() as writer:
                raw_doc = writer.raw
                ensure_toc_styles(raw_doc, cfg)
                insert_toc(raw_doc, cfg)
                writer.mark_style_dirty("TOC Heading")
                writer.mark_style_dirty("TOC 1")
            return ToolResult(
                ok=True,
                message="TOC inserted/updated",
                changed_styles=list(doc.last_changes.styles),
                rollback_token=token,
            )
        except Exception as exc:
            return ToolResult(ok=False, message=str(exc), rollback_token=token)


TOOLS = [InsertToc()]
