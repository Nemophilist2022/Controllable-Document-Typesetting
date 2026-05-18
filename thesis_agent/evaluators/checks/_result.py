"""Small helpers for classified evaluator outcomes.

``skip`` is still a first-class evaluator status, but it must not mean
"not implemented".  These helpers attach stable machine-readable reason
codes so delivery/reporting layers can distinguish optional content from
OOXML fields that cannot be measured.
"""

from __future__ import annotations

from typing import Any

from ..types import CheckResult


def skip_result(
    *,
    rule,
    evidence: str,
    locator: dict[str, Any] | None = None,
    reason: str,
    check_coverage: str = "implemented",
) -> CheckResult:
    return CheckResult(
        rule_id=rule.id,
        status="skip",
        evidence=evidence,
        locator_resolved=locator if locator is not None else (rule.locator or {}),
        severity=rule.severity,
        metadata={
            "skip_reason": reason,
            "check_coverage": check_coverage,
        },
    )
