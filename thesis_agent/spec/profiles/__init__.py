"""Named profiles registry.

Each profile is a Python module that exposes ``load() -> RuleSet``.
:func:`load_profile` is the only public entry point; it scans this
package on first call and caches the resolution map.
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import Callable

from ..rule_set import RuleSet


class UnknownProfileError(Exception):
    """Raised when load_profile is called with a name we don't ship."""


_LOADERS: dict[str, Callable[[], RuleSet]] | None = None


def _discover() -> dict[str, Callable[[], RuleSet]]:
    out: dict[str, Callable[[], RuleSet]] = {}
    for mi in pkgutil.iter_modules(__path__):
        if mi.name.startswith("_"):
            continue
        mod = importlib.import_module(f"{__name__}.{mi.name}")
        loader = getattr(mod, "load", None)
        if callable(loader):
            out[mi.name] = loader
    return out


def load_profile(name: str) -> RuleSet:
    global _LOADERS
    if _LOADERS is None:
        _LOADERS = _discover()
    if name not in _LOADERS:
        raise UnknownProfileError(
            f"unknown profile {name!r}; available: {sorted(_LOADERS)}"
        )
    return _LOADERS[name]()


def available_profiles() -> list[str]:
    global _LOADERS
    if _LOADERS is None:
        _LOADERS = _discover()
    return sorted(_LOADERS)
