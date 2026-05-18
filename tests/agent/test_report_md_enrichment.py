"""Report.md should include diagnosis root_cause / fix_plan / rationale
for partial and failed items."""

import tempfile
import unittest
from pathlib import Path

from thesis_agent.delivery.report import (
    DeliveryItem, DeliveryReport, write_report_md,
)


def _delivery_with(items):
    return DeliveryReport(
        profile="test",
        mode="full",
        iterations=1,
        exit_reason="ok",
        items=items,
        summary={
            "total": len(items),
            "done": sum(1 for i in items if i.status == "done"),
            "partial": sum(1 for i in items if i.status == "partial"),
            "failed": sum(1 for i in items if i.status == "failed"),
            "skipped": sum(1 for i in items if i.status == "skipped"),
        },
        meta={},
    )


class ReportMdEnrichmentTests(unittest.TestCase):
    def test_failed_item_with_diagnosis_renders_root_cause_and_pending_tools(self):
        item = DeliveryItem(
            rule_id="body.line_spacing",
            status="failed",
            severity="must",
            evidence="actual=2.0 expected=1.5",
            locator={"style_name": "Normal"},
            fix_attempts=[],
            diagnosis={
                "root_cause": "Normal style line spacing was set to 2.0",
                "rationale": "Numeric — straightforward fix.",
                "confidence": 0.9,
                "needs_human": True,
                "fix_plan": [
                    {"tool": "tool_format_body",
                     "params": {"line_spacing": 1.5}},
                ],
            },
            advice="诊断置信度不足，请人工确认后调整",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.md"
            write_report_md(_delivery_with([item]), str(path))
            text = path.read_text(encoding="utf-8")

        self.assertIn("根因：Normal style line spacing was set to 2.0", text)
        self.assertIn("待执行：tool_format_body", text)
        self.assertIn("说明：Numeric", text)
        self.assertIn("操作建议：诊断置信度", text)

    def test_partial_item_says_attempted_not_pending(self):
        item = DeliveryItem(
            rule_id="caption.numbering.continuity",
            status="partial",
            severity="should",
            evidence="figures jumped from 5 to 7",
            locator={"caption": True},
            fix_attempts=[],
            diagnosis={
                "root_cause": "missing figure 6",
                "rationale": "",
                "confidence": 0.6,
                "needs_human": True,
                "fix_plan": [
                    {"tool": "tool_format_figure_captions",
                     "params": {}},
                ],
            },
            advice="已尝试自动修复，建议在 Word 中复核标注的段落",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.md"
            write_report_md(_delivery_with([item]), str(path))
            text = path.read_text(encoding="utf-8")

        self.assertIn("已尝试：tool_format_figure_captions", text)
        # No "待执行" wording for partial items.
        self.assertNotIn("待执行：tool_format_figure_captions", text)

    def test_done_items_dont_show_diagnosis_block(self):
        item = DeliveryItem(
            rule_id="body.font.size",
            status="done",
            severity="must",
            evidence="actual=12.0 expected=12",
            locator={"style_name": "Normal"},
            fix_attempts=[],
            diagnosis=None,
            advice="",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.md"
            write_report_md(_delivery_with([item]), str(path))
            text = path.read_text(encoding="utf-8")

        # No "根因" / "待执行" / "已尝试" shown for done items.
        self.assertNotIn("根因", text)
        self.assertNotIn("待执行", text)
        self.assertNotIn("已尝试", text)


if __name__ == "__main__":
    unittest.main()
