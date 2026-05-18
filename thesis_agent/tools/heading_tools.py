"""Heading-related tools.

- ``tool_assign_heading_styles``       — auto-promote chapter/section
  paragraphs to Heading{1..4}
- ``tool_renumber_headings``           — fix gaps in heading numbering
- ``tool_normalize_heading_spacing``   — apply space_before / space_after
  per the profile
- ``tool_setup_multilevel_list``       — wire Heading{1..4} into a Word
  multilevel list so editing a heading auto-renumbers downstream
"""

from __future__ import annotations

from typing import Any

from thesis_formatter._common import (
    _ALIGN_MAP,
    apply_paragraph_spacing,
    parse_length,
    set_style_font,
)
from thesis_formatter.headings import (
    auto_assign_heading_styles,
    normalize_heading_spacing,
    renumber_headings,
)
from thesis_formatter.numbering import setup_multilevel_list

from ._legacy import run_legacy
from .base import ToolContext, ToolResult

_INPUT_SCHEMA_EMPTY: dict[str, Any] = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}

_INPUT_SCHEMA_PRESERVE_LOOK: dict[str, Any] = {
    "type": "object",
    "properties": {
        "preserve_look": {"type": "boolean", "default": False},
    },
    "additionalProperties": False,
}


# ---------------------------------------------------------------------------
# tool_assign_heading_styles (existing)
# ---------------------------------------------------------------------------

class AssignHeadingStyles:
    name = "tool_assign_heading_styles"
    description = (
        "Detect chapter/section paragraphs and apply Heading1..Heading4 "
        "styles. Backs rule heading.h1.style_present."
    )
    input_schema = _INPUT_SCHEMA_PRESERVE_LOOK
    requires: list[str] = []
    idempotent = True

    # KNOWN LIMITATION (C2):
    # The legacy ``auto_assign_heading_styles`` matches chapter headings
    # via a permissive regex (``^第\s*\d+\s*章``) that also matches TOC
    # entries like ``第一章 绪论 ............ 1`` and promotes them to
    # Heading 1. This affects real theses that contain a styled TOC
    # before tool runs. Two safe workarounds for callers:
    #   1. Make sure TOC paragraphs use the ``TOC 1`` style before this
    #      tool runs (legacy auto_assign skips paragraphs that already
    #      have a non-default style).
    #   2. If you control the input text, avoid the ``第N章`` literal
    #      in TOC entries until v0.3 ships a fix.
    # The fix lives in ``thesis_formatter.headings.auto_assign_heading_styles``;
    # touching it would alter behaviour for every existing thesis-format
    # CLI user, so it stays out of the MVP Tool layer.

    def run(self, doc, params: dict[str, Any], ctx: ToolContext) -> ToolResult:
        token = ctx.snapshot_mgr.take(doc, tool_name=self.name) if ctx.snapshot_mgr else None
        try:
            return self._run_inner(doc, params, ctx, token)
        except Exception as exc:
            return ToolResult(ok=False, message=str(exc), rollback_token=token)

    def _run_inner(self, doc, params, ctx, token) -> ToolResult:
        cfg = ctx.config or {}
        preserve_look = bool(params.get("preserve_look", False))
        with doc.write() as writer:
            raw_doc = writer.raw
            changes = auto_assign_heading_styles(
                raw_doc, cfg, preserve_look=preserve_look
            )
            for i, para in enumerate(raw_doc.paragraphs):
                if para.style and para.style.name.lower().startswith("heading"):
                    writer._model._record_paragraph(i)  # type: ignore[attr-defined]
            for level in (1, 2, 3, 4):
                writer.mark_style_dirty(f"Heading {level}")

        cs = doc.last_changes
        return ToolResult(
            ok=True,
            message=f"auto-assigned {len(changes)} heading style(s)",
            changed_paragraphs=[{"paragraph_index": i} for i in cs.paragraphs],
            changed_styles=list(cs.styles),
            warnings=[],
            rollback_token=token,
        )


# ---------------------------------------------------------------------------
# tool_renumber_headings
# ---------------------------------------------------------------------------

class RenumberHeadings:
    name = "tool_renumber_headings"
    description = (
        "Fix gaps in heading numbering (e.g. 1, 1.1, 1.3 → 1, 1.1, 1.2). "
        "No-op for paragraphs whose ids appear in skip_para_ids."
    )
    input_schema = _INPUT_SCHEMA_EMPTY
    requires: list[str] = ["tool_assign_heading_styles"]
    idempotent = True

    def run(self, doc, params: dict[str, Any], ctx: ToolContext) -> ToolResult:
        return run_legacy(
            name=self.name,
            doc=doc,
            ctx=ctx,
            legacy_fn=renumber_headings,
            dirty_styles=("Heading 1", "Heading 2", "Heading 3", "Heading 4"),
        )


# ---------------------------------------------------------------------------
# tool_normalize_heading_spacing
# ---------------------------------------------------------------------------

class NormalizeHeadingSpacing:
    name = "tool_normalize_heading_spacing"
    description = (
        "Apply heading space_before / space_after from the profile to "
        "all Heading{1..4} paragraphs."
    )
    input_schema = _INPUT_SCHEMA_EMPTY
    requires: list[str] = ["tool_assign_heading_styles"]
    idempotent = True

    def run(self, doc, params: dict[str, Any], ctx: ToolContext) -> ToolResult:
        result = run_legacy(
            name=self.name,
            doc=doc,
            ctx=ctx,
            legacy_fn=normalize_heading_spacing,
            dirty_styles=("Heading 1", "Heading 2", "Heading 3", "Heading 4"),
        )
        if not result.ok:
            return result

        try:
            changed = _apply_heading_style_config(doc, ctx.config or {})
        except Exception as exc:
            return ToolResult(
                ok=False,
                message=str(exc),
                rollback_token=result.rollback_token,
                warnings=list(result.warnings),
            )

        styles = set(result.changed_styles)
        styles.update(changed)
        return ToolResult(
            ok=True,
            message="heading styles normalized",
            changed_paragraphs=list(result.changed_paragraphs),
            changed_styles=sorted(styles),
            changed_sections=list(result.changed_sections),
            warnings=list(result.warnings),
            rollback_token=result.rollback_token,
        )


# ---------------------------------------------------------------------------
# tool_setup_multilevel_list
# ---------------------------------------------------------------------------

class SetupMultilevelList:
    name = "tool_setup_multilevel_list"
    description = (
        "Bind Heading{1..4} styles to a Word multilevel list so inserts "
        "auto-renumber. Idempotent: re-running adds a fresh list def."
    )
    input_schema = _INPUT_SCHEMA_EMPTY
    requires: list[str] = ["tool_assign_heading_styles"]
    idempotent = True

    def run(self, doc, params: dict[str, Any], ctx: ToolContext) -> ToolResult:
        return run_legacy(
            name=self.name,
            doc=doc,
            ctx=ctx,
            legacy_fn=setup_multilevel_list,
            dirty_styles=("Heading 1", "Heading 2", "Heading 3", "Heading 4"),
        )


TOOLS = [
    AssignHeadingStyles(),
    RenumberHeadings(),
    NormalizeHeadingSpacing(),
    SetupMultilevelList(),
]


def _apply_heading_style_config(doc, cfg: dict[str, Any]) -> list[str]:
    """Apply H1-H4 style font/size/bold/alignment from profile config.

    The legacy helper named ``normalize_heading_spacing`` only normalizes
    paragraph text spacing. The RuleSet also binds heading font/size/bold
    checks to this tool, so the wrapper owns the profile style sync.
    """
    changed: list[str] = []
    fonts = cfg.get("fonts", {}) or {}
    sizes = cfg.get("sizes", {}) or {}
    headings = cfg.get("headings", {}) or {}
    latin = fonts.get("latin", "Times New Roman")

    with doc.write() as writer:
        raw_doc = writer.raw
        for level in (1, 2, 3, 4):
            style_name = f"Heading {level}"
            h_key = f"h{level}"
            try:
                style = raw_doc.styles[style_name]
            except KeyError:
                continue

            h_cfg = headings.get(h_key, {}) or {}
            east_asia = fonts.get(h_key)
            size = sizes.get(h_key)
            bold = h_cfg.get("bold")
            if bold == "keep":
                bold = None

            if east_asia is not None and size is not None:
                set_style_font(
                    style,
                    east_asia=east_asia,
                    size_pt=parse_length(size),
                    bold=bold,
                    latin=latin,
                )

            pf = style.paragraph_format
            align = h_cfg.get("align")
            if align in _ALIGN_MAP:
                pf.alignment = _ALIGN_MAP[align]
            if "space_before" in h_cfg:
                apply_paragraph_spacing(pf, "before", h_cfg.get("space_before"))
            if "space_after" in h_cfg:
                apply_paragraph_spacing(pf, "after", h_cfg.get("space_after"))

            writer.mark_style_dirty(style_name)
            changed.append(style_name)

    return changed
