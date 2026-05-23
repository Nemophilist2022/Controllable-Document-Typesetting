from __future__ import annotations

import json
from typing import Any

from researchdraft.core.context import DraftContext


MISSING_LABELS = {
    "title": "论文题目",
    "background": "研究背景",
    "research_problem": "研究问题",
    "method": "方法模块",
    "dataset": "数据集或材料",
    "metrics": "实验指标",
    "innovation_points": "创新点",
    "references": "参考文献",
}


def build_keywords(ctx: DraftContext) -> list[str]:
    keywords = []
    keywords.extend(ctx.method[:2])
    keywords.extend(ctx.innovation_points[:2])
    if not keywords:
        keywords.append("科研草稿生成")
    return keywords[:5]


def missing_marker(field: str) -> str:
    return f"[待补充：{MISSING_LABELS.get(field, field)}]"


def confirmation_marker(label: str) -> str:
    return f"[待确认：{label}]"


def outline_to_markdown(outline: dict[str, Any]) -> str:
    lines = [f"# {outline.get('title', '论文草稿大纲')}", ""]
    for section in outline.get("sections", []):
        lines.append(f"## {section.get('title', '')}")
        for goal in section.get("goals", []):
            lines.append(f"- {goal}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def llm_prompt(ctx: DraftContext, outline: dict[str, Any]) -> str:
    payload = {
        "task": (
            "根据用户提供的 DraftContext 生成小论文 Markdown 草稿。"
            "不要编造实验结果、数据集规模、指标数值或参考文献。"
            "缺失信息必须使用【待补充：...】或【待确认：...】标记。"
        ),
        "draft_context": ctx.to_dict(),
        "outline": outline,
        "output": {"format": "json", "schema": {"markdown": "string"}},
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)
