"""Pending-state serialization roundtrip + version checks."""

import json
import tempfile
import unittest
from pathlib import Path

from thesis_agent.diagnoser.types import Diagnosis, ToolCall
from thesis_agent.orchestrator import pending as pending_io


def _sample_diagnoses():
    return [
        Diagnosis(
            rule_id="body.line_spacing",
            root_cause="set to 2.0",
            fix_plan=[ToolCall("tool_format_body", {"line_spacing": 1.5}, "fix")],
            confidence=0.4,
            needs_human=True,
            rationale="low confidence",
        ),
        Diagnosis(
            rule_id="auto_runnable",
            root_cause="",
            fix_plan=[ToolCall("tool_format_body", {"size": 12})],
            confidence=0.95,
            needs_human=False,
            rationale="ok",
        ),
    ]


class PendingRoundtripTests(unittest.TestCase):
    def test_only_needs_human_items_persist(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x_pending.json"
            state = pending_io.from_diagnoses(
                input_path="/in/x.docx",
                profile="scau_2024",
                mode="full",
                stem="x",
                output_dir=tmp,
                docx_path=str(Path(tmp) / "x_inflight.docx"),
                iteration=2,
                diagnoses=_sample_diagnoses(),
                llm_telemetry={"calls": 3, "total_tokens": 200},
                triggered_by_per_rule={"body.line_spacing": ["ambiguous_headings"]},
            )
            self.assertEqual(len(state.items), 1)
            self.assertEqual(state.items[0].rule_id, "body.line_spacing")
            self.assertEqual(state.items[0].decision, "pending")
            self.assertEqual(state.items[0].triggered_by, ["ambiguous_headings"])

            pending_io.save(state, str(path))
            self.assertTrue(path.exists())
            # Human-readable hint must be present in the file.
            text = path.read_text(encoding="utf-8")
            self.assertIn("decision", text)

            loaded = pending_io.load(str(path))
            self.assertEqual(loaded.iteration, 2)
            self.assertEqual(loaded.profile, "scau_2024")
            self.assertEqual(loaded.llm_telemetry["calls"], 3)
            self.assertEqual(len(loaded.items), 1)
            self.assertEqual(loaded.items[0].rule_id, "body.line_spacing")

    def test_invalid_schema_version_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "p.json"
            path.write_text(json.dumps({
                "schema_version": 999,
                "input_path": "/x", "profile": "p", "mode": "full",
                "stem": "x", "output_dir": tmp, "docx_path": "/x",
                "iteration": 0, "items": [], "llm_telemetry": {},
            }), encoding="utf-8")
            with self.assertRaises(pending_io.PendingStateError):
                pending_io.load(str(path))

    def test_to_diagnosis_clears_needs_human_when_accepted(self):
        item = pending_io.PendingItem(
            rule_id="x", root_cause="", rationale="",
            confidence=0.9,
            fix_plan=[{"tool": "tool_format_body", "params": {}}],
            decision="accept",
        )
        d = item.to_diagnosis()
        self.assertFalse(d.needs_human)
        self.assertEqual(d.fix_plan[0].tool, "tool_format_body")

    def test_to_diagnosis_keeps_needs_human_when_pending(self):
        item = pending_io.PendingItem(
            rule_id="x", root_cause="", rationale="",
            confidence=0.4, fix_plan=[], decision="pending",
        )
        self.assertTrue(item.to_diagnosis().needs_human)


if __name__ == "__main__":
    unittest.main()
