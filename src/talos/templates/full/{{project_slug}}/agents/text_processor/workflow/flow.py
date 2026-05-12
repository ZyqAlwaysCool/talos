"""TextProcessor 工作流 — Preprocess → Summarize."""

from __future__ import annotations

from typing import Any

from agents.text_processor.workflow.nodes.preprocess import PreprocessNode
from agents.text_processor.workflow.nodes.summarize import SummarizeNode


class TextProcessorWorkflow:
    """文本处理工作流."""

    def __init__(self):
        self.preprocess_node = PreprocessNode()
        self.summarize_node = SummarizeNode()

    async def run(self, text: str, options: dict[str, Any]) -> dict[str, Any]:
        # Node 1: 预处理
        preprocessed = await self.preprocess_node.process(text, options)

        # Node 2: LLM 摘要 / hardcode fallback
        summary_result = await self.summarize_node.process(
            text=text, preprocessed=preprocessed, options=options
        )

        return {
            "preprocessed": preprocessed,
            "summary": summary_result["summary"],
            "used_llm": summary_result["used_llm"],
        }
