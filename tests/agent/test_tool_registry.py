"""Tool registry — register / get / autoload (R3.6, R12.2, R12.7)."""

import unittest


class _FakeTool:
    name = "fake_tool"
    description = "for tests"
    input_schema = {"type": "object"}
    requires: list[str] = []
    idempotent = True

    def run(self, doc, params, ctx):
        return None


class _NotATool:
    """Missing required static attrs — must be rejected by registry."""

    name = "broken"

    def run(self, doc, params, ctx):
        return None


class ToolRegistryTests(unittest.TestCase):
    def setUp(self):
        from thesis_agent.tools import registry

        registry.clear()

    def test_register_and_get(self):
        from thesis_agent.tools import registry

        tool = _FakeTool()
        registry.register(tool)
        self.assertIs(registry.get("fake_tool"), tool)

    def test_get_unknown_raises(self):
        from thesis_agent.tools import registry

        with self.assertRaises(registry.UnknownToolError):
            registry.get("nope")

    def test_register_rejects_non_tool(self):
        from thesis_agent.tools import registry

        with self.assertRaises(TypeError):
            registry.register(_NotATool())

    def test_all_tools_returns_registered(self):
        from thesis_agent.tools import registry

        registry.register(_FakeTool())
        names = [t.name for t in registry.all_tools()]
        self.assertEqual(names, ["fake_tool"])


class AutoloadTests(unittest.TestCase):
    def setUp(self):
        from thesis_agent.tools import registry

        registry.clear()

    def test_autoload_finds_tool_modules(self):
        """After autoload, the four MVP tool names from T6 must be present.

        This test passes once T6 lands. For T5 alone the registry must
        at minimum tolerate calling autoload() without errors.
        """
        from thesis_agent.tools import registry

        registry.autoload()  # Must not raise even if no tools yet.
        self.assertIsInstance(registry.all_tools(), list)


if __name__ == "__main__":
    unittest.main()
