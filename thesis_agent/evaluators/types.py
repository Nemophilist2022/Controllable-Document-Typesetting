"""CheckResult / EvalReport data contracts (R4.3, R4.6, R4.7).

Evaluator-layer status uses four values: ``pass / fail / skip / error``.
The mapping to delivery-layer ``done / partial / failed / skipped`` is
done by ``thesis_agent.delivery.report`` (see R4.6 mapping rule).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

# Tuple kept for runtime iteration (e.g. ``set(CheckStatus)`` in tests).
CheckStatus: tuple[str, ...] = ("pass", "fail", "skip", "error")
StatusValue = Literal["pass", "fail", "skip", "error"]


@dataclass
class CheckResult:
    """Outcome of evaluating a single :class:`Rule`.

    Attributes:
        rule_id: The id of the rule this result belongs to.
        status: ``pass`` / ``fail`` / ``skip`` / ``error``.
        evidence: Short, human-readable string explaining what was
            observed. Bounded to 80 chars by C5; the truncation policy
            itself is enforced by the layer that creates evidence
            strings, not here.
        locator_resolved: A concrete locator (paragraph index, style
            name, ...). Empty dict when not applicable.
        severity: Mirrors :attr:`Rule.severity` for convenience.
        metadata: Extra context for the diagnoser layer (e.g.
            ``text_hash`` of the truncated paragraph).
    """

    rule_id: str
    status: StatusValue
    evidence: str
    locator_resolved: dict[str, Any]
    severity: Literal["must", "should", "info"]
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in CheckStatus:
            raise ValueError(
                f"invalid status {self.status!r}; "
                f"must be one of {CheckStatus}"
            )


@dataclass
class EvalReport:
    """Aggregate outcome of running a :class:`RuleSet` over a document.

    ``summary`` is auto-derived from ``results`` so callers always see a
    consistent snapshot.
    """

    profile: str
    results: list[CheckResult]
    duration_ms: int = 0
    summary: dict[str, int] = field(init=False)

    def __post_init__(self) -> None:
        self.summary = self._summarize(self.results)

    @staticmethod
    def _summarize(results: list[CheckResult]) -> dict[str, int]:
        summary = {key: 0 for key in ("total", *CheckStatus)}
        for cr in results:
            summary["total"] += 1
            summary[cr.status] += 1
        return summary
