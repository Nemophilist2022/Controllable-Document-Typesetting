"""Front-matter presence checks (摘要 / Abstract / 关键词 / Key words).

Handles rules of the form::

    locator = {"front_matter": "cn_abstract"}     # 中文摘要标题
    locator = {"front_matter": "cn_keywords"}     # 关键词：xxx
    locator = {"front_matter": "en_abstract"}     # Abstract: xxx
    locator = {"front_matter": "en_keywords"}     # Key words: xxx

We deliberately do NOT reuse ``thesis_formatter.structure.validate_structure``
here — that function has the still-unfixed ``normalize_title`` bug
(C1) and conflates style detection with structural advice. The
implementation below mirrors the regex patterns from the SCAU profile
``sections`` block but stays in the evaluator layer.
"""

from __future__ import annotations

import re

from ..runner import register_check
from ..types import CheckResult


def _truncate(s: str, limit: int = 80) -> str:
    if len(s) <= limit:
        return s
    return s[: limit - 1] + "…"


def _iter_paragraph_texts(doc):
    if hasattr(doc, "paragraphs"):
        get = doc.paragraphs
        if callable(get):
            for p in get():
                yield p.text
        else:
            for p in get:
                yield p.text


def _has_cn_abstract_title(doc) -> bool:
    for text in _iter_paragraph_texts(doc):
        compact = re.sub(r"\s+", "", text or "").replace("　", "")
        if compact == "摘要":
            return True
    return False


def _has_cn_keywords(doc) -> bool:
    pat = re.compile(r"^\s*关键词\s*[：:]")
    for text in _iter_paragraph_texts(doc):
        if pat.match(text or ""):
            return True
    return False


def _has_en_abstract(doc) -> bool:
    pat = re.compile(r"(?i)^\s*Abstract\s*[:：]")
    title_pat = re.compile(r"(?i)^\s*Abstract\s*$")
    for text in _iter_paragraph_texts(doc):
        if pat.match(text or "") or title_pat.match(text or ""):
            return True
    return False


def _has_en_keywords(doc) -> bool:
    pat = re.compile(r"(?i)^\s*Key\s*words?\s*[:：]")
    for text in _iter_paragraph_texts(doc):
        compact = re.sub(r"\s+", " ", text or "")
        if pat.match(compact):
            return True
    return False


_PROBES = {
    "cn_abstract": _has_cn_abstract_title,
    "cn_keywords": _has_cn_keywords,
    "en_abstract": _has_en_abstract,
    "en_keywords": _has_en_keywords,
}


def check_front_matter_presence(rule, doc) -> CheckResult:
    locator = rule.locator or {}
    target = locator.get("front_matter")
    probe = _PROBES.get(target) if target else None
    if probe is None:
        return CheckResult(
            rule_id=rule.id, status="skip",
            evidence=f"no probe for front_matter={target!r}",
            locator_resolved=locator, severity=rule.severity,
        )
    present = probe(doc)
    expected = bool(rule.expected)
    passed = present == expected
    return CheckResult(
        rule_id=rule.id,
        status="pass" if passed else "fail",
        evidence=_truncate(f"front_matter.{target} present={present}"),
        locator_resolved=locator,
        severity=rule.severity,
    )


# No standalone register() — the ``exists`` predicate is multiplexed
# inside ``check_headings._exists_dispatcher`` to avoid two modules
# fighting for the same predicate slot.
def register() -> None:
    return None
