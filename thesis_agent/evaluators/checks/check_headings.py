"""Heading presence checks + ``exists`` predicate dispatcher.

Owns the ``exists`` predicate registration. Heading rules live here;
front-matter rules forward to ``check_front_matter``.
"""

from __future__ import annotations

from ..runner import register_check
from ..types import CheckResult


def _has_heading_level(doc, level: int) -> bool:
    """Return True if any paragraph in *doc* uses Heading{level}."""
    name_short = f"Heading {level}"
    name_compact = f"Heading{level}"
    if hasattr(doc, "paragraphs"):
        get_paragraphs = doc.paragraphs
        if callable(get_paragraphs):
            paragraphs = get_paragraphs()
            for p in paragraphs:
                if p.style_name in (name_short, name_compact):
                    return True
            return False
        for p in get_paragraphs:
            sn = p.style.name if p.style else ""
            if sn in (name_short, name_compact):
                return True
        return False
    return False


def check_heading_exists(rule, doc) -> CheckResult:
    locator = rule.locator or {}
    level = locator.get("heading_level")
    if level is None:
        return CheckResult(
            rule_id=rule.id,
            status="skip",
            evidence="locator missing heading_level; check_headings cannot dispatch",
            locator_resolved=locator,
            severity=rule.severity,
        )

    present = _has_heading_level(doc, int(level))
    expected = bool(rule.expected)
    passed = present == expected
    return CheckResult(
        rule_id=rule.id,
        status="pass" if passed else "fail",
        evidence=f"heading_level={level} present={present}",
        locator_resolved=locator,
        severity=rule.severity,
    )


def _exists_dispatcher(rule, doc):
    locator = rule.locator or {}
    if locator.get("heading_level") is not None:
        return check_heading_exists(rule, doc)
    if locator.get("front_matter"):
        from .check_front_matter import check_front_matter_presence
        return check_front_matter_presence(rule, doc)
    return CheckResult(
        rule_id=rule.id,
        status="skip",
        evidence=f"no exists handler for locator {locator!r}",
        locator_resolved=locator,
        severity=rule.severity,
    )


def register() -> None:
    register_check("exists", _exists_dispatcher)


register()
