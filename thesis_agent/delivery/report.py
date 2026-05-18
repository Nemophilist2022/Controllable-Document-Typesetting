"""Delivery report — md (human) + json (machine) (R7.1~R7.5).

Status mapping evaluator → delivery (R4.6 / R7.4):
    pass  → done
    fail  → partial   (when at least one fix attempt was made)
            failed    (otherwise)
    skip  → skipped
    error → failed    (with diagnosis.rationale = "evaluation_error: ...")

The orchestrator can attach per-rule ``fix_attempts`` so the user can
see exactly which tool tried to fix each rule and whether it succeeded.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Datatypes
# ---------------------------------------------------------------------------

@dataclass
class DeliveryItem:
    rule_id: str
    status: str          # done / partial / failed / skipped
    severity: str
    evidence: str
    locator: dict[str, Any]
    fix_attempts: list[dict[str, Any]]
    diagnosis: Optional[dict[str, Any]]
    advice: str = ""


@dataclass
class DeliveryReport:
    profile: str
    mode: str
    iterations: int
    exit_reason: str
    items: list[DeliveryItem]
    summary: dict[str, int] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

def _map_status(eval_status: str, diagnosis, fix_attempts=None) -> str:
    if eval_status == "pass":
        return "done"
    if eval_status == "skip":
        return "skipped"
    if eval_status == "error":
        return "failed"
    # eval_status == "fail"
    if fix_attempts:
        return "partial"
    if diagnosis is None or diagnosis.needs_human:
        return "failed"
    if diagnosis.fix_plan:
        return "partial"
    return "failed"


def _advice(item_status: str, diagnosis) -> str:
    if item_status == "done":
        return ""
    if item_status == "skipped":
        return "本次模式未触发；如需修复请切换到 mode=full"
    if diagnosis is not None and diagnosis.needs_human:
        return "诊断置信度不足，请人工确认后调整"
    if item_status == "partial":
        return "已尝试自动修复，建议在 Word 中复核标注的段落"
    return "请检查文档结构后重新运行 mode=full"


def build_delivery_report(
    *,
    rule_set,
    eval_report,
    diagnoses,
    mode: str,
    iterations: int,
    exit_reason: str,
    llm_telemetry: Optional[dict] = None,
    fix_attempts_by_rule: Optional[dict[str, list[dict[str, Any]]]] = None,
    tool_calls_count: int = 0,
) -> DeliveryReport:
    diag_by_rule = {d.rule_id: d for d in (diagnoses or [])}
    attempts_by_rule = fix_attempts_by_rule or {}
    items: list[DeliveryItem] = []

    if eval_report is not None:
        for cr in eval_report.results:
            d = diag_by_rule.get(cr.rule_id)
            attempts = list(attempts_by_rule.get(cr.rule_id, []))
            status = _map_status(cr.status, d, attempts)
            items.append(
                DeliveryItem(
                    rule_id=cr.rule_id,
                    status=status,
                    severity=cr.severity,
                    evidence=cr.evidence,
                    locator=dict(cr.locator_resolved),
                    fix_attempts=attempts,
                    diagnosis=_diagnosis_dict(d),
                    advice=_advice(status, d),
                )
            )

    summary = {
        "total": len(items),
        "done": sum(1 for it in items if it.status == "done"),
        "partial": sum(1 for it in items if it.status == "partial"),
        "failed": sum(1 for it in items if it.status == "failed"),
        "skipped": sum(1 for it in items if it.status == "skipped"),
    }

    profile_name = getattr(rule_set, "profile", "unknown") if rule_set is not None else "fast"

    # R11.6 / R11.7: meta carries iteration + tool/llm telemetry. The
    # orchestrator passes a dict (or empty / None when no LLM ran).
    llm_meta = llm_telemetry or {}
    llm_calls_count = int(llm_meta.get("calls", 0))

    return DeliveryReport(
        profile=profile_name,
        mode=mode,
        iterations=iterations,
        exit_reason=exit_reason,
        items=items,
        summary=summary,
        meta={
            "iterations": iterations,
            "tool_calls_count": int(tool_calls_count),
            "llm_calls_count": llm_calls_count,
            "llm_cost_estimate_usd": float(llm_meta.get("cost_usd_estimate", 0.0)),
            "llm_timeouts_count": int(llm_meta.get("timeouts", 0)),
            "llm_telemetry": llm_meta,
        },
    )


def _diagnosis_dict(d) -> Optional[dict[str, Any]]:
    if d is None:
        return None
    return {
        "rule_id": d.rule_id,
        "root_cause": d.root_cause,
        "confidence": d.confidence,
        "needs_human": d.needs_human,
        "rationale": d.rationale,
        "fix_plan": [
            {"tool": tc.tool, "params": tc.params, "expected_effect": tc.expected_effect}
            for tc in d.fix_plan
        ],
    }


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------

def write_report_json(delivery: DeliveryReport, path: str) -> None:
    payload = {
        "profile": delivery.profile,
        "mode": delivery.mode,
        "iterations": delivery.iterations,
        "exit_reason": delivery.exit_reason,
        "summary": delivery.summary,
        "meta": delivery.meta,
        "items": [
            {
                "rule_id": it.rule_id,
                "status": it.status,
                "severity": it.severity,
                "evidence": it.evidence,
                "locator": it.locator,
                "fix_attempts": it.fix_attempts,
                "diagnosis": it.diagnosis,
                "advice": it.advice,
            }
            for it in delivery.items
        ],
    }
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)


def write_report_md(delivery: DeliveryReport, path: str) -> None:
    by_status: dict[str, list[DeliveryItem]] = {
        "done": [], "partial": [], "failed": [], "skipped": [],
    }
    for it in delivery.items:
        by_status.setdefault(it.status, []).append(it)

    sections = [
        f"# 论文排版完成度报告\n",
        f"- 模板：{delivery.profile}",
        f"- 模式：{delivery.mode}",
        f"- 迭代轮数：{delivery.iterations}",
        f"- 退出原因：{delivery.exit_reason}",
        f"- 汇总：✅ {delivery.summary['done']}  "
        f"⚠️ {delivery.summary['partial']}  "
        f"❌ {delivery.summary['failed']}  "
        f"⏭ {delivery.summary['skipped']}",
        "",
    ]

    def _block(title: str, items: list[DeliveryItem]) -> list[str]:
        out = [f"## {title} ({len(items)})"]
        if not items:
            out.append("（无）")
            return out + [""]
        for it in items:
            lines = [f"- **{it.rule_id}** [{it.severity}] — {it.evidence}"]

            # Show diagnosis details for partial / failed items so the
            # user can act without opening the JSON file.
            if it.status in ("partial", "failed"):
                d = it.diagnosis or {}
                root_cause = d.get("root_cause") or ""
                rationale = d.get("rationale") or ""
                fix_plan = d.get("fix_plan") or []
                if root_cause:
                    lines.append(f"  根因：{root_cause}")
                if fix_plan:
                    tools_summary = ", ".join(
                        tc.get("tool", "") for tc in fix_plan if tc.get("tool")
                    )
                    if it.status == "partial":
                        lines.append(f"  已尝试：{tools_summary}")
                    else:
                        lines.append(f"  待执行：{tools_summary}")
                if rationale and rationale != root_cause:
                    lines.append(f"  说明：{rationale}")

            if it.fix_attempts:
                attempts_summary = ", ".join(
                    f"{a.get('tool')}({'ok' if a.get('ok') else 'failed'})"
                    for a in it.fix_attempts
                )
                lines.append(f"  修复尝试：{attempts_summary}")

            if it.advice:
                lines.append(f"  操作建议：{it.advice}")

            out.extend(lines)
        out.append("")
        return out

    sections += _block("✅ 已完成", by_status["done"])
    sections += _block("⚠️ 部分完成", by_status["partial"])
    sections += _block("❌ 未完成", by_status["failed"])
    sections += _block("⏭ 已跳过", by_status["skipped"])
    sections.append("---\n")
    sections.append(
        "如报告中含 Word 批注或浅蓝底色标注，可在 Word 中右键 → 删除批注 / 清除底色一键移除。"
    )

    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(sections))
