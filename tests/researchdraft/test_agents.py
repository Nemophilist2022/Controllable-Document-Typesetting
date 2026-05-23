import json
import tempfile
import unittest
from pathlib import Path


class InterviewAgentTests(unittest.TestCase):
    def test_collects_fixed_questions_and_writes_context(self):
        from researchdraft.agents.interview_agent import InterviewAgent

        answers = iter(
            [
                "Title",
                "Background",
                "Problem",
                "Method A; Method B",
                "",
                "",
                "Traceability",
                "",
                "",
                "",
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            agent = InterviewAgent(output_dir=tmp, input_fn=lambda _: next(answers))
            ctx = agent.run()

            payload = json.loads((Path(tmp) / "draft_context.json").read_text("utf-8"))

        self.assertEqual(ctx.title, "Title")
        self.assertEqual(payload["method"], ["Method A", "Method B"])
        self.assertIn("dataset", payload["missing_fields"])
        self.assertIn("references", payload["missing_fields"])


class WritingAgentTests(unittest.TestCase):
    def test_falls_back_to_template_and_marks_missing_fields(self):
        from researchdraft.agents.planning_agent import PlanningAgent
        from researchdraft.agents.writing_agent import WritingAgent
        from researchdraft.core.context import DraftContext

        ctx = DraftContext.from_answers(
            {
                "title": "Harness MVP",
                "background": "Use supplied materials.",
                "research_problem": "Can agents draft safely?",
                "method": "manager agent; verifier agent",
                "dataset": "",
                "metrics": "",
                "innovation_points": "control surface",
                "paper_type": "short_paper",
                "output_format": "docx",
                "references": "",
            }
        )
        outline = PlanningAgent().run(ctx)
        draft = WritingAgent(llm_client=object()).run(ctx, outline)

        self.assertIn("# Harness MVP", draft)
        for heading in [
            "# Harness MVP",
            "## 摘要",
            "## 关键词",
            "## 引言",
            "## 相关工作",
            "## 方法",
            "## 实验与结果分析",
            "## 结论",
            "## 参考文献",
        ]:
            self.assertIn(heading, draft)
        self.assertIn("[待补充：实验指标]", draft)
        self.assertIn("[待补充：参考文献]", draft)
        self.assertIn("[待确认：数据集规模]", draft)


if __name__ == "__main__":
    unittest.main()
