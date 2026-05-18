"""Template loader and template extractors.

YAML files remain the canonical RuleSet input. Natural-language and DOCX
paths generate reviewable YAML override files that can be passed to
``thesis-agent run --config``.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any

from thesis_config import DEFAULT_CONFIG, _deep_merge

try:
    import yaml as _yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False


class InvalidTemplateError(Exception):
    """Raised when a YAML template has a structurally unusable shape."""


@dataclass
class NaturalLanguageResult:
    yaml_path: str
    pending_human_review: bool
    extracted_fields: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# YAML
# ---------------------------------------------------------------------------

def from_yaml(path: str) -> dict[str, Any]:
    """Load *path* as YAML, deep-merge over :data:`DEFAULT_CONFIG`."""
    if not _HAS_YAML:
        raise RuntimeError("pyyaml is required to load templates")
    if not os.path.isfile(path):
        raise FileNotFoundError(path)

    with open(path, "r", encoding="utf-8") as fh:
        loaded = _yaml.safe_load(fh)

    if loaded is None:
        loaded = {}
    if not isinstance(loaded, dict):
        raise InvalidTemplateError(
            f"template root must be a mapping; got {type(loaded).__name__}"
        )

    return _deep_merge(DEFAULT_CONFIG, loaded)


# ---------------------------------------------------------------------------
# Natural language
# ---------------------------------------------------------------------------

_FONT_NAMES = ("宋体", "黑体", "楷体", "仿宋", "微软雅黑", "Times New Roman")
_SIZE_PT = {
    "初号": 42,
    "小初": 36,
    "一号": 26,
    "小一": 24,
    "二号": 22,
    "小二": 18,
    "三号": 16,
    "小三": 15,
    "四号": 14,
    "小四": 12,
    "五号": 10.5,
    "小五": 9,
    "六号": 7.5,
    "小六": 6.5,
}
_HEADING_LEVELS = {
    "一": "h1", "1": "h1",
    "二": "h2", "2": "h2",
    "三": "h3", "3": "h3",
    "四": "h4", "4": "h4",
}
_MARGIN_KEYS = {
    "上": "top",
    "下": "bottom",
    "左": "left",
    "右": "right",
}


def from_natural_language(text: str, output_path: str) -> NaturalLanguageResult:
    """Extract common thesis format requirements from Chinese prose.

    This is intentionally deterministic and conservative. Recognised
    values are written as YAML overrides; unrecognised prose is preserved
    as ``source_text`` and marked for human review.
    """
    cfg, fields = _extract_from_text(text or "")
    if fields:
        cfg.setdefault("meta", {})["extracted_from"] = "natural_language"
        cfg.setdefault("meta", {})["source_text"] = text or ""
        _write_yaml(cfg, output_path)
        return NaturalLanguageResult(
            yaml_path=output_path,
            pending_human_review=False,
            extracted_fields=fields,
        )

    placeholder = {
        "pending_human_review": True,
        "source_text": text or "",
    }
    _write_yaml(placeholder, output_path, header=(
        "# Auto-generated draft from a natural-language template.\n"
        "# No supported formatting rules were recognised automatically.\n"
    ))
    return NaturalLanguageResult(
        yaml_path=output_path,
        pending_human_review=True,
        extracted_fields=[],
    )


def _extract_from_text(text: str) -> tuple[dict[str, Any], list[str]]:
    cfg: dict[str, Any] = {}
    fields: list[str] = []
    compact = re.sub(r"\s+", "", text)
    clauses = [c for c in re.split(r"[；;。\n]", compact) if c]

    _extract_body(compact, clauses, cfg, fields)
    _extract_headings(clauses, cfg, fields)
    _extract_page_margins(compact, cfg, fields)
    _extract_toc(compact, cfg, fields)
    _extract_captions(compact, cfg, fields)
    return cfg, fields


def _extract_body(text: str, clauses: list[str], cfg: dict[str, Any], fields: list[str]) -> None:
    body_clauses = [c for c in clauses if "正文" in c] or [text]
    body_text = "；".join(body_clauses)
    font = _find_font(body_text)
    size = _find_size(body_text)
    spacing = _find_line_spacing(body_text)
    indent = _find_first_line_indent(body_text)

    if font:
        cfg.setdefault("fonts", {})["body"] = font
        _add_field(fields, "body.font")
    if size is not None:
        cfg.setdefault("sizes", {})["body"] = size
        _add_field(fields, "body.size")
    if spacing is not None:
        cfg.setdefault("body", {})["line_spacing"] = spacing
        _add_field(fields, "body.line_spacing")
    if indent is not None:
        cfg.setdefault("body", {})["first_line_indent"] = indent
        _add_field(fields, "body.first_line_indent")


def _extract_headings(clauses: list[str], cfg: dict[str, Any], fields: list[str]) -> None:
    for clause in clauses:
        m = re.search(r"([一二三四1234])级标题", clause)
        if not m:
            continue
        h_key = _HEADING_LEVELS[m.group(1)]
        font = _find_font(clause)
        size = _find_size(clause)
        if font:
            cfg.setdefault("fonts", {})[h_key] = font
            _add_field(fields, f"heading.{h_key}.font")
        if size is not None:
            cfg.setdefault("sizes", {})[h_key] = size
            _add_field(fields, f"heading.{h_key}.size")
        h_cfg = cfg.setdefault("headings", {}).setdefault(h_key, {})
        if "加粗" in clause or "粗体" in clause:
            h_cfg["bold"] = True
            _add_field(fields, f"heading.{h_key}.bold")
        elif "不加粗" in clause:
            h_cfg["bold"] = False
            _add_field(fields, f"heading.{h_key}.bold")
        if "居中" in clause:
            h_cfg["align"] = "center"
            _add_field(fields, f"heading.{h_key}.align")
        elif "左对齐" in clause or "靠左" in clause:
            h_cfg["align"] = "left"
            _add_field(fields, f"heading.{h_key}.align")


def _extract_page_margins(text: str, cfg: dict[str, Any], fields: list[str]) -> None:
    margins: dict[str, float] = {}
    for cn, key in _MARGIN_KEYS.items():
        m = re.search(rf"{cn}(?:边距)?([0-9]+(?:\.[0-9]+)?)(?:厘米|cm)", text, re.I)
        if m:
            margins[key] = float(m.group(1))
    if margins:
        cfg.setdefault("page", {}).setdefault("margins", {}).update(margins)
        for key in margins:
            _add_field(fields, f"page.margin.{key}")


def _extract_toc(text: str, cfg: dict[str, Any], fields: list[str]) -> None:
    if "目录" not in text:
        return
    cfg.setdefault("toc", {})["enabled"] = False if "不需要目录" in text else True
    _add_field(fields, "toc.enabled")
    depth = re.search(r"目录(?:层级|级别|深度)?(?:到|为)?([一二三四1234])级", text)
    if depth:
        val = depth.group(1)
        cfg.setdefault("toc", {})["depth"] = int({"一": 1, "二": 2, "三": 3, "四": 4}.get(val, val))
        _add_field(fields, "toc.depth")


def _extract_captions(text: str, cfg: dict[str, Any], fields: list[str]) -> None:
    if "题注" not in text and "图题" not in text and "表题" not in text:
        return
    font = _find_font(text)
    size = _find_size(text)
    if font:
        cfg.setdefault("captions", {})["font"] = font
        _add_field(fields, "caption.font")
    if size is not None:
        cfg.setdefault("captions", {})["size"] = size
        _add_field(fields, "caption.size")


def _find_font(text: str) -> str | None:
    for font in _FONT_NAMES:
        if font.replace(" ", "") in text.replace(" ", ""):
            return font
    return None


def _find_size(text: str) -> float | int | None:
    for label, pt in sorted(
        _SIZE_PT.items(),
        key=lambda kv: (len(kv[0]), kv[0].startswith("小")),
        reverse=True,
    ):
        if label in text:
            return pt
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)磅", text)
    if m:
        return _number(float(m.group(1)))
    return None


def _find_line_spacing(text: str) -> float | None:
    if "单倍" in text:
        return 1.0
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)(?:倍行距|倍)", text)
    return float(m.group(1)) if m else None


def _find_first_line_indent(text: str) -> float | int | None:
    m = re.search(r"首行缩进([0-9]+(?:\.[0-9]+)?)(?:字符|字)", text)
    if m:
        return _number(float(m.group(1)) * 12)
    m = re.search(r"首行缩进([0-9]+(?:\.[0-9]+)?)磅", text)
    if m:
        return _number(float(m.group(1)))
    return None


# ---------------------------------------------------------------------------
# DOCX template
# ---------------------------------------------------------------------------

def from_docx_template(path: str, output_path: str) -> NaturalLanguageResult:
    """Extract style/page settings from a Word ``.docx`` template."""
    if not os.path.isfile(path):
        raise FileNotFoundError(path)

    from docx import Document

    doc = Document(path)
    cfg: dict[str, Any] = {"meta": {"extracted_from": "docx_template"}}
    fields: list[str] = []

    _extract_style(doc, "Normal", "body", cfg, fields, is_body=True)
    for level in range(1, 5):
        _extract_style(doc, f"Heading {level}", f"h{level}", cfg, fields)
    _extract_docx_margins(doc, cfg, fields)

    _write_yaml(cfg, output_path)
    return NaturalLanguageResult(
        yaml_path=output_path,
        pending_human_review=not bool(fields),
        extracted_fields=fields,
    )


def _extract_style(doc, style_name: str, key: str, cfg: dict[str, Any], fields: list[str], *, is_body: bool = False) -> None:
    try:
        style = doc.styles[style_name]
    except KeyError:
        return
    font = _style_east_asia_font(style)
    size = _style_size(style)
    if font:
        cfg.setdefault("fonts", {})[key] = font
        _add_field(fields, "body.font" if is_body else f"heading.{key}.font")
    if size is not None:
        cfg.setdefault("sizes", {})[key] = size
        _add_field(fields, "body.size" if is_body else f"heading.{key}.size")
    if not is_body and style.font.bold is not None:
        cfg.setdefault("headings", {}).setdefault(key, {})["bold"] = bool(style.font.bold)
        _add_field(fields, f"heading.{key}.bold")
    if is_body:
        spacing = style.paragraph_format.line_spacing
        if isinstance(spacing, (int, float)):
            cfg.setdefault("body", {})["line_spacing"] = float(spacing)
            _add_field(fields, "body.line_spacing")


def _extract_docx_margins(doc, cfg: dict[str, Any], fields: list[str]) -> None:
    if not doc.sections:
        return
    sec = doc.sections[0]
    margins = {
        "top": _number(sec.top_margin.cm),
        "bottom": _number(sec.bottom_margin.cm),
        "left": _number(sec.left_margin.cm),
        "right": _number(sec.right_margin.cm),
    }
    cfg.setdefault("page", {})["margins"] = margins
    for key in margins:
        _add_field(fields, f"page.margin.{key}")


def _style_east_asia_font(style) -> str | None:
    rpr = style.element.rPr
    if rpr is None:
        return None
    rfonts = rpr.find(".//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}rFonts")
    if rfonts is None:
        return None
    return (
        rfonts.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}eastAsia")
        or rfonts.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}ascii")
    )


def _style_size(style) -> float | int | None:
    size = style.font.size
    if size is None:
        return None
    return _number(size.pt)


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------

def _write_yaml(payload: dict[str, Any], output_path: str, *, header: str = "") -> None:
    if not _HAS_YAML:
        raise RuntimeError("pyyaml is required to write templates")
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        if header:
            fh.write(header)
        _yaml.safe_dump(payload, fh, allow_unicode=True, sort_keys=False)


def _add_field(fields: list[str], field_name: str) -> None:
    if field_name not in fields:
        fields.append(field_name)


def _number(value: float) -> float | int:
    rounded = round(float(value), 2)
    return int(rounded) if abs(rounded - int(rounded)) < 0.001 else rounded
