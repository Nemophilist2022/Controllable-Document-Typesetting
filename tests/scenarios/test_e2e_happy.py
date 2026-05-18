"""MVP end-to-end happy path (R requirements.md §4 修订版).

Asserts only what MVP actually delivers:
- the agent runs to completion
- the four artefacts (docx / report.md / report.json / trace.jsonl) exist
- the output docx can be reopened by python-docx
- summary["done"] >= 4 and summary["failed"] == 0
- the four MVP rule_ids are present and "done"
"""

import json
import tempfile
import unittest
from pathlib import Path

from docx import Document

from tests.scenarios.fixtures.build_fixtures import build_perfect_docx


class HappyPathTests(unittest.TestCase):
    def setUp(self):
        # Reset module-level caches so this test is independent of the
        # order it runs alongside other tests.
        from thesis_agent.diagnoser.diagnoser import reset_caches
        from thesis_agent.evaluators import runner
        from thesis_agent.tools import registry

        reset_caches()
        runner.clear_checks()
        registry.clear()

    def test_full_mode_produces_done_report_against_minimal_perfect_fixture(self):
        from thesis_agent.cli import main

        with tempfile.TemporaryDirectory() as tmp:
            in_path = Path(tmp) / "scau_perfect_thesis.docx"
            build_perfect_docx(str(in_path))

            rc = main([
                "run",
                "--input", str(in_path),
                "--profile", "scau_2024",
                "--mode", "full",
                "--output-dir", tmp,
            ])
            self.assertEqual(rc, 0, msg="thesis-agent run exited non-zero")

            out_docx = Path(tmp) / "scau_perfect_thesis_formatted.docx"
            out_md = Path(tmp) / "scau_perfect_thesis_report.md"
            out_json = Path(tmp) / "scau_perfect_thesis_report.json"
            out_trace = Path(tmp) / "scau_perfect_thesis_trace.jsonl"
            for f in (out_docx, out_md, out_json, out_trace):
                self.assertTrue(f.exists(), msg=f"missing artefact: {f.name}")

            # Output docx must reopen cleanly.
            Document(str(out_docx))

            # Summary contract.
            report = json.loads(out_json.read_text(encoding="utf-8"))
            summary = report["summary"]
            self.assertGreaterEqual(
                summary["done"], 4,
                msg=f"expected done>=4, got summary={summary}",
            )
            self.assertEqual(
                summary["failed"], 0,
                msg=f"expected failed=0, got summary={summary}",
            )

            # Each MVP rule must be present and done.
            statuses = {it["rule_id"]: it["status"] for it in report["items"]}
            for rid in (
                "body.font.east_asia",
                "body.font.size",
                "body.line_spacing",
                "heading.h1.style_present",
            ):
                self.assertEqual(
                    statuses.get(rid), "done",
                    msg=f"{rid} status was {statuses.get(rid)!r}, "
                        f"expected 'done'. Full statuses: {statuses}",
                )


if __name__ == "__main__":
    unittest.main()
