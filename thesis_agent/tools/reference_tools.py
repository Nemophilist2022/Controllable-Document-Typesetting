"""Reference / bibliography tools.

- ``tool_format_references`` — apply hanging indent and cross-link
  ``[1]`` / ``[2]`` style citations to the references section
"""

from __future__ import annotations

from typing import Any

from thesis_formatter.references import apply_ref_crosslinks

from ._legacy import run_legacy
from .base import ToolContext, ToolResult


class FormatReferences:
    name = "tool_format_references"
    description = (
        "Format the references section: hanging indent per profile, "
        "and turn [n]-style citations into hyperlinks where possible."
    )
    input_schema = {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }
    requires: list[str] = []
    idempotent = True

    def run(self, doc, params: dict[str, Any], ctx: ToolContext) -> ToolResult:
        return run_legacy(
            name=self.name,
            doc=doc,
            ctx=ctx,
            legacy_fn=apply_ref_crosslinks,
        )


TOOLS = [FormatReferences()]
