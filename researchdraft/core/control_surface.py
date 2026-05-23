from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ControlSurface:
    agent: str
    readable_keys: tuple[str, ...]
    writable_keys: tuple[str, ...]
    allowed_tools: tuple[str, ...] = ()


CONTROL_SURFACES = {
    "InterviewAgent": ControlSurface(
        "InterviewAgent", readable_keys=(), writable_keys=("context",)
    ),
    "PlanningAgent": ControlSurface(
        "PlanningAgent", readable_keys=("context",), writable_keys=("outline",)
    ),
    "WritingAgent": ControlSurface(
        "WritingAgent",
        readable_keys=("context", "outline"),
        writable_keys=("draft_markdown", "draft_path"),
    ),
    "WordFormatAgent": ControlSurface(
        "WordFormatAgent",
        readable_keys=("draft_markdown",),
        writable_keys=("docx_path",),
        allowed_tools=(
            "markdown_to_docx",
            "tool_assign_heading_styles",
            "tool_format_body",
            "tool_insert_toc",
            "tool_setup_page_numbers",
            "tool_format_references",
            "tool_word_postprocess",
        ),
    ),
    "VerifierAgent": ControlSurface(
        "VerifierAgent",
        readable_keys=("draft_markdown", "docx_path", "trace_entries"),
        writable_keys=("report_path", "verification"),
    ),
}

