"""Shared scaffolding for Tools that wrap a single ``thesis_formatter``
function.

The pattern is always:

    1. Snapshot before the call (``ctx.snapshot_mgr.take``)
    2. Call the legacy function with ``(raw_doc, cfg, ...)``
    3. Mark the styles / paragraphs / sections it touched as dirty
    4. Catch *any* exception and convert into ``ToolResult(ok=False)``

This module does **not** define any Tool itself; concrete wrappers live
in body_tools / heading_tools / caption_tools / ... and call into here.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable

from .base import ToolContext, ToolResult


def run_legacy(
    *,
    name: str,
    doc,
    ctx: ToolContext,
    legacy_fn: Callable[..., Any],
    extra_args: tuple = (),
    extra_kwargs: dict | None = None,
    dirty_styles: Iterable[str] = (),
    dirty_sections: Iterable[int] = (),
    after_save_path: str | None = None,
) -> ToolResult:
    """Run *legacy_fn(raw_doc, cfg, *extra_args, **extra_kwargs)* under a
    snapshot, with uniform exception handling.

    ``dirty_styles`` / ``dirty_sections`` are recorded into
    ``DocumentModel.last_changes`` so the resulting ``ToolResult`` can
    report what changed without each Tool re-implementing the bookkeeping.
    """
    snapshot_mgr = ctx.snapshot_mgr
    token = snapshot_mgr.take(doc, tool_name=name) if snapshot_mgr else None

    try:
        cfg = ctx.config or {}
        with doc.write() as writer:
            raw_doc = writer.raw
            result = legacy_fn(raw_doc, cfg, *extra_args, **(extra_kwargs or {}))
            for style_name in dirty_styles:
                writer.mark_style_dirty(style_name)
            for sec_idx in dirty_sections:
                writer.mark_section_dirty(sec_idx)
        if after_save_path:
            doc.save(after_save_path)
        cs = doc.last_changes
        message = "ok"
        # Some legacy functions return a list of human-readable changes;
        # surface the count for traceability without echoing user content.
        if isinstance(result, list):
            message = f"{name}: {len(result)} change(s)"
        return ToolResult(
            ok=True,
            message=message,
            changed_paragraphs=[{"paragraph_index": i} for i in cs.paragraphs],
            changed_styles=list(cs.styles),
            changed_sections=list(cs.sections),
            rollback_token=token,
        )
    except Exception as exc:
        return ToolResult(
            ok=False,
            message=f"{name} failed: {exc}",
            rollback_token=token,
        )
