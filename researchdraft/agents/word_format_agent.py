from __future__ import annotations

from pathlib import Path

from researchdraft.tools.word_tools import markdown_to_docx, run_word_toolchain


class WordFormatAgent:
    def __init__(self, *, output_dir: str | Path = "researchdraft/outputs") -> None:
        self.output_dir = Path(output_dir)

    def run(self, draft_markdown: str) -> tuple[str, list[dict]]:
        docx_path = self.output_dir / "paper.docx"
        markdown_to_docx(draft_markdown, docx_path)
        tool_results = run_word_toolchain(docx_path)
        return str(docx_path), tool_results

