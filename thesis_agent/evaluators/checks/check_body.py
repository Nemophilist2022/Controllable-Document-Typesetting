"""Body / Normal-style checks.

Covers rules:
    body.font.east_asia
    body.font.size
    body.line_spacing
    body.first_line_indent

All four rules use predicate ``equals`` and resolve via the Normal
style. Other ``equals``-based rules dispatch to their own check
functions registered in this package.
"""

from __future__ import annotations

from docx.enum.text import WD_LINE_SPACING

from ...spec.predicates import evaluate as predicate_evaluate
from ..runner import register_check
from ..types import CheckResult
from ._result import skip_result


def _truncate(s: str, limit: int = 80) -> str:
    if len(s) <= limit:
        return s
    return s[: limit - 1] + "…"


def _normal_style(doc):
    """Pull the Normal style off whatever doc-like object we got."""
    if hasattr(doc, "_doc"):  # DocumentModel
        return doc._doc.styles["Normal"]
    return doc.styles["Normal"]


def _line_spacing_value(pf):
    """Return line_spacing as a comparable value (multiple float or pt)."""
    rule = pf.line_spacing_rule
    if pf.line_spacing is None:
        return None
    if rule == WD_LINE_SPACING.MULTIPLE or rule is None:
        return pf.line_spacing
    if rule == WD_LINE_SPACING.EXACTLY or rule == WD_LINE_SPACING.AT_LEAST:
        return float(pf.line_spacing.pt)
    return pf.line_spacing


def _first_line_indent_pt(pf):
    if pf.first_line_indent is None:
        return None
    return float(pf.first_line_indent.pt)


def check_normal_style_equals(rule, doc) -> CheckResult:
    """Dispatch ``equals`` rules whose locator points at Normal style."""
    locator = rule.locator or {}
    if locator.get("style_name") != "Normal":
        return skip_result(
            rule=rule,
            evidence="locator not Normal style; not handled here",
            locator=locator,
            reason="unmeasurable",
            check_coverage="unimplemented",
        )

    style = _normal_style(doc)

    if rule.id == "body.font.east_asia":
        rfonts = style.element.find(
            "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}rPr"
        )
        actual = None
        if rfonts is not None:
            font_el = rfonts.find(
                "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}rFonts"
            )
            if font_el is not None:
                actual = font_el.get(
                    "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}eastAsia"
                )
    elif rule.id == "body.font.size":
        actual = style.font.size.pt if style.font.size is not None else None
    elif rule.id == "body.line_spacing":
        actual = _line_spacing_value(style.paragraph_format)
    elif rule.id == "body.first_line_indent":
        actual = _first_line_indent_pt(style.paragraph_format)
    else:
        return CheckResult(
            rule_id=rule.id,
            status="error",
            evidence=f"unknown rule id for body check: {rule.id}",
            locator_resolved=locator,
            severity=rule.severity,
        )

    passed = predicate_evaluate(rule.predicate, actual, rule.expected)
    return CheckResult(
        rule_id=rule.id,
        status="pass" if passed else "fail",
        evidence=_truncate(f"actual={actual!r} expected={rule.expected!r}"),
        locator_resolved=locator,
        severity=rule.severity,
    )


def register() -> None:
    register_check("equals", check_normal_style_equals)


# Register all four rules under predicate "equals".
register()
