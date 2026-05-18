"""Style-level checks for non-Normal styles (Headings, TOC entries...).

Handles rules of the form::

    locator = {"style_name": "Heading 1", "attr": "east_asia_font"}
    locator = {"style_name": "Heading 2", "attr": "size_pt"}

When the locator omits ``attr`` (as with the auto-emitted heading
rules whose id already encodes the attribute, e.g.
``heading.h1.font.east_asia``) we infer the attribute from the rule
id suffix.

These cover the per-level heading font / size / bold rules added in A2.
``check_body`` already handles the ``Normal`` style; this module covers
everything else.
"""

from __future__ import annotations

from typing import Any

from ...spec.predicates import evaluate as predicate_evaluate
from ..types import CheckResult


_W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

# rule.id suffix → attr name we read off the style.
_ID_SUFFIX_TO_ATTR = {
    "font.east_asia": "east_asia_font",
    "font.size": "size_pt",
    "bold": "bold",
}


def _truncate(s: str, limit: int = 80) -> str:
    if len(s) <= limit:
        return s
    return s[: limit - 1] + "…"


def _infer_attr(rule_id: str) -> str | None:
    """Match the longest known suffix of *rule_id*."""
    for suffix, attr in _ID_SUFFIX_TO_ATTR.items():
        if rule_id.endswith("." + suffix) or rule_id.endswith(suffix):
            return attr
    return None


def _get_style(doc, name: str):
    if hasattr(doc, "_doc"):
        styles = doc._doc.styles
    else:
        styles = doc.styles
    try:
        return styles[name]
    except KeyError:
        return None


def _get_east_asia_font(style) -> str | None:
    """Read ``rPr/rFonts/@eastAsia`` directly from the style XML.

    python-docx's high-level ``style.font.name`` only exposes the
    Latin font slot. Heading styles in the default docx template
    typically set east-asian via ``rFonts`` only, so we go to the
    XML directly.
    """
    rpr = style.element.find(_W_NS + "rPr")
    if rpr is None:
        return None
    rfonts = rpr.find(_W_NS + "rFonts")
    if rfonts is None:
        return None
    return rfonts.get(_W_NS + "eastAsia")


def _get_attr(style, attr: str) -> Any:
    if attr == "east_asia_font":
        return _get_east_asia_font(style)
    if attr == "size_pt":
        return style.font.size.pt if style.font.size is not None else None
    if attr == "bold":
        return style.font.bold
    return None


def check_style_attr(rule, doc) -> CheckResult:
    """Resolve ``rule.locator['style_name']`` and compare ``attr``."""
    locator = rule.locator or {}
    style_name = locator.get("style_name")
    attr = locator.get("attr") or _infer_attr(rule.id)

    style = _get_style(doc, style_name) if style_name else None
    if style is None:
        return CheckResult(
            rule_id=rule.id,
            status="skip",
            evidence=f"style {style_name!r} not found",
            locator_resolved=locator,
            severity=rule.severity,
        )

    if not attr:
        return CheckResult(
            rule_id=rule.id,
            status="skip",
            evidence=f"could not infer attr from rule id {rule.id!r}",
            locator_resolved=locator,
            severity=rule.severity,
        )

    actual = _get_attr(style, attr)
    if actual is None:
        return CheckResult(
            rule_id=rule.id,
            status="skip",
            evidence=f"attr {attr!r} unset on style {style_name!r}",
            locator_resolved=locator,
            severity=rule.severity,
        )

    passed = predicate_evaluate(rule.predicate, actual, rule.expected)
    return CheckResult(
        rule_id=rule.id,
        status="pass" if passed else "fail",
        evidence=_truncate(f"{style_name}.{attr}: actual={actual!r} expected={rule.expected!r}"),
        locator_resolved=locator,
        severity=rule.severity,
    )
