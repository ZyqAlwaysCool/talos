"""任务 ID 前缀到查询处理器的注册表。"""

from __future__ import annotations

from typing import Any, Protocol

from core.task.prefix_match import resolve_prefixed_mapping


class TaskQueryHandler(Protocol):
    """统一任务查询 handler 约定。

    - 成功：code=0, msg="success", detail=本域 QueryResponseData
    - 可预期业务失败：return task_query_err(code, msg, detail)，detail 非空且字段结构与成功一致
    - 系统异常（DB 故障等）：raise，由编排层捕获并以 detail={} 返回
    """

    async def __call__(self, task_id: str) -> tuple[int, str, dict[str, Any]]:
        ...


class TaskQueryRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, TaskQueryHandler] = {}

    def register(self, task_id_prefix: str, handler: TaskQueryHandler) -> None:
        key = task_id_prefix.strip()
        if not key:
            raise ValueError("task_id_prefix 不能为空")
        self._handlers[key] = handler

    def resolve(self, task_id: str) -> tuple[str | None, TaskQueryHandler | None]:
        matched, handler = resolve_prefixed_mapping(
            task_id, self._handlers, first_segment_fallback=True
        )
        return matched, handler


task_query_registry = TaskQueryRegistry()
