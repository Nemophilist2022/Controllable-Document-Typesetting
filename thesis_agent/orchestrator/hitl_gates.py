"""Human-in-the-loop trigger gates (R9.1, R9.5, R9.6).

Each gate inspects a Diagnosis (and optional cfg context) and returns
the list of trigger names that fired. The harness aggregates results
into ``triggered_by_per_rule`` so the pending file shows operators why
their attention is needed.

Active gates:
- ``destructive_ops``        — fix_plan touches a delete / reorder Tool
                               or carries known-destructive params
- ``ambiguous_headings``     — confidence < 0.7 on heading.* rules
- ``front_matter``           — confidence < 0.7 on front_matter.* rules
- ``cover``                  — fix_plan calls tool_insert_cover_*

This module owns the policy logic only; persisting pending state and
gating the loop is the harness's job.
"""

from __future__ import annotations

from typing import Iterable

from ..diagnoser.types import Diagnosis

# Tools we never auto-execute. R9.5: deleting paragraphs / re-ordering
# front matter is irreversible, so even a 0.99-confidence diagnosis
# must escalate to the human.
_DESTRUCTIVE_TOOLS = frozenset({
    "tool_delete_paragraph",
    "tool_remove_paragraph",
    "tool_reorder_paragraphs",
    "tool_reorder_sections",
    "tool_strip_front_matter",
})

# Param keys that make an otherwise-safe Tool destructive.
_DESTRUCTIVE_PARAMS = frozenset({
    "delete_paragraphs",
    "remove_paragraphs",
    "reorder",
    "rewrite_text",
})


def is_destructive(d: Diagnosis) -> bool:
    """True when *d*'s fix_plan would mutate document content rather
    than just formatting."""
    for tc in d.fix_plan or []:
        if tc.tool in _DESTRUCTIVE_TOOLS:
            return True
        for key in tc.params or {}:
            if key in _DESTRUCTIVE_PARAMS:
                return True
    return False


def evaluate_gates(
    d: Diagnosis,
    *,
    confidence_threshold: float,
    enabled_gates: Iterable[str],
) -> list[str]:
    """Return the list of gate names that fire for *d*.

    Per R9.5 ``destructive_ops`` is applied **regardless** of whether
    the user enabled it — destructive changes never go through silently.
    """
    enabled = set(enabled_gates)
    triggered: list[str] = []

    if is_destructive(d):
        triggered.append("destructive_ops")

    if "ambiguous_headings" in enabled:
        if d.rule_id.startswith("heading.") and d.confidence < confidence_threshold:
            triggered.append("ambiguous_headings")

    if "front_matter" in enabled:
        if d.rule_id.startswith("front_matter.") and d.confidence < confidence_threshold:
            triggered.append("front_matter")

    if "cover" in enabled:
        for tc in d.fix_plan or []:
            if tc.tool.startswith("tool_insert_cover"):
                triggered.append("cover")
                break

    return triggered


def apply_gates_in_place(
    diagnoses: list[Diagnosis],
    *,
    confidence_threshold: float,
    enabled_gates: Iterable[str],
) -> dict[str, list[str]]:
    """Mutate diagnoses so any gated one becomes ``needs_human=True``.

    Returns a ``{rule_id: [gate_names]}`` map for the pending file.
    """
    triggered: dict[str, list[str]] = {}
    for d in diagnoses:
        gates = evaluate_gates(
            d,
            confidence_threshold=confidence_threshold,
            enabled_gates=enabled_gates,
        )
        if gates:
            d.needs_human = True
            triggered[d.rule_id] = gates
    return triggered
