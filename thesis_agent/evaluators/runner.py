"""Evaluator runner — drives Rules → CheckResults (R4.1, R4.5~R4.7).

Pure rule logic; **must not** import any LLM client (see
``test_evaluators_no_llm_imports.py``). Each predicate name has at most
one registered check function. Register checks via :func:`register_check`
or — preferred — by writing a module under ``evaluators/checks/`` that
calls ``register_check`` at import time.
"""

from __future__ import annotations

import time
from typing import Callable

from ..spec.rule_set import Rule, RuleSet
from .types import CheckResult, EvalReport

# A check function maps (rule, doc) → CheckResult. Different rules
# sharing the same predicate (e.g. equals) typically share one check
# function that switches on rule.locator / rule.id internally. For MVP
# we use a single registry keyed on predicate name.
CheckFn = Callable[[Rule, object], CheckResult]

_CHECKS: dict[str, CheckFn] = {}


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_check(predicate_name: str, fn: CheckFn) -> None:
    _CHECKS[predicate_name] = fn


def clear_checks() -> None:
    _CHECKS.clear()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def evaluate(
    doc,
    rule_set: RuleSet,
    only_rule_ids: list[str] | None = None,
) -> EvalReport:
    """Run *rule_set* over *doc* and aggregate the results."""
    only = set(only_rule_ids) if only_rule_ids else None
    results: list[CheckResult] = []
    started = time.perf_counter()

    for rule in rule_set.rules:
        if only is not None and rule.id not in only:
            continue
        results.append(_run_one(rule, doc))

    duration_ms = int((time.perf_counter() - started) * 1000)
    return EvalReport(
        profile=rule_set.profile,
        results=results,
        duration_ms=duration_ms,
    )


def _run_one(rule: Rule, doc) -> CheckResult:
    fn = _CHECKS.get(rule.predicate)
    if fn is None:
        return CheckResult(
            rule_id=rule.id,
            status="error",
            evidence=f"no check registered for predicate {rule.predicate!r}",
            locator_resolved=rule.locator,
            severity=rule.severity,
        )
    try:
        return fn(rule, doc)
    except Exception as exc:
        return CheckResult(
            rule_id=rule.id,
            status="error",
            evidence=f"check error: {exc}",
            locator_resolved=rule.locator,
            severity=rule.severity,
        )
