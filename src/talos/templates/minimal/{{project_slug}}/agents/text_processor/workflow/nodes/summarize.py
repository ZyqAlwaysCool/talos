"""Summarize 节点 — pydantic-ai LLM 调用 / hardcode fallback."""

from __future__ import annotations

import os
from typing import Any

from loguru import logger


DEFAULT_SUMMARY = (
    "该文本包含 {word_count} 个单词、{char_count} 个字符。"
    "内容预览: {preview}"
)

SYSTEM_PROMPT = (
    "你是一个文本摘要助手。请用一段简短的中文总结以下文本的核心内容。"
    "要求：不超过 3 句话，抓住核心要点，使用中文输出。"
)


def _llm_available() -> bool:
    """检查是否配置了 LLM 环境变量."""
    return bool(os.getenv("TALOS_LLM_API_KEY", "").strip())


async def _call_llm(text: str) -> str:
    """通过 pydantic-ai 发起 LLM 调用."""
    from pydantic_ai import Agent
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider

    base_url = os.getenv("TALOS_LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    api_key = os.getenv("TALOS_LLM_API_KEY", "")
    model_name = os.getenv("TALOS_LLM_MODEL", "gpt-4o")

    model = OpenAIChatModel(
        model_name=model_name,
        provider=OpenAIProvider(base_url=base_url, api_key=api_key),
    )
    agent = Agent(model=model, system_prompt=SYSTEM_PROMPT)
    result = await agent.run(text)
    return str(result.output).strip()


class SummarizeNode:
    """文本摘要节点 — pydantic-ai LLM 优先，fallback 到 hardcode."""

    async def process(
        self,
        text: str,
        preprocessed: dict[str, Any],
        options: dict[str, Any],
    ) -> dict[str, Any]:
        used_llm = False
        if _llm_available():
            try:
                summary = await _call_llm(text)
                used_llm = True
            except Exception as exc:
                logger.warning("LLM 调用失败，使用默认摘要: {}", str(exc))
                summary = DEFAULT_SUMMARY.format(**preprocessed)
        else:
            logger.info("未配置 LLM，使用默认摘要")
            summary = DEFAULT_SUMMARY.format(**preprocessed)

        return {
            "summary": summary,
            "used_llm": used_llm,
        }
