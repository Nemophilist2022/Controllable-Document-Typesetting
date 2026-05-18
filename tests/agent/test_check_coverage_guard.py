"""Coverage guard for scau_2024 evaluator skips.

A skipped result is acceptable only when the check can explain *why* the
rule is not applicable or cannot be measured from the current OOXML. It
must not mean "we did not implement this rule's check".
"""

import tempfile
import unittest
from pathlib import Path

from docx import Document

from tests.scenarios.fixtures.build_fixtures import build_perfect_docx


class ScauCheckCoverageGuardTests(unittest.TestCase):
    def setUp(self):
        from thesis_agent.evaluators import runner
        from thesis_agent.evaluators.checks import autoload

        runner.clear_checks()
        autoload()

    def test_all_scau_skips_are_classified_and_not_unimplemented(self):
        from thesis_agent.evaluators import runner
        from thesis_agent.spec.profiles.scau_2024 import load

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fixture.docx"
            build_perfect_docx(str(path))
            report = runner.evaluate(Document(str(path)), load())

        self.assertEqual(report.summary["total"], 41)

        allowed_reasons = {
            "not_applicable",
            "unmeasurable",
        }
        skipped = [result for result in report.results if result.status == "skip"]
        self.assertGreater(skipped, [], "fixture should exercise skip classification")

        problems = []
        for result in skipped:
            reason = result.metadata.get("skip_reason")
            if reason not in allowed_reasons:
                problems.append((result.rule_id, reason, result.evidence))
            if result.metadata.get("check_coverage") == "unimplemented":
                problems.append((result.rule_id, "unimplemented", result.evidence))

        self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()

class DeliveryMetadataTests(unittest.TestCase):
    def test_report_json_preserves_skip_reason_metadata(self):
        from thesis_agent.delivery.report import build_delivery_report
        from thesis_agent.evaluators.types import CheckResult, EvalReport

        check = CheckResult(
            rule_id="caption.font.size",
            status="skip",
            evidence="no captions in document",
            locator_resolved={"caption": True},
            severity="should",
            metadata={"skip_reason": "not_applicable", "check_coverage": "implemented"},
        )
        delivery = build_delivery_report(
            rule_set=None,
            eval_report=EvalReport(profile="p", results=[check]),
            diagnoses=[],
            mode="eval_only",
            iterations=1,
            exit_reason="done",
        )

        self.assertEqual(
            delivery.items[0].check_metadata,
            {"skip_reason": "not_applicable", "check_coverage": "implemented"},
        )
