"""template_loader — YAML, natural-language, and Word-template ingestion."""

import tempfile
import unittest
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt


class TemplateLoaderYamlTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_from_yaml_returns_dict_with_known_top_keys(self):
        from thesis_agent.ingest.template_loader import from_yaml

        path = self.tmp / "t.yaml"
        path.write_text(
            "meta:\n  school_name: 测试\nbody:\n  line_spacing: 2.0\n",
            encoding="utf-8",
        )
        cfg = from_yaml(str(path))
        self.assertIn("body", cfg)
        self.assertIn("page", cfg)
        self.assertEqual(cfg["body"]["line_spacing"], 2.0)
        self.assertEqual(cfg["meta"]["school_name"], "测试")

    def test_from_yaml_with_non_dict_root_raises(self):
        from thesis_agent.ingest.template_loader import (
            InvalidTemplateError,
            from_yaml,
        )

        path = self.tmp / "broken.yaml"
        path.write_text("- a\n- b\n", encoding="utf-8")
        with self.assertRaises(InvalidTemplateError):
            from_yaml(str(path))


class TemplateLoaderNaturalLanguageTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_from_natural_language_extracts_body_format_yaml(self):
        from thesis_agent.ingest.template_loader import from_natural_language, from_yaml

        out_path = self.tmp / "extracted.yaml"
        result = from_natural_language(
            "正文采用小四号宋体，1.5倍行距，首行缩进2字符。",
            output_path=str(out_path),
        )

        self.assertFalse(result.pending_human_review)
        self.assertEqual(result.yaml_path, str(out_path))
        self.assertIn("body.font", result.extracted_fields)
        self.assertIn("body.line_spacing", result.extracted_fields)

        cfg = from_yaml(str(out_path))
        self.assertEqual(cfg["fonts"]["body"], "宋体")
        self.assertEqual(cfg["sizes"]["body"], 12)
        self.assertEqual(cfg["body"]["line_spacing"], 1.5)
        self.assertEqual(cfg["body"]["first_line_indent"], 24)

    def test_from_natural_language_extracts_heading_and_page_rules(self):
        from thesis_agent.ingest.template_loader import from_natural_language, from_yaml

        out_path = self.tmp / "headings.yaml"
        result = from_natural_language(
            "一级标题黑体三号加粗居中；二级标题黑体小三号加粗。页边距上2.5厘米，下2.5厘米，左3厘米，右2厘米。",
            output_path=str(out_path),
        )

        self.assertFalse(result.pending_human_review)
        cfg = from_yaml(str(out_path))
        self.assertEqual(cfg["fonts"]["h1"], "黑体")
        self.assertEqual(cfg["sizes"]["h1"], 16)
        self.assertTrue(cfg["headings"]["h1"]["bold"])
        self.assertEqual(cfg["headings"]["h1"]["align"], "center")
        self.assertEqual(cfg["fonts"]["h2"], "黑体")
        self.assertEqual(cfg["sizes"]["h2"], 15)
        self.assertEqual(cfg["page"]["margins"], {
            "top": 2.5, "bottom": 2.5, "left": 3.0, "right": 2.0,
        })

    def test_from_natural_language_marks_pending_when_nothing_recognized(self):
        from thesis_agent.ingest.template_loader import from_natural_language

        out_path = self.tmp / "unknown.yaml"
        result = from_natural_language("请按学院最新要求处理。", output_path=str(out_path))

        self.assertTrue(result.pending_human_review)
        self.assertEqual(result.extracted_fields, [])
        self.assertIn("pending_human_review: true", out_path.read_text(encoding="utf-8"))


class TemplateLoaderDocxTemplateTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _set_east_asia(self, style, font_name):
        rpr = style.element.get_or_add_rPr()
        rfonts = rpr.find(qn("w:rFonts"))
        if rfonts is None:
            rfonts = OxmlElement("w:rFonts")
            rpr.append(rfonts)
        rfonts.set(qn("w:eastAsia"), font_name)

    def test_from_docx_template_extracts_normal_heading_and_margins(self):
        from thesis_agent.ingest.template_loader import from_docx_template, from_yaml

        template_path = self.tmp / "template.docx"
        out_path = self.tmp / "template.yaml"
        doc = Document()
        normal = doc.styles["Normal"]
        normal.font.size = Pt(12)
        self._set_east_asia(normal, "宋体")
        normal.paragraph_format.line_spacing = 1.5
        h1 = doc.styles["Heading 1"]
        h1.font.size = Pt(16)
        h1.font.bold = True
        self._set_east_asia(h1, "黑体")
        section = doc.sections[0]
        section.top_margin = Cm(2.5)
        section.bottom_margin = Cm(2.5)
        section.left_margin = Cm(3.0)
        section.right_margin = Cm(2.0)
        doc.save(template_path)

        result = from_docx_template(str(template_path), output_path=str(out_path))

        self.assertFalse(result.pending_human_review)
        self.assertIn("body.font", result.extracted_fields)
        self.assertIn("heading.h1.font", result.extracted_fields)
        cfg = from_yaml(str(out_path))
        self.assertEqual(cfg["fonts"]["body"], "宋体")
        self.assertEqual(cfg["sizes"]["body"], 12)
        self.assertEqual(cfg["body"]["line_spacing"], 1.5)
        self.assertEqual(cfg["fonts"]["h1"], "黑体")
        self.assertEqual(cfg["sizes"]["h1"], 16)
        self.assertEqual(cfg["page"]["margins"], {
            "top": 2.5, "bottom": 2.5, "left": 3.0, "right": 2.0,
        })


if __name__ == "__main__":
    unittest.main()
