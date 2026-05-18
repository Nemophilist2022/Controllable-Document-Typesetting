"""Tool registry with package-scan auto-discovery (R3.6, R12.2, R12.7).

Tools live in ``thesis_agent.tools.<name>_tools`` modules. Each module
exposes a module-level ``TOOLS`` list of Tool instances. Autoload
imports every sibling module and registers any ``TOOLS`` it finds.
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
from typing import Iterable

from .base import Tool, is_tool

_LOG = logging.getLogger(__name__)
_REGISTRY: dict[str, Tool] = {}


class UnknownToolError(Exception):
    """Raised by :func:`get` for an unregistered name."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def register(tool: Tool) -> None:
    if not is_tool(tool):
        raise TypeError(
            f"object {tool!r} does not satisfy the Tool protocol"
            " (name/description/input_schema/requires/idempotent + run)"
        )
    _REGISTRY[tool.name] = tool


def get(name: str) -> Tool:
    try:
        return _REGISTRY[name]
    except KeyError as exc:
        raise UnknownToolError(name) from exc


def all_tools() -> list[Tool]:
    return list(_REGISTRY.values())


def clear() -> None:
    _REGISTRY.clear()


def autoload() -> None:
    """Scan ``thesis_agent.tools`` for sibling modules; register their
    ``TOOLS`` lists. Modules that fail to import are logged but do not
    break startup (R12.7).
    """
    package = importlib.import_module(__name__.rsplit(".", 1)[0])
    for mi in pkgutil.iter_modules(package.__path__):
        # Skip private modules and our own internals.
        if mi.name.startswith("_") or mi.name in {"base", "registry"}:
            continue
        full = f"{package.__name__}.{mi.name}"
        try:
            mod = importlib.import_module(full)
        except Exception as exc:  # pragma: no cover - defensive only
            _LOG.warning("autoload skipped %s: %s", full, exc)
            continue
        tools: Iterable[Tool] | None = getattr(mod, "TOOLS", None)
        if not tools:
            continue
        for t in tools:
            try:
                register(t)
            except TypeError as exc:
                _LOG.warning("autoload rejected %r from %s: %s", t, full, exc)
