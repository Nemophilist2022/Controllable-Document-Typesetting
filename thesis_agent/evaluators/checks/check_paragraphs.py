"""Paragraph-scoped checks for caption / reference / TOC entry rules.

Handles rules whose locators look like:

    {"caption": True, "attr": "east_asia_font"}
    {"caption": True, "attr": "size_pt"}
    {"references_section": True, "attr": "first_line_indent_pt"}
    {"toc_entries": True, "attr": "east_asia_font"}

Each check picks paragraphs by simple text / style heuristics and
asserts that **all** matching paragraphs agree on the expected value.
If no paragraph matches the locator at all we return ``skip`` —
that's the right behaviour for documents that just don't have any
captions / references / TOC yet.
"""

from __future__ import annotations

import re
from typing import Iterable, Optional

from ...spec.predicates import evaluate as predicate_evaluate
from ..types import CheckResult
from ._result import skip_result


_W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

_FIG_PAT = re.compile(r"^\s*图\s*\d")
_TBL_PAT = re.compile(r"^\s*(续)?表\s*\d")
_REF_PAT = re.compile(r"^\s*\[\s*\d+\s*\]")  # 参考文献条目 [1] / [12] ...


def _truncate(s: str, limit: int = 80) -> str:
    if len(s) <= limit:
        return s
    return s[: limit - 1] + "…"


def _paragraphs(doc):
    if hasattr(doc, "_doc"):
        return doc._doc.paragraphs
    return doc.paragraphs


def _para_east_asia(para) -> Optional[str]:
    """Read the first run's eastAsia font; fall back to the paragraph's
    style if the run has none set."""
    for run in para.runs:
        rpr = run._element.find(_W_NS + "rPr")
        if rpr is not None:
            rfonts = rpr.find(_W_NS + "rFonts")
            if rfonts is not None:
                v = rfonts.get(_W_NS + "eastAsia")
                if v:
                    return v
    style = para.style
    if style is not None:
        rpr = style.element.find(_W_NS + "rPr")
        if rpr is not None:
            rfonts = rpr.find(_W_NS + "rFonts")
            if rfonts is not None:
                return rfonts.get(_W_NS + "eastAsia")
    return None


def _para_size_pt(para) -> Optional[float]:
    for run in para.runs:
        if run.font.size is not None:
            return float(run.font.size.pt)
    style = para.style
    if style is not None and style.font.size is not None:
        return float(style.font.size.pt)
    return None


def _para_first_line_indent_pt(para) -> Optional[float]:
    pf = para.paragraph_format
    if pf.first_line_indent is None:
        return None
    return float(pf.first_line_indent.pt)


# ---------------------------------------------------------------------------
# Selectors
# ---------------------------------------------------------------------------

def _select_captions(paragraphs) -> Iterable:
    for p in paragraphs:
        text = (p.text or "").strip()
        if _FIG_PAT.match(text) or _TBL_PAT.match(text):
            yield p


def _select_reference_entries(paragraphs) -> Iterable:
    """References section paragraphs ([1] xxx, [2] yyy ...).

    We yield every paragraph that starts with ``[<digit>]``; the
    ``参考文献`` heading itself is filtered out by the prefix.
    """
    for p in paragraphs:
        text = (p.text or "").strip()
        if _REF_PAT.match(text):
            yield p


def _select_toc_entries(paragraphs) -> Iterable:
    for p in paragraphs:
        sn = (p.style.name if p.style else "") or ""
        if sn.lower().startswith("toc "):
            yield p


# ---------------------------------------------------------------------------
# Attribute readers
# ---------------------------------------------------------------------------

_ATTR_READERS = {
    "east_asia_font": _para_east_asia,
    "size_pt": _para_size_pt,
    "first_line_indent_pt": _para_first_line_indent_pt,
}


def _aggregate(paragraphs, attr: str):
    """Return (sample, uniform, count). ``sample`` is the first non-None
    value; ``uniform`` says all values agree."""
    reader = _ATTR_READERS.get(attr)
    if reader is None:
        return None, False, 0
    sample = None
    uniform = True
    count = 0
    for p in paragraphs:
        v = reader(p)
        if v is None:
            continue
        count += 1
        if sample is None:
            sample = v
        elif sample != v:
            uniform = False
    return sample, uniform, count


# ---------------------------------------------------------------------------
# Public dispatcher (called by check_toc._equals_dispatcher)
# ---------------------------------------------------------------------------

def check_paragraph_group_attr(rule, doc) -> CheckResult:
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

    paragraphs = _paragraphs(doc)
    if locator.get("caption"):
        selected = list(_select_captions(paragraphs))
        group_label = "captions"
    elif locator.get("references_section"):
        selected = list(_select_reference_entries(paragraphs))
        group_label = "references"
    elif locator.get("toc_entries"):
        selected = list(_select_toc_entries(paragraphs))
        group_label = "toc_entries"
    else:
        return skip_result(
            rule=rule,
            evidence=f"unsupported paragraph locator {locator!r}",
            locator=locator,
            reason="unmeasurable",
            check_coverage="unimplemented",
        )

    if not selected:
        return skip_result(
            rule=rule,
            evidence=f"no {group_label} found in document",
            locator=locator,
            reason="not_applicable",
        )

    sample, uniform, count = _aggregate(selected, attr)
    if sample is None:
        return skip_result(
            rule=rule,
            evidence=f"{group_label} have no {attr} set ({count} checked)",
            locator=locator,
            reason="unmeasurable",
        )
    if not uniform:
        return CheckResult(
            rule_id=rule.id, status="fail",
            evidence=_truncate(f"{group_label} disagree on {attr}: sample={sample!r}"),
            locator_resolved=locator, severity=rule.severity,
        )

    passed = predicate_evaluate(rule.predicate, sample, rule.expected)
    return CheckResult(
        rule_id=rule.id,
        status="pass" if passed else "fail",
        evidence=_truncate(
            f"{group_label}.{attr}: actual={sample!r} expected={rule.expected!r}"
        ),
        locator_resolved=locator,
        severity=rule.severity,
    )
