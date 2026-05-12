"""text_processor 任务持久化."""

from __future__ import annotations

from typing import Any

from core.task.base.storage_backend import StorageBackend
from core.task.models.task_models import BaseTask, TaskStatus


class TextProcessorTaskRepository:
    """text_processor 任务仓储."""

    def __init__(self, storage: StorageBackend):
        self.storage = storage

    async def create_task(self, task_id: str, metadata: dict[str, Any]) -> bool:
        task = BaseTask(task_id=task_id, metadata=metadata)
        return await self.storage.create_task(task)

    async def get_task(self, task_id: str) -> BaseTask | None:
        return await self.storage.get_task(task_id)

    async def update_status(
        self,
        task_id: str,
        status: TaskStatus,
        *,
        error_message: str | None = None,
        queue_task_id: str | None = None,
    ) -> bool:
        kwargs: dict[str, Any] = {}
        if error_message:
            kwargs["error_message"] = error_message
        if queue_task_id:
            kwargs["queue_task_id"] = queue_task_id
        return await self.storage.update_task_status(task_id, status, **kwargs)
