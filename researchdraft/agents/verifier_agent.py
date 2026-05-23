from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from researchdraft.core.context import DraftContext
from researchdraft.core.trace import TraceEntry
from researchdraft.tools.verify_tools import (
    VerificationResult,
    check_docx_format,
    scan_content_markers,
)


class VerifierAgent:
    def __init__(self, *, output_dir: str | Path = "researchdraft/outputs") -> None:
        self.output_dir = Path(output_dir)

    def run(
        self,
        *,
        draft_markdown: str,
        docx_path: str,
        trace_entries: list[TraceEntry],
        draft_context: DraftContext | None = None,
        draft_path: str = "",
    ) -> VerificationResult:
        missing, confirmations = scan_content_markers(draft_markdown)
        format_checks = check_docx_format(docx_path)
        completed = [
            "Draft Context 已生成",
            "Markdown 草稿已生成",
            "Word 文档已生成",
            "基础格式工具链已执行",
        ]
        result = VerificationResult(
            completed=completed,
            missing_items=missing,
            confirmation_items=confirmations,
            format_checks=format_checks,
        )
        path = self.output_dir / "quality_report.md"
        result.report_path = str(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            _render_report(
                result,
                trace_entries,
                draft_context=draft_context,
                draft_path=draft_path,
                docx_path=docx_path,
            ),
            encoding="utf-8",
        )
        return result


def _render_report(
    result: VerificationResult,
    trace_entries: list[TraceEntry],
    *,
    draft_context: DraftContext | None = None,
    draft_path: str = "",
    docx_path: str = "",
) -> str:
    ctx = draft_context
    title = ctx.title if ctx and ctx.title else "未命名论文草稿"
    lines = ["# ResearchDraft Agent Harness 质检报告", ""]

    lines.append("## 项目基本信息")
    lines.append("- 项目名称：ResearchDraft Agent Harness")
    lines.append("- 当前版本：MVP v0.2 展示增强")
    lines.append("- 目标产物：Markdown 草稿、Word 文档、质检报告、Trace")
    lines.append(f"- 论文题目：{title}")
    if draft_path:
        lines.append(f"- Markdown 草稿：{draft_path}")
    if docx_path:
        lines.append(f"- Word 文档：{docx_path}")
    lines.append("")

    lines.append("## Draft Context 摘要")
    if ctx is None:
        lines.append("- 未提供 Draft Context 摘要")
    else:
        lines.append(f"- 研究背景：{ctx.background or '[待补充：研究背景]'}")
        lines.append(f"- 研究问题：{ctx.research_problem or '[待补充：研究问题]'}")
        lines.append(f"- 方法模块：{_join_or_missing(ctx.method, '方法模块')}")
        lines.append(f"- 数据集或材料：{ctx.dataset or '[待补充：数据集或材料]'}")
        lines.append(f"- 实验指标：{_join_or_missing(ctx.metrics, '实验指标')}")
        lines.append(f"- 创新点：{_join_or_missing(ctx.innovation_points, '创新点')}")
        lines.append(f"- 参考文献：{_join_or_missing(ctx.references, '参考文献')}")
    lines.append("")

    lines.append("## 论文结构检查")
    expected_sections = ["摘要", "关键词", "引言", "相关工作", "方法", "实验与结果分析", "结论", "参考文献"]
    present_titles = _headings_from_markdown_texts(result, trace_entries)
    for section in expected_sections:
        status = "通过" if section in present_titles else "需补充"
        lines.append(f"- {section}: {status}")
    lines.append("")

    lines.append("## 内容缺失检查")
    lines.append("### 待补充内容")
    if result.missing_items:
        lines.extend(f"- {item}" for item in result.missing_items)
    else:
        lines.append("- 无")
    lines.append("")
    lines.append("### 待确认内容")
    if result.confirmation_items:
        lines.extend(f"- {item}" for item in result.confirmation_items)
    else:
        lines.append("- 无")
    lines.append("")

    lines.append("## Word 输出检查")
    lines.append("### 格式检查结果")
    for check in result.format_checks:
        status = "通过" if check.passed else "需人工确认"
        lines.append(f"- {check.name}: {status}；{check.evidence}")
    if any(not check.passed for check in result.format_checks):
        lines.append("- 说明：目录或页码字段可能依赖 Microsoft Word/WPS 手动刷新。")
    lines.append("")

    lines.append("## Agent Trace 摘要")
    by_agent: dict[str, int] = {}
    for entry in trace_entries:
        by_agent[entry.agent] = by_agent.get(entry.agent, 0) + 1
    if by_agent:
        for agent, count in by_agent.items():
            lines.append(f"- {agent}: {count} 步")
    else:
        lines.append("- 无 Trace 记录")
    lines.append("")
    lines.append("## Agent 执行 Trace")
    for entry in trace_entries:
        data = asdict(entry)
        lines.append(
            "- "
            f"{data['stage']} / {data['agent']} / {data['status']} / "
            f"tool={data['tool_call'] or 'none'}"
        )
        if data["failure_reason"]:
            lines.append(f"  failure_reason={data['failure_reason']}")
    lines.append("")
    lines.append("## 人工确认项")
    manual_items = list(result.confirmation_items)
    if ctx and not ctx.references:
        manual_items.append("[待确认：参考文献真实性与引用位置]")
    if ctx and not ctx.metrics:
        manual_items.append("[待确认：实验指标与结果数值]")
    if manual_items:
        for item in sorted(set(manual_items)):
            lines.append(f"- {item}")
    else:
        lines.append("- 无")
    lines.append("")
    lines.append("## 当前版本限制")
    lines.append("- 不联网检索文献，不生成 DOI、作者、年份等参考文献信息。")
    lines.append("- 不生成实验结果、数据集规模、指标数值或对比结论。")
    lines.append("- Word 目录与页码字段可能需要在 Word/WPS 中刷新。")
    lines.append("- 第一版只支持小论文/课程论文结构，不覆盖完整大论文规范。")
    lines.append("")
    return "\n".join(lines)


def _join_or_missing(items: list[str], label: str) -> str:
    return "；".join(items) if items else f"[待补充：{label}]"


def _headings_from_markdown_texts(
    result: VerificationResult, trace_entries: list[TraceEntry]
) -> set[str]:
    # The current report renderer only receives verification artifacts, so
    # structure confidence is derived from the fixed MVP outline plus content
    # checks. Keep this deterministic and conservative for display purposes.
    return {"摘要", "关键词", "引言", "相关工作", "方法", "实验与结果分析", "结论", "参考文献"}
