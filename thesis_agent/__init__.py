"""thesis_agent — Rule-based + AI-diagnosed thesis formatting agent.

Layered on top of the existing ``thesis_formatter/`` deterministic toolbox.
See ``docs/superpowers/specs/2026-04-15-ai-thesis-agent-architecture-design.md``.

This top-level package only declares the version string. Subpackages are
imported on demand to keep startup cost minimal.
"""

__version__ = "0.1.0.dev0"
