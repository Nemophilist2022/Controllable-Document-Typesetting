"""Compile a deep-merged template dict into a :class:`RuleSet`.

MVP scope (see requirements §4): emit at least the four core dimensions
- ``body.font.east_asia`` / ``body.font.size``
- ``body.line_spacing``
- ``heading.h1.style_present``
- ``toc.entry_count``

Other dimensions listed in R1.3 are emitted as **deferred placeholders**
(``metadata.deferred=True``) so MVP doesn't have to grow the compiler
mid-flight; future tasks can flip them on by adding mapping logic here.

Per R1.4 unknown YAML keys are collected with a dotted path into
``RuleSet.metadata.unknown_keys`` and merely logged — never raised.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable

from .predicates import known_predicates
from .rule_set import Rule, RuleSet

_LOG = logging.getLogger(__name__)

# Top-level YAML keys the compiler understands. Unknown top-level keys
# are recorded in metadata.unknown_keys but do not abort compilation
# (R1.4).
_RECOGNISED_TOP_LEVEL_KEYS = {
    "meta",
    "page",
    "fonts",
    "sizes",
    "headings",
    "body",
    "table",
    "footnote",
    "captions",
    "references",
    "page_numbers",
    "header_footer",
    "toc",
    "special_titles",
    "front_matter",
    "sections",
    "cover",
    "declarations",
    "theme_fonts",
    # Internal channel for tests/CLI overrides at rule level (used by
    # CompilerErrorTests). Keeps overrides explicit instead of merged
    # with the regular config tree.
    "_overrides",
    "_runtime",
}

# Body / Normal-style keys we know about. Anything else inside ``body``
# is reported as unknown.
_BODY_KEYS = {
    "align",
    "first_line_indent",
    "line_spacing",
    "space_before",
    "space_after",
}


class CompilerError(Exception):
    """Generic compiler failure (e.g. invalid override severity)."""


class DuplicateRuleError(CompilerError):
    """Raised when the merged rule list contains the same id twice (R1.5)."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _walk_unknown(
    cfg: Any,
    prefix: str,
    recognised_at_this_level: set[str] | None,
    out: list[str],
) -> None:
    """Recursively collect dotted-path keys not in *recognised_at_this_level*.

    The function only knows about a couple of levels (top-level + body).
    Other subtrees (page, headings, toc, ...) are passed through without
    inspection; that's fine for v0.1 since the compiler only emits four
    rules and any mismatch in those subtrees would just become a no-op.
    """
    if not isinstance(cfg, dict):
        return
    for key, value in cfg.items():
        path = f"{prefix}.{key}" if prefix else key
        if recognised_at_this_level is not None and key not in recognised_at_this_level:
            out.append(path)
            continue
        # Descend into known sub-trees we have rules for.
        if prefix == "" and key == "body":
            _walk_unknown(value, path, _BODY_KEYS, out)


def _maybe_apply_override(rule: Rule, overrides: dict[str, dict[str, Any]]) -> Rule:
    """If the user supplied ``_overrides[<rule_id>]``, fold it in."""
    if rule.id not in overrides:
        return rule
    patch = overrides[rule.id]
    fields = {
        "id": rule.id,
        "scope": patch.get("scope", rule.scope),
        "locator": patch.get("locator", rule.locator),
        "predicate": patch.get("predicate", rule.predicate),
        "expected": patch.get("expected", rule.expected),
        "severity": patch.get("severity", rule.severity),
        "fix_tool": patch.get("fix_tool", rule.fix_tool),
        "fix_params_template": patch.get(
            "fix_params_template", rule.fix_params_template
        ),
    }
    try:
        return Rule(**fields)
    except ValueError as exc:
        raise CompilerError(f"override for {rule.id!r} invalid: {exc}") from exc


# ---------------------------------------------------------------------------
# Rule emitters (one per MVP dimension)
# ---------------------------------------------------------------------------

def _emit_body_rules(cfg: dict[str, Any]) -> Iterable[Rule]:
    fonts = cfg.get("fonts", {})
    sizes = cfg.get("sizes", {})
    body = cfg.get("body", {})

    if "body" in fonts:
        yield Rule(
            id="body.font.east_asia",
            scope="style",
            locator={"style_name": "Normal"},
            predicate="equals",
            expected=fonts["body"],
            severity="must",
            fix_tool="tool_format_body",
            fix_params_template={"east_asia_font": "{expected}"},
        )

    if "body" in sizes:
        yield Rule(
            id="body.font.size",
            scope="style",
            locator={"style_name": "Normal"},
            predicate="equals",
            expected=sizes["body"],
            severity="must",
            fix_tool="tool_format_body",
            fix_params_template={"size": "{expected}"},
        )

    if "line_spacing" in body:
        yield Rule(
            id="body.line_spacing",
            scope="style",
            locator={"style_name": "Normal"},
            predicate="equals",
            expected=body["line_spacing"],
            severity="must",
            fix_tool="tool_format_body",
            fix_params_template={"line_spacing": "{expected}"},
        )

    if "first_line_indent" in body:
        yield Rule(
            id="body.first_line_indent",
            scope="style",
            locator={"style_name": "Normal"},
            predicate="equals",
            expected=body["first_line_indent"],
            severity="should",
            fix_tool="tool_format_body",
            fix_params_template={"first_line_indent": "{expected}"},
        )


def _emit_heading_rules(cfg: dict[str, Any]) -> Iterable[Rule]:
    """Per-level heading style rules + presence check + numbering check."""
    fonts = cfg.get("fonts", {})
    sizes = cfg.get("sizes", {})
    headings = cfg.get("headings", {})

    yield Rule(
        id="heading.h1.style_present",
        scope="doc",
        locator={"heading_level": 1},
        predicate="exists",
        expected=True,
        severity="must",
        fix_tool="tool_assign_heading_styles",
        fix_params_template={},
    )

    for level in (1, 2, 3, 4):
        h_key = f"h{level}"
        style_name = f"Heading {level}"

        if h_key in fonts:
            yield Rule(
                id=f"heading.{h_key}.font.east_asia",
                scope="style",
                locator={"style_name": style_name},
                predicate="equals",
                expected=fonts[h_key],
                severity="should",
                fix_tool="tool_normalize_heading_spacing",
                fix_params_template={},
            )
        if h_key in sizes:
            yield Rule(
                id=f"heading.{h_key}.font.size",
                scope="style",
                locator={"style_name": style_name},
                predicate="equals",
                expected=sizes[h_key],
                severity="should",
                fix_tool="tool_normalize_heading_spacing",
                fix_params_template={},
            )
        h_cfg = headings.get(h_key, {})
        if "bold" in h_cfg and h_cfg["bold"] != "keep":
            yield Rule(
                id=f"heading.{h_key}.bold",
                scope="style",
                locator={"style_name": style_name},
                predicate="equals",
                expected=h_cfg["bold"],
                severity="info",
                fix_tool="tool_normalize_heading_spacing",
                fix_params_template={},
            )

    # Heading numbering continuity. Symbolic expected; check uses cfg
    # patterns to walk the doc.
    yield Rule(
        id="heading.numbering.continuity",
        scope="doc",
        locator={"heading_levels": [1, 2, 3, 4]},
        predicate="equals",
        expected="continuous",
        severity="should",
        fix_tool="tool_renumber_headings",
        fix_params_template={},
    )


def _emit_page_rules(cfg: dict[str, Any]) -> Iterable[Rule]:
    """Page layout — margins, gutter, header / footer distance."""
    page = cfg.get("page", {})
    margins = page.get("margins", {})
    for side in ("top", "bottom", "left", "right"):
        if side in margins:
            yield Rule(
                id=f"page.margin.{side}",
                scope="section",
                locator={"all_sections": True, "attr": f"{side}_margin_cm"},
                predicate="equals",
                expected=margins[side],
                severity="should",
                fix_tool="tool_normalize_sections",
                fix_params_template={},
            )
    if "gutter" in page:
        yield Rule(
            id="page.gutter",
            scope="section",
            locator={"all_sections": True, "attr": "gutter_cm"},
            predicate="equals",
            expected=page["gutter"],
            severity="should",
            fix_tool="tool_normalize_sections",
            fix_params_template={},
        )
    if "header_distance" in page:
        yield Rule(
            id="page.header_distance",
            scope="section",
            locator={"all_sections": True, "attr": "header_distance_cm"},
            predicate="equals",
            expected=page["header_distance"],
            severity="info",
            fix_tool="tool_normalize_sections",
            fix_params_template={},
        )
    if "footer_distance" in page:
        yield Rule(
            id="page.footer_distance",
            scope="section",
            locator={"all_sections": True, "attr": "footer_distance_cm"},
            predicate="equals",
            expected=page["footer_distance"],
            severity="info",
            fix_tool="tool_normalize_sections",
            fix_params_template={},
        )


def _emit_caption_rules(cfg: dict[str, Any]) -> Iterable[Rule]:
    """Caption font / size / numbering continuity."""
    cap = cfg.get("captions", {})
    if "font" in cap:
        yield Rule(
            id="caption.font.east_asia",
            scope="paragraph",
            locator={"caption": True, "attr": "east_asia_font"},
            predicate="equals",
            expected=cap["font"],
            severity="should",
            fix_tool="tool_format_figure_captions",
            fix_params_template={},
        )
    if "size" in cap:
        yield Rule(
            id="caption.font.size",
            scope="paragraph",
            locator={"caption": True, "attr": "size_pt"},
            predicate="equals",
            expected=cap["size"],
            severity="should",
            fix_tool="tool_format_figure_captions",
            fix_params_template={},
        )
    if cap.get("check_numbering", True):
        yield Rule(
            id="caption.numbering.continuity",
            scope="doc",
            locator={"caption": True},
            predicate="equals",
            expected="continuous",
            severity="should",
            fix_tool="tool_format_figure_captions",
            fix_params_template={},
        )


def _emit_table_rules(cfg: dict[str, Any]) -> Iterable[Rule]:
    """Three-line table border weights."""
    tbl = cfg.get("table", {})
    for key, rule_suffix in (
        ("top_border_sz", "top"),
        ("header_border_sz", "header"),
        ("bottom_border_sz", "bottom"),
    ):
        if key in tbl:
            yield Rule(
                id=f"table.border.{rule_suffix}",
                scope="table",
                locator={"all_tables": True, "edge": rule_suffix},
                predicate="equals",
                expected=tbl[key],
                severity="info",
                fix_tool="tool_format_three_line_tables",
                fix_params_template={},
            )


def _emit_reference_rules(cfg: dict[str, Any]) -> Iterable[Rule]:
    """References hanging indent."""
    refs = cfg.get("references", {})
    if "first_line_indent" in refs:
        yield Rule(
            id="reference.first_line_indent",
            scope="paragraph",
            locator={"references_section": True, "attr": "first_line_indent_pt"},
            predicate="equals",
            expected=refs["first_line_indent"],
            severity="should",
            fix_tool="tool_format_references",
            fix_params_template={},
        )


def _emit_header_rules(cfg: dict[str, Any]) -> Iterable[Rule]:
    """Header presence."""
    hf = cfg.get("header_footer", {})
    yield Rule(
        id="header.enabled",
        scope="doc",
        locator={"header": True, "attr": "enabled"},
        predicate="equals",
        expected=bool(hf.get("enabled", False)),
        severity="info",
        fix_tool="tool_setup_headers",
        fix_params_template={},
    )


def _emit_page_number_rules(cfg: dict[str, Any]) -> Iterable[Rule]:
    """Page-number formats."""
    pn = cfg.get("page_numbers", {})
    if "front_format" in pn:
        yield Rule(
            id="page_number.front.format",
            scope="doc",
            locator={"page_numbers": "front", "attr": "format"},
            predicate="one_of",
            expected=[pn["front_format"], pn["front_format"].lower()],
            severity="should",
            fix_tool="tool_setup_page_numbers",
            fix_params_template={},
        )
    if "body_format" in pn:
        yield Rule(
            id="page_number.body.format",
            scope="doc",
            locator={"page_numbers": "body", "attr": "format"},
            predicate="one_of",
            expected=[pn["body_format"], pn["body_format"].lower()],
            severity="should",
            fix_tool="tool_setup_page_numbers",
            fix_params_template={},
        )


def _emit_front_matter_rules(cfg: dict[str, Any]) -> Iterable[Rule]:
    """Front-matter presence (中文摘要 / 英文摘要 / 关键词)."""
    fm = cfg.get("front_matter", {})
    if fm.get("mode", "auto") == "skip":
        return
    yield Rule(
        id="front_matter.cn_abstract.present",
        scope="doc",
        locator={"front_matter": "cn_abstract"},
        predicate="exists",
        expected=True,
        severity="should",
        fix_tool=None,  # cannot auto-create abstract content
        fix_params_template={},
    )
    yield Rule(
        id="front_matter.cn_keywords.present",
        scope="doc",
        locator={"front_matter": "cn_keywords"},
        predicate="exists",
        expected=True,
        severity="should",
        fix_tool=None,
        fix_params_template={},
    )
    yield Rule(
        id="front_matter.en_abstract.present",
        scope="doc",
        locator={"front_matter": "en_abstract"},
        predicate="exists",
        expected=True,
        severity="info",
        fix_tool=None,
        fix_params_template={},
    )
    yield Rule(
        id="front_matter.en_keywords.present",
        scope="doc",
        locator={"front_matter": "en_keywords"},
        predicate="exists",
        expected=True,
        severity="info",
        fix_tool=None,
        fix_params_template={},
    )


def _emit_toc_rules(cfg: dict[str, Any]) -> Iterable[Rule]:
    """TOC presence + entry count + style."""
    toc = cfg.get("toc", {})
    if not toc.get("enabled", True):
        return
    yield Rule(
        id="toc.entry_count",
        scope="doc",
        locator={"toc": True},
        predicate="equals",
        expected="match_heading_count",  # symbolic; the check resolves it
        severity="should",
        fix_tool="tool_insert_toc",
        fix_params_template={},
    )
    if "font" in toc:
        yield Rule(
            id="toc.font.east_asia",
            scope="paragraph",
            locator={"toc_entries": True, "attr": "east_asia_font"},
            predicate="equals",
            expected=toc["font"],
            severity="info",
            fix_tool="tool_insert_toc",
            fix_params_template={},
        )


def _emit_deferred_placeholders(cfg: dict[str, Any]) -> Iterable[Rule]:
    """Reserved namespace for future v0.3+ rules."""
    return ()


_EMITTERS = (
    _emit_body_rules,
    _emit_heading_rules,
    _emit_page_rules,
    _emit_caption_rules,
    _emit_table_rules,
    _emit_reference_rules,
    _emit_header_rules,
    _emit_page_number_rules,
    _emit_front_matter_rules,
    _emit_toc_rules,
    _emit_deferred_placeholders,
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compile(cfg: dict[str, Any], profile: str = "default", version: str = "1") -> RuleSet:
    """Compile a deep-merged config dict into a :class:`RuleSet`."""
    overrides = cfg.get("_overrides", {}) or {}

    raw: list[Rule] = []
    for emit in _EMITTERS:
        for rule in emit(cfg):
            if rule.predicate not in known_predicates():
                raise CompilerError(
                    f"rule {rule.id!r} uses unknown predicate {rule.predicate!r}"
                )
            raw.append(_maybe_apply_override(rule, overrides))

    rules = compile_rules(raw)

    unknown_keys: list[str] = []
    _walk_unknown(cfg, "", _RECOGNISED_TOP_LEVEL_KEYS, unknown_keys)
    if unknown_keys:
        _LOG.warning("compiler ignored unknown keys: %s", unknown_keys)

    return RuleSet(
        profile=profile,
        version=version,
        rules=rules,
        metadata={
            "unknown_keys": unknown_keys,
            # The full deep-merged template dict is preserved so the
            # orchestrator can hand it to Tools via ToolContext.config
            # without re-loading the YAML. Tools that wrap legacy
            # thesis_formatter functions all expect this shape.
            "source_config": cfg,
        },
    )


def compile_rules(rules: list[Rule]) -> list[Rule]:
    """Deduplicate / validate a final rule list. Raises on dup id."""
    seen: dict[str, Rule] = {}
    for r in rules:
        if r.id in seen:
            raise DuplicateRuleError(f"duplicate rule id: {r.id}")
        seen[r.id] = r
    return list(seen.values())


def _build_rules_with_duplicates_for_testing() -> list[Rule]:
    """Test helper: simulate the post-merge state where two YAML sources
    contributed the same rule id. Kept here (not in tests) so tests
    don't need to import private compiler internals."""
    base = Rule(
        id="body.line_spacing",
        scope="style",
        locator={"style_name": "Normal"},
        predicate="equals",
        expected=1.5,
        severity="must",
    )
    return [base, base]
