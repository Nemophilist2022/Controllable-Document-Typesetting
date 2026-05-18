"""Three-line table border checks.

Handles rules of the form::

    locator = {"all_tables": True, "edge": "top"}

In Word OOXML the border weight is stored as ``w:sz`` in eighths of a
point. The yaml expected value is also in eighths so we compare raw.
"""

from __future__ import annotations

from ...spec.predicates import evaluate as predicate_evaluate
from ..types import CheckResult
from ._result import skip_result

_W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _truncate(s: str, limit: int = 80) -> str:
    if len(s) <= limit:
        return s
    return s[: limit - 1] + "…"


def _tables(doc):
    if hasattr(doc, "_doc"):
        return doc._doc.tables
    return doc.tables


def _edge_sz_for_table(table, edge: str) -> int | None:
    """Read the size-of-line attribute on the requested edge of the
    first eligible cell (top edge → row 0, bottom → last row, header →
    bottom of row 0). Returns None when no border is set."""
    rows = table.rows
    if not rows:
        return None
    if edge == "top":
        cells = rows[0].cells
        target_edge = "top"
    elif edge == "bottom":
        cells = rows[-1].cells
        target_edge = "bottom"
    elif edge == "header":
        cells = rows[0].cells
        target_edge = "bottom"
    else:
        return None

    if not cells:
        return None
    tc = cells[0]._tc
    tc_pr = tc.find(_W_NS + "tcPr")
    if tc_pr is None:
        return None
    borders = tc_pr.find(_W_NS + "tcBorders")
    if borders is None:
        return None
    edge_el = borders.find(_W_NS + target_edge)
    if edge_el is None:
        return None
    val = edge_el.get(_W_NS + "sz")
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def check_all_tables_edge(rule, doc) -> CheckResult:
    locator = rule.locator or {}
    edge = locator.get("edge")
    tables = _tables(doc)
    if not tables:
        return skip_result(
            rule=rule,
            evidence="document has no tables",
            locator=locator,
            reason="not_applicable",
        )
    actual_values = [_edge_sz_for_table(t, edge) for t in tables]
    # If the document has tables but none have a border on this edge,
    # mark as skip (likely not a three-line table at all).
    if all(v is None for v in actual_values):
        return skip_result(
            rule=rule,
            evidence=f"no {edge} border found on any table",
            locator=locator,
            reason="unmeasurable",
        )

    measurable = [v for v in actual_values if v is not None]
    sample = measurable[0]
    uniform = all(v == sample for v in measurable)
    passed = uniform and predicate_evaluate(rule.predicate, sample, rule.expected)
    return CheckResult(
        rule_id=rule.id,
        status="pass" if passed else "fail",
        evidence=_truncate(f"{edge} border sz: actual={sample} expected={rule.expected}"),
        locator_resolved=locator,
        severity=rule.severity,
    )
