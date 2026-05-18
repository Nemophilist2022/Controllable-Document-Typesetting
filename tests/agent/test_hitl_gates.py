"""HITL gate logic — destructive_ops / ambiguous_headings / front_matter / cover."""

import unittest

from thesis_agent.diagnoser.types import Diagnosis, ToolCall
from thesis_agent.orchestrator.hitl_gates import (
    apply_gates_in_place, evaluate_gates, is_destructive,
)


def _diag(rule_id="x", confidence=0.9, fix_plan=None, needs_human=False):
    return Diagnosis(
        rule_id=rule_id,
        root_cause="",
        fix_plan=fix_plan or [],
        confidence=confidence,
        needs_human=needs_human,
        rationale="",
    )


class IsDestructiveTests(unittest.TestCase):
    def test_safe_format_tool_is_not_destructive(self):
        d = _diag(fix_plan=[ToolCall("tool_format_body", {"line_spacing": 1.5})])
        self.assertFalse(is_destructive(d))

    def test_delete_paragraph_tool_is_destructive(self):
        d = _diag(fix_plan=[ToolCall("tool_delete_paragraph", {"index": 3})])
        self.assertTrue(is_destructive(d))

    def test_destructive_param_key_promotes_safe_tool(self):
        d = _diag(fix_plan=[ToolCall("tool_format_body", {"delete_paragraphs": [1]})])
        self.assertTrue(is_destructive(d))


class EvaluateGatesTests(unittest.TestCase):
    def test_destructive_fires_even_if_disabled(self):
        # R9.5: destructive_ops is unconditional. Disabling it via the
        # human-in-the-loop_at config does not turn it off.
        d = _diag(fix_plan=[ToolCall("tool_delete_paragraph", {"index": 1})])
        gates = evaluate_gates(d, confidence_threshold=0.7, enabled_gates=[])
        self.assertEqual(gates, ["destructive_ops"])

    def test_ambiguous_headings_only_when_enabled(self):
        d = _diag(rule_id="heading.h1.style_present", confidence=0.4)
        without = evaluate_gates(d, confidence_threshold=0.7, enabled_gates=[])
        with_gate = evaluate_gates(
            d, confidence_threshold=0.7, enabled_gates=["ambiguous_headings"]
        )
        self.assertEqual(without, [])
        self.assertEqual(with_gate, ["ambiguous_headings"])

    def test_high_confidence_heading_does_not_fire_ambiguous(self):
        d = _diag(rule_id="heading.h1.style_present", confidence=0.95)
        gates = evaluate_gates(
            d, confidence_threshold=0.7, enabled_gates=["ambiguous_headings"]
        )
        self.assertEqual(gates, [])

    def test_cover_gate_fires_on_insert_cover_tool(self):
        d = _diag(fix_plan=[ToolCall("tool_insert_cover_and_declaration", {})])
        gates = evaluate_gates(
            d, confidence_threshold=0.7, enabled_gates=["cover"]
        )
        self.assertIn("cover", gates)


class ApplyGatesInPlaceTests(unittest.TestCase):
    def test_marks_needs_human_and_returns_triggered_map(self):
        diagnoses = [
            _diag(rule_id="body.line_spacing", confidence=0.9),  # passes
            _diag(rule_id="heading.h1.style_present", confidence=0.4),  # ambiguous
            _diag(
                rule_id="something.else",
                confidence=0.99,
                fix_plan=[ToolCall("tool_delete_paragraph", {"index": 5})],
            ),  # destructive
        ]
        triggered = apply_gates_in_place(
            diagnoses,
            confidence_threshold=0.7,
            enabled_gates=("ambiguous_headings", "cover"),
        )
        # body.line_spacing should remain auto-executable
        self.assertFalse(diagnoses[0].needs_human)
        self.assertNotIn("body.line_spacing", triggered)
        # heading is gated
        self.assertTrue(diagnoses[1].needs_human)
        self.assertIn("heading.h1.style_present", triggered)
        # destructive escalated even though "destructive_ops" isn't listed
        self.assertTrue(diagnoses[2].needs_human)
        self.assertIn("destructive_ops", triggered["something.else"])


if __name__ == "__main__":
    unittest.main()
