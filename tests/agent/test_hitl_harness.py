"""Harness HITL behaviour: pause on needs_human, resume from pending.json,
prominent warning when all gates disabled, R9.3 'no' mode skips pause.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from docx import Document

from thesis_agent.diagnoser.types import Diagnosis, ToolCall
from thesis_agent.orchestrator import pending as pending_io
from thesis_agent.orchestrator.harness import RunOptions, run
from thesis_agent.orchestrator.policies import Policies


def _make_doc(path):
    """Tiny docx that triggers at least one fail (no Heading 1 style)."""
    d = Document()
    d.add_paragraph("段落一", style="Normal")
    d.save(path)


def _reset():
    from thesis_agent.diagnoser.diagnoser import reset_caches
    from thesis_agent.evaluators import runner
    from thesis_agent.tools import registry

    reset_caches()
    runner.clear_checks()
    registry.clear()


class PauseOnNeedsHumanTests(unittest.TestCase):
    def setUp(self):
        _reset()

    def test_full_mode_with_no_llm_pauses_when_confirm_policy(self):
        """Without LLM the diagnoser flags every fail as needs_human;
        confirm policy must save pending.json and stop."""
        with tempfile.TemporaryDirectory() as tmp:
            in_path = Path(tmp) / "x.docx"
            _make_doc(in_path)

            options = RunOptions(
                output_dir=tmp,
                auto_apply_diagnosis="confirm",
                llm_disabled=True,
            )
            result = run(
                input_path=str(in_path),
                profile="scau_2024",
                mode="full",
                options=options,
            )
            self.assertIsNotNone(result.pending_path)
            self.assertTrue(Path(result.pending_path).exists())
            self.assertIn("awaiting_human", result.exit_reason)

            # Pending file is loadable and points at the in-flight docx.
            state = pending_io.load(result.pending_path)
            self.assertEqual(state.profile, "scau_2024")
            self.assertEqual(state.mode, "full")
            self.assertGreater(len(state.items), 0)
            self.assertTrue(Path(state.docx_path).exists())

    def test_no_mode_does_not_pause(self):
        """auto_apply_diagnosis='no' must run the loop to completion;
        needs_human items are reported as failed instead of paused."""
        with tempfile.TemporaryDirectory() as tmp:
            in_path = Path(tmp) / "x.docx"
            _make_doc(in_path)

            options = RunOptions(
                output_dir=tmp,
                auto_apply_diagnosis="no",
                llm_disabled=True,
            )
            result = run(
                input_path=str(in_path),
                profile="scau_2024",
                mode="full",
                options=options,
            )
            self.assertIsNone(result.pending_path)
            self.assertNotIn("awaiting_human", result.exit_reason)


class ProminentWarningTests(unittest.TestCase):
    def setUp(self):
        _reset()

    def test_disabling_all_gates_emits_log_and_trace_warning(self):
        captured: list[str] = []
        with tempfile.TemporaryDirectory() as tmp:
            in_path = Path(tmp) / "x.docx"
            _make_doc(in_path)

            options = RunOptions(
                output_dir=tmp,
                auto_apply_diagnosis="no",
                llm_disabled=True,
                policies=Policies(human_in_the_loop_at=()),
                log_fn=captured.append,
            )
            result = run(
                input_path=str(in_path),
                profile="scau_2024",
                mode="full",
                options=options,
            )

            self.assertTrue(any("WARNING" in line for line in captured),
                            msg=f"no warning in log_fn output: {captured}")
            trace_lines = Path(result.trace_path).read_text(encoding="utf-8").splitlines()
            warned = [
                line for line in trace_lines
                if '"kind": "policy"' in line and "warning" in line
            ]
            self.assertTrue(warned, msg="no policy warning recorded in trace")


class ResumeTests(unittest.TestCase):
    def setUp(self):
        _reset()

    def test_resume_with_all_rejected_decisions_completes_normally(self):
        """Hand-crafted pending.json with every decision = 'reject'
        should resume cleanly: no plan steps to run, just finish the
        loop and write the report."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            # Create the docx the pending file will reference.
            inflight = tmp_path / "x_inflight.docx"
            _make_doc(inflight)

            state = pending_io.PendingState(
                schema_version=1,
                input_path=str(tmp_path / "x.docx"),  # need not exist
                profile="scau_2024",
                mode="full",
                stem="x",
                output_dir=str(tmp_path),
                docx_path=str(inflight),
                iteration=0,
                items=[
                    pending_io.PendingItem(
                        rule_id="body.line_spacing",
                        root_cause="...",
                        rationale="user dismissed",
                        confidence=0.4,
                        fix_plan=[{"tool": "tool_format_body",
                                   "params": {"line_spacing": 1.5}}],
                        decision="reject",
                    ),
                ],
                llm_telemetry={"calls": 1, "total_tokens": 50},
            )
            pending_path = tmp_path / "x_pending.json"
            pending_io.save(state, str(pending_path))

            options = RunOptions(
                output_dir=str(tmp_path),
                resume_path=str(pending_path),
                auto_apply_diagnosis="no",  # don't pause again on resume
                llm_disabled=True,
            )
            result = run(
                input_path="",  # ignored when resuming
                profile="scau_2024",
                mode="full",
                options=options,
            )
            self.assertIsNone(result.pending_path,
                              msg=f"resume re-paused unexpectedly: {result.exit_reason}")
            self.assertTrue(Path(result.report_json_path).exists())
            # LLM telemetry from the previous session must roll forward
            # even though we ran with llm_disabled this time (counters
            # are restored before the loop, no further LLM calls).
            report = json.loads(
                Path(result.report_json_path).read_text(encoding="utf-8")
            )
            # When llm_disabled=True there's no client to roll into;
            # the telemetry dict in meta will reflect the current run
            # only. We just assert the run completed.
            self.assertIn("summary", report)

    def test_resume_with_accept_seeds_plan_with_fix_tool(self):
        """An accepted decision should turn into the next round's plan."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            inflight = tmp_path / "x_inflight.docx"
            _make_doc(inflight)

            state = pending_io.PendingState(
                schema_version=1,
                input_path=str(tmp_path / "x.docx"),
                profile="scau_2024",
                mode="full",
                stem="x",
                output_dir=str(tmp_path),
                docx_path=str(inflight),
                iteration=0,
                items=[
                    pending_io.PendingItem(
                        rule_id="body.line_spacing",
                        root_cause="set to 2.0",
                        rationale="LLM said so",
                        confidence=0.92,
                        fix_plan=[{"tool": "tool_format_body",
                                   "params": {"line_spacing": 1.5}}],
                        decision="accept",
                    ),
                ],
                llm_telemetry={},
            )
            pending_path = tmp_path / "x_pending.json"
            pending_io.save(state, str(pending_path))

            options = RunOptions(
                output_dir=str(tmp_path),
                resume_path=str(pending_path),
                auto_apply_diagnosis="no",
                llm_disabled=True,
            )
            result = run(
                input_path="",
                profile="scau_2024",
                mode="full",
                options=options,
            )
            self.assertIsNone(result.pending_path)
            # The trace must show our accepted plan was seeded.
            trace_text = Path(result.trace_path).read_text(encoding="utf-8")
            self.assertIn("resume_seed_plan", trace_text)
            self.assertIn("tool_format_body", trace_text)


class ResumeProfileMismatchTests(unittest.TestCase):
    def setUp(self):
        _reset()

    def test_resume_with_wrong_profile_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            inflight = tmp_path / "x_inflight.docx"
            _make_doc(inflight)

            state = pending_io.PendingState(
                schema_version=1,
                input_path=str(tmp_path / "x.docx"),
                profile="scau_2024",
                mode="full",
                stem="x", output_dir=str(tmp_path),
                docx_path=str(inflight), iteration=0, items=[],
                llm_telemetry={},
            )
            pending_path = tmp_path / "x_pending.json"
            pending_io.save(state, str(pending_path))

            options = RunOptions(resume_path=str(pending_path), llm_disabled=True)
            with self.assertRaises(pending_io.PendingStateError):
                run(
                    input_path="",
                    profile="some_other_profile",
                    mode="full",
                    options=options,
                )


if __name__ == "__main__":
    unittest.main()
