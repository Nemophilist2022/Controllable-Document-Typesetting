"""document_loader — reuses thesis_runner conversion chain (R2.1, R2.2)."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from docx import Document


def _make_docx(path):
    doc = Document()
    doc.add_paragraph("hi")
    doc.save(path)


class DocumentLoaderTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_load_docx_passthrough(self):
        from thesis_agent.ingest.document_loader import load

        path = self.tmp / "x.docx"
        _make_docx(path)
        result = load(str(path))
        self.assertTrue(result.ok)
        self.assertEqual(result.document_path, str(path))
        self.assertIsNone(result.error)

    def test_load_unsupported_extension_returns_error(self):
        from thesis_agent.ingest.document_loader import load

        path = self.tmp / "x.pdf"
        path.write_bytes(b"%PDF-1.4 fake")
        result = load(str(path))
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "unsupported_extension")

    def test_load_missing_file_returns_error(self):
        from thesis_agent.ingest.document_loader import load

        result = load(str(self.tmp / "missing.docx"))
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "file_not_found")

    def test_load_doc_without_word_returns_load_result_error(self):
        """When .doc input is given but Word COM cannot be initialised,
        the loader must return LoadResult(ok=False) — never raise."""
        from thesis_agent.ingest import document_loader

        path = self.tmp / "x.doc"
        path.write_bytes(b"fake")

        # Force the COM conversion path to fail. We patch the function the
        # loader actually calls; it should catch this and convert it into
        # an ErrorInfo.
        with mock.patch.object(
            document_loader,
            "_convert_doc_to_docx",
            side_effect=OSError("Word COM not available"),
        ):
            result = document_loader.load(str(path))
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "word_com_unavailable")

    def test_load_md_without_pandoc_returns_error(self):
        from thesis_agent.ingest import document_loader

        path = self.tmp / "x.md"
        path.write_text("# hello", encoding="utf-8")

        with mock.patch.object(
            document_loader, "_find_pandoc", return_value=None
        ):
            result = document_loader.load(str(path))
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "pandoc_not_found")


if __name__ == "__main__":
    unittest.main()
