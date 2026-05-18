"""Doc-scoped checks that don't introspect paragraphs.

Only ``header.enabled`` for now. The expected value is read off the
profile's ``header_footer.enabled`` boolean — there is no document
side because Word has no top-level ``has-header?`` flag, headers
exist per-section. We treat the rule as passing if **any** section
declares a non-empty header story, and as failing otherwise.
"""

from __future__ import annotations

from ..types import CheckResult


_W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _truncate(s: str, limit: int = 80) -> str:
    if len(s) <= limit:
        return s
    return s[: limit - 1] + "…"


def _has_any_header(doc) -> bool:
    sections = doc._doc.sections if hasattr(doc, "_doc") else doc.sections
    for section in sections:
        for header in (section.header, section.first_page_header,
                        section.even_page_header):
            if header is None:
                continue
            for p in header.paragraphs:
                if (p.text or "").strip():
                    return True
    return False


def check_header_enabled(rule, doc) -> CheckResult:
    locator = rule.locator or {}
    expected = bool(rule.expected)
    actual = _has_any_header(doc)
    passed = actual == expected
    return CheckResult(
        rule_id=rule.id,
        status="pass" if passed else "fail",
        evidence=_truncate(f"header_enabled: actual={actual} expected={expected}"),
        locator_resolved=locator,
        severity=rule.severity,
    )
