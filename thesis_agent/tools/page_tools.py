"""Page-layout / page-number tools.

- ``tool_normalize_sections``         — apply margins / gutter / header
  & footer distance to every section
- ``tool_setup_page_numbers``         — full page-number setup (may
  insert a section break before the first body heading)
- ``tool_setup_page_numbers_strict``  — strict variant for the
  "单独改页码" mode: never inserts new section breaks, only adjusts
  existing sections
"""

from __future__ import annotations

from typing import Any

from thesis_formatter.page import (
    normalize_sections,
    setup_page_numbers,
    setup_page_numbers_strict,
)

from ._legacy import run_legacy
from .base import ToolContext, ToolResult


_INPUT_SCHEMA_EMPTY: dict[str, Any] = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}


class NormalizeSections:
    name = "tool_normalize_sections"
    description = (
        "Apply page margins / gutter / header & footer distances from "
        "the profile to every section in the document."
    )
    input_schema = _INPUT_SCHEMA_EMPTY
    requires: list[str] = []
    idempotent = True

    def run(self, doc, params: dict[str, Any], ctx: ToolContext) -> ToolResult:
        return run_legacy(
            name=self.name,
            doc=doc,
            ctx=ctx,
            legacy_fn=normalize_sections,
        )


class SetupPageNumbers:
    name = "tool_setup_page_numbers"
    description = (
        "Full page-number setup: front-matter / body sections, formats "
        "(roman / decimal), positions, optional section break insertion."
    )
    input_schema = _INPUT_SCHEMA_EMPTY
    requires: list[str] = []
    idempotent = True

    def run(self, doc, params: dict[str, Any], ctx: ToolContext) -> ToolResult:
        return run_legacy(
            name=self.name,
            doc=doc,
            ctx=ctx,
            legacy_fn=setup_page_numbers,
        )


class SetupPageNumbersStrict:
    name = "tool_setup_page_numbers_strict"
    description = (
        "Strict page-number adjustment: only modifies existing sections; "
        "never inserts new section breaks. Backing the GUI's "
        "'单独改页码' mode."
    )
    input_schema = _INPUT_SCHEMA_EMPTY
    requires: list[str] = []
    idempotent = True

    def run(self, doc, params: dict[str, Any], ctx: ToolContext) -> ToolResult:
        return run_legacy(
            name=self.name,
            doc=doc,
            ctx=ctx,
            legacy_fn=setup_page_numbers_strict,
        )


TOOLS = [
    NormalizeSections(),
    SetupPageNumbers(),
    SetupPageNumbersStrict(),
]
