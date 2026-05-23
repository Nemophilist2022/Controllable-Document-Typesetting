from __future__ import annotations

from pathlib import Path
from typing import Callable

from researchdraft.agents.interview_agent import InterviewAgent
from researchdraft.agents.planning_agent import PlanningAgent
from researchdraft.agents.verifier_agent import VerifierAgent
from researchdraft.agents.word_format_agent import WordFormatAgent
from researchdraft.agents.writing_agent import WritingAgent
from researchdraft.core.state import ResearchDraftState, RunResult, Stage
from researchdraft.core.trace import TraceRecorder


class ResearchManagerAgent:
    def __init__(
        self,
        *,
        output_dir: str | Path = "researchdraft/outputs",
        input_fn: Callable[[str], str] = input,
        llm_client=None,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.input_fn = input_fn
        self.llm_client = llm_client
        self.state = ResearchDraftState()
        self.trace = TraceRecorder(self.output_dir / "trace.jsonl")
        self.state.trace_path = str(self.trace.path)

    def run(self) -> RunResult:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._run_interview()
        self._run_planning()
        self._run_drafting()
        self._run_formatting()
        self._run_verifying()
        if self.state.verification and self.state.verification.has_format_problem:
            self._run_formatting(task_id="formatting-retry")
            self._run_verifying(task_id="verifying-retry")
        self.state.stage = Stage.DONE
        return RunResult(
            ok=True,
            output_dir=str(self.output_dir),
            context_path=str(self.output_dir / "draft_context.json"),
            draft_path=self.state.draft_path,
            docx_path=self.state.docx_path,
            report_path=self.state.report_path,
            trace_path=self.state.trace_path,
        )

    def _run_interview(self) -> None:
        self.state.stage = Stage.INTERVIEWING
        ctx = InterviewAgent(output_dir=self.output_dir, input_fn=self.input_fn).run()
        self.state.context = ctx
        self.trace.record(
            task_id="interview",
            agent="InterviewAgent",
            stage=self.state.stage.value,
            input_keys=[],
            output_keys=["context", "draft_context.json"],
            tool_call="fixed_questionnaire",
        )

    def _run_planning(self) -> None:
        self.state.stage = Stage.PLANNING
        assert self.state.context is not None
        self.state.outline = PlanningAgent().run(self.state.context)
        self.trace.record(
            task_id="planning",
            agent="PlanningAgent",
            stage=self.state.stage.value,
            input_keys=["context"],
            output_keys=["outline"],
            tool_call="paper_outline.yaml",
        )

    def _run_drafting(self) -> None:
        self.state.stage = Stage.DRAFTING
        assert self.state.context is not None
        draft = WritingAgent(llm_client=self.llm_client).run(
            self.state.context, self.state.outline
        )
        draft_path = self.output_dir / "draft.md"
        draft_path.write_text(draft, encoding="utf-8")
        self.state.draft_markdown = draft
        self.state.draft_path = str(draft_path)
        tool_call = "llm_optional_or_template"
        self.trace.record(
            task_id="drafting",
            agent="WritingAgent",
            stage=self.state.stage.value,
            input_keys=["context", "outline"],
            output_keys=["draft_markdown", "draft.md"],
            tool_call=tool_call,
        )

    def _run_formatting(self, task_id: str = "formatting") -> None:
        self.state.stage = Stage.FORMATTING
        docx_path, tool_results = WordFormatAgent(output_dir=self.output_dir).run(
            self.state.draft_markdown
        )
        self.state.docx_path = docx_path
        tool_call = ", ".join(result["tool"] for result in tool_results)
        status = "ok" if all(result["ok"] for result in tool_results) else "partial"
        failure_reason = "; ".join(
            result["message"] for result in tool_results if not result["ok"]
        )
        self.trace.record(
            task_id=task_id,
            agent="WordFormatAgent",
            stage=self.state.stage.value,
            input_keys=["draft_markdown"],
            output_keys=["docx_path"],
            tool_call=tool_call,
            status=status,
            failure_reason=failure_reason,
        )

    def _run_verifying(self, task_id: str = "verifying") -> None:
        self.state.stage = Stage.VERIFYING
        self.trace.record(
            task_id=task_id,
            agent="VerifierAgent",
            stage=self.state.stage.value,
            input_keys=["draft_markdown", "docx_path", "trace_entries"],
            output_keys=["quality_report.md", "verification"],
            tool_call="verify_content_and_format",
            status="ok",
        )
        result = VerifierAgent(output_dir=self.output_dir).run(
            draft_markdown=self.state.draft_markdown,
            docx_path=self.state.docx_path,
            trace_entries=list(self.trace.entries),
            draft_context=self.state.context,
            draft_path=self.state.draft_path,
        )
        self.state.verification = result
        self.state.report_path = result.report_path
        self.trace.write_json(self.output_dir / "trace.json")
