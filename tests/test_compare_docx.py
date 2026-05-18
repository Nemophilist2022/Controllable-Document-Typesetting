"""Tests for tools.compare_docx — semantic-level docx comparator.

Backs requirement R10.2: 现有 thesis_format_cli.py 不带新参数运行时与改造前
"段落级 / 节级 / 样式级"语义等价，docx ZIP 时间戳/随机 id 不参与比较。
"""

import io
import os
import tempfile
import time
import unittest
import zipfile
from pathlib import Path

from docx import Document


def _make_doc(path, paragraphs=("段落一", "段落二")):
    doc = Document()
    for text in paragraphs:
        doc.add_paragraph(text)
    doc.save(path)


def _repackage_zip(src_path, dst_path):
    """Re-zip the docx so all entries get fresh timestamps (and a fresh
    central directory order). The XML payload itself is byte-identical."""
    with zipfile.ZipFile(src_path, "r") as src:
        members = [(name, src.read(name)) for name in src.namelist()]
    # Force a non-1980 timestamp so the resulting ZIP differs byte-wise.
    fake_time = (2024, 6, 1, 12, 0, 0)
    with zipfile.ZipFile(dst_path, "w", compression=zipfile.ZIP_DEFLATED) as dst:
        for name, data in members:
            info = zipfile.ZipInfo(filename=name, date_time=fake_time)
            info.compress_type = zipfile.ZIP_DEFLATED
            dst.writestr(info, data)


class CompareDocxTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_segment_level_equal_for_identical_docs(self):
        from tools.compare_docx import segment_equal

        a = self.tmp / "a.docx"
        b = self.tmp / "b.docx"
        _make_doc(a)
        _make_doc(b)

        self.assertTrue(segment_equal(str(a), str(b)))

    def test_segment_diff_detects_paragraph_text_change(self):
        from tools.compare_docx import segment_diff, segment_equal

        a = self.tmp / "a.docx"
        b = self.tmp / "b.docx"
        _make_doc(a, paragraphs=("段落一", "段落二"))
        _make_doc(b, paragraphs=("段落一", "段落-改"))

        self.assertFalse(segment_equal(str(a), str(b)))
        diffs = segment_diff(str(a), str(b))
        self.assertTrue(any(d.kind == "paragraph_text" for d in diffs),
                        f"expected paragraph_text diff, got {diffs!r}")

    def test_ignores_zip_metadata_changes(self):
        """Re-zipping with different timestamps must not break equality."""
        from tools.compare_docx import segment_equal

        original = self.tmp / "orig.docx"
        repacked = self.tmp / "repacked.docx"
        _make_doc(original)
        _repackage_zip(original, repacked)

        # Sanity: the bytes did change.
        self.assertNotEqual(original.read_bytes(), repacked.read_bytes())
        # But semantic comparison must still be equal.
        self.assertTrue(segment_equal(str(original), str(repacked)))


if __name__ == "__main__":
    unittest.main()
