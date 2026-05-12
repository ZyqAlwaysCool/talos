"""存储后端抽象接口."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from core.task.models.task_models import (
    BaseTask,
    TaskQuery,
    TaskResult,
    TaskStatus,
)


class StorageBackend(ABC):
    """任务存储后端抽象基类."""

    @abstractmethod
    async def create_task(self, task: BaseTask) -> bool:
        """创建任务记录."""
        ...

    @abstractmethod
    async def get_task(self, task_id: str) -> BaseTask | None:
        """获取任务."""
        ...

    @abstractmethod
    async def update_task_status(
        self, task_id: str, status: TaskStatus, **kwargs: Any
    ) -> bool:
        """更新任务状态."""
        ...

    @abstractmethod
    async def query_tasks(self, query: TaskQuery) -> list[BaseTask]:
        """查询任务列表."""
        ...

    @abstractmethod
    async def delete_task(self, task_id: str) -> bool:
        """删除任务."""
        ...

    @abstractmethod
    async def save_task_result(
        self, task_id: str, result: TaskResult
    ) -> bool:
        """保存任务结果."""
        ...

    @abstractmethod
    def close(self) -> None:
        """关闭连接."""
        ...
