import unittest


class DraftContextTests(unittest.TestCase):
    def test_from_answers_tracks_missing_and_splits_lists(self):
        from researchdraft.core.context import DraftContext

        ctx = DraftContext.from_answers(
            {
                "title": "Agent Harness",
                "background": "",
                "research_problem": "How to control drafting",
                "method": "interview; planning, writing\nverification",
                "dataset": "",
                "metrics": "format pass rate, missing marker count",
                "innovation_points": "controlled context; traceable workflow",
                "paper_type": "",
                "output_format": "",
                "references": "Smith 2024\nWang 2025",
            }
        )

        self.assertEqual(ctx.title, "Agent Harness")
        self.assertEqual(
            ctx.method, ["interview", "planning", "writing", "verification"]
        )
        self.assertEqual(
            ctx.metrics, ["format pass rate", "missing marker count"]
        )
        self.assertEqual(ctx.paper_type, "short_paper")
        self.assertEqual(ctx.output_format, ["docx"])
        self.assertEqual(ctx.references, ["Smith 2024", "Wang 2025"])
        self.assertIn("background", ctx.missing_fields)
        self.assertIn("dataset", ctx.missing_fields)


if __name__ == "__main__":
    unittest.main()
