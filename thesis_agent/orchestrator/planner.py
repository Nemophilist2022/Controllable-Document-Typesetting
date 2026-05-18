"""Planner — initial plan + replan from diagnoses (R6.2, R6.3).

The initial plan is conservative and deterministic. Follow-up plans can
come from LLM diagnoses, or fall back to the RuleSet's ``fix_tool`` /
``fix_params_template`` mappings when no actionable LLM plan exists.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Step:
    tool: str
    params: dict[str, Any] = field(default_factory=dict)
    rule_ids: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Default plans per mode
# ---------------------------------------------------------------------------

_FULL_DEFAULT_PLAN = (
    Step(tool="tool_assign_heading_styles"),
    Step(tool="tool_format_body", params={
        "east_asia_font": "宋体",
        "size": 12,
        "line_spacing": 1.5,
    }),
    Step(tool="tool_normalize_heading_spacing"),
    Step(tool="tool_insert_toc"),
    Step(tool="tool_word_postprocess", params={"mode": "full"}),
)


def default_plan(rule_set, mode: str) -> list[Step]:
    """Return a fresh plan list for the given mode.

    For mutating modes the initial plan is compiled from the RuleSet
    where possible, so custom YAML templates affect the first ACT phase
    instead of waiting for a later replan.
    """
    if mode in ("full", "targeted"):
        return _full_default_plan(rule_set)
    if mode in ("eval_only", "diagnose_only", "dry_run"):
        return []  # observation-only modes skip act phase
    if mode == "fast":
        # mode=fast bypasses the harness entirely; planner returns empty.
        return []
    raise ValueError(f"unsupported mode: {mode!r}")


def _full_default_plan(rule_set) -> list[Step]:
    body_step = _step_from_rules(
        rule_set,
        "tool_format_body",
        fallback_params={
            "east_asia_font": "瀹嬩綋",
            "size": 12,
            "line_spacing": 1.5,
        },
    )
    return [
        Step(tool="tool_assign_heading_styles"),
        body_step,
        Step(tool="tool_normalize_heading_spacing"),
        Step(tool="tool_insert_toc"),
        Step(tool="tool_word_postprocess", params={"mode": "full"}),
    ]


def _step_from_rules(rule_set, tool: str, fallback_params: dict[str, Any]) -> Step:
    params: dict[str, Any] = {}
    rule_ids: list[str] = []
    for rule in getattr(rule_set, "rules", []) or []:
        if getattr(rule, "fix_tool", None) != tool:
            continue
        params.update(_render_params(rule.fix_params_template, rule.expected))
        rule_ids.append(rule.id)
    return Step(
        tool=tool,
        params=params or dict(fallback_params),
        rule_ids=tuple(rule_ids),
    )


# ---------------------------------------------------------------------------
# Replan from diagnoses
# ---------------------------------------------------------------------------

def replan(
    diagnoses,
    prev_plan: list[Step],
    *,
    eval_report=None,
    rule_set=None,
    allow_rule_fallback: bool = False,
) -> list[Step]:
    """Build a follow-up plan from diagnoses' fix_plan items.

    - Skip diagnoses flagged ``needs_human``.
    - If no LLM plan is actionable and ``allow_rule_fallback`` is true,
      synthesize deterministic Tool calls from failed Rules.
    - If nothing is actionable, return a plan equivalent to ``prev_plan``
      so the orchestrator's convergence check fires.
    - Otherwise append every actionable ToolCall in order.
    """
    actionable: list[Step] = []
    any_actionable = False
    for d in diagnoses or []:
        if getattr(d, "needs_human", False):
            continue
        for tc in getattr(d, "fix_plan", []) or []:
            actionable.append(
                Step(tool=tc.tool, params=dict(tc.params), rule_ids=(d.rule_id,))
            )
            any_actionable = True

    if allow_rule_fallback and not any_actionable:
        actionable = _replan_from_failed_rules(eval_report, rule_set)
        any_actionable = bool(actionable)

    if not any_actionable:
        # Signal convergence by returning a plan equivalent to the
        # previous one. The orchestrator compares via canonical JSON.
        return list(prev_plan)
    return actionable


def _replan_from_failed_rules(eval_report, rule_set) -> list[Step]:
    if eval_report is None or rule_set is None:
        return []

    rules_by_id = {r.id: r for r in getattr(rule_set, "rules", [])}
    steps_by_tool: dict[str, Step] = {}

    for cr in getattr(eval_report, "results", []) or []:
        if cr.status not in ("fail", "error"):
            continue
        rule = rules_by_id.get(cr.rule_id)
        if rule is None or not rule.fix_tool:
            continue
        params = _render_params(rule.fix_params_template, rule.expected)
        _append_tool_with_prerequisites(
            steps_by_tool, rule.fix_tool, params, rule_id=rule.id
        )

    return list(steps_by_tool.values())


def _render_params(template: dict[str, Any], expected: Any) -> dict[str, Any]:
    params: dict[str, Any] = {}
    for key, value in (template or {}).items():
        if value == "{expected}":
            params[key] = expected
        elif isinstance(value, str):
            params[key] = value.replace("{expected}", str(expected))
        else:
            params[key] = value
    return params


_PREREQUISITES = {
    "tool_normalize_heading_spacing": ("tool_assign_heading_styles",),
    "tool_renumber_headings": ("tool_assign_heading_styles",),
    "tool_setup_multilevel_list": ("tool_assign_heading_styles",),
    "tool_insert_toc": ("tool_assign_heading_styles",),
}


def _append_tool_with_prerequisites(
    steps_by_tool: dict[str, Step],
    tool: str,
    params: dict[str, Any],
    *,
    rule_id: str,
) -> None:
    for prereq in _PREREQUISITES.get(tool, ()):
        steps_by_tool.setdefault(prereq, Step(tool=prereq))

    existing = steps_by_tool.get(tool)
    if existing is None:
        steps_by_tool[tool] = Step(
            tool=tool, params=dict(params), rule_ids=(rule_id,)
        )
    else:
        merged = dict(existing.params)
        merged.update(params)
        rule_ids = tuple(dict.fromkeys((*existing.rule_ids, rule_id)))
        steps_by_tool[tool] = Step(tool=tool, params=merged, rule_ids=rule_ids)
