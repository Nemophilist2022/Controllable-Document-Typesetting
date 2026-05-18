"""Check modules — register themselves with the runner on import.

The orchestrator calls :func:`autoload` once at startup; subsequent
imports of any individual ``check_*.py`` are no-ops.

Registration order matters: each predicate has at most one registered
function. For ``equals`` we want the dispatcher in ``check_toc`` to be
the last one registered so it can fan out to ``check_body`` for non-toc
rule ids.
"""

from __future__ import annotations

import importlib
import logging

_LOG = logging.getLogger(__name__)

# Explicit deterministic order so the equals-dispatcher in check_toc
# always wins. New check modules MUST be appended here.
_LOAD_ORDER = (
    "check_headings",       # registers ``exists`` (multiplexes to front_matter)
    "check_body",           # registers ``equals`` -> Normal style
    "check_styles",         # passive (called by check_toc dispatcher)
    "check_sections",       # passive (called by check_toc dispatcher)
    "check_tables",         # passive (called by check_toc dispatcher)
    "check_paragraphs",     # passive — caption / references / toc_entries
    "check_doc",            # passive — header.enabled
    "check_numbering",      # passive — heading / caption continuity
    "check_front_matter",   # passive (called by check_headings dispatcher)
    "check_fonts",          # placeholder, no registrations
    "check_one_of",         # registers ``one_of``
    "check_toc",            # registers final ``equals`` dispatcher
)


def autoload() -> None:
    """Register every check module's predicates.

    Safe to call multiple times — each module exposes ``register()``
    which is idempotent at the runner level (later calls overwrite the
    same predicate keys with the same function).
    """
    for name in _LOAD_ORDER:
        try:
            mod = importlib.import_module(f"{__name__}.{name}")
        except Exception as exc:  # pragma: no cover
            _LOG.warning("autoload skipped %s: %s", name, exc)
            continue
        register = getattr(mod, "register", None)
        if callable(register):
            register()
