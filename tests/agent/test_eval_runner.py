"""Evaluator runner — rule scheduling + status mapping (R4.1, R4.5~R4.7)."""

import unittest

from thesis_agent.evaluators.types import CheckResult
from thesis_agent.spec.rule_set import Rule, RuleSet


class _StubDoc:
    """Minimal stand-in for DocumentModel during evaluator tests."""

    def __init__(self, body_line_spacing=1.5, body_font="宋体"):
        self._body_line_spacing = body_line_spacing
        self._body_font = body_font

    # The runner asks the doc via DocumentModel-style APIs; for this
    # test we use a small dispatch table keyed on locator content.
    def normal_style(self):
        return {
            "line_spacing": self._body_line_spacing,
            "font.east_asia": self._body_font,
        }


def _runner_check_pass():
    """Trivial check that always passes."""

    def _impl(rule, doc):
        return CheckResult(
            rule_id=rule.id,
            status="pass",
            evidence="ok",
            locator_resolved=rule.locator,
            severity=rule.severity,
        )
    return _impl


def _runner_check_fail():
    def _impl(rule, doc):
        return CheckResult(
            rule_id=rule.id,
            status="fail",
            evidence="mismatch",
            locator_resolved=rule.locator,
            severity=rule.severity,
        )
    return _impl


def _runner_check_raises():
    def _impl(rule, doc):
        raise RuntimeError("locator gone")
    return _impl


class EvalRunnerTests(unittest.TestCase):
    def test_runs_all_rules_and_emits_summary(self):
        from thesis_agent.evaluators import runner

        runner.clear_checks()
        runner.register_check("equals", _runner_check_pass())

        rs = RuleSet(
            profile="t",
            version="1",
            rules=[
                Rule(id="a", scope="style", locator={}, predicate="equals",
                     expected=1, severity="must"),
                Rule(id="b", scope="style", locator={}, predicate="equals",
                     expected=1, severity="should"),
            ],
        )
        report = runner.evaluate(_StubDoc(), rs)
        for k in ("total", "pass", "fail", "skip", "error"):
            self.assertIn(k, report.summary)
        self.assertEqual(report.summary["total"], 2)
        self.assertEqual(report.summary["pass"], 2)

    def test_only_rule_ids_subset(self):
        from thesis_agent.evaluators import runner

        runner.clear_checks()
        runner.register_check("equals", _runner_check_pass())

        rs = RuleSet(
            profile="t",
            version="1",
            rules=[
                Rule(id="a", scope="style", locator={}, predicate="equals",
                     expected=1, severity="must"),
                Rule(id="b", scope="style", locator={}, predicate="equals",
                     expected=1, severity="must"),
            ],
        )
        report = runner.evaluate(_StubDoc(), rs, only_rule_ids=["a"])
        self.assertEqual({r.rule_id for r in report.results}, {"a"})

    def test_check_exception_becomes_error_status(self):
        from thesis_agent.evaluators import runner

        runner.clear_checks()
        runner.register_check("equals", _runner_check_raises())

        rs = RuleSet(
            profile="t",
            version="1",
            rules=[
                Rule(id="a", scope="style", locator={}, predicate="equals",
                     expected=1, severity="must"),
            ],
        )
        report = runner.evaluate(_StubDoc(), rs)
        self.assertEqual(report.results[0].status, "error")
        self.assertIn("locator gone", report.results[0].evidence)

    def test_unknown_predicate_becomes_error(self):
        from thesis_agent.evaluators import runner

        runner.clear_checks()  # nothing registered

        rs = RuleSet(
            profile="t",
            version="1",
            rules=[
                Rule(id="a", scope="style", locator={}, predicate="equals",
                     expected=1, severity="must"),
            ],
        )
        report = runner.evaluate(_StubDoc(), rs)
        self.assertEqual(report.results[0].status, "error")
        self.assertIn("no check", report.results[0].evidence.lower())


if __name__ == "__main__":
    unittest.main()
