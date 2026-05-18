"""Loader-layer data contracts (R2.2, m1).

When the document loader encounters a recoverable failure (e.g. ``.doc``
input but no Word COM available) it must return a ``LoadResult`` with
an ``ErrorInfo``, never raise a platform-specific exception.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ErrorInfo:
    """Machine-readable error tag plus human-readable message.

    ``code`` should be a stable string the orchestrator / GUI can switch
    on (e.g. ``word_com_unavailable``, ``unsupported_extension``,
    ``pandoc_failed``).
    """

    code: str
    message: str


@dataclass
class LoadResult:
    """Outcome of trying to load an input document.

    On success ``ok`` is True, ``document_path`` points at a
    normalised ``.docx`` file (possibly the original input), and
    ``error`` is None. On failure the inverse holds.
    """

    ok: bool
    document_path: Optional[str] = None
    error: Optional[ErrorInfo] = None
