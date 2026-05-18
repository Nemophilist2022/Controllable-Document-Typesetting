"""TOC sanity checks.

Covers rule:
    toc.entry_count

The rule's ``expected`` is the symbolic string ``"match_heading_count"``;
the check counts headings in the doc and TOC entries (paragraphs whose
style starts with "TOC ") and verifies they agree.
"""

from __future__ import annotations

from ..runner import register_check
from ..types import CheckResult
from ._result import skip_result


def _iter_paragraph_style_names(doc):
    if hasattr(doc, "paragraphs"):
        get = doc.paragraphs
        if callable(get):
            for p in get():
                yield p.style_name
        else:
            for p in get:
                yield p.style.name if p.style else ""


def _count_headings_and_toc_entries(doc) -> tuple[int, int]:
    headings = 0
    toc_entries = 0
    for sn in _iter_paragraph_style_names(doc):
        sn_low = (sn or "").lower()
        if sn_low.startswith("heading ") or sn_low.startswith("heading"):
            headings += 1
        elif sn_low.startswith("toc "):
            toc_entries += 1
    return headings, toc_entries


def check_toc_entry_count(rule, doc) -> CheckResult:
    if rule.id != "toc.entry_count":
        return skip_result(
            rule=rule,
            evidence="not handled by check_toc",
            locator=rule.locator or {},
            reason="unmeasurable",
            check_coverage="unimplemented",
        )

    headings, toc_entries = _count_headings_and_toc_entries(doc)
    if rule.expected == "match_heading_count":
        passed = (toc_entries == headings)
        return CheckResult(
            rule_id=rule.id,
            status="pass" if passed else "fail",
            evidence=f"headings={headings} toc_entries={toc_entries}",
            locator_resolved=rule.locator or {},
            severity=rule.severity,
        )

    # Numeric expected
    try:
        passed = toc_entries == int(rule.expected)
    except (TypeError, ValueError):
        return CheckResult(
            rule_id=rule.id,
            status="error",
            evidence=f"unsupported expected: {rule.expected!r}",
            locator_resolved=rule.locator or {},
            severity=rule.severity,
        )
    return CheckResult(
        rule_id=rule.id,
        status="pass" if passed else "fail",
        evidence=f"toc_entries={toc_entries} expected={rule.expected}",
        locator_resolved=rule.locator or {},
        severity=rule.severity,
    )


# ---------------------------------------------------------------------------
# Equals dispatcher
# ---------------------------------------------------------------------------
#
# Different rule families share predicate ``equals`` but resolve via
# different document fixtures (Normal style, Heading styles, sections,
# tables, captions, references, headers...). The runner only allows
# one check per predicate, so this module owns the dispatcher and
# fans out by locator / rule.id.
#
# Order:
#   1. toc.entry_count             -> check_toc_entry_count (this file)
#   2. locator.style_name=Normal   -> check_body
#   3. locator.style_name=*        -> check_styles
#   4. locator.all_sections        -> check_sections
#   5. locator.all_tables          -> check_tables
#   6. locator.caption|references_section|toc_entries -> check_paragraphs
#   7. locator.header              -> check_doc
#   8. anything else               -> skip with a clear evidence message

def _equals_dispatcher(rule, doc):
    locator = rule.locator or {}

    if rule.id.startswith("toc."):
        # toc.entry_count handled here; toc.font.* falls through to the
        # paragraph-style branch below.
        if rule.id == "toc.entry_count":
            return check_toc_entry_count(rule, doc)

    # Numbering continuity rules — symbolic expected="continuous".
    if rule.id == "heading.numbering.continuity":
        from .check_numbering import check_heading_numbering_continuity
        return check_heading_numbering_continuity(rule, doc)
    if rule.id == "caption.numbering.continuity":
        from .check_numbering import check_caption_numbering_continuity
        return check_caption_numbering_continuity(rule, doc)

    if locator.get("style_name") == "Normal":
        from .check_body import check_normal_style_equals
        return check_normal_style_equals(rule, doc)

    if locator.get("style_name"):
        from .check_styles import check_style_attr
        return check_style_attr(rule, doc)

    if locator.get("all_sections"):
        from .check_sections import check_all_sections_attr
        return check_all_sections_attr(rule, doc)

    if locator.get("all_tables"):
        from .check_tables import check_all_tables_edge
        return check_all_tables_edge(rule, doc)

    if (locator.get("caption")
            or locator.get("references_section")
            or locator.get("toc_entries")):
        from .check_paragraphs import check_paragraph_group_attr
        return check_paragraph_group_attr(rule, doc)

    if locator.get("header"):
        from .check_doc import check_header_enabled
        return check_header_enabled(rule, doc)

    # Fallthrough: not addressable by any registered handler. Skip
    # (rather than fail) so MVP-style fixtures aren't punished for
    # rules whose checks land in v0.3.
    return skip_result(
        rule=rule,
        evidence=f"no equals handler for locator {locator!r}",
        locator=locator,
        reason="unmeasurable",
        check_coverage="unimplemented",
    )


def register() -> None:
    register_check("equals", _equals_dispatcher)


# Auto-register on first import so simple ``import check_toc`` callers
# don't need to remember to call register().
register()
