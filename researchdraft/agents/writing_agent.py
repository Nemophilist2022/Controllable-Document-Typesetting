from __future__ import annotations

import json
import re
from typing import Any

from researchdraft.core.context import DraftContext
from researchdraft.tools.draft_tools import (
    build_keywords,
    confirmation_marker,
    llm_prompt,
    missing_marker,
)


SYSTEM_PROMPT = (
    "You are ResearchDraft WritingAgent. Return JSON only with key markdown. "
    "Use only the supplied DraftContext. Do not fabricate experimental results, "
    "dataset scale, metric values, or references. Mark missing facts as "
    "[待补充：...] or [待确认：...]."
)


class WritingAgent:
    def __init__(self, llm_client=None) -> None:
        self.llm_client = llm_client

    def run(self, ctx: DraftContext, outline: dict[str, Any]) -> str:
        draft = self._try_llm(ctx, outline)
        if not draft:
            draft = self._template_draft(ctx, outline)
        return self._enforce_required_markers(ctx, draft)

    def _try_llm(self, ctx: DraftContext, outline: dict[str, Any]) -> str:
        client = self.llm_client
        if client is None or not hasattr(client, "complete"):
            return ""
        try:
            payload = client.complete(
                llm_prompt(ctx, outline), schema={"system_prompt": SYSTEM_PROMPT}
            )
        except Exception:
            return ""
        markdown = payload.get("markdown") if isinstance(payload, dict) else None
        if not isinstance(markdown, str) or not markdown.strip():
            return ""
        if _looks_fabricated(ctx, markdown):
            return ""
        return markdown.strip() + "\n"

    def _template_draft(self, ctx: DraftContext, outline: dict[str, Any]) -> str:
        title = ctx.title or missing_marker("title")
        keywords = "；".join(build_keywords(ctx))
        method_text = "；".join(ctx.method) if ctx.method else missing_marker("method")
        metrics_text = "；".join(ctx.metrics) if ctx.metrics else missing_marker("metrics")
        refs_text = (
            "\n".join(f"[{i}] {ref}" for i, ref in enumerate(ctx.references, 1))
            if ctx.references
            else missing_marker("references")
        )
        dataset_text = ctx.dataset or f"{missing_marker('dataset')}；{confirmation_marker('数据集规模')}"

        sections = [
            f"# {title}",
            "",
            "## 摘要",
            (
                f"本文围绕“{ctx.research_problem or missing_marker('research_problem')}”展开。"
                f"研究背景为：{ctx.background or missing_marker('background')}。"
                f"方法上，本文计划采用{method_text}。"
                "由于第一版系统只基于用户提供材料生成草稿，所有未提供的信息均保留为人工补充标记。"
            ),
            "",
            "## 关键词",
            keywords,
            "",
            "## 引言",
            (
                f"{ctx.background or missing_marker('background')} "
                f"本文关注的问题是：{ctx.research_problem or missing_marker('research_problem')}。"
                "草稿仅整理用户输入内容，不扩展未经确认的事实。"
            ),
            "",
            "## 相关工作",
            (
                "本节用于梳理与研究问题相关的已有工作。"
                f"{missing_marker('references') if not ctx.references else '已有参考文献将在正式写作时逐条对应到相关工作论述。'}"
            ),
            "",
            "## 方法",
            f"本文拟采用的方法模块包括：{method_text}。",
            f"创新点包括：{'；'.join(ctx.innovation_points) if ctx.innovation_points else missing_marker('innovation_points')}。",
            "",
            "## 实验与结果分析",
            f"数据集或材料：{dataset_text}。",
            f"实验指标：{metrics_text}。",
            "实验结果、指标数值和对比结论需要由用户提供后再写入，本文不自动生成。",
            "",
            "## 结论",
            (
                "本文形成了基于用户材料的科研论文草稿生成流程。"
                "后续需要根据质检报告补充缺失材料，并人工确认数据、指标和引用。"
            ),
            "",
            "## 参考文献",
            refs_text,
            "",
        ]
        return "\n".join(sections)

    @staticmethod
    def _enforce_required_markers(ctx: DraftContext, draft: str) -> str:
        additions: list[str] = []
        if not ctx.metrics and "[待补充：实验指标]" not in draft:
            additions.append("[待补充：实验指标]")
        if not ctx.references and "[待补充：参考文献]" not in draft:
            additions.append("[待补充：参考文献]")
        if not ctx.dataset and "[待确认：数据集规模]" not in draft:
            additions.append("[待确认：数据集规模]")
        if not additions:
            return draft
        return draft.rstrip() + "\n\n## 自动质检标记\n" + "\n".join(additions) + "\n"


def _looks_fabricated(ctx: DraftContext, markdown: str) -> bool:
    if not ctx.references and re.search(r"^\s*\[\d+\]\s+.+\d{4}", markdown, re.M):
        return True
    if not ctx.metrics and re.search(r"\b\d+(?:\.\d+)?\s*%", markdown):
        return True
    return False
