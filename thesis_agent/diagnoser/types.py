"""ToolCall and Diagnosis data contracts (R5.5).

The diagnoser layer can only emit structured ``Diagnosis`` objects. Each
``Diagnosis`` carries a ``fix_plan`` of ``ToolCall`` items — the LLM
itself never writes OOXML directly (R5.4).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCall:
    """A planned invocation of a single Tool.

    Attributes:
        tool: Tool name as registered in :mod:`thesis_agent.tools.registry`.
        params: Tool input arguments. Must validate against the Tool's
            ``input_schema``.
        expected_effect: Optional human-readable note for the report.
    """

    tool: str
    params: dict[str, Any]
    expected_effect: str = ""


@dataclass
class Diagnosis:
    """Structured root cause + fix plan for a single failed rule.

    ``confidence`` is clamped to ``[0.0, 1.0]`` at init time; values
    outside this range are common when LLMs hallucinate scores like 1.5.
    Per R5.5 the system also force-downgrades confidence in repeat-fail
    cases, but that logic lives in the diagnoser, not here.
    """

    rule_id: str
    root_cause: str
    fix_plan: list[ToolCall]
    confidence: float
    needs_human: bool
    rationale: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.confidence < 0.0:
            self.confidence = 0.0
        elif self.confidence > 1.0:
            self.confidence = 1.0
