"""Pending-decision persistence for human-in-the-loop pause/resume.

When ``auto_apply_diagnosis="confirm"`` and the diagnoser produces at
least one diagnosis flagged ``needs_human=True``, the harness writes a
``<stem>_pending.json`` and exits with reason ``awaiting_human``. The
user reviews the file, edits each pending decision to ``accept`` or
``reject``, then re-runs ``thesis-agent run --resume <pending.json>``.

The on-disk shape is intentionally readable / hand-editable. JSON
keys mirror the dataclasses below so a reviewer can diff what changes
between sessions.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

from ..diagnoser.types import Diagnosis, ToolCall

PendingDecision = Literal["pending", "accept", "reject"]


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------

@dataclass
class PendingItem:
    """One diagnosis awaiting a human decision."""

    rule_id: str
    root_cause: str
    rationale: str
    confidence: float
    fix_plan: list[dict]   # serialised ToolCall list
    decision: PendingDecision = "pending"
    triggered_by: list[str] = field(default_factory=list)  # which gate fired

    def to_diagnosis(self) -> Diagnosis:
        return Diagnosis(
            rule_id=self.rule_id,
            root_cause=self.root_cause,
            fix_plan=[
                ToolCall(
                    tool=tc.get("tool", ""),
                    params=dict(tc.get("params", {})),
                    expected_effect=tc.get("expected_effect", ""),
                )
                for tc in self.fix_plan
            ],
            confidence=float(self.confidence),
            needs_human=(self.decision == "pending"),
            rationale=self.rationale,
        )


@dataclass
class PendingState:
    """The full snapshot persisted to ``<stem>_pending.json``."""

    schema_version: int
    input_path: str
    profile: str
    mode: str
    stem: str
    output_dir: str
    docx_path: str          # current intermediate docx
    iteration: int
    items: list[PendingItem]
    llm_telemetry: dict     # roll-forward across resumes
    note: str = ""          # human-readable reminder shown in the file


_SCHEMA_VERSION = 1


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def save(state: PendingState, path: str) -> None:
    payload = {
        "schema_version": state.schema_version,
        "input_path": state.input_path,
        "profile": state.profile,
        "mode": state.mode,
        "stem": state.stem,
        "output_dir": state.output_dir,
        "docx_path": state.docx_path,
        "iteration": state.iteration,
        "llm_telemetry": state.llm_telemetry,
        "note": state.note,
        "items": [
            {
                "rule_id": it.rule_id,
                "root_cause": it.root_cause,
                "rationale": it.rationale,
                "confidence": it.confidence,
                "fix_plan": it.fix_plan,
                "decision": it.decision,
                "triggered_by": list(it.triggered_by),
            }
            for it in state.items
        ],
    }
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)


def load(path: str) -> PendingState:
    with open(path, "r", encoding="utf-8") as fh:
        raw = json.load(fh)
    if not isinstance(raw, dict):
        raise PendingStateError(f"pending file must be a JSON object: {path}")
    sv = int(raw.get("schema_version", 0))
    if sv != _SCHEMA_VERSION:
        raise PendingStateError(
            f"unsupported pending schema version {sv}; expected {_SCHEMA_VERSION}"
        )
    items = []
    for item in raw.get("items", []):
        items.append(PendingItem(
            rule_id=item["rule_id"],
            root_cause=item.get("root_cause", ""),
            rationale=item.get("rationale", ""),
            confidence=float(item.get("confidence", 0.0)),
            fix_plan=list(item.get("fix_plan", [])),
            decision=item.get("decision", "pending"),
            triggered_by=list(item.get("triggered_by", [])),
        ))
    return PendingState(
        schema_version=sv,
        input_path=raw["input_path"],
        profile=raw["profile"],
        mode=raw["mode"],
        stem=raw["stem"],
        output_dir=raw["output_dir"],
        docx_path=raw["docx_path"],
        iteration=int(raw.get("iteration", 0)),
        items=items,
        llm_telemetry=dict(raw.get("llm_telemetry", {})),
        note=raw.get("note", ""),
    )


# ---------------------------------------------------------------------------
# Constructors
# ---------------------------------------------------------------------------

def from_diagnoses(
    *,
    input_path: str,
    profile: str,
    mode: str,
    stem: str,
    output_dir: str,
    docx_path: str,
    iteration: int,
    diagnoses: list[Diagnosis],
    llm_telemetry: dict,
    triggered_by_per_rule: Optional[dict[str, list[str]]] = None,
) -> PendingState:
    """Build a :class:`PendingState` from the current run state. Only
    diagnoses with ``needs_human=True`` are included; the rest run
    autonomously."""
    triggered_by_per_rule = triggered_by_per_rule or {}
    items = [
        PendingItem(
            rule_id=d.rule_id,
            root_cause=d.root_cause,
            rationale=d.rationale,
            confidence=d.confidence,
            fix_plan=[
                {
                    "tool": tc.tool,
                    "params": dict(tc.params),
                    "expected_effect": tc.expected_effect,
                }
                for tc in d.fix_plan
            ],
            triggered_by=triggered_by_per_rule.get(d.rule_id, []),
        )
        for d in diagnoses
        if d.needs_human
    ]
    note = (
        "请将每个 item 的 decision 字段改为 'accept' 或 'reject' 后，"
        "重新运行：thesis-agent run --resume <此文件>"
    )
    return PendingState(
        schema_version=_SCHEMA_VERSION,
        input_path=input_path,
        profile=profile,
        mode=mode,
        stem=stem,
        output_dir=output_dir,
        docx_path=docx_path,
        iteration=iteration,
        items=items,
        llm_telemetry=llm_telemetry,
        note=note,
    )


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class PendingStateError(Exception):
    """Raised when loading or applying a pending file is not possible."""
