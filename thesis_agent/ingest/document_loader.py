"""Input document loader (R2.1, R2.2).

Wraps the existing ``thesis_runner`` conversion chain — pandoc for
``.txt/.md/.tex``, Word COM for ``.doc`` — and turns any environment
failure into a structured :class:`LoadResult` rather than a platform
exception.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

# Reuse, do not reimplement.
from thesis_runner import convert_doc_to_docx as _runner_convert_doc_to_docx
from thesis_runner import find_pandoc as _runner_find_pandoc

# preprocess_txt_to_md is at the project root (sibling of thesis_runner).
from preprocess_txt_to_md import preprocess as _preprocess_txt_to_md

from .types import ErrorInfo, LoadResult

_SUPPORTED = {".docx", ".doc", ".txt", ".md", ".tex"}


# ---------------------------------------------------------------------------
# Indirection points (so tests can patch them)
# ---------------------------------------------------------------------------

def _find_pandoc():
    return _runner_find_pandoc()


def _convert_doc_to_docx(src, dst):
    return _runner_convert_doc_to_docx(src, dst)


def _run_pandoc(pandoc, source, fmt_from, dst):
    return subprocess.run(
        [pandoc, source, f"--from={fmt_from}", "--to=docx", "--standalone", "-o", dst],
        capture_output=True, text=True,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load(input_path: str, work_dir: str | None = None) -> LoadResult:
    """Load *input_path* and return a normalised ``.docx`` path.

    On success ``LoadResult.document_path`` is either *input_path* itself
    (if input was already ``.docx``) or a freshly created ``.docx`` in
    *work_dir* (defaults to a system temp directory).
    """
    if not os.path.isfile(input_path):
        return LoadResult(
            ok=False,
            error=ErrorInfo(code="file_not_found", message=f"missing: {input_path}"),
        )

    ext = os.path.splitext(input_path)[1].lower()
    if ext not in _SUPPORTED:
        return LoadResult(
            ok=False,
            error=ErrorInfo(
                code="unsupported_extension",
                message=f"{ext} not in {sorted(_SUPPORTED)}",
            ),
        )

    if ext == ".docx":
        return LoadResult(ok=True, document_path=input_path)

    out_dir = work_dir or tempfile.mkdtemp(prefix="thesis_agent_ingest_")
    out_docx = os.path.join(out_dir, "input.docx")

    if ext == ".doc":
        try:
            _convert_doc_to_docx(input_path, out_docx)
        except Exception as exc:
            # Could be ImportError (pywin32 missing on non-Windows),
            # OSError (Word not installed), pythoncom.com_error, etc.
            return LoadResult(
                ok=False,
                error=ErrorInfo(
                    code="word_com_unavailable",
                    message=str(exc),
                ),
            )
        return LoadResult(ok=True, document_path=out_docx)

    # .txt / .md / .tex go through pandoc
    pandoc = _find_pandoc()
    if not pandoc:
        return LoadResult(
            ok=False,
            error=ErrorInfo(code="pandoc_not_found", message="pandoc executable not located"),
        )

    if ext == ".txt":
        tmp_md = os.path.join(out_dir, "input.md")
        try:
            _preprocess_txt_to_md(input_path, tmp_md)
        except Exception as exc:
            return LoadResult(
                ok=False,
                error=ErrorInfo(code="txt_preprocess_failed", message=str(exc)),
            )
        source, fmt_from = tmp_md, "markdown-smart"
    elif ext == ".md":
        source, fmt_from = input_path, "markdown-smart"
    else:
        source, fmt_from = input_path, "latex"

    ret = _run_pandoc(pandoc, source, fmt_from, out_docx)
    if ret.returncode != 0:
        return LoadResult(
            ok=False,
            error=ErrorInfo(
                code="pandoc_failed",
                message=(ret.stderr or "").strip()[:400] or "pandoc returned non-zero",
            ),
        )

    return LoadResult(ok=True, document_path=out_docx)
