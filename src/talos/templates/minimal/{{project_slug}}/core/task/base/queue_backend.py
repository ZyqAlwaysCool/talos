"""队列后端抽象接口."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from core.task.models.task_models import BaseTask, TaskResult


class QueueBackend(ABC):
    """队列后端抽象基类."""

    @abstractmethod
    async def enqueue_task(
        self, task: BaseTask, func: Callable, *args: Any, **kwargs: Any
    ) -> str:
        """任务入队，返回队列任务ID."""
        ...

    @abstractmethod
    async def get_task_status(self, queue_task_id: str) -> dict[str, Any]:
        """获取任务执行状态."""
        ...

    @abstractmethod
    async def get_task_result(self, queue_task_id: str) -> TaskResult | None:
        """获取已完成任务的结果."""
        ...

    @abstractmethod
    async def cancel_task(self, queue_task_id: str) -> bool:
        """取消任务."""
        ...

    @abstractmethod
    async def get_queue_length(self, queue_name: str = "default") -> int:
        """获取队列长度."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """健康检查."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """关闭连接."""
        ...
