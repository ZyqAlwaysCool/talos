"""text_processor 工作流。"""

from __future__ import annotations

from typing import Any


class TextProcessorWorkflow:
    def __init__(self):
        pass

    async def run(self, text: str, options: dict[str, Any]) -> dict[str, Any]:
        return {
            "text_length": len(text),
            "processed": True,
            "options": options,
        }
