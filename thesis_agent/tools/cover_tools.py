"""Cover / declaration tools.

- ``tool_insert_cover_and_declaration`` — generate the cover page and
  declaration pages from the profile, with optional ``--skip-cover``
"""

from __future__ import annotations

from typing import Any

from thesis_formatter.cover import insert_cover_and_declaration

from ._legacy import run_legacy
from .base import ToolContext, ToolResult


class InsertCoverAndDeclaration:
    name = "tool_insert_cover_and_declaration"
    description = (
        "Generate cover page (with optional logo) and declaration pages "
        "from the profile. Pass skip_cover=true to keep declarations only."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "config_path": {"type": ["string", "null"]},
            "skip_cover": {"type": "boolean", "default": False},
        },
        "additionalProperties": False,
    }
    requires: list[str] = []
    idempotent = False  # writes new paragraphs each call

    def run(self, doc, params: dict[str, Any], ctx: ToolContext) -> ToolResult:
        return run_legacy(
            name=self.name,
            doc=doc,
            ctx=ctx,
            legacy_fn=insert_cover_and_declaration,
            extra_kwargs={
                "config_path": params.get("config_path"),
                "skip_cover": bool(params.get("skip_cover", False)),
            },
        )


TOOLS = [InsertCoverAndDeclaration()]
