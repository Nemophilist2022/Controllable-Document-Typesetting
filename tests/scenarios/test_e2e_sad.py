"""MVP end-to-end sad path: prove the rule engine actually catches problems."""

import json
import tempfile
import unittest
from pathlib import Path

from tests.scenarios.fixtures.build_fixtures import build_messy_docx


class SadPathTests(unittest.TestCase):
    def setUp(self):
        from thesis_agent.diagnoser.diagnoser import reset_caches
        from thesis_agent.evaluators import runner
        from thesis_agent.tools import registry

        reset_caches()
        runner.clear_checks()
        registry.clear()

    def test_eval_only_reports_at_least_three_violations(self):
        from thesis_agent.cli import main

        with tempfile.TemporaryDirectory() as tmp:
            in_path = Path(tmp) / "scau_messy_thesis.docx"
            input_bytes_before = None
            build_messy_docx(str(in_path))
            input_bytes_before = in_path.read_bytes()

            rc = main([
                "run",
                "--input", str(in_path),
                "--profile", "scau_2024",
                "--mode", "eval_only",
                "--output-dir", tmp,
            ])
            self.assertEqual(rc, 0)

            # eval_only must not write a formatted docx (R8.2).
            self.assertFalse(
                (Path(tmp) / "scau_messy_thesis_formatted.docx").exists()
            )
            # Input file must be byte-identical (R13.1).
            self.assertEqual(in_path.read_bytes(), input_bytes_before)

            report = json.loads(
                (Path(tmp) / "scau_messy_thesis_report.json")
                .read_text(encoding="utf-8")
            )
            summary = report["summary"]
            self.assertGreaterEqual(
                summary["failed"] + summary["partial"], 3,
                msg=f"expected ≥3 violations, got summary={summary}",
            )

            violators = [
                it for it in report["items"]
                if it["status"] in ("failed", "partial")
            ]
            # Top 3 violators must each carry rule_id + evidence + advice.
            self.assertGreaterEqual(len(violators), 3)
            for it in violators[:3]:
                self.assertTrue(it["rule_id"], msg=f"empty rule_id in {it}")
                self.assertTrue(it["evidence"], msg=f"empty evidence in {it}")
                self.assertTrue(it["advice"], msg=f"empty advice in {it}")


if __name__ == "__main__":
    unittest.main()
