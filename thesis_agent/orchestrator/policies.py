"""Run-time policies — convergence, retries, human-in-loop (R6.3, R6.9, R9.1).

Frozen defaults from the requirements doc § 6:
- D3: global timeout = 600 s
- D4: confidence threshold = 0.7
- D5: max iterations = 3
- D6: snapshot capacity = 10
- D7: cost telemetry enabled
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Literal


# ---------------------------------------------------------------------------
# Frozen defaults
# ---------------------------------------------------------------------------

DEFAULT_MAX_ITERATIONS = 3              # D5
DEFAULT_TIMEOUT_SEC = 600               # D3 (10 min)
DEFAULT_CONFIDENCE_THRESHOLD = 0.7      # D4
DEFAULT_SNAPSHOT_CAPACITY = 10          # D6
DEFAULT_COST_TELEMETRY = True           # D7

DEFAULT_HUMAN_IN_LOOP_AT: tuple[str, ...] = (
    "front_matter",
    "cover",
    "ambiguous_headings",
    "destructive_ops",
)


# ---------------------------------------------------------------------------
# Policy dataclass
# ---------------------------------------------------------------------------

@dataclass
class Policies:
    max_iterations: int = DEFAULT_MAX_ITERATIONS
    timeout_sec: float = DEFAULT_TIMEOUT_SEC
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD
    snapshot_capacity: int = DEFAULT_SNAPSHOT_CAPACITY
    cost_telemetry: bool = DEFAULT_COST_TELEMETRY
    human_in_the_loop_at: tuple[str, ...] = DEFAULT_HUMAN_IN_LOOP_AT
    auto_apply_diagnosis: Literal["yes", "confirm", "no"] = "confirm"
    rollback_strategy: Literal["step", "plan"] = "step"


# ---------------------------------------------------------------------------
# Convergence helpers
# ---------------------------------------------------------------------------

@dataclass
class ExitDecision:
    should_exit: bool
    reason: str = ""


def all_must_pass(report) -> bool:
    """True iff every must-severity rule reached status=pass."""
    for r in report.results:
        if r.severity == "must" and r.status != "pass":
            return False
    return True


def plans_equivalent(prev_plan, new_plan) -> bool:
    """Two plans are equivalent iff their canonical JSON serialisations
    are identical (R6.3 third exit condition)."""
    return _canonical_plan_json(prev_plan) == _canonical_plan_json(new_plan)


def _canonical_plan_json(plan) -> str:
    if plan is None:
        return ""
    serial = []
    for step in plan:
        serial.append(
            {
                "tool": getattr(step, "tool", None),
                "params": getattr(step, "params", {}),
            }
        )
    return json.dumps(serial, sort_keys=True, ensure_ascii=False)


def should_exit(
    *,
    eval_report,
    iteration: int,
    prev_plan,
    new_plan,
    deadline: float,
    cancelled: bool,
    policies: Policies,
) -> ExitDecision:
    if cancelled:
        return ExitDecision(True, "cancelled by user")
    if all_must_pass(eval_report):
        return ExitDecision(True, "all must-severity rules pass")
    if iteration >= policies.max_iterations:
        return ExitDecision(True, f"max_iterations={policies.max_iterations} reached")
    if prev_plan is not None and plans_equivalent(prev_plan, new_plan):
        return ExitDecision(True, "replan converged (no progress)")
    if time.monotonic() >= deadline:
        return ExitDecision(True, "global timeout exceeded")
    return ExitDecision(False, "")
