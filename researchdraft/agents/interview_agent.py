from __future__ import annotations

from pathlib import Path
from typing import Callable

from researchdraft.core.context import DraftContext


QUESTIONS = [
    ("title", "1）论文题目："),
    ("background", "2）研究背景："),
    ("research_problem", "3）研究问题："),
    ("method", "4）方法模块（可用分号/逗号/换行分隔）："),
    ("dataset", "5）数据集或材料："),
    ("metrics", "6）实验指标（可用分号/逗号/换行分隔）："),
    ("innovation_points", "7）创新点（可用分号/逗号/换行分隔）："),
    ("paper_type", "8）目标论文类型（默认 short_paper）："),
    ("output_format", "9）输出格式（默认 docx）："),
    ("references", "10）是否已有参考文献（可逐条输入，用分号/换行分隔）："),
]


class InterviewAgent:
    def __init__(
        self,
        *,
        output_dir: str | Path = "researchdraft/outputs",
        input_fn: Callable[[str], str] = input,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.input_fn = input_fn

    def run(self) -> DraftContext:
        answers = {}
        for key, prompt in QUESTIONS:
            answers[key] = self.input_fn(prompt)
        ctx = DraftContext.from_answers(answers)
        ctx.save_json(self.output_dir / "draft_context.json")
        return ctx

