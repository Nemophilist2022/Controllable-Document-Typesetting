"""Freeze the core data contracts shared across agent layers.

Backs:
- R1.1 / R1.6  — Rule / RuleSet shape and severity enum
- R3.1 / R3.2  — Tool / ToolResult / ToolContext shape
- R4.3 / R4.6 / R4.7 — CheckResult / EvalReport shape and status enum
- R5.5         — Diagnosis.confidence clamp to [0, 1]
- R2.2 / m1    — LoadResult / ErrorInfo shape
"""

import unittest


# ---------------------------------------------------------------------------
# spec.rule_set
# ---------------------------------------------------------------------------

class RuleContractTests(unittest.TestCase):
    def test_rule_severity_must_be_in_enum(self):
        from thesis_agent.spec.rule_set import Rule

        with self.assertRaises(ValueError):
            Rule(
                id="x",
                scope="paragraph",
                locator={},
                predicate="equals",
                expected=1,
                severity="critical",  # invalid
            )

    def test_rule_severity_accepts_must_should_info(self):
        from thesis_agent.spec.rule_set import Rule

        for sev in ("must", "should", "info"):
            r = Rule(
                id=f"x.{sev}",
                scope="paragraph",
                locator={},
                predicate="equals",
                expected=1,
                severity=sev,
            )
            self.assertEqual(r.severity, sev)

    def test_rule_set_metadata_default_dict(self):
        from thesis_agent.spec.rule_set import Rule, RuleSet

        rs = RuleSet(
            profile="t",
            version="1",
            rules=[
                Rule(
                    id="x",
                    scope="paragraph",
                    locator={},
                    predicate="equals",
                    expected=1,
                    severity="must",
                )
            ],
        )
        # metadata must be a fresh dict per instance (no shared default).
        self.assertIsInstance(rs.metadata, dict)
        rs.metadata["unknown_keys"] = ["a"]
        rs2 = RuleSet(profile="t2", version="1", rules=[])
        self.assertEqual(rs2.metadata, {})


# ---------------------------------------------------------------------------
# evaluators.types
# ---------------------------------------------------------------------------

class CheckResultContractTests(unittest.TestCase):
    def test_check_status_has_exactly_four_values(self):
        from thesis_agent.evaluators.types import CheckStatus

        self.assertEqual(set(CheckStatus), {"pass", "fail", "skip", "error"})

    def test_check_result_rejects_invalid_status(self):
        from thesis_agent.evaluators.types import CheckResult

        with self.assertRaises(ValueError):
            CheckResult(
                rule_id="x",
                status="done",  # not a valid evaluator-layer status
                evidence="",
                locator_resolved={},
                severity="must",
            )

    def test_eval_report_summary_has_five_keys(self):
        from thesis_agent.evaluators.types import CheckResult, EvalReport

        results = [
            CheckResult(rule_id="a", status="pass",  evidence="", locator_resolved={}, severity="must"),
            CheckResult(rule_id="b", status="fail",  evidence="", locator_resolved={}, severity="must"),
            CheckResult(rule_id="c", status="skip",  evidence="", locator_resolved={}, severity="should"),
            CheckResult(rule_id="d", status="error", evidence="x", locator_resolved={}, severity="info"),
        ]
        report = EvalReport(profile="t", results=results)
        for key in ("total", "pass", "fail", "skip", "error"):
            self.assertIn(key, report.summary)
        self.assertEqual(report.summary["total"], 4)
        self.assertEqual(report.summary["pass"], 1)
        self.assertEqual(report.summary["fail"], 1)
        self.assertEqual(report.summary["skip"], 1)
        self.assertEqual(report.summary["error"], 1)


# ---------------------------------------------------------------------------
# diagnoser.types
# ---------------------------------------------------------------------------

class DiagnosisContractTests(unittest.TestCase):
    def test_diagnosis_confidence_clamped_above_one(self):
        from thesis_agent.diagnoser.types import Diagnosis

        d = Diagnosis(
            rule_id="x",
            root_cause="",
            fix_plan=[],
            confidence=1.5,
            needs_human=False,
            rationale="",
        )
        self.assertEqual(d.confidence, 1.0)

    def test_diagnosis_confidence_clamped_below_zero(self):
        from thesis_agent.diagnoser.types import Diagnosis

        d = Diagnosis(
            rule_id="x",
            root_cause="",
            fix_plan=[],
            confidence=-0.5,
            needs_human=False,
            rationale="",
        )
        self.assertEqual(d.confidence, 0.0)

    def test_tool_call_dataclass(self):
        from thesis_agent.diagnoser.types import ToolCall

        tc = ToolCall(tool="tool_format_body", params={"line_spacing": 1.5})
        self.assertEqual(tc.tool, "tool_format_body")
        self.assertEqual(tc.params, {"line_spacing": 1.5})
        # expected_effect should be optional with empty default
        self.assertEqual(tc.expected_effect, "")


# ---------------------------------------------------------------------------
# tools.base
# ---------------------------------------------------------------------------

class ToolResultContractTests(unittest.TestCase):
    def test_tool_result_default_change_lists_are_empty(self):
        from thesis_agent.tools.base import ToolResult

        r = ToolResult(ok=False, message="boom")
        self.assertEqual(r.changed_paragraphs, [])
        self.assertEqual(r.changed_styles, [])
        self.assertEqual(r.changed_sections, [])
        self.assertEqual(r.warnings, [])
        self.assertIsNone(r.rollback_token)

    def test_tool_result_independent_default_lists(self):
        """Default lists must not be shared between instances."""
        from thesis_agent.tools.base import ToolResult

        a = ToolResult(ok=True)
        b = ToolResult(ok=True)
        a.changed_paragraphs.append({"paragraph_index": 0})
        self.assertEqual(b.changed_paragraphs, [])

    def test_tool_protocol_has_required_static_attrs(self):
        """A class missing any of the 5 static attributes is not a Tool."""
        from thesis_agent.tools.base import is_tool

        class Incomplete:
            name = "x"
            description = "x"
            input_schema = {}
            requires = []
            # idempotent missing

            def run(self, doc, params, ctx):  # noqa: D401
                ...

        class Complete:
            name = "x"
            description = "x"
            input_schema = {}
            requires = []
            idempotent = True

            def run(self, doc, params, ctx):  # noqa: D401
                ...

        self.assertFalse(is_tool(Incomplete()))
        self.assertTrue(is_tool(Complete()))

    def test_tool_context_required_fields(self):
        from thesis_agent.tools.base import ToolContext

        ctx = ToolContext(
            trace=object(),
            snapshot_mgr=object(),
            config={},
            runtime={},
        )
        self.assertIs(ctx.config, ctx.config)  # smoke


# ---------------------------------------------------------------------------
# ingest.types
# ---------------------------------------------------------------------------

class LoadResultContractTests(unittest.TestCase):
    def test_error_info_fields(self):
        from thesis_agent.ingest.types import ErrorInfo

        e = ErrorInfo(code="word_com_unavailable", message="no Word here")
        self.assertEqual(e.code, "word_com_unavailable")
        self.assertEqual(e.message, "no Word here")

    def test_load_result_ok_with_path(self):
        from thesis_agent.ingest.types import LoadResult

        r = LoadResult(ok=True, document_path="/tmp/x.docx")
        self.assertTrue(r.ok)
        self.assertIsNone(r.error)

    def test_load_result_failure_carries_error(self):
        from thesis_agent.ingest.types import ErrorInfo, LoadResult

        r = LoadResult(
            ok=False,
            error=ErrorInfo(code="unsupported_extension", message="x"),
        )
        self.assertFalse(r.ok)
        self.assertIsNone(r.document_path)
        self.assertEqual(r.error.code, "unsupported_extension")


if __name__ == "__main__":
    unittest.main()
