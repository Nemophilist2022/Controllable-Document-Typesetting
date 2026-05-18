"""Prompt template registry — pick a template by rule_id prefix.

Each ``.md`` file in this package is a template body; the file's
**stem** is matched as a prefix against ``rule_id``. The most-specific
match wins. ``fallback.md`` is the catch-all.

Prefixes shipped:
- body / heading / caption / page / page_number / table /
  reference / header / front_matter / toc / fallback

Add a new template? Drop ``<prefix>.md`` next to this file. No code
change needed — the registry rescans on each import.

Each template's first non-blank paragraph is treated as the system
prompt; the rest is appended to the user prompt verbatim. The actual
``rule_id`` / ``severity`` / ``locator`` / ``evidence`` lines are
appended by ``diagnoser._make_prompt`` and **not** part of the
template — the templates only steer style.
"""

from __future__ import annotations

import os
from functools import lru_cache


_HERE = os.path.dirname(os.path.abspath(__file__))


def _list_templates() -> dict[str, str]:
    """Stem → file path."""
    out: dict[str, str] = {}
    if not os.path.isdir(_HERE):
        return out
    for name in os.listdir(_HERE):
        if not name.endswith(".md"):
            continue
        stem = os.path.splitext(name)[0]
        out[stem] = os.path.join(_HERE, name)
    return out


@lru_cache(maxsize=1)
def _registry() -> dict[str, str]:
    return _list_templates()


def select_template(rule_id: str) -> str:
    """Return the most specific matching template body, or fallback."""
    reg = _registry()

    # Walk dotted rule_id from most-specific to least:
    # heading.h1.font.east_asia → heading.h1.font → heading.h1 → heading
    candidates = [rule_id]
    parts = rule_id.split(".")
    for i in range(len(parts) - 1, 0, -1):
        candidates.append(".".join(parts[:i]))

    for cand in candidates:
        if cand in reg:
            return _read(reg[cand])

    if "fallback" in reg:
        return _read(reg["fallback"])
    return ""  # truly empty registry — diagnoser falls back to bare prompt


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read().strip()


def reset_cache() -> None:
    """For tests: re-scan the directory (e.g. after adding .md files)."""
    _registry.cache_clear()
