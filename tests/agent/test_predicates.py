"""Predicate registry — equals / one_of / regex / range / exists."""

import unittest


class PredicateTests(unittest.TestCase):
    def test_equals(self):
        from thesis_agent.spec.predicates import evaluate

        self.assertTrue(evaluate("equals", "a", "a"))
        self.assertFalse(evaluate("equals", "a", "b"))

    def test_one_of(self):
        from thesis_agent.spec.predicates import evaluate

        self.assertTrue(evaluate("one_of", "宋体", ["宋体", "SimSun"]))
        self.assertFalse(evaluate("one_of", "黑体", ["宋体", "SimSun"]))

    def test_regex(self):
        from thesis_agent.spec.predicates import evaluate

        self.assertTrue(evaluate("regex", "Heading 1", r"^Heading \d$"))
        self.assertFalse(evaluate("regex", "footnote text", r"^Heading \d$"))

    def test_range_inclusive(self):
        from thesis_agent.spec.predicates import evaluate

        self.assertTrue(evaluate("range", 1.5, [1.0, 2.0]))
        self.assertTrue(evaluate("range", 1.0, [1.0, 2.0]))
        self.assertTrue(evaluate("range", 2.0, [1.0, 2.0]))
        self.assertFalse(evaluate("range", 0.9, [1.0, 2.0]))
        self.assertFalse(evaluate("range", 2.1, [1.0, 2.0]))

    def test_exists(self):
        from thesis_agent.spec.predicates import evaluate

        self.assertTrue(evaluate("exists", "anything", True))
        self.assertFalse(evaluate("exists", None, True))
        # exists with expected=False inverts: target must be missing
        self.assertTrue(evaluate("exists", None, False))
        self.assertFalse(evaluate("exists", "x", False))

    def test_unknown_predicate_raises(self):
        from thesis_agent.spec.predicates import (
            UnknownPredicateError,
            evaluate,
        )

        with self.assertRaises(UnknownPredicateError):
            evaluate("unknown_op", 1, 1)


if __name__ == "__main__":
    unittest.main()
