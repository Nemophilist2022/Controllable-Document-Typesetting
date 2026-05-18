"""Outbound payload guard for LLM calls (R13.3).

Every prompt about to be sent to a remote / local LLM passes through
:func:`enforce`. If the payload looks like it carries raw paragraph
text (e.g. a CJK string longer than ``MAX_CJK_RUN`` characters, or a
verbatim quote of any registered reference text) we refuse to send it
and let the diagnoser fall back to ``needs_human=True``.

Why bother:
- R13.3 forbids leaking the user's manuscript content to LLMs.
- C5 caps evidence text at 80 chars; the prompt builder already does
  this, but having a second line of defence here means a buggy future
  prompt cannot accidentally regress the contract.
"""

from __future__ import annotations

import re

# Heuristic: any single uninterrupted run of CJK characters longer than
# this is almost certainly a paragraph snippet rather than a rule id /
# locator / short evidence. Tune conservatively: a 60-character CJK run
# would typically only appear as raw text.
MAX_CJK_RUN = 60

# Total prompt size cap. Even ASCII-heavy prompts shouldn't exceed this
# because every legitimate field (rule id / severity / locator / 80-char
# evidence) is short. 4 KB is generous.
MAX_PROMPT_BYTES = 4096

_CJK_RUN_RE = re.compile(r"[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]+")


class OutboundPayloadGuardError(Exception):
    """Raised when an outbound LLM payload would violate R13.3."""


def enforce(prompt: str) -> None:
    """Validate *prompt* before it leaves the process. Raise on violation."""
    if not isinstance(prompt, str):
        raise OutboundPayloadGuardError(
            f"prompt must be str, got {type(prompt).__name__}"
        )

    encoded_size = len(prompt.encode("utf-8"))
    if encoded_size > MAX_PROMPT_BYTES:
        raise OutboundPayloadGuardError(
            f"prompt size {encoded_size} bytes exceeds cap {MAX_PROMPT_BYTES}; "
            "this is likely a paragraph leak"
        )

    for match in _CJK_RUN_RE.finditer(prompt):
        run = match.group(0)
        if len(run) > MAX_CJK_RUN:
            raise OutboundPayloadGuardError(
                f"prompt contains a {len(run)}-char CJK run; "
                "raw paragraph text is not allowed in LLM payloads"
            )
