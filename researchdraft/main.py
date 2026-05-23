from __future__ import annotations

from researchdraft.agents.manager_agent import ResearchManagerAgent


def _build_llm_client():
    try:
        from thesis_agent.diagnoser.openai_client import (
            LLMTelemetry,
            OpenAICompatibleClient,
            settings_from_env,
        )

        settings = settings_from_env()
        if settings is None:
            return None
        return OpenAICompatibleClient(settings, telemetry=LLMTelemetry())
    except Exception:
        return None


def main() -> int:
    print("ResearchDraft Agent Harness MVP")
    print("请根据提示输入研究材料；没有的信息可直接回车，系统会标记待补充。")
    result = ResearchManagerAgent(llm_client=_build_llm_client()).run()
    print("\n输出完成：")
    print(f"- Draft Context: {result.context_path}")
    print(f"- Markdown 草稿: {result.draft_path}")
    print(f"- Word 文档: {result.docx_path}")
    print(f"- 质检报告: {result.report_path}")
    print(f"- Trace: {result.trace_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

