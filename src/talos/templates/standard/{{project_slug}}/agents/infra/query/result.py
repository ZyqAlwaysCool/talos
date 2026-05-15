"""任务查询 handler 统一返回值工厂 + 跨域公共工具函数。"""

from __future__ import annotations

from typing import Any

from agents.infra.llm.usage_metadata import (
    LLM_USAGE_INPUT_TOKENS_TOTAL_KEY,
    LLM_USAGE_OUTPUT_TOKENS_TOTAL_KEY,
)

TASK_QUERY_SUCCESS_CODE: int = 0
TASK_QUERY_SUCCESS_MSG: str = "success"

TaskQueryResult = tuple[int, str, dict[str, Any]]


def task_query_ok(detail: dict[str, Any]) -> TaskQueryResult:
    """构造成功返回值。detail 为本域 *QueryResponseData.model_dump()。"""
    return TASK_QUERY_SUCCESS_CODE, TASK_QUERY_SUCCESS_MSG, detail


def task_query_err(code: int, msg: str, detail: dict[str, Any]) -> TaskQueryResult:
    """构造可预期业务失败返回值。detail 必传，强制调用方提供结构化错误体。"""
    return code, msg, detail


def normalize_task_status(task: Any) -> str:
    """将 BaseTask.status 统一转为字符串，兼容枚举和已序列化的 str。"""
    status = getattr(task, "status", None)
    raw = getattr(status, "value", status) if status is not None else ""
    return str(raw or "")


def get_token_usage(metadata: dict[str, Any], token_usage_cls: type) -> Any | None:
    """从 metadata 提取 LLM token 用量统计，返回对应域的 TokenUsage 模型实例。"""
    input_total = int(metadata.get(LLM_USAGE_INPUT_TOKENS_TOTAL_KEY) or 0)
    output_total = int(metadata.get(LLM_USAGE_OUTPUT_TOKENS_TOTAL_KEY) or 0)
    if input_total <= 0 or output_total <= 0:
        return None
    return token_usage_cls(
        input_total_tokens=input_total,
        output_total_tokens=output_total,
    )
