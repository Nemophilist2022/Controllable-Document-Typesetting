"""Trace — append-only jsonl audit log (R7.7, R11.1, R11.2, R11.3, R11.8).

Allowed kinds form a whitelist. Payloads pass through a sanitiser that
drops anything that looks like raw paragraph text (C5 / R13.3) — for
v0.1 this is a soft check: payload values are JSON-serialised verbatim
but caller-visible fields are documented to omit raw text.

Log level is taken from CLI ``--log-level`` if set, else from
environment variable ``THESIS_AGENT_LOG`` (default INFO). DEBUG enables
recording of LLM prompts and raw responses.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

ALLOWED_KINDS = (
    "plan",
    "tool_call",
    "tool_result",
    "eval",
    "diagnose",
    "policy",
    "error",
    "llm_request",
    "llm_response",
)


class InvalidTraceKindError(Exception):
    pass


def _resolve_log_level(cli_level: str | None) -> str:
    if cli_level:
        return cli_level.upper()
    env = os.environ.get("THESIS_AGENT_LOG")
    return (env or "INFO").upper()


class Trace:
    def __init__(self, path: str, *, log_level: str | None = None) -> None:
        self._path = path
        self._level = _resolve_log_level(log_level)
        os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
        # Truncate so each run starts fresh; resume support comes in v0.3.
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("")

    @property
    def path(self) -> str:
        return self._path

    @property
    def log_level(self) -> str:
        return self._level

    def record(self, *, kind: str, payload: dict[str, Any]) -> None:
        if kind not in ALLOWED_KINDS:
            raise InvalidTraceKindError(
                f"unknown trace kind {kind!r}; allowed: {ALLOWED_KINDS}"
            )
        if kind in ("llm_request", "llm_response") and self._level != "DEBUG":
            return  # silently drop heavy payloads at INFO+

        line = json.dumps(
            {"ts": time.time(), "kind": kind, "payload": payload},
            ensure_ascii=False,
        )
        with open(self._path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
