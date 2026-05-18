"""Skeleton self-check tests for the thesis_agent package.

Locks the directory layout described in
docs/superpowers/specs/2026-04-15-ai-thesis-agent-architecture-design.md
so all subsequent tasks can rely on stable import paths.
"""

import importlib
import unittest


class ThesisAgentSkeletonTests(unittest.TestCase):
    def test_top_level_package_importable(self):
        importlib.import_module("thesis_agent")

    def test_all_subpackages_importable(self):
        expected = [
            "ingest",
            "spec",
            "tools",
            "evaluators",
            "diagnoser",
            "orchestrator",
            "delivery",
        ]
        for name in expected:
            with self.subTest(subpackage=name):
                importlib.import_module(f"thesis_agent.{name}")


if __name__ == "__main__":
    unittest.main()
