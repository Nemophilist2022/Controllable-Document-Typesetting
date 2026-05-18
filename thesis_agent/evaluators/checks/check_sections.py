"""Section-level checks for page layout (margins / gutter / distances).

Handles rules of the form::

    locator = {"all_sections": True, "attr": "top_margin_cm"}

Cm-based attributes are resolved via ``Length.cm`` from python-docx so
the comparison happens in user-facing units regardless of how Word
stores them.
"""

from __future__ import annotations

from ...spec.predicates import evaluate as predicate_evaluate
from ..types import CheckResult
from ._result import skip_result


_CM_TOLERANCE = 0.01  # 1 mm; cm values from yaml are written to 1-2 decimals


def _truncate(s: str, limit: int = 80) -> str:
    if len(s) <= limit:
        return s
    return s[: limit - 1] + "…"


def _sections(doc):
    if hasattr(doc, "_doc"):
        return doc._doc.sections
    return doc.sections


def _attr_value_cm(section, attr: str) -> float | None:
    mapping = {
        "top_margin_cm": section.top_margin,
        "bottom_margin_cm": section.bottom_margin,
        "left_margin_cm": section.left_margin,
        "right_margin_cm": section.right_margin,
        "gutter_cm": section.gutter,
        "header_distance_cm": section.header_distance,
        "footer_distance_cm": section.footer_distance,
    }
    length = mapping.get(attr)
    if length is None:
        return None
    return float(length.cm)


def _approx_equal(actual: float, expected) -> bool:
    try:
        expected_f = float(expected)
    except (TypeError, ValueError):
        return False
    return abs(actual - expected_f) <= _CM_TOLERANCE


def check_all_sections_attr(rule, doc) -> CheckResult:
    """All sections must agree on the same value for *attr*."""
    locator = rule.locator or {}
    attr = locator.get("attr")
    if not attr:
        return skip_result(
            rule=rule,
            evidence="locator missing attr",
            locator=locator,
            reason="unmeasurable",
            check_coverage="unimplemented",
        )

    sections = _sections(doc)
    if not sections:
        return skip_result(
            rule=rule,
            evidence="document has no sections",
            locator=locator,
            reason="unmeasurable",
        )

    actual_values = [_attr_value_cm(s, attr) for s in sections]
    if any(v is None for v in actual_values):
        return skip_result(
            rule=rule,
            evidence=f"attr {attr!r} unsupported",
            locator=locator,
            reason="unmeasurable",
            check_coverage="unimplemented",
        )

    # Sections must (a) all match expected and (b) be uniform.
    uniform = all(_approx_equal(v, actual_values[0]) for v in actual_values)
    matches_expected = all(_approx_equal(v, rule.expected) for v in actual_values)
    passed = uniform and matches_expected

    sample = actual_values[0]
    return CheckResult(
        rule_id=rule.id,
        status="pass" if passed else "fail",
        evidence=_truncate(
            f"{attr}: section[0]={sample:.2f}cm expected={rule.expected}"
        ),
        locator_resolved=locator,
        severity=rule.severity,
    )
