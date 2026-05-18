"""Header / footer tools.

- ``tool_setup_headers`` — full header setup with section partitioning
  per the profile (front / body / odd-even split / chapter title field)
"""

from __future__ import annotations

from typing import Any

from thesis_formatter.headers import setup_headers

from ._legacy import run_legacy
from .base import ToolContext, ToolResult


class SetupHeaders:
    name = "tool_setup_headers"
    description = (
        "Configure document headers per the profile: scope (body only / "
        "all pages), odd-even split, chapter title field, optional "
        "underline. No-op when header_footer.enabled=false."
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
            legacy_fn=setup_headers,
        )


TOOLS = [SetupHeaders()]
