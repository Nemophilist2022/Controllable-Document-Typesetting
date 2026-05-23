from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from researchdraft.core.context import DraftContext


DEFAULT_SECTIONS = [
    "摘要",
    "关键词",
    "引言",
    "相关工作",
    "方法",
    "实验与结果分析",
    "结论",
    "参考文献",
]


class PlanningAgent:
    def __init__(
        self,
        template_path: str | Path = "researchdraft/templates/paper_outline.yaml",
    ) -> None:
        self.template_path = Path(template_path)

    def run(self, ctx: DraftContext) -> dict[str, Any]:
        sections = self._load_sections()
        return {
            "title": ctx.title or "【待补充：论文题目】",
            "paper_type": ctx.paper_type,
            "sections": [
                {
                    "title": name,
                    "goals": self._goals_for(name, ctx),
                }
                for name in sections
            ],
        }

    def _load_sections(self) -> list[str]:
        if not self.template_path.exists():
            return DEFAULT_SECTIONS
        data = yaml.safe_load(self.template_path.read_text("utf-8")) or {}
        return list(data.get("sections") or DEFAULT_SECTIONS)

    @staticmethod
    def _goals_for(name: str, ctx: DraftContext) -> list[str]:
        if name == "摘要":
            return ["概述背景、问题、方法、主要贡献，缺失信息显式标记"]
        if name == "方法":
            return ctx.method or ["【待补充：方法模块】"]
        if name == "实验与结果分析":
            return ["只描述用户提供的数据集、材料和指标，不编造结果"]
        if name == "参考文献":
            return ctx.references or ["【待补充：参考文献】"]
        return [f"围绕“{ctx.research_problem or '【待补充：研究问题】'}”展开"]

