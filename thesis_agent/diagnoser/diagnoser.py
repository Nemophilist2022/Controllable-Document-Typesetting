"""Diagnoser — turn fail/error CheckResults into Diagnosis objects.

MVP scope:
- ``llm=None``           → return ``Diagnosis(needs_human=True)`` (R5.7)
- ``llm=MockLLMClient``  → call complete(); validate JSON shape
- ``llm=real client``    → v0.2

Confidence post-processing (R5.5):
- Clamp to ``[0, 1]`` (handled in :class:`Diagnosis.__post_init__`).
- Force-downgrade to ≤0.5 when the same ``(rule_id, evidence_hash)``
  fails twice in a single run (cache stored in module state).
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Optional

from .types import Diagnosis, ToolCall


_REPEAT_FAIL_HISTORY: dict[str, int] = {}
_DIAGNOSIS_CACHE: dict[str, Diagnosis] = {}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def reset_caches() -> None:
    _REPEAT_FAIL_HISTORY.clear()
    _DIAGNOSIS_CACHE.clear()


def diagnose(eval_report, doc, *, llm=None) -> list[Diagnosis]:
    """Return a Diagnosis for every fail/error CheckResult.

    *doc* is currently unused by the MVP diagnoser; future versions will
    pass paragraph snippets to the LLM (subject to R13.3 outbound hook).
    """
    out: list[Diagnosis] = []
    if eval_report is None:
        return out

    for cr in eval_report.results:
        if cr.status not in ("fail", "error"):
            continue

        key = _evidence_hash(cr)
        cached = _DIAGNOSIS_CACHE.get(key)
        if cached is not None:
            out.append(cached)
            continue

        if llm is None:
            d = Diagnosis(
                rule_id=cr.rule_id,
                root_cause="",
                fix_plan=[],
                confidence=0.0,
                needs_human=True,
                rationale="未配置 LLM",
            )
        else:
            d = _diagnose_with_llm(cr, llm)

        d = _apply_repeat_fail_penalty(cr, d, key)
        _DIAGNOSIS_CACHE[key] = d
        out.append(d)
    return out


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "rule_id", "root_cause", "fix_plan", "confidence",
        "needs_human", "rationale",
    ],
}


def _diagnose_with_llm(cr, llm) -> Diagnosis:
    prompt = _make_prompt(cr)
    last_error: Optional[str] = None
    for _ in range(2 + 1):  # initial + 2 retries (R5.3, D2=2)
        raw = llm.complete(prompt, _RESPONSE_SCHEMA)
        problem = _validate_response(raw)
        if problem is None:
            return Diagnosis(
                rule_id=raw.get("rule_id") or cr.rule_id,
                root_cause=raw.get("root_cause", ""),
                fix_plan=[
                    ToolCall(
                        tool=tc.get("tool", ""),
                        params=dict(tc.get("params", {})),
                        expected_effect=tc.get("expected_effect", ""),
                    )
                    for tc in raw.get("fix_plan", []) or []
                ],
                confidence=float(raw.get("confidence", 0.0)),
                needs_human=bool(raw.get("needs_human", False)),
                rationale=raw.get("rationale", ""),
            )
        last_error = problem
    return Diagnosis(
        rule_id=cr.rule_id,
        root_cause="",
        fix_plan=[],
        confidence=0.0,
        needs_human=True,
        rationale=f"LLM response invalid after retries: {last_error}",
    )


def _make_prompt(cr) -> str:
    """Build the diagnoser prompt. Per R13.3 we never send raw paragraph
    text to the LLM; only the rule id, severity, locator and short
    evidence string. A rule-specific template (selected by rule_id
    prefix) is prepended so the LLM has hand-tuned guidance per rule
    family — see ``thesis_agent.diagnoser.prompts``.
    """
    from .prompts import select_template

    guidance = select_template(cr.rule_id)
    body = (
        f"rule_id={cr.rule_id}\n"
        f"severity={cr.severity}\n"
        f"locator={json.dumps(cr.locator_resolved, ensure_ascii=False)}\n"
        f"evidence={cr.evidence}\n"
    )
    if guidance:
        return guidance + "\n\n" + body
    return body


def _validate_response(raw) -> Optional[str]:
    if not isinstance(raw, dict):
        return f"expected dict, got {type(raw).__name__}"
    for key in _RESPONSE_SCHEMA["required"]:
        if key not in raw:
            return f"missing key: {key}"
    return None


def _evidence_hash(cr) -> str:
    locator_canonical = json.dumps(
        cr.locator_resolved or {}, sort_keys=True, ensure_ascii=False
    )
    evidence_normalized = re.sub(r"\s+", " ", (cr.evidence or "").strip())
    raw = f"{cr.rule_id}\n{locator_canonical}\n{evidence_normalized}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _apply_repeat_fail_penalty(cr, d: Diagnosis, key: str) -> Diagnosis:
    """Per R5.5: force confidence ≤ 0.5 when same (rule_id, evidence) fails
    twice in a single run."""
    _REPEAT_FAIL_HISTORY[key] = _REPEAT_FAIL_HISTORY.get(key, 0) + 1
    if _REPEAT_FAIL_HISTORY[key] >= 2 and d.confidence > 0.5:
        # Re-build via the dataclass to keep all invariants.
        d = Diagnosis(
            rule_id=d.rule_id,
            root_cause=d.root_cause,
            fix_plan=d.fix_plan,
            confidence=0.5,
            needs_human=True,
            rationale=d.rationale + " (downgraded: repeat-fail)",
        )
    return d
