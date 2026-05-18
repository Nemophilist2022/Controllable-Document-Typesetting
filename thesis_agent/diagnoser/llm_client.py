"""LLMClient abstraction + MockLLMClient (R5.2).

The real OpenAI / local-model clients land in v0.2; for MVP we only
need the protocol shape and a deterministic mock.
"""

from __future__ import annotations

from typing import Any, Protocol


class LLMClient(Protocol):
    def complete(self, prompt: str, schema: dict) -> dict:
        ...


class MockLLMClient:
    """Returns canned responses keyed on the rule_id embedded in the prompt.

    Useful for orchestrator tests that need a non-None LLM but should
    never hit the network.
    """

    def __init__(self, canned: dict[str, dict[str, Any]] | None = None) -> None:
        self._canned = canned or {}
        self.calls: list[dict[str, Any]] = []

    def complete(self, prompt: str, schema: dict) -> dict:
        self.calls.append({"prompt": prompt, "schema": schema})
        # Best-effort: extract a rule_id token from the prompt.
        for rule_id, response in self._canned.items():
            if rule_id in prompt:
                return response
        # Default canned response: needs_human, no fix.
        return {
            "rule_id": "",
            "root_cause": "",
            "fix_plan": [],
            "confidence": 0.0,
            "needs_human": True,
            "rationale": "no canned response",
        }
