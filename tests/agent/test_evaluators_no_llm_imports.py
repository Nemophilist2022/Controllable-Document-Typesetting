"""Static guard — evaluators must not import any LLM client (R4.2).

Scans every ``.py`` file under ``thesis_agent/evaluators/`` and asserts
that no forbidden module name appears as an import.
"""

import os
import re
import unittest

_FORBIDDEN = (
    "openai",
    "anthropic",
    "google.generativeai",
    "ollama",
    # LLM proxies via the requests library are not banned outright (the
    # report layer may use it for telemetry), but evaluators have no
    # legitimate need for HTTP, so we ban it here too.
    "requests",
    "httpx",
)

_IMPORT_RE = re.compile(r"^\s*(?:from\s+([\w\.]+)\s+import|import\s+([\w\.]+))", re.M)


class EvaluatorsNoLlmImportsTests(unittest.TestCase):
    def test_no_forbidden_imports_in_evaluators(self):
        root = os.path.join(
            os.path.dirname(__file__), "..", "..", "thesis_agent", "evaluators"
        )
        root = os.path.abspath(root)
        offenders: list[str] = []
        for dirpath, _dirs, files in os.walk(root):
            for fname in files:
                if not fname.endswith(".py"):
                    continue
                path = os.path.join(dirpath, fname)
                with open(path, "r", encoding="utf-8") as fh:
                    src = fh.read()
                for m in _IMPORT_RE.finditer(src):
                    mod = m.group(1) or m.group(2) or ""
                    head = mod.split(".", 1)[0] if mod else ""
                    if head in _FORBIDDEN:
                        offenders.append(f"{path}: imports {mod}")
        self.assertEqual(
            offenders, [], msg=f"forbidden imports in evaluators: {offenders}"
        )


if __name__ == "__main__":
    unittest.main()
