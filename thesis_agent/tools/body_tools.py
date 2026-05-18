"""tool_format_body — apply font / size / line spacing to the Normal style.

Wraps ``thesis_formatter._common.set_style_font`` plus the line-spacing
helper. Idempotent: a second invocation with the same params produces
no further mutation.
"""

from __future__ import annotations

from typing import Any

from thesis_formatter._common import (
    _ALIGN_MAP,
    apply_line_spacing,
    apply_paragraph_spacing,
    parse_length,
    set_style_font,
)

from .base import ToolContext, ToolResult


_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "east_asia_font": {"type": "string"},
        "size": {"type": ["number", "string"]},
        "line_spacing": {"type": ["number", "string"]},
        "first_line_indent": {"type": ["number", "string"]},
        "align": {"type": "string"},
        "latin_font": {"type": "string"},
    },
    "additionalProperties": False,
}


class FormatBody:
    name = "tool_format_body"
    description = (
        "Apply body font / size / line spacing / first-line indent to "
        "the Normal style. Backs rules body.font.* and body.line_spacing."
    )
    input_schema = _INPUT_SCHEMA
    requires: list[str] = []
    idempotent = True

    def run(self, doc, params: dict[str, Any], ctx: ToolContext) -> ToolResult:
        token = ctx.snapshot_mgr.take(doc, tool_name=self.name) if ctx.snapshot_mgr else None
        try:
            return self._run_inner(doc, params, token)
        except Exception as exc:  # never propagate; ToolResult always
            return ToolResult(ok=False, message=str(exc), rollback_token=token)

    def _run_inner(self, doc, params: dict[str, Any], token) -> ToolResult:
        latin_font = params.get("latin_font") or "Times New Roman"
        east_asia = params.get("east_asia_font")
        size = params.get("size")
        line_spacing = params.get("line_spacing")
        first_line_indent = params.get("first_line_indent")
        align = params.get("align")

        with doc.write() as writer:
            raw_doc = writer.raw
            try:
                normal = raw_doc.styles["Normal"]
            except KeyError:
                return ToolResult(
                    ok=False,
                    message="Normal style not found",
                    rollback_token=token,
                )

            if east_asia is not None or size is not None:
                # set_style_font requires both east_asia and size_pt; fill
                # the missing side from the current style state.
                cur_size = normal.font.size
                size_pt = parse_length(size) if size is not None else cur_size
                ea = east_asia if east_asia is not None else "宋体"
                set_style_font(
                    normal, east_asia=ea, size_pt=size_pt, bold=None, latin=latin_font
                )
                writer.mark_style_dirty("Normal")

            pf = normal.paragraph_format
            if line_spacing is not None:
                apply_line_spacing(pf, line_spacing)
                writer.mark_style_dirty("Normal")
            if first_line_indent is not None:
                pf.first_line_indent = parse_length(first_line_indent)
                writer.mark_style_dirty("Normal")
            if align is not None:
                mapped = _ALIGN_MAP.get(align)
                if mapped is not None:
                    pf.alignment = mapped
                    writer.mark_style_dirty("Normal")

        cs = doc.last_changes
        return ToolResult(
            ok=True,
            message="body style updated",
            changed_styles=list(cs.styles),
            rollback_token=token,
        )


TOOLS = [FormatBody()]
