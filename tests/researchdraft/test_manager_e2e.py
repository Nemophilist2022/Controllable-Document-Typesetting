import json
import tempfile
import unittest
from pathlib import Path


class ResearchDraftManagerE2ETests(unittest.TestCase):
    def test_full_flow_generates_expected_artifacts_and_trace(self):
        from researchdraft.agents.manager_agent import ResearchManagerAgent

        answers = iter(
            [
                "可控科研草稿生成 Harness",
                "用户提供研究材料后需要生成可审查草稿。",
                "如何避免模型编造并保留人工确认点？",
                "访谈采集; 结构化上下文; Word 排版; 质检",
                "",
                "",
                "多 Agent 调度; 工具白名单; Trace",
                "short_paper",
                "docx",
                "",
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            result = ResearchManagerAgent(
                output_dir=tmp,
                input_fn=lambda _: next(answers),
                llm_client=None,
            ).run()
            out = Path(tmp)

            expected = [
                "draft_context.json",
                "draft.md",
                "paper.docx",
                "quality_report.md",
                "trace.json",
                "trace.jsonl",
            ]
            for name in expected:
                self.assertTrue((out / name).exists(), name)

            report = (out / "quality_report.md").read_text("utf-8")
            trace_items = json.loads((out / "trace.json").read_text("utf-8"))

        self.assertTrue(result.ok)
        for heading in [
            "项目基本信息",
            "Draft Context 摘要",
            "论文结构检查",
            "内容缺失检查",
            "Word 输出检查",
            "Agent Trace 摘要",
            "人工确认项",
            "当前版本限制",
        ]:
            self.assertIn(heading, report)
        self.assertIn("格式检查结果", report)
        self.assertIn("Agent 执行 Trace", report)
        agents = {line["agent"] for line in trace_items}
        self.assertGreaterEqual(
            agents,
            {
                "InterviewAgent",
                "PlanningAgent",
                "WritingAgent",
                "WordFormatAgent",
                "VerifierAgent",
            },
        )
        for item in trace_items:
            self.assertGreaterEqual(
                set(item),
                {
                    "agent",
                    "stage",
                    "input_keys",
                    "output_keys",
                    "tool_call",
                    "status",
                    "failure_reason",
                },
            )
        tool_calls = [line["tool_call"] for line in trace_items]
        self.assertTrue(any("tool_assign_heading_styles" in t for t in tool_calls))
        self.assertTrue(any("tool_format_body" in t for t in tool_calls))
        self.assertTrue(any("tool_insert_toc" in t for t in tool_calls))
        self.assertTrue(any("tool_setup_page_numbers" in t for t in tool_calls))
        self.assertTrue(any("tool_format_references" in t for t in tool_calls))


if __name__ == "__main__":
    unittest.main()
