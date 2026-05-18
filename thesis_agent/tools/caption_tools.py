"""Caption / table tools.

- ``tool_format_figure_captions`` — apply caption font/size/spacing and
  optionally inject SEQ / STYLEREF fields per the profile's caption mode
- ``tool_format_table_captions``  — same for table captions, including
  "续表" continuation handling
- ``tool_format_three_line_tables`` — table cell font + three-line
  borders (top / header / bottom)
"""

from __future__ import annotations

from typing import Any

from thesis_formatter.formatter import _format_tables
from thesis_formatter.numbering import (
    setup_figure_captions,
    setup_table_captions,
)

from ._legacy import run_legacy
from .base import ToolContext, ToolResult


_INPUT_SCHEMA_EMPTY: dict[str, Any] = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}


# ---------------------------------------------------------------------------
# tool_format_figure_captions
# ---------------------------------------------------------------------------

class FormatFigureCaptions:
    name = "tool_format_figure_captions"
    description = (
        "Format figure captions (font/size/spacing) and, if the profile "
        "uses dynamic mode, inject SEQ / STYLEREF fields."
    )
    input_schema = _INPUT_SCHEMA_EMPTY
    requires: list[str] = []
    idempotent = True

    def run(self, doc, params: dict[str, Any], ctx: ToolContext) -> ToolResult:
        return run_legacy(
            name=self.name,
            doc=doc,
            ctx=ctx,
            legacy_fn=setup_figure_captions,
        )


# ---------------------------------------------------------------------------
# tool_format_table_captions
# ---------------------------------------------------------------------------

class FormatTableCaptions:
    name = "tool_format_table_captions"
    description = (
        "Format table captions (incl. 续表) per the profile's caption "
        "settings and inject SEQ fields when caption mode is dynamic."
    )
    input_schema = _INPUT_SCHEMA_EMPTY
    requires: list[str] = []
    idempotent = True

    def run(self, doc, params: dict[str, Any], ctx: ToolContext) -> ToolResult:
        return run_legacy(
            name=self.name,
            doc=doc,
            ctx=ctx,
            legacy_fn=setup_table_captions,
        )


# ---------------------------------------------------------------------------
# tool_format_three_line_tables
# ---------------------------------------------------------------------------

class FormatThreeLineTables:
    name = "tool_format_three_line_tables"
    description = (
        "Apply three-line table formatting: top / header-bottom / bottom "
        "borders with the profile-specified weights, plus uniform cell "
        "font / line spacing."
    )
    input_schema = _INPUT_SCHEMA_EMPTY
    requires: list[str] = []
    idempotent = True

    def run(self, doc, params: dict[str, Any], ctx: ToolContext) -> ToolResult:
        return run_legacy(
            name=self.name,
            doc=doc,
            ctx=ctx,
            legacy_fn=_format_tables,
        )


TOOLS = [
    FormatFigureCaptions(),
    FormatTableCaptions(),
    FormatThreeLineTables(),
]
