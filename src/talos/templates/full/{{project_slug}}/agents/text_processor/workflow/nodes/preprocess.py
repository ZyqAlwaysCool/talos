"""Preprocess 节点 — 预处理文本，统计分析."""

from __future__ import annotations

from typing import Any


class PreprocessNode:
    """对输入文本做预处理和统计分析."""

    async def process(self, text: str, options: dict[str, Any]) -> dict[str, Any]:  # noqa: ARG002
        return {
            "word_count": len(text.split()),
            "char_count": len(text),
            "line_count": len(text.splitlines()),
            "preview": text[:200] + ("..." if len(text) > 200 else ""),
        }
