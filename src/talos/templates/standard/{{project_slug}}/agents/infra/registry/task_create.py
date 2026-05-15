"""任务创建 handler 协议与注册表。"""

from __future__ import annotations

from typing import Any, Protocol


class TaskCreateHandler(Protocol):
    """业务域创建任务的 handler 接口。"""

    async def create(self, payload: dict[str, Any], trace_id: str = "") -> str:
        """业务域实现校验、持久化、入队；返回 task_id。"""
        ...


class TaskCreateRegistry:
    """task_type 字符串到创建 handler 的映射。"""

    def __init__(self) -> None:
        self._handlers: dict[str, TaskCreateHandler] = {}

    def register(self, task_type: str, handler: TaskCreateHandler) -> None:
        key = task_type.strip()
        if not key:
            raise ValueError("task_type 不能为空")
        self._handlers[key] = handler

    def resolve(self, task_type: str) -> TaskCreateHandler | None:
        return self._handlers.get(task_type.strip())
