"""v0.2 — rule-prefix-based prompt template selection."""

import unittest

from thesis_agent.diagnoser.prompts import reset_cache, select_template


class TemplateSelectionTests(unittest.TestCase):
    def setUp(self):
        reset_cache()

    def test_body_rule_picks_body_template(self):
        out = select_template("body.line_spacing")
        self.assertIn("Normal-style", out)
        self.assertIn("tool_format_body", out)

    def test_heading_subrule_picks_heading_template(self):
        out = select_template("heading.h1.font.east_asia")
        # Most specific match falls back to "heading" prefix.
        self.assertIn("Heading", out)
        self.assertIn("tool_assign_heading_styles", out)

    def test_page_number_picks_page_number_not_page(self):
        """page_number.body.format must hit page_number.md, not page.md
        (most-specific match wins)."""
        out = select_template("page_number.body.format")
        # Distinguishing token only present in page_number.md
        self.assertIn("Page-number", out)

    def test_unknown_prefix_uses_fallback(self):
        out = select_template("totally.unrelated.rule")
        self.assertIn("Diagnose", out)
        self.assertIn("rule_id", out)


class DiagnoserUsesTemplateTests(unittest.TestCase):
    def setUp(self):
        from thesis_agent.diagnoser.diagnoser import reset_caches as rc

        rc()

    def test_make_prompt_includes_rule_specific_guidance(self):
        from thesis_agent.diagnoser.diagnoser import _make_prompt
        from thesis_agent.evaluators.types import CheckResult

        cr = CheckResult(
            rule_id="body.line_spacing",
            status="fail",
            evidence="actual=2.0 expected=1.5",
            locator_resolved={"style_name": "Normal"},
            severity="must",
        )
        prompt = _make_prompt(cr)
        self.assertIn("Normal-style", prompt)         # template body
        self.assertIn("rule_id=body.line_spacing", prompt)  # body block
        self.assertIn("evidence=actual=2.0", prompt)


if __name__ == "__main__":
    unittest.main()
