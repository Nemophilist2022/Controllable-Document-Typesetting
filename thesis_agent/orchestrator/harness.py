"""Main harness loop — plan → act → evaluate → diagnose → replan (R6).

For MVP this is a synchronous, single-threaded loop. v0.2 will add real
LLM diagnoser calls; v0.3 will add resume / human-in-loop pause points.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal, Optional

from ..delivery.report import build_delivery_report, write_report_json, write_report_md
from ..delivery.trace import Trace
from ..diagnoser.diagnoser import diagnose
from ..evaluators.checks import autoload as autoload_checks
from ..evaluators.runner import evaluate
from ..ingest.document_loader import load as load_document
from ..ingest.document_model import DocumentModel
from ..ingest.template_loader import from_yaml
from ..spec.compiler import compile as compile_rule_set
from ..spec.profiles import load_profile
from ..tools import registry as tool_registry
from . import pending as pending_io
from .hitl_gates import apply_gates_in_place
from .planner import Step, default_plan, replan
from .policies import Policies, should_exit
from .snapshot import SnapshotManager

_LOG = logging.getLogger(__name__)

Mode = Literal["full", "fast", "eval_only", "diagnose_only", "targeted", "dry_run"]


class InvalidModeError(Exception):
    pass


class OverwriteInputError(Exception):
    pass


class UnboundFixToolError(Exception):
    pass


# ---------------------------------------------------------------------------
# Run options + return type
# ---------------------------------------------------------------------------

@dataclass
class RunOptions:
    output_path: Optional[str] = None
    output_dir: Optional[str] = None
    policies: Policies = field(default_factory=Policies)
    overwrite_output: bool = False
    log_fn: Callable[[str], None] = print
    # LLM config — None means "no LLM available", which makes the
    # diagnoser fall back to needs_human=True per R5.7.
    llm_api_key: Optional[str] = None
    llm_base_url: Optional[str] = None
    llm_model: Optional[str] = None
    # Force-disable LLM even if env vars are set (useful for tests).
    llm_disabled: bool = False
    # Human-in-the-loop. Default ``confirm`` matches R9.2; tests and
    # automated pipelines can opt out with ``yes`` / ``no``.
    auto_apply_diagnosis: Literal["yes", "confirm", "no"] = "confirm"
    # If set, harness skips ingest and resumes from this pending.json.
    resume_path: Optional[str] = None
    # Optional user YAML template/config. When present it is compiled
    # directly instead of loading a built-in named profile.
    config_path: Optional[str] = None


@dataclass
class RunResult:
    ok: bool
    summary: dict[str, int]
    docx_path: Optional[str]
    report_md_path: str
    report_json_path: str
    trace_path: str
    exit_reason: str
    # Path to a pending.json when the run paused for human review;
    # otherwise None.
    pending_path: Optional[str] = None


_VALID_MODES = ("full", "fast", "eval_only", "diagnose_only", "targeted", "dry_run")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run(
    *,
    input_path: str,
    profile: str,
    mode: Mode = "full",
    options: Optional[RunOptions] = None,
) -> RunResult:
    if mode not in _VALID_MODES:
        raise InvalidModeError(f"invalid mode {mode!r}; must be one of {_VALID_MODES}")
    options = options or RunOptions()

    # ----- resume short-circuit -----
    if options.resume_path:
        return _run_resume(profile=profile, mode=mode, options=options)

    output_path = _resolve_output_path(input_path, options, mode)
    if output_path and os.path.abspath(output_path) == os.path.abspath(input_path):
        raise OverwriteInputError(
            f"output_path equals input_path: {input_path!r}; "
            "refusing to overwrite the original file"
        )

    work_dir = os.path.dirname(output_path or input_path) or "."
    stem = _stem_of(input_path)
    trace_path = os.path.join(work_dir, f"{stem}_trace.jsonl")
    report_md_path = os.path.join(work_dir, f"{stem}_report.md")
    report_json_path = os.path.join(work_dir, f"{stem}_report.json")
    pending_path = os.path.join(work_dir, f"{stem}_pending.json")

    trace = Trace(path=trace_path)

    # R9.6: warn loudly when the user disabled all human-in-the-loop
    # gates. Trace + log_fn so it's visible everywhere.
    if not options.policies.human_in_the_loop_at:
        msg = "已关闭人在回路，所有修改将自动执行，请审阅最终输出"
        options.log_fn(f"thesis-agent: WARNING — {msg}")
        trace.record(kind="policy", payload={"warning": msg})

    # ----- mode=fast: short-circuit to legacy thesis_runner -----
    if mode == "fast":
        return _run_fast(
            input_path=input_path,
            output_path=output_path,
            options=options,
            stem=stem,
            trace=trace,
            report_md_path=report_md_path,
            report_json_path=report_json_path,
            trace_path=trace_path,
        )

    # ----- ingest -----
    load_result = load_document(input_path)
    if not load_result.ok:
        return _bail_out(
            options,
            trace=trace,
            stem=stem,
            report_md_path=report_md_path,
            report_json_path=report_json_path,
            trace_path=trace_path,
            reason=f"load failed: {load_result.error.code}",
        )

    return _run_loop(
        input_path=input_path,
        profile=profile,
        mode=mode,
        options=options,
        stem=stem,
        work_dir=work_dir,
        output_path=output_path,
        report_md_path=report_md_path,
        report_json_path=report_json_path,
        trace_path=trace_path,
        pending_path=pending_path,
        trace=trace,
        document_path=load_result.document_path,
        starting_iteration=0,
        starting_telemetry=None,
        accepted_diagnoses=None,
    )


# ---------------------------------------------------------------------------
# Loop body shared by fresh runs and resumes
# ---------------------------------------------------------------------------

def _run_loop(
    *,
    input_path: str,
    profile: str,
    mode: Mode,
    options: RunOptions,
    stem: str,
    work_dir: str,
    output_path: Optional[str],
    report_md_path: str,
    report_json_path: str,
    trace_path: str,
    pending_path: str,
    trace: Trace,
    document_path: str,
    starting_iteration: int,
    starting_telemetry: Optional[dict],
    accepted_diagnoses: Optional[list],
) -> RunResult:
    rule_set = _load_rule_set(profile, options)
    _validate_fix_tools_bound(rule_set)

    autoload_checks()
    tool_registry.autoload()

    dm = DocumentModel.from_path(document_path)
    snapshots = SnapshotManager(
        work_dir=work_dir, capacity=options.policies.snapshot_capacity
    )

    llm_client = _build_llm_client(options)
    if starting_telemetry and llm_client is not None:
        # Roll-forward LLM telemetry across resumes so cost / token
        # totals don't reset to zero on session #2.
        _restore_telemetry(llm_client, starting_telemetry)

    deadline = time.monotonic() + options.policies.timeout_sec

    # When resuming, the user-accepted diagnoses become iteration 0's
    # plan instead of the default plan.
    if accepted_diagnoses:
        plan: list[Step] = replan(accepted_diagnoses, prev_plan=[])
        trace.record(kind="policy", payload={
            "resume_seed_plan": [{"tool": s.tool, "params": s.params} for s in plan],
        })
    else:
        plan = default_plan(rule_set, mode=mode)

    prev_plan: Optional[list[Step]] = None
    iteration = starting_iteration
    eval_report = None
    diagnoses: list = []
    exit_reason = ""
    pending_state = None
    fix_attempts_by_rule: dict[str, list[dict[str, Any]]] = {}
    tool_calls_count = 0

    while True:
        trace.record(kind="plan", payload={"iteration": iteration, "plan": [
            {"tool": s.tool, "params": s.params, "rule_ids": list(s.rule_ids)}
            for s in plan
        ]})

        # ACT — only if mode allows mutations
        if mode in ("full", "targeted"):
            for attempt in _act(
                plan=plan, dm=dm, mode=mode, options=options,
                rule_set=rule_set, snapshots=snapshots, trace=trace,
                output_path=output_path, fallback_path=document_path,
                iteration=iteration,
            ):
                tool_calls_count += 1
                for rule_id in attempt.pop("_rule_ids", []):
                    fix_attempts_by_rule.setdefault(rule_id, []).append(dict(attempt))

        # EVALUATE
        eval_report = evaluate(dm, rule_set)
        trace.record(kind="eval", payload={"summary": eval_report.summary})

        # DIAGNOSE
        if mode in ("full", "diagnose_only", "dry_run"):
            diagnoses = diagnose(eval_report, dm, llm=llm_client)
            # R9.5: destructive operations always force needs_human,
            # regardless of which gates the user enabled.
            triggered_per_rule = apply_gates_in_place(
                diagnoses,
                confidence_threshold=options.policies.confidence_threshold,
                enabled_gates=options.policies.human_in_the_loop_at,
            )
            trace.record(
                kind="diagnose",
                payload={
                    "count": len(diagnoses),
                    "needs_human": [d.rule_id for d in diagnoses if d.needs_human],
                    "gates_triggered": triggered_per_rule,
                },
            )

            new_plan = replan(
                diagnoses,
                plan,
                eval_report=eval_report,
                rule_set=rule_set,
                allow_rule_fallback=True,
            )

            # HITL gate. Only ``confirm`` mode pauses; ``yes`` and
            # ``no`` continue immediately (the latter just leaves
            # needs_human entries unfixed → reported as failed). If a
            # deterministic RuleSet fallback plan exists, run it before
            # pausing so fixable format failures don't require human
            # approval merely because no LLM is configured.
            needs_human = [d for d in diagnoses if d.needs_human]
            has_deterministic_followup = bool(new_plan) and not _plans_same(plan, new_plan)
            if (
                mode == "full"
                and needs_human
                and options.auto_apply_diagnosis == "confirm"
                and not has_deterministic_followup
            ):
                # Save the current docx so the user can inspect / the
                # resume can pick up. Then write pending.json and exit.
                if output_path:
                    dm.save(output_path)
                    inflight_path = output_path
                else:
                    inflight_path = os.path.join(work_dir, f"{stem}_inflight.docx")
                    dm.save(inflight_path)

                pending_state = pending_io.from_diagnoses(
                    input_path=input_path,
                    profile=profile,
                    mode=mode,
                    stem=stem,
                    output_dir=work_dir,
                    docx_path=inflight_path,
                    iteration=iteration,
                    diagnoses=diagnoses,
                    llm_telemetry=_telemetry_dict(llm_client),
                    triggered_by_per_rule=triggered_per_rule,
                )
                pending_io.save(pending_state, pending_path)
                trace.record(kind="policy", payload={
                    "paused": True,
                    "pending_path": pending_path,
                    "needs_human_count": len(needs_human),
                })
                exit_reason = f"awaiting_human ({len(needs_human)} pending)"
                break

        # POLICY GATE / EXIT CHECK
        if mode == "full":
            new_plan = replan(
                diagnoses,
                plan,
                eval_report=eval_report,
                rule_set=rule_set,
                allow_rule_fallback=True,
            )
        else:
            new_plan = []
        decision = should_exit(
            eval_report=eval_report,
            iteration=iteration + 1,
            prev_plan=prev_plan,
            new_plan=new_plan,
            deadline=deadline,
            cancelled=False,
            policies=options.policies,
        )
        if decision.should_exit:
            exit_reason = decision.reason
            break

        prev_plan = plan
        plan = new_plan
        iteration += 1

    # ----- write outputs -----
    saved_docx = None
    if pending_state is None and mode in ("full", "targeted") and output_path:
        dm.save(output_path)
        saved_docx = output_path
    elif pending_state is not None:
        # Paused — surface the in-flight docx so the user can review.
        saved_docx = pending_state.docx_path

    delivery = build_delivery_report(
        rule_set=rule_set,
        eval_report=eval_report,
        diagnoses=diagnoses,
        mode=mode,
        iterations=iteration + 1,
        exit_reason=exit_reason,
        llm_telemetry=_telemetry_dict(llm_client),
        fix_attempts_by_rule=fix_attempts_by_rule,
        tool_calls_count=tool_calls_count,
    )
    write_report_json(delivery, report_json_path)
    write_report_md(delivery, report_md_path)

    # ----- annotate the saved docx with partial / failed markers -----
    # Best-effort (R7.6): annotation never fails the run. Any IO /
    # OOXML error gets captured in the trace as a warning and the
    # report still ships.
    if saved_docx and mode in ("full", "targeted"):
        from ..delivery.annotator import annotate as annotate_docx

        ann = annotate_docx(saved_docx, delivery)
        trace.record(kind="policy", payload={
            "annotation": {
                "annotated_paragraphs": ann.annotated_paragraphs,
                "skipped_items": ann.skipped_items,
                "warnings": ann.warnings,
            },
        })

    return RunResult(
        ok=True,
        summary=delivery.summary,
        docx_path=saved_docx,
        report_md_path=report_md_path,
        report_json_path=report_json_path,
        trace_path=trace_path,
        exit_reason=exit_reason,
        pending_path=pending_path if pending_state is not None else None,
    )


def _act(
    *,
    plan,
    dm,
    mode,
    options,
    rule_set,
    snapshots,
    trace,
    output_path,
    fallback_path,
    iteration: int,
):
    """Run one ACT phase. Extracted from _run_loop for readability."""
    attempts: list[dict[str, Any]] = []
    for step in plan:
        tool = _get_tool_or_skip(step.tool, trace)
        if tool is None:
            continue
        if not _requires_satisfied(tool, plan):
            trace.record(
                kind="error",
                payload={"reason": "missing_prerequisite", "tool": step.tool,
                         "requires": list(getattr(tool, "requires", []))},
            )
            continue
        ctx = _make_tool_context(trace, snapshots, options, rule_set)
        trace.record(
            kind="tool_call",
            payload={"tool": step.tool, "params": step.params},
        )
        params = dict(step.params)
        if step.tool == "tool_word_postprocess":
            params.setdefault("docx_path", output_path or fallback_path)
            if mode != "dry_run" and output_path:
                dm.save(output_path)
        result = tool.run(dm, params, ctx)
        attempts.append(
            {
                "iteration": iteration,
                "tool": step.tool,
                "params": params,
                "ok": bool(result.ok),
                "message": result.message,
                "warnings": list(result.warnings),
                "_rule_ids": list(
                    step.rule_ids or _rule_ids_for_tool(rule_set, step.tool)
                ),
            }
        )
        trace.record(
            kind="tool_result",
            payload={
                "tool": step.tool,
                "ok": result.ok,
                "message": result.message,
                "warnings": result.warnings,
            },
        )
        if not result.ok and options.policies.rollback_strategy == "step":
            snapshots.rollback_last(dm)
            break
    return attempts


def _run_resume(*, profile: str, mode: Mode, options: RunOptions) -> RunResult:
    """Pick up where a previous run paused.

    Reads ``options.resume_path``, applies the user's accept / reject
    decisions, and re-enters the main loop. The caller's ``profile`` /
    ``mode`` arguments must match the saved state (otherwise we'd be
    cross-applying decisions across incompatible profiles).
    """
    state = pending_io.load(options.resume_path)
    if state.profile != profile:
        raise pending_io.PendingStateError(
            f"profile mismatch: pending={state.profile!r} cli={profile!r}"
        )
    if state.mode != mode:
        # We allow reduction to eval_only / diagnose_only on resume but
        # not promotion or sideways changes.
        if mode != state.mode and mode not in ("full", "diagnose_only", "eval_only"):
            raise pending_io.PendingStateError(
                f"mode mismatch on resume: pending={state.mode!r} cli={mode!r}"
            )

    work_dir = state.output_dir
    stem = state.stem
    output_path = options.output_path or os.path.join(work_dir, f"{stem}_formatted.docx")
    trace_path = os.path.join(work_dir, f"{stem}_trace.jsonl")
    report_md_path = os.path.join(work_dir, f"{stem}_report.md")
    report_json_path = os.path.join(work_dir, f"{stem}_report.json")
    pending_path = options.resume_path

    # Append-mode trace: record that we're resuming.
    trace = Trace(path=trace_path)
    trace.record(kind="policy", payload={
        "resumed_from": pending_path,
        "starting_iteration": state.iteration + 1,
        "decisions": {it.rule_id: it.decision for it in state.items},
    })

    accepted = [it.to_diagnosis() for it in state.items if it.decision == "accept"]
    # Rejected items are simply dropped — they neither pause nor execute.
    accepted = [d for d in accepted if not d.needs_human]

    return _run_loop(
        input_path=state.input_path,
        profile=profile,
        mode=mode,
        options=options,
        stem=stem,
        work_dir=work_dir,
        output_path=output_path,
        report_md_path=report_md_path,
        report_json_path=report_json_path,
        trace_path=trace_path,
        pending_path=pending_path,
        trace=trace,
        document_path=state.docx_path,  # resume from the in-flight docx
        starting_iteration=state.iteration + 1,
        starting_telemetry=state.llm_telemetry,
        accepted_diagnoses=accepted,
    )


def _restore_telemetry(llm_client, telemetry: dict) -> None:
    """Roll forward LLM counters across a resume."""
    tel = getattr(llm_client, "telemetry", None)
    if tel is None:
        return
    tel.calls = int(telemetry.get("calls", 0) or 0)
    tel.timeouts = int(telemetry.get("timeouts", 0) or 0)
    tel.errors = int(telemetry.get("errors", 0) or 0)
    tel.prompt_tokens = int(telemetry.get("prompt_tokens", 0) or 0)
    tel.completion_tokens = int(telemetry.get("completion_tokens", 0) or 0)
    tel.total_tokens = int(telemetry.get("total_tokens", 0) or 0)
    tel.cost_usd_estimate = float(telemetry.get("cost_usd_estimate", 0.0) or 0.0)


# ---------------------------------------------------------------------------
# fast mode short-circuit
# ---------------------------------------------------------------------------

def _run_fast(
    *, input_path, output_path, options, stem, trace, report_md_path,
    report_json_path, trace_path,
) -> RunResult:
    from thesis_runner import run_format

    trace.record(kind="plan", payload={"iteration": 0, "plan": [{"tool": "fast"}]})
    ok = run_format(input_path, output_path, options.log_fn)
    trace.record(kind="tool_result", payload={"tool": "fast", "ok": ok})

    summary = {"total": 0, "done": 0, "partial": 0, "failed": 0, "skipped": 0}
    # Minimal report.json so callers always find the four artefacts.
    from ..delivery.report import build_delivery_report, write_report_json, write_report_md

    delivery = build_delivery_report(
        rule_set=None,
        eval_report=None,
        diagnoses=[],
        mode="fast",
        iterations=1,
        exit_reason="fast mode delegated to thesis_runner",
    )
    write_report_json(delivery, report_json_path)
    write_report_md(delivery, report_md_path)
    return RunResult(
        ok=ok,
        summary=delivery.summary,
        docx_path=output_path if ok else None,
        report_md_path=report_md_path,
        report_json_path=report_json_path,
        trace_path=trace_path,
        exit_reason="fast mode",
    )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _stem_of(path: str) -> str:
    return os.path.splitext(os.path.basename(path))[0]


def _load_rule_set(profile: str, options: RunOptions):
    if options.config_path:
        cfg = from_yaml(options.config_path)
        return compile_rule_set(
            cfg,
            profile=profile or Path(options.config_path).stem,
            version="custom",
        )
    return load_profile(profile)


def _resolve_output_path(input_path, options: RunOptions, mode: Mode) -> Optional[str]:
    if mode in ("eval_only", "diagnose_only", "dry_run"):
        return None
    if options.output_path:
        return options.output_path
    out_dir = options.output_dir or os.path.dirname(input_path) or "."
    return os.path.join(out_dir, f"{_stem_of(input_path)}_formatted.docx")


def _validate_fix_tools_bound(rule_set) -> None:
    names = {t.name for t in tool_registry.all_tools()}
    if not names:
        # registry.autoload() is called later in run(); skip the check
        # if the registry is empty so unit tests can pre-populate.
        tool_registry.autoload()
        names = {t.name for t in tool_registry.all_tools()}
    for rule in rule_set.rules:
        ft = rule.fix_tool
        if ft and ft not in names:
            raise UnboundFixToolError(
                f"rule {rule.id!r} references unknown fix_tool {ft!r}"
            )


def _get_tool_or_skip(name, trace):
    try:
        return tool_registry.get(name)
    except tool_registry.UnknownToolError:
        trace.record(kind="error", payload={"reason": "unknown_tool", "tool": name})
        return None


def _requires_satisfied(tool, plan: list[Step]) -> bool:
    needs = list(getattr(tool, "requires", []))
    if not needs:
        return True
    plan_names = [s.tool for s in plan]
    return all(n in plan_names for n in needs)


def _rule_ids_for_tool(rule_set, tool_name: str) -> list[str]:
    if rule_set is None:
        return []
    return [
        rule.id
        for rule in getattr(rule_set, "rules", []) or []
        if getattr(rule, "fix_tool", None) == tool_name
    ]


def _plans_same(a: list[Step], b: list[Step]) -> bool:
    from .policies import plans_equivalent

    return plans_equivalent(a, b)


def _make_tool_context(trace, snapshots, options: RunOptions, rule_set):
    from ..tools.base import ToolContext

    # Hand Tools the deep-merged template config so wrappers around
    # ``thesis_formatter/*`` (which all take ``cfg`` as second arg) see
    # the same shape they expect. The compiler stashes it in metadata
    # — see ``thesis_agent.spec.compiler.compile``.
    config = (rule_set.metadata.get("source_config") if rule_set is not None else {}) or {}
    return ToolContext(
        trace=trace,
        snapshot_mgr=snapshots,
        config=config,
        runtime={"profile": rule_set.profile, "version": rule_set.version},
    )


def _bail_out(
    options, *, trace, stem, report_md_path, report_json_path, trace_path, reason,
):
    options.log_fn(f"thesis-agent: {reason}")
    trace.record(kind="error", payload={"reason": reason})
    return RunResult(
        ok=False,
        summary={"total": 0, "done": 0, "partial": 0, "failed": 0, "skipped": 0},
        docx_path=None,
        report_md_path=report_md_path,
        report_json_path=report_json_path,
        trace_path=trace_path,
        exit_reason=reason,
    )


# ---------------------------------------------------------------------------
# LLM wiring
# ---------------------------------------------------------------------------

def _build_llm_client(options: RunOptions):
    """Return an LLM client instance or None if not configured.

    Order of precedence:
    1. ``options.llm_disabled=True``      → always None
    2. CLI flags / explicit kwargs        → real client
    3. Environment variables              → real client
    4. Otherwise                          → None (R5.7)
    """
    if options.llm_disabled:
        return None

    # Local import to avoid pulling urllib into modules that don't need it.
    from ..diagnoser.openai_client import (
        LLMTelemetry, OpenAICompatibleClient, settings_from_env,
    )

    settings = settings_from_env(
        api_key=options.llm_api_key,
        base_url=options.llm_base_url,
        model=options.llm_model,
    )
    if settings is None:
        return None
    return OpenAICompatibleClient(settings, telemetry=LLMTelemetry())


def _telemetry_dict(llm_client) -> dict:
    """Convert the LLM client's telemetry into a plain dict ready to
    drop into ``report.json.meta``."""
    if llm_client is None:
        return {}
    tel = getattr(llm_client, "telemetry", None)
    if tel is None:
        return {}
    return {
        "model": llm_client.settings.model,
        "calls": tel.calls,
        "timeouts": tel.timeouts,
        "errors": tel.errors,
        "prompt_tokens": tel.prompt_tokens,
        "completion_tokens": tel.completion_tokens,
        "total_tokens": tel.total_tokens,
        "cost_usd_estimate": round(tel.cost_usd_estimate, 6),
    }
