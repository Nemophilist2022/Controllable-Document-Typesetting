"""Predicate ``one_of`` dispatcher.

For v0.2 the only consumers are page-number format rules
(``page_number.front.format`` / ``page_number.body.format``). We resolve
them by reading the ``w:pgNumType`` ``fmt`` attribute on the relevant
section's ``sectPr`` element.

When we can't determine which section is "front" vs "body" (single-
section documents are common in fixtures), we mark the rule as
``skip`` rather than fail — this is informational, not destructive.
"""

from __future__ import annotations

from ...spec.predicates import evaluate as predicate_evaluate
from ..runner import register_check
from ..types import CheckResult

_W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _truncate(s: str, limit: int = 80) -> str:
    if len(s) <= limit:
        return s
    return s[: limit - 1] + "…"


def _section_fmt(section) -> str | None:
    sect_pr = section._sectPr
    pgNumType = sect_pr.find(_W_NS + "pgNumType")
    if pgNumType is None:
        return None
    return pgNumType.get(_W_NS + "fmt")


def _check_page_number_format(rule, doc) -> CheckResult:
    locator = rule.locator or {}
    target = locator.get("page_numbers")  # "front" or "body"

    if hasattr(doc, "_doc"):
        sections = doc._doc.sections
    else:
        sections = doc.sections

    if not sections:
        return CheckResult(
            rule_id=rule.id, status="skip",
            evidence="document has no sections",
            locator_resolved=locator, severity=rule.severity,
        )

    if len(sections) < 2 and target == "body":
        # No body/front split yet (typical for hand-built fixtures).
        return CheckResult(
            rule_id=rule.id, status="skip",
            evidence="single-section doc; no body section yet",
            locator_resolved=locator, severity=rule.severity,
        )

    section = sections[0] if target == "front" else sections[-1]
    actual = _section_fmt(section)
    if actual is None:
        return CheckResult(
            rule_id=rule.id, status="skip",
            evidence="no pgNumType set on section",
            locator_resolved=locator, severity=rule.severity,
        )

    passed = predicate_evaluate(rule.predicate, actual, rule.expected)
    return CheckResult(
        rule_id=rule.id,
        status="pass" if passed else "fail",
        evidence=_truncate(f"section_fmt={actual!r} expected one_of {rule.expected}"),
        locator_resolved=locator,
        severity=rule.severity,
    )


def _one_of_dispatcher(rule, doc):
    if rule.id.startswith("page_number."):
        return _check_page_number_format(rule, doc)
    return CheckResult(
        rule_id=rule.id,
        status="skip",
        evidence=f"no one_of handler for {rule.id!r}",
        locator_resolved=rule.locator or {},
        severity=rule.severity,
    )


def register() -> None:
    register_check("one_of", _one_of_dispatcher)


register()
