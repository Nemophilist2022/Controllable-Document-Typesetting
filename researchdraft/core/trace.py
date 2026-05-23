from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class TraceEntry:
    task_id: str
    agent: str
    stage: str
    input_keys: list[str]
    output_keys: list[str]
    tool_call: str
    status: str
    failure_reason: str = ""


class TraceRecorder:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("", encoding="utf-8")
        self.entries: list[TraceEntry] = []

    def record(
        self,
        *,
        task_id: str,
        agent: str,
        stage: str,
        input_keys: list[str],
        output_keys: list[str],
        tool_call: str = "",
        status: str = "ok",
        failure_reason: str = "",
    ) -> TraceEntry:
        entry = TraceEntry(
            task_id=task_id,
            agent=agent,
            stage=stage,
            input_keys=input_keys,
            output_keys=output_keys,
            tool_call=tool_call,
            status=status,
            failure_reason=failure_reason,
        )
        self.entries.append(entry)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")
        return entry

    def write_json(self, path: str | Path | None = None) -> str:
        output = Path(path) if path is not None else self.path.with_suffix(".json")
        output.parent.mkdir(parents=True, exist_ok=True)
        payload = [asdict(entry) for entry in self.entries]
        output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return str(output)
