from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


LIST_FIELDS = {"method", "metrics", "innovation_points", "output_format", "references"}
REQUIRED_FIELDS = {
    "title",
    "background",
    "research_problem",
    "method",
    "dataset",
    "metrics",
    "innovation_points",
    "references",
}


@dataclass
class DraftContext:
    title: str = ""
    background: str = ""
    research_problem: str = ""
    method: list[str] = field(default_factory=list)
    dataset: str = ""
    metrics: list[str] = field(default_factory=list)
    innovation_points: list[str] = field(default_factory=list)
    paper_type: str = "short_paper"
    output_format: list[str] = field(default_factory=lambda: ["docx"])
    references: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)

    @classmethod
    def from_answers(cls, answers: dict[str, Any]) -> "DraftContext":
        data: dict[str, Any] = {}
        for key in (
            "title",
            "background",
            "research_problem",
            "dataset",
            "paper_type",
        ):
            data[key] = _clean_scalar(answers.get(key, ""))
        for key in LIST_FIELDS:
            data[key] = _split_list(answers.get(key, ""))

        if not data["paper_type"]:
            data["paper_type"] = "short_paper"
        if not data["output_format"]:
            data["output_format"] = ["docx"]

        ctx = cls(**data)
        ctx.missing_fields = ctx.compute_missing_fields()
        return ctx

    def compute_missing_fields(self) -> list[str]:
        missing: list[str] = []
        for key in REQUIRED_FIELDS:
            value = getattr(self, key)
            if isinstance(value, list):
                is_missing = len(value) == 0
            else:
                is_missing = not str(value).strip()
            if is_missing:
                missing.append(key)
        return sorted(missing)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def save_json(self, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def _clean_scalar(value: Any) -> str:
    return str(value or "").strip()


def _split_list(value: Any) -> list[str]:
    if isinstance(value, list):
        raw_items = [str(v) for v in value]
    else:
        raw_items = re.split(r"[,，;；\n]+", str(value or ""))
    return [item.strip() for item in raw_items if item.strip()]

