"""Numbering continuity checks for headings and captions.

Two rules supported:
- ``heading.numbering.continuity`` — chapter / section numbering 1 → 2 → 3,
  1.1 → 1.2 → 1.3 (no gaps within the same parent)
- ``caption.numbering.continuity`` — figure / table numbering, both
  flat (图 1 → 图 2) and per-chapter (图 1.1 → 图 1.2)

We deliberately reuse ``_check_caption_numbering`` from
``thesis_formatter._common`` for the caption side — it already
handles 续表 / appendix prefixes and is exercised by the legacy
formatter. For the heading side we walk Heading{1..4} paragraphs
and parse the dotted prefix.
"""

from __future__ import annotations

import re
from typing import Iterable

from thesis_formatter._common import (
    _check_caption_numbering,
    get_paragraph_heading_level,
)

from ..types import CheckResult
from ._result import skip_result


def _truncate(s: str, limit: int = 80) -> str:
    if len(s) <= limit:
        return s
    return s[: limit - 1] + "…"


def _paragraphs(doc):
    if hasattr(doc, "_doc"):
        return doc._doc.paragraphs
    return doc.paragraphs


# ---------------------------------------------------------------------------
# Heading numbering
# ---------------------------------------------------------------------------

# Match a leading numeric prefix like:
#   "1 引言"        → ("1",)
#   "1.1 研究背景"  → ("1", "1")
#   "1.1.1 ..."     → ("1", "1", "1")
# The leading "第N章" form is recognised separately.
_NUMERIC_PREFIX = re.compile(r"^\s*(\d+(?:\.\d+)*)(?:\s|[、,，.])")
_CHAPTER_CN = re.compile(
    r"^\s*第\s*(?:(\d+)|([一二三四五六七八九十百千零两〇]+))\s*章"
)
_CN_NUM_MAP = {ch: i + 1 for i, ch in enumerate("一二三四五六七八九十")}


def _cn_to_int(s: str) -> int | None:
    """Best-effort 1..20 conversion. We don't need to handle 千 / 万."""
    if s in _CN_NUM_MAP:
        return _CN_NUM_MAP[s]
    if s == "十":
        return 10
    if s.startswith("十") and len(s) == 2:
        tail = _CN_NUM_MAP.get(s[1])
        if tail is not None:
            return 10 + tail
    if len(s) == 2 and s.endswith("十"):
        head = _CN_NUM_MAP.get(s[0])
        if head is not None:
            return head * 10
    if len(s) == 3 and s[1] == "十":
        head = _CN_NUM_MAP.get(s[0])
        tail = _CN_NUM_MAP.get(s[2])
        if head is not None and tail is not None:
            return head * 10 + tail
    return None


def _parse_heading_path(text: str) -> tuple[int, ...] | None:
    """Return the dotted numeric path of a heading text, or None."""
    m = _CHAPTER_CN.match(text)
    if m:
        if m.group(1):
            return (int(m.group(1)),)
        v = _cn_to_int(m.group(2))
        return (v,) if v is not None else None
    m = _NUMERIC_PREFIX.match(text)
    if m:
        parts = tuple(int(p) for p in m.group(1).split(".") if p)
        return parts or None
    return None


def _walk_headings(doc) -> Iterable[tuple[int, tuple[int, ...]]]:
    """Yield (level, parsed_path) for every Heading{1..4} paragraph."""
    for para in _paragraphs(doc):
        level = get_paragraph_heading_level(para)
        if level is None or level < 1 or level > 4:
            continue
        text = (para.text or "").strip()
        if not text:
            continue
        path = _parse_heading_path(text)
        if path is None:
            continue
        yield level, path


def _detect_heading_gaps(headings) -> list[str]:
    """Return human-readable gap descriptions, empty when continuous.

    Rule: within each parent prefix, the trailing index must increase
    by 1. Skipping a number = a gap; equal / decreasing also reported.
    """
    last_seen: dict[tuple[int, ...], int] = {}
    gaps: list[str] = []

    for level, path in headings:
        parent = path[:-1]
        idx = path[-1]
        prev = last_seen.get(parent)
        if prev is None:
            if idx != 1:
                gaps.append(
                    f"H{level} 起始号 {_format_path(parent, idx)} 不为 1"
                )
        else:
            expected = prev + 1
            if idx != expected:
                gaps.append(
                    f"H{level} 编号跳号: "
                    f"{_format_path(parent, prev)} → {_format_path(parent, idx)}"
                )
        last_seen[parent] = idx
    return gaps


def _format_path(parent: tuple[int, ...], tail: int) -> str:
    return ".".join(str(p) for p in parent + (tail,))


def check_heading_numbering_continuity(rule, doc) -> CheckResult:
    locator = rule.locator or {}
    headings = list(_walk_headings(doc))
    if not headings:
        return skip_result(
            rule=rule,
            evidence="no parsable numbered headings",
            locator=locator,
            reason="unmeasurable",
        )
    gaps = _detect_heading_gaps(headings)
    if not gaps:
        return CheckResult(
            rule_id=rule.id, status="pass",
            evidence=f"{len(headings)} headings continuous",
            locator_resolved=locator, severity=rule.severity,
        )
    return CheckResult(
        rule_id=rule.id, status="fail",
        evidence=_truncate("; ".join(gaps)),
        locator_resolved=locator, severity=rule.severity,
    )


# ---------------------------------------------------------------------------
# Caption numbering (delegate to legacy)
# ---------------------------------------------------------------------------

def check_caption_numbering_continuity(rule, doc) -> CheckResult:
    locator = rule.locator or {}
    cfg = getattr(doc, "_runtime_cfg", None)
    if cfg is None and hasattr(doc, "_doc"):
        # DocumentModel doesn't carry cfg yet; the runner passes it
        # via a side channel only when populated. Fall back to the
        # default scau patterns (defaults are conservative).
        cfg = {}
    raw = doc._doc if hasattr(doc, "_doc") else doc
    cap_cfg = (cfg or {}).get("captions", {}) if cfg else {}
    fig_pat = cap_cfg.get("figure_pattern", r"^图\s*\d")
    tbl_pat = cap_cfg.get("table_pattern", r"^(续)?表\s*\d")
    warnings = _check_caption_numbering(raw, fig_pat, tbl_pat, cfg=cfg) or []
    # No captions in doc → skip rather than pass (don't claim correctness).
    if not warnings and not _has_any_caption(raw, fig_pat, tbl_pat):
        return skip_result(
            rule=rule,
            evidence="no captions in document",
            locator=locator,
            reason="not_applicable",
        )
    if warnings:
        # Each warning is already a clear human-readable line; pick the
        # first to anchor evidence (≤80 chars).
        evidence = warnings[0].strip()
        # Strip the leading "  警告: " noise the legacy fn prepends.
        evidence = re.sub(r"^\s*警告\s*[:：]\s*", "", evidence)
        return CheckResult(
            rule_id=rule.id, status="fail",
            evidence=_truncate(evidence),
            locator_resolved=locator, severity=rule.severity,
        )
    return CheckResult(
        rule_id=rule.id, status="pass",
        evidence="captions continuous",
        locator_resolved=locator, severity=rule.severity,
    )


def _has_any_caption(doc, fig_pat: str, tbl_pat: str) -> bool:
    fig_re = re.compile(fig_pat)
    tbl_re = re.compile(tbl_pat)
    for p in doc.paragraphs:
        text = (p.text or "").strip()
        if fig_re.match(text) or tbl_re.match(text):
            return True
    return False
